package main

import (
	"fmt"
	"os"

	"gopkg.in/yaml.v2"
)

func main() {
	// YAML alias bomb: each level references the previous 9 times,
	// creating exponential expansion (9^8 ~ 43 million leaf nodes).
	// The document is under 500 bytes but expands to gigabytes of memory.
	yamlBomb := `
version: "3"
services: &services ["lol","lol","lol","lol","lol","lol","lol","lol","lol"]
b: &b [*services,*services,*services,*services,*services,*services,*services,*services,*services]
c: &c [*b,*b,*b,*b,*b,*b,*b,*b,*b]
d: &d [*c,*c,*c,*c,*c,*c,*c,*c,*c]
e: &e [*d,*d,*d,*d,*d,*d,*d,*d,*d]
f: &f [*e,*e,*e,*e,*e,*e,*e,*e,*e]
g: &g [*f,*f,*f,*f,*f,*f,*f,*f,*f]
h: &h [*g,*g,*g,*g,*g,*g,*g,*g,*g]
i: &i [*h,*h,*h,*h,*h,*h,*h,*h,*h]
`

	var t interface{}
	err := yaml.Unmarshal([]byte(yamlBomb), &t)

	if err != nil {
		fmt.Println("PASS: alias bomb was rejected:", err)
		os.Exit(0)
	}
	fmt.Println("FAIL: alias bomb was not rejected, vulnerability triggered")
	os.Exit(1)
}
