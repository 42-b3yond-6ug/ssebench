package main

import (
	"bufio"
	"fmt"
	"net"
	"net/http"
	"os"
	"strings"
	"time"

	"goyave.dev/goyave/v5"
	"goyave.dev/goyave/v5/config"
	"goyave.dev/goyave/v5/util/fsutil/osfs"
)

var server *goyave.Server

func setupServer() bool {
	os.MkdirAll("static", 0755)
	os.WriteFile("static/index.html", []byte("public"), 0644)
	os.WriteFile("secret.txt", []byte("sensitive data"), 0644)

	cfg, err := config.LoadFrom("config.json")
	if err != nil {
		fmt.Println("FAIL: could not load config:", err)
		return false
	}

	server, err = goyave.New(goyave.Options{Config: cfg})
	if err != nil {
		fmt.Println("FAIL: could not create server:", err)
		return false
	}

	server.RegisterRoutes(func(s *goyave.Server, r *goyave.Router) {
		fs, _ := (&osfs.FS{}).Sub("static")
		r.Static(fs, "/static", false)
	})

	go server.Start()

	for i := 0; i < 100; i++ {
		resp, err := http.Get("http://127.0.0.1:8080/static/index.html")
		if err == nil {
			resp.Body.Close()
			if resp.StatusCode == 200 {
				return true
			}
		}
		time.Sleep(100 * time.Millisecond)
	}

	fmt.Println("FAIL: server did not become ready")
	return false
}

func cleanup() {
	if server != nil {
		server.Stop()
	}
	os.RemoveAll("static")
	os.Remove("secret.txt")
}

// sendRawRequest sends a raw HTTP request to avoid URL normalization
// that would otherwise sanitize path traversal sequences.
func sendRawRequest(path string) (*http.Response, error) {
	conn, err := net.DialTimeout("tcp", "127.0.0.1:8080", 5*time.Second)
	if err != nil {
		return nil, err
	}
	defer conn.Close()

	conn.SetDeadline(time.Now().Add(5 * time.Second))
	rawReq := fmt.Sprintf("GET %s HTTP/1.1\r\nHost: 127.0.0.1:8080\r\nConnection: close\r\n\r\n", path)
	conn.Write([]byte(rawReq))

	reader := bufio.NewReader(conn)
	return http.ReadResponse(reader, nil)
}

// checkBlocked verifies the server returns a non-200 response (blocked).
func checkBlocked(path string) (bool, error) {
	resp, err := sendRawRequest(path)
	if err != nil {
		return false, err
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusOK {
		buf := make([]byte, 4096)
		n, _ := resp.Body.Read(buf)
		body := string(buf[:n])
		if strings.Contains(body, "sensitive data") {
			return false, nil
		}
	}
	return true, nil
}

// testDotDotTraversal checks whether URL-encoded "../" sequences in the
// request path can escape the static directory and read arbitrary files.
// This exercises the ".." check in checkStaticPath().
func testDotDotTraversal() bool {
	blocked, err := checkBlocked("/static/%2e%2e/secret.txt")
	if err != nil {
		fmt.Println("FAIL: could not send URL-encoded traversal request:", err)
		return false
	}
	if !blocked {
		fmt.Println("FAIL: URL-encoded ../ path traversal accessed file outside static directory")
		return false
	}
	fmt.Println("PASS: URL-encoded ../ path traversal correctly blocked")
	return true
}

// testBackslashTraversal checks whether backslash characters in the
// request path can bypass the static directory boundary.
// This exercises the backslash check in checkStaticPath().
func testBackslashTraversal() bool {
	blocked, err := checkBlocked("/static/..\\secret.txt")
	if err != nil {
		fmt.Println("FAIL: could not send backslash traversal request:", err)
		return false
	}
	if !blocked {
		fmt.Println("FAIL: backslash path traversal accessed file outside static directory")
		return false
	}
	fmt.Println("PASS: backslash path traversal correctly blocked")
	return true
}

// testDoubleSlashTraversal checks whether double slashes in the path
// can confuse the static handler into serving unintended content.
// This exercises the "//" check in checkStaticPath().
func testDoubleSlashTraversal() bool {
	blocked, err := checkBlocked("/static//..%2f..%2fsecret.txt")
	if err != nil {
		fmt.Println("FAIL: could not send double slash request:", err)
		return false
	}
	if !blocked {
		fmt.Println("FAIL: double slash path traversal accessed file outside static directory")
		return false
	}
	fmt.Println("PASS: double slash path traversal correctly blocked")
	return true
}

// testDotSegment checks whether a single "." segment in the path
// is rejected by the static handler.
// This exercises the "." check in checkStaticPath().
func testDotSegment() bool {
	blocked, err := checkBlocked("/static/./index.html")
	if err != nil {
		fmt.Println("FAIL: could not send dot segment request:", err)
		return false
	}
	if !blocked {
		fmt.Println("FAIL: dot segment was not rejected by static handler")
		return false
	}
	fmt.Println("PASS: dot segment correctly blocked")
	return true
}

func main() {
	if !setupServer() {
		cleanup()
		os.Exit(1)
	}
	defer cleanup()

	passed := true

	if !testDotDotTraversal() {
		passed = false
	}
	if !testBackslashTraversal() {
		passed = false
	}
	if !testDoubleSlashTraversal() {
		passed = false
	}
	if !testDotSegment() {
		passed = false
	}

	if passed {
		fmt.Println("All path traversal checks passed")
		os.Exit(0)
	}
	fmt.Println("Some path traversal checks failed")
	os.Exit(1)
}
