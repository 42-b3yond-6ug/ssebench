package entrypoint

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"os"
	"strings"
)

// ssebenchHandler is a custom slog.Handler that produces logfmt output:
//
//	time=<RFC3339> level=<LEVEL> service=<prefix> msg=<message> [key=value ...]
type ssebenchHandler struct {
	prefix   string
	w        io.Writer
	level    slog.Level
	preAttrs []slog.Attr // attrs bound via WithAttrs
}

func (h *ssebenchHandler) Enabled(_ context.Context, l slog.Level) bool {
	return l >= h.level
}

func (h *ssebenchHandler) Handle(_ context.Context, r slog.Record) error {
	var level string
	switch {
	case r.Level <= slog.LevelDebug:
		level = "DEBUG"
	case r.Level <= slog.LevelInfo:
		level = "INFO"
	case r.Level <= slog.LevelWarn:
		level = "WARN"
	default:
		level = "ERROR"
	}

	var sb strings.Builder
	sb.WriteString("time=")
	sb.WriteString(r.Time.UTC().Format("2006-01-02T15:04:05Z"))
	sb.WriteString(" level=")
	sb.WriteString(level)
	sb.WriteString(" service=")
	sb.WriteString(h.prefix)
	sb.WriteString(" msg=")
	sb.WriteString(logfmtValue(r.Message))

	// pre-bound attributes (from WithAttrs)
	for _, a := range h.preAttrs {
		writeAttr(&sb, a)
	}

	// per-record attributes
	r.Attrs(func(a slog.Attr) bool {
		writeAttr(&sb, a)
		return true
	})

	sb.WriteByte('\n')
	_, err := fmt.Fprint(h.w, sb.String())
	return err
}

func (h *ssebenchHandler) WithAttrs(attrs []slog.Attr) slog.Handler {
	merged := make([]slog.Attr, len(h.preAttrs)+len(attrs))
	copy(merged, h.preAttrs)
	copy(merged[len(h.preAttrs):], attrs)
	return &ssebenchHandler{
		prefix:   h.prefix,
		w:        h.w,
		level:    h.level,
		preAttrs: merged,
	}
}

func (h *ssebenchHandler) WithGroup(_ string) slog.Handler { return h }

// writeAttr appends a single key=value logfmt pair to sb.
func writeAttr(sb *strings.Builder, a slog.Attr) {
	a.Value = a.Value.Resolve()
	if a.Equal(slog.Attr{}) {
		return
	}
	sb.WriteByte(' ')
	sb.WriteString(a.Key)
	sb.WriteByte('=')
	sb.WriteString(logfmtValue(fmt.Sprintf("%v", a.Value.Any())))
}

// logfmtValue quotes the value if it contains spaces, quotes, or is empty.
func logfmtValue(s string) string {
	if s == "" {
		return `""`
	}
	if strings.ContainsAny(s, " \t\r\n\"=") {
		return `"` + strings.ReplaceAll(s, `"`, `\"`) + `"`
	}
	return s
}

// logger is the package-level slog.Logger used by all log helpers.
var logger *slog.Logger

// initLogger initialises the package-level logger.
//   - prefix  — the service name, e.g. "ssebench"
//   - w       — destination writer
//   - debug   — whether to enable DEBUG level
func initLogger(prefix string, w io.Writer, debug bool) {
	level := slog.LevelInfo
	if debug {
		level = slog.LevelDebug
	}
	logger = slog.New(&ssebenchHandler{
		prefix: prefix,
		w:      w,
		level:  level,
	})
}

func init() {
	// Safe default so callers don't panic before main() calls initLogger.
	initLogger("ssebench", os.Stdout, false)
}
