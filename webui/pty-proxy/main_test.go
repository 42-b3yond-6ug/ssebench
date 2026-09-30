package main

import (
	"reflect"
	"testing"
)

func TestParseArgsTakesTheCommandAfterDashes(t *testing.T) {
	name, args, err := parseArgs([]string{"--", "ssebench", "runs", "exec", "--tty", "run-1", "--", "bash"})
	if err != nil {
		t.Fatal(err)
	}
	if name != "ssebench" {
		t.Fatalf("name %q", name)
	}
	want := []string{"runs", "exec", "--tty", "run-1", "--", "bash"}
	if !reflect.DeepEqual(args, want) {
		t.Fatalf("got %q, want %q", args, want)
	}
}

func TestParseArgsPassesArgumentsVerbatim(t *testing.T) {
	payload := "'; touch /tmp/pwned; echo '"
	name, args, err := parseArgs([]string{"prog", "--workdir", payload})
	if err != nil {
		t.Fatal(err)
	}
	if name != "prog" || !reflect.DeepEqual(args, []string{"--workdir", payload}) {
		t.Fatalf("got %q %q", name, args)
	}
}

func TestParseArgsRejectsNoCommandAndOptions(t *testing.T) {
	for _, argv := range [][]string{nil, {"--"}, {"--workdir", "/src", "bash"}, {"-c", "id"}} {
		if _, _, err := parseArgs(argv); err == nil {
			t.Errorf("%q accepted", argv)
		}
	}
}
