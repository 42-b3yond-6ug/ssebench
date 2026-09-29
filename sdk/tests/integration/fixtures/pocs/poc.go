package main

import (
	"fmt"

	"buggy"
)

func main() {
	// This input triggers the bug:
	// - len("{") = 1, which is < 2
	// - But due to operator precedence bug, the condition evaluates to true
	// - Then s[1:0] causes a panic
	input := "{"
	fmt.Printf("Calling Unwrap(%q)...\n", input)
	result := buggy.Unwrap(input)
	fmt.Printf("Result: %q\n", result)
	fmt.Println("If you see this, the bug is fixed!")
}
