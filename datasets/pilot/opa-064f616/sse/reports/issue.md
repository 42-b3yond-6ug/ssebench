If a local var in a comprehension body overrides a function call in the comprehension head, it will never be possible to make that call.

```
package test
f(x) := x
p := [f(y) | y = 1; f = 2] # var f overrides function f()

```

Will cause an eval-time error:

```
2 errors occurred:
policy.rego:3: rego_type_error: match error
	left  : (any) => any
	right : number
policy.rego:3: rego_type_error: undefined ref: data.test.f
	data.test.f
	^^^^^^^^^^^
	have: (any) => any

```

A compile-time error should be introduced for capturing this case.

A special case exists that will cause a compiler panic:

```
package test
p := [input() | input := 1] # var input overrides function input()

```

Command: `opa eval -d policy.rego 'data.test'` =>

```
panic: interface conversion: ast.Value is ast.Var, not ast.Ref [recovered]
	panic: interface conversion: ast.Value is ast.Var, not ast.Ref

goroutine 1 [running]:
github.com/open-policy-agent/opa/ast.(*Compiler).compile.func1()
	github.com/open-policy-agent/opa/ast/compile.go:1225 +0x60
panic({0x103d6db20, 0x14000404ae0})
	runtime/panic.go:838 +0x204
github.com/open-policy-agent/opa/ast.(*Expr).Operator(...)
	github.com/open-policy-agent/opa/ast/policy.go:1164
github.com/open-policy-agent/opa/ast.isRegoMetadataChainCall(0x1400057d2c8?)
	github.com/open-policy-agent/opa/ast/compile.go:1922 +0x10c

```