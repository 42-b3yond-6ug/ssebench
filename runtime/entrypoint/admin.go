package main

import (
	"context"
	"fmt"
	"net"
	"net/http"
	"strings"
	"time"
)

// replaceEnv returns env with any existing entries for key removed and a single
// key=value appended, so the child process sees exactly one value for key.
func replaceEnv(env []string, key, value string) []string {
	prefix := key + "="
	out := make([]string, 0, len(env)+1)
	for _, e := range env {
		if !strings.HasPrefix(e, prefix) {
			out = append(out, e)
		}
	}
	return append(out, prefix+value)
}

// adminClient returns an HTTP client that dials the daemon's admin Unix socket.
// The socket is root-only (0600); the entrypoint runs as root.
func adminClient(socketPath string) *http.Client {
	return &http.Client{
		Timeout: 5 * time.Second,
		Transport: &http.Transport{
			DialContext: func(ctx context.Context, _, _ string) (net.Conn, error) {
				var d net.Dialer
				return d.DialContext(ctx, "unix", socketPath)
			},
		},
	}
}

// notifyAgentExited tells the daemon over the admin socket that the agent phase
// has ended, which unlocks the reference patch for the web UI post-run. It
// retries briefly so a slow admin-socket bind does not lose the signal.
func (r *runner) notifyAgentExited() {
	socket := r.cfg.adminSocketPath
	client := adminClient(socket)

	var lastErr error
	for i := 0; i < 10; i++ {
		req, err := http.NewRequest(http.MethodPost, "http://unix/admin/agent_exited", strings.NewReader("{}"))
		if err != nil {
			lastErr = err
			break
		}
		req.Header.Set("Content-Type", "application/json")

		resp, err := client.Do(req)
		if err == nil {
			resp.Body.Close()
			if resp.StatusCode == http.StatusOK {
				logger.Info("Signalled agent phase end to daemon")
				return
			}
			lastErr = fmt.Errorf("admin socket returned HTTP %d", resp.StatusCode)
		} else {
			lastErr = err
		}
		time.Sleep(500 * time.Millisecond)
	}
	logger.Warn("Failed to signal agent phase end; reference patch stays locked", "err", lastErr)
}
