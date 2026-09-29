package main

import (
	"github.com/open-policy-agent/opa/ast"
)

func main() {
	moduleStr := `package test
p := [input() | input := 1]`
	parsed, _ := ast.ParseModule("test.rego", moduleStr)
	compiler := ast.NewCompiler()
	compiler.Compile(map[string]*ast.Module{
		"test.rego": parsed,
	})
}