package main

import (
	"bytes"
	"fmt"
	"os"
	"strings"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/cli-runtime/pkg/printers"
	"k8s.io/kubectl/pkg/cmd/events"
)

// This PoC demonstrates ANSI escape sequence injection in kubectl's table
// printer and event printer output.
//
// The bug: printTable and EventPrinter write user-controlled values to the
// terminal without sanitizing ANSI escape sequences or control characters
// (\r, \f). An attacker who controls Kubernetes object fields (e.g. Event
// messages, types, reasons) can inject escape codes that clear the screen,
// reposition the cursor, or spoof output when a user runs "kubectl get" or
// "kubectl events".
//
// The fix introduces WriteEscaped() and EscapeTerminal() which replace \x1b
// with ^[ and \r with \\r, and changes truncation from newline-only to \f\n\r.
// The patched paths are:
//   - tableprinter.go "case string:" branch → WriteEscaped
//   - tableprinter.go "default:" branch → WriteEscaped
//   - event_printer.go printOneEvent → EscapeTerminal on all user fields
//
// Behavior:
//   Unpatched: raw \x1b / \r bytes appear in output → exit 1
//   Patched:   all control chars replaced with safe representations → exit 0

// malStringer is a non-string type whose String() returns ANSI escape chars.
// This forces the tableprinter through the "default:" branch rather than
// "case string:".
type malStringer struct{ s string }

func (m malStringer) String() string { return m.s }

func main() {
	vulnerable := false
	printer := printers.NewTablePrinter(printers.PrintOptions{NoHeaders: true})

	// === TablePrinter tests (tableprinter.go) ===

	// Test 1: String cell with ANSI escape — exercises "case string:" + WriteEscaped.
	vulnerable = testStringCell(printer, "ANSI escape in string cell",
		"\x1b[31m[MALICIOUS]\x1b[0m",
		containsESC,
	) || vulnerable

	// Test 2: Non-string cell with ANSI escape — exercises "default:" + WriteEscaped.
	vulnerable = testNonStringCell(printer, "ANSI escape in non-string cell",
		"\x1b[31m[MALICIOUS]\x1b[0m",
		containsESC,
	) || vulnerable

	// Test 3: String cell with carriage return — exercises the new \r truncation
	// path added by the patch (strings.IndexAny with "\f\n\r" instead of just "\n").
	// Pre-patch: \r passes through and lets attacker overwrite the line.
	// Post-patch: truncated at \r and \r replaced with \\r by WriteEscaped.
	vulnerable = testStringCell(printer, "Carriage return in string cell",
		"visible\roverwritten",
		containsCR,
	) || vulnerable

	// Test 4: String cell with form feed — exercises the new \f truncation path.
	// Pre-patch: \f passes through (tabwriter treats it as newline, corrupting output).
	// Post-patch: truncated at \f with "..." appended.
	vulnerable = testStringCell(printer, "Form feed in string cell",
		"before\fafter",
		func(out []byte) bool {
			return strings.Contains(string(out), "after")
		},
	) || vulnerable

	// === EventPrinter tests (event_printer.go) ===

	// Test 5: EventPrinter — Message field with ANSI escape.
	// Exercises: EscapeTerminal(strings.TrimSpace(e.Message)) in printOneEvent.
	vulnerable = testEventField("EventPrinter Message with ANSI escape",
		func(e *corev1.Event) { e.Message = "\x1b[35mMalicious message\x1b[0m" },
		containsESC,
	) || vulnerable

	// Test 6: EventPrinter — Type field with ANSI escape.
	// Exercises: EscapeTerminal(e.Type) in printOneEvent.
	vulnerable = testEventField("EventPrinter Type with ANSI escape",
		func(e *corev1.Event) { e.Type = "\x1b[32mNormal\x1b[0m" },
		containsESC,
	) || vulnerable

	// Test 7: EventPrinter — Reason field with ANSI escape.
	// Exercises: EscapeTerminal(e.Reason) in printOneEvent.
	vulnerable = testEventField("EventPrinter Reason with ANSI escape",
		func(e *corev1.Event) { e.Reason = "\x1b[31mFailed\x1b[0m" },
		containsESC,
	) || vulnerable

	// Test 8: EventPrinter — InvolvedObject.Kind with ANSI escape.
	// Exercises: EscapeTerminal(e.InvolvedObject.Kind) in printOneEvent.
	vulnerable = testEventField("EventPrinter InvolvedObject.Kind with ANSI escape",
		func(e *corev1.Event) { e.InvolvedObject.Kind = "\x1b[33mPod\x1b[0m" },
		containsESC,
	) || vulnerable

	// Test 9: EventPrinter — InvolvedObject.Name with ANSI escape.
	// Exercises: EscapeTerminal(e.InvolvedObject.Name) in printOneEvent.
	vulnerable = testEventField("EventPrinter InvolvedObject.Name with ANSI escape",
		func(e *corev1.Event) { e.InvolvedObject.Name = "\x1b[34mtest-pod\x1b[0m" },
		containsESC,
	) || vulnerable

	if vulnerable {
		os.Exit(1)
	}
	fmt.Println("[SAFE] All output paths properly sanitize escape sequences and control characters")
	os.Exit(0)
}

func testStringCell(printer printers.ResourcePrinter, name, payload string, isVuln func([]byte) bool) bool {
	table := &metav1.Table{
		ColumnDefinitions: []metav1.TableColumnDefinition{
			{Name: "MESSAGE", Type: "string"},
		},
		Rows: []metav1.TableRow{
			{Cells: []interface{}{payload}},
		},
	}
	var buf bytes.Buffer
	if err := printer.PrintObj(table, &buf); err != nil {
		fmt.Printf("[ERROR] %s: %v\n", name, err)
		return true
	}
	if isVuln(buf.Bytes()) {
		fmt.Printf("[VULNERABLE] %s: unsanitized control character in output\n", name)
		return true
	}
	fmt.Printf("[SAFE] %s: output properly sanitized\n", name)
	return false
}

func testNonStringCell(printer printers.ResourcePrinter, name, payload string, isVuln func([]byte) bool) bool {
	table := &metav1.Table{
		ColumnDefinitions: []metav1.TableColumnDefinition{
			{Name: "VALUE", Type: "integer"},
		},
		Rows: []metav1.TableRow{
			{Cells: []interface{}{malStringer{payload}}},
		},
	}
	var buf bytes.Buffer
	if err := printer.PrintObj(table, &buf); err != nil {
		fmt.Printf("[ERROR] %s: %v\n", name, err)
		return true
	}
	if isVuln(buf.Bytes()) {
		fmt.Printf("[VULNERABLE] %s: unsanitized control character in output\n", name)
		return true
	}
	fmt.Printf("[SAFE] %s: output properly sanitized\n", name)
	return false
}

func testEventField(name string, mutate func(*corev1.Event), isVuln func([]byte) bool) bool {
	event := &corev1.Event{
		ObjectMeta:     metav1.ObjectMeta{Name: "test-event", Namespace: "default"},
		InvolvedObject: corev1.ObjectReference{Kind: "Pod", Name: "test-pod"},
		Type:           "Normal",
		Reason:         "Started",
		Message:        "Container started",
		Count:          1,
	}
	mutate(event)
	var buf bytes.Buffer
	ep := &events.EventPrinter{NoHeaders: true}
	ep.PrintObj(event, &buf)
	if isVuln(buf.Bytes()) {
		fmt.Printf("[VULNERABLE] %s: unsanitized control character in output\n", name)
		return true
	}
	fmt.Printf("[SAFE] %s: output properly sanitized\n", name)
	return false
}

func containsESC(data []byte) bool {
	for _, b := range data {
		if b == 0x1b {
			return true
		}
	}
	return false
}

func containsCR(data []byte) bool {
	for _, b := range data {
		if b == '\r' {
			return true
		}
	}
	return false
}
