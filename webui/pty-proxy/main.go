package main

import (
	"bufio"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log"
	"os"
	"os/exec"
	"os/signal"
	"regexp"
	"syscall"

	"github.com/creack/pty"
)

const usage = "Usage: pty-proxy [--workdir WORKDIR] <container-id> [command [arg...]]"

// version is set at build time: -ldflags "-X main.version=<version>".
var version = "dev"

var containerIDPattern = regexp.MustCompile(`^[a-f0-9]{12,64}$`)

// Message types - must match frontend/backend
type ClientMessage struct {
	Type string `json:"type"` // "input" | "resize"
	Data string `json:"data,omitempty"`
	Cols int    `json:"cols,omitempty"`
	Rows int    `json:"rows,omitempty"`
}

type ServerMessage struct {
	Type    string `json:"type"` // "output" | "error" | "exit"
	Data    string `json:"data,omitempty"`
	Message string `json:"message,omitempty"`
	Code    *int   `json:"code,omitempty"`
}

// parseArgs reads the command line. Flags stop at the container ID, so the
// command and its arguments reach docker exec verbatim and are never parsed
// by a shell.
func parseArgs(argv []string) (dockerArgs []string, err error) {
	fs := flag.NewFlagSet("pty-proxy", flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	workdir := fs.String("workdir", "", "working directory inside the container")
	if err := fs.Parse(argv); err != nil {
		return nil, err
	}

	args := fs.Args()
	if len(args) == 0 {
		return nil, fmt.Errorf("missing container ID")
	}
	containerID := args[0]
	if !containerIDPattern.MatchString(containerID) {
		return nil, fmt.Errorf("invalid container ID %q", containerID)
	}
	command := args[1:]
	if len(command) == 0 {
		command = []string{"bash"}
	}

	dockerArgs = []string{"exec", "-it"}
	if *workdir != "" {
		dockerArgs = append(dockerArgs, "-w", *workdir)
	}
	dockerArgs = append(dockerArgs, containerID)
	return append(dockerArgs, command...), nil
}

func main() {
	// Set up logging to stderr (stdout is for JSON messages)
	log.SetOutput(os.Stderr)
	log.SetPrefix("[PTY-PROXY] ")

	if len(os.Args) == 2 && os.Args[1] == "--version" {
		fmt.Println("pty-proxy", version)
		return
	}

	dockerArgs, err := parseArgs(os.Args[1:])
	if err != nil {
		sendError(fmt.Sprintf("%v. %s", err, usage))
		os.Exit(1)
	}

	log.Printf("Starting PTY session: docker %q", dockerArgs)

	// Start docker exec with PTY
	cmd := exec.Command("docker", dockerArgs...)
	cmd.Env = append(os.Environ(), "TERM=xterm-256color")

	// Start with PTY
	ptmx, err := pty.Start(cmd)
	if err != nil {
		sendError(fmt.Sprintf("Failed to start PTY: %v", err))
		os.Exit(1)
	}
	defer ptmx.Close()

	// Set initial size (80x24 default)
	if err := pty.Setsize(ptmx, &pty.Winsize{
		Rows: 24,
		Cols: 80,
	}); err != nil {
		log.Printf("Warning: failed to set initial size: %v", err)
	}

	log.Printf("PTY started (PID: %d)", cmd.Process.Pid)

	// Handle graceful shutdown
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)

	// Channel to signal shutdown
	done := make(chan struct{})

	// Stream PTY output to stdout (as JSON)
	go streamPTYOutput(ptmx, done)

	// Read commands from stdin (JSON)
	go handleStdinCommands(ptmx, done)

	// Wait for process to exit or signal
	go func() {
		cmd.Wait()
		exitCode := getExitCode(cmd)
		log.Printf("Process exited with code: %d", exitCode)
		sendExit(exitCode)
		close(done)
	}()

	// Wait for shutdown signal or process exit
	select {
	case <-sigChan:
		log.Println("Received shutdown signal")
		cmd.Process.Kill()
	case <-done:
		log.Println("Process completed")
	}
}

func streamPTYOutput(ptmx *os.File, done chan struct{}) {
	buf := make([]byte, 32*1024) // 32KB buffer

	for {
		select {
		case <-done:
			return
		default:
			n, err := ptmx.Read(buf)
			if err != nil {
				if err != io.EOF {
					log.Printf("PTY read error: %v", err)
				}
				return
			}

			if n > 0 {
				sendOutput(string(buf[:n]))
			}
		}
	}
}

func handleStdinCommands(ptmx *os.File, done chan struct{}) {
	scanner := bufio.NewScanner(os.Stdin)
	scanner.Buffer(make([]byte, 64*1024), 1024*1024) // 64KB initial, 1MB max

	for scanner.Scan() {
		select {
		case <-done:
			return
		default:
			line := scanner.Text()
			var msg ClientMessage

			if err := json.Unmarshal([]byte(line), &msg); err != nil {
				log.Printf("Failed to parse message: %v", err)
				continue
			}

			switch msg.Type {
			case "input":
				// Write input to PTY
				if _, err := ptmx.Write([]byte(msg.Data)); err != nil {
					log.Printf("PTY write error: %v", err)
					return
				}

			case "resize":
				// Resize PTY
				if msg.Cols > 0 && msg.Rows > 0 {
					if err := pty.Setsize(ptmx, &pty.Winsize{
						Rows: uint16(msg.Rows),
						Cols: uint16(msg.Cols),
					}); err != nil {
						log.Printf("Resize failed: %v", err)
					} else {
						log.Printf("Resized to %dx%d", msg.Cols, msg.Rows)
					}
				}

			default:
				log.Printf("Unknown message type: %s", msg.Type)
			}
		}
	}

	if err := scanner.Err(); err != nil {
		log.Printf("Stdin read error: %v", err)
	}
}

func sendOutput(data string) {
	msg := ServerMessage{
		Type: "output",
		Data: data,
	}
	sendJSON(msg)
}

func sendError(message string) {
	msg := ServerMessage{
		Type:    "error",
		Message: message,
	}
	sendJSON(msg)
}

func sendExit(code int) {
	msg := ServerMessage{
		Type: "exit",
		Code: &code,
	}
	sendJSON(msg)
}

func sendJSON(msg ServerMessage) {
	data, err := json.Marshal(msg)
	if err != nil {
		log.Printf("Failed to marshal JSON: %v", err)
		return
	}
	fmt.Println(string(data))
}

func getExitCode(cmd *exec.Cmd) int {
	if cmd.ProcessState == nil {
		return -1
	}

	if exitErr, ok := cmd.ProcessState.Sys().(syscall.WaitStatus); ok {
		return exitErr.ExitStatus()
	}

	return -1
}
