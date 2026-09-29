# Bug Report: Panic in Unwrap function

## Description

The `Unwrap` function panics when given a single-character string like `"{"` or `"["`.

## Steps to Reproduce

```go
package main

import "buggy"

func main() {
    buggy.Unwrap("{")  // Panics!
}
```

## Expected Behavior

The function should return the input unchanged for strings that are too short to unwrap.

## Actual Behavior

```
panic: runtime error: slice bounds out of range [1:0]
```

## Root Cause

Operator precedence issue in the condition:
```go
if len(s) >= 2 && s[0] == '[' || s[0] == '{' {
```

This evaluates as `(len(s) >= 2 && s[0] == '[') || s[0] == '{'` instead of the intended `len(s) >= 2 && (s[0] == '[' || s[0] == '{')`.
