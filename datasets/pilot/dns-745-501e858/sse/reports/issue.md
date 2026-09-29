### What did I do?

PoC.go

```
package main

import (
	"fmt"
	"strings"

	"github.com/miekg/dns"
)

func main() {
	r := strings.NewReader(` Ta 0 0 0`)
	for x := range dns.ParseZone(r, "", "") {
		if x.Error != nil {
			fmt.Println(x.Error)
		} else if x == nil {
			// This should never be reached
			fmt.Println("x == NIL")
		} else {
			// Do something with x.RR
			fmt.Println(x.RR.String())
		}
	}
	return
}
```

### What happened?

```
panic: runtime error: invalid memory address or nil pointer dereference
[signal SIGSEGV: segmentation violation code=0x1 addr=0x20 pc=0x65a762]

goroutine 1 [running]:
main.main()
	/path/to/gopath/src/fuzz/dns/worker/main.go:20 +0x122
exit status 2
```