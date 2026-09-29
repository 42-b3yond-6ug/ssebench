package buggy

// Unwrap removes surrounding brackets from a string.
// BUG: Missing parentheses causes incorrect operator precedence.
// The condition `len(s) >= 2 && s[0] == '[' || s[0] == '{'` evaluates as:
// `(len(s) >= 2 && s[0] == '[') || s[0] == '{'`
// This causes a panic when s is a short string like "{" because:
// - len("{") = 1, so len(s) >= 2 is false
// - s[0] == '[' is false
// - But s[0] == '{' is true, so the whole condition is true
// - Then s[1:len(s)-1] becomes s[1:0] which panics
func Unwrap(s string) string {
	if len(s) >= 2 && s[0] == '[' || s[0] == '{' {
		return s[1 : len(s)-1] // Panic: slice bounds out of range
	}
	return s
}
