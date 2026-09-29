package main

import (
	"bytes"
	"fmt"
	"io"
	"os"
	"strings"

	"github.com/ulikunitz/xz"
)

func main() {
	var a = []byte{0x81, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89, 0x8a, 0x8b}
	r := bytes.NewReader(a)
	val, n, err := xz.ReadUvarint(r)
	_ = val 
	if err != nil {
		if err == io.EOF {
			fmt.Printf("Vulnerable! Hit EOF after %d bytes. Overflow was NOT detected.\n", n)
			os.Exit(1) 
		} else if strings.Contains(err.Error(), "overflows") {
			fmt.Printf("Fixed! Detected overflow error: %v\n", err)
			os.Exit(0)
		} 
	}
}