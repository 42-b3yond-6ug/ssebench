package main

import (
	"reflect"
	"testing"
)

const testID = "0123456789ab"

func TestParseArgsDefaultsToBash(t *testing.T) {
	got, err := parseArgs([]string{testID})
	if err != nil {
		t.Fatal(err)
	}
	want := []string{"exec", "-it", testID, "bash"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("got %q, want %q", got, want)
	}
}

func TestParseArgsPassesCommandVerbatim(t *testing.T) {
	payload := "'; touch /tmp/pwned; echo '"
	got, err := parseArgs([]string{"--workdir", "/src", testID, "opencode", "run", payload, "--workdir"})
	if err != nil {
		t.Fatal(err)
	}
	want := []string{"exec", "-it", "-w", "/src", testID, "opencode", "run", payload, "--workdir"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("got %q, want %q", got, want)
	}
}

func TestParseArgsRejectsBadContainerID(t *testing.T) {
	for _, id := range []string{"x; touch /tmp/pwned", "--privileged", "my-container", "0123456789AB", "0123456789a"} {
		if _, err := parseArgs([]string{id}); err == nil {
			t.Errorf("container ID %q accepted", id)
		}
	}
	if _, err := parseArgs(nil); err == nil {
		t.Error("missing container ID accepted")
	}
}
