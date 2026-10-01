# Task

You are a software security engineer. Fix a confirmed vulnerability in gjson, a Go project, by modifying its source code.

## Objective

Deliver a complete, root-cause fix that prevents all inputs from triggering the vulnerability or crashing the program, not only the known proof-of-vulnerability (PoV) cases.

## Requirements

1. Identify the vulnerability type, trigger conditions, affected code paths, and security impact before changing code.
2. Fix the underlying issue at its root cause. Don't patch only symptoms or the PoV. Do not "fix" by catch-all swallowing, disabling features, PoV-only special casing, or overly broad input bans.
3. Change only the project's code. Do not add, update or delete tests or test data, even where a test expects the old behavior: the validation tests are kept separately and take care of that. To check your fix, write temporary programs or inputs outside the project's source tree.
4. Do not unintentionally break expected behavior. If behavior must change, make it explicit and justified.
5. Prefer minimal, clear, idiomatic changes. Avoid hacks, fragile checks, or broad refactors unless necessary.
6. Use available tools deliberately. Inspect surrounding code to infer intended behavior and constraints.

After the fix is complete, commit your changes with a clear commit message.

## Validation

Your fix will be validated by tests designed by human experts to evaluate the code quality:

- running the test suite to confirm no regressions;
- running PoVs to confirm the exploit no longer works (PoVs may not be available to you);
- testing security-oriented edge cases beyond the PoV;
- developer review for code quality and alignment with intended functionality.

## Vulnerability

### Report 1 of 2

```text
panic: runtime error: slice bounds out of range [1:0]

goroutine 1 [running]:
github.com/tidwall/gjson.unwrap(...)
        /src/gjson/gjson.go:2596
github.com/tidwall/gjson.modJoin.func2({0x3, {0x4cc22f, 0xa}, {0x4cc230, 0x8}, 0x0, 0x6}, {0x5, {0xc0000160dc, 0x2}, ...})
        /src/gjson/gjson.go:2776 +0x285
github.com/tidwall/gjson.Result.ForEach({0x5, {0xc0000160d8, 0x6}, {0x0, 0x0}, 0x0, 0x0}, 0xc00011e208)
        /src/gjson/gjson.go:279 +0x46c
github.com/tidwall/gjson.modJoin({0xc0000160d8, 0x6}, {0x4cc229, 0x14})
        /src/gjson/gjson.go:2769 +0x436
github.com/tidwall/gjson.execModifier({0xc0000160d8, 0x6}, {0x4cc223?, 0xc0000160d0?})
        /src/gjson/gjson.go:2587 +0x36c
github.com/tidwall/gjson.Get({0xc0000160d8, 0x6}, {0x4cc223, 0x1e})
        /src/gjson/gjson.go:1881 +0x92
github.com/tidwall/gjson.Get({0x4cc23d, 0x4}, {0x4cc21b, 0x26})
        /src/gjson/gjson.go:1885 +0x1b4
github.com/tidwall/gjson.Result.Get(...)
        /src/gjson/gjson.go:297
github.com/tidwall/gjson.parseArray(0xc00011fa10, 0x1, {0x4cc219?, 0x28?})
        /src/gjson/gjson.go:1579 +0x124a
github.com/tidwall/gjson.Get({0x4cc218, 0x2a}, {0x4cc219?, 0x0?})
        /src/gjson/gjson.go:1968 +0x44a
github.com/tidwall/gjson.Get({0x4cc218, 0x2a}, {0x4cc218?, 0x0?})
        /src/gjson/gjson.go:1905 +0xa05
main.main()
        /ssebench/pocs/poc.go:10 +0x2b
exit status 2
```

### Report 2 of 2

````text
```
package main

import (
"fmt"
"github.com/tidwall/gjson"
)

func main() {
testJson := [#.@pretty.@join:{""[]""preserve"3,"][{]]]
gjson.Get(testJson, testJson)
fmt.Println("hello")
}
```
````

## Project

- Name: gjson
- Language: Go
- Source code: /src/gjson

## Build and test

### Build script

```bash
#!/bin/bash
set -euo pipefail

export GOPATH="/go"
export PATH="$GOPATH/bin:/usr/local/go/bin:$PATH"

go build
```

### Test script

```bash
#!/bin/bash

# build the project first.

go test ./... -short -mod=vendor
```
