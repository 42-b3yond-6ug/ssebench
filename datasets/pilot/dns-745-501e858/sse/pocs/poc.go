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