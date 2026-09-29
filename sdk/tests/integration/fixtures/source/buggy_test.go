package buggy

import "testing"

func TestUnwrapNormal(t *testing.T) {
	tests := []struct {
		input    string
		expected string
	}{
		{"[hello]", "hello"},
		{"{world}", "world"},
		{"plain", "plain"},
		{"[]", ""},
		{"{}", ""},
	}

	for _, tt := range tests {
		result := Unwrap(tt.input)
		if result != tt.expected {
			t.Errorf("Unwrap(%q) = %q, want %q", tt.input, result, tt.expected)
		}
	}
}

func TestUnwrapEdgeCases(t *testing.T) {
	// These edge cases expose the bug - they should NOT panic
	// but they will panic with the buggy code
	edgeCases := []string{
		"{", // Single open brace - will panic due to bug
		"[", // Single open bracket - will panic due to bug
		"",  // Empty string
		"a", // Single character
	}

	for _, input := range edgeCases {
		t.Run(input, func(t *testing.T) {
			defer func() {
				if r := recover(); r != nil {
					t.Errorf("Unwrap(%q) panicked: %v", input, r)
				}
			}()
			Unwrap(input)
		})
	}
}
