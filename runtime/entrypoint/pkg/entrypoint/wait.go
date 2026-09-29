package entrypoint

import (
	"fmt"
	"net/http"
	"os"
	"time"
)

// waitForSocket blocks until a Unix socket appears at path, or until timeout
// is exceeded. healthCheck (optional) is called every iteration; returning
// false causes an immediate error.
func waitForSocket(path string, timeout time.Duration, name string, healthCheck func() bool, logInterval time.Duration) error {
	timeoutSec := int(timeout.Seconds())
	logger.Info("Waiting for socket", "name", name, "timeout", timeoutSec)
	start := time.Now()
	lastLog := start

	for {
		if info, err := os.Stat(path); err == nil {
			if info.Mode().Type()&os.ModeSocket != 0 {
				elapsed := int(time.Since(start).Seconds())
				logger.Info("Ready", "name", name, "elapsed", elapsed)
				return nil
			}
		}

		elapsed := int(time.Since(start).Seconds())

		if healthCheck != nil && !healthCheck() {
			return fmt.Errorf("%s exited before creating socket", name)
		}

		if elapsed >= timeoutSec {
			return fmt.Errorf("timeout waiting for %s after %ds (socket path: %s)", name, timeoutSec, path)
		}

		if now := time.Now(); now.Sub(lastLog) >= logInterval {
			logger.Info("Still waiting...", "name", name, "elapsed", elapsed)
			lastLog = now
		}

		time.Sleep(1 * time.Second)
	}
}

// waitForHTTP blocks until the given URL returns a non-5xx response, or until
// timeout is exceeded.
func waitForHTTP(url string, timeout time.Duration, name string, httpTimeout time.Duration, logInterval time.Duration) error {
	timeoutSec := int(timeout.Seconds())
	logger.Info("Waiting for HTTP", "name", name, "timeout", timeoutSec)
	start := time.Now()
	lastLog := start

	client := &http.Client{Timeout: httpTimeout}
	var lastErr string

	for {
		elapsed := int(time.Since(start).Seconds())

		if elapsed >= timeoutSec {
			ctx := ""
			if lastErr != "" {
				ctx = fmt.Sprintf(" (last error: %s)", lastErr)
			}
			return fmt.Errorf("timeout waiting for %s after %ds%s", name, timeoutSec, ctx)
		}

		resp, err := client.Get(url)
		if err == nil {
			resp.Body.Close()
			if resp.StatusCode < 500 {
				logger.Info("Ready", "name", name, "status", resp.StatusCode, "elapsed", elapsed)
				return nil
			}
			lastErr = fmt.Sprintf("HTTP %d", resp.StatusCode)
		} else {
			lastErr = err.Error()
		}

		if now := time.Now(); now.Sub(lastLog) >= logInterval {
			logger.Info("Still waiting...", "name", name, "elapsed", elapsed)
			lastLog = now
		}

		time.Sleep(1 * time.Second)
	}
}
