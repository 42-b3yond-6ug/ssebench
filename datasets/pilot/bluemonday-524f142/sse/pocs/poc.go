package main

import (
	"fmt"
	"os"
	"strings"

	"github.com/microcosm-cc/bluemonday"
)

func main() {
	p := bluemonday.NewPolicy()
	original := "<scr\u0130pt>&lt;script&gt;alert(/XSS/)&lt;/script&gt;"
	output := p.Sanitize(original)
	if strings.Contains(output, "<script>alert(/XSS/)</script>") {
		fmt.Println("[-] Vulnerability Detected: Escaped entities were improperly decoded to raw tags!")
		os.Exit(1)
	}
	fmt.Println("[+] Patch Verified: Output remains escaped or stripped.")
	os.Exit(0)
}