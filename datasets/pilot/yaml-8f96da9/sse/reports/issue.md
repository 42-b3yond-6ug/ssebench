Hi folks 👋🏻 Found this panic (along with [#665](https://github.com/go-yaml/yaml/issues/665)) while fuzzing my own project.

Minimal example of the panic ([https://play.golang.org/p/gLM_eHzcrgz](https://play.golang.org/p/gLM_eHzcrgz)):

```
package main

import (
	"gopkg.in/yaml.v3"
)

func main() {
	var t interface{}
	yaml.Unmarshal([]byte("0: [:!00 \\xef"), &t)
}

```

Output:

```
panic: internal error: attempted to parse unknown event (please report): none [recovered]
	panic: internal error: attempted to parse unknown event (please report): none

	goroutine 1 [running]:
	gopkg.in/yaml%2ev3.handleErr(0xc000043f60)
		/tmp/gopath818249317/pkg/mod/gopkg.in/yaml.v3@v3.0.0-20200615113413-eeeca48fe776/yaml.go:294 +0x85
	panic(0x50f120, 0xc000010330)
		/usr/local/go-faketime/src/runtime/panic.go:969 +0x1b9
	gopkg.in/yaml%2ev3.(*parser).parse(0xc000036c00, 0x0)
		/tmp/gopath818249317/pkg/mod/gopkg.in/yaml.v3@v3.0.0-20200615113413-eeeca48fe776/decode.go:163 +0x277
	gopkg.in/yaml%2ev3.(*parser).parseChild(...)
		/tmp/gopath818249317/pkg/mod/gopkg.in/yaml.v3@v3.0.0-20200615113413-eeeca48fe776/decode.go:194
	gopkg.in/yaml%2ev3.(*parser).sequence(0xc000036c00, 0xc00000e007)
		/tmp/gopath818249317/pkg/mod/gopkg.in/yaml.v3@v3.0.0-20200615113413-eeeca48fe776/decode.go:259 +0xff
	gopkg.in/yaml%2ev3.(*parser).parse(0xc000036c00, 0x0)
		/tmp/gopath818249317/pkg/mod/gopkg.in/yaml.v3@v3.0.0-20200615113413-eeeca48fe776/decode.go:154 +0xe7
	gopkg.in/yaml%2ev3.(*parser).parseChild(0xc000036c00, 0xc00007e3c0, 0xc00007e460)
		/tmp/gopath818249317/pkg/mod/gopkg.in/yaml.v3@v3.0.0-20200615113413-eeeca48fe776/decode.go:194 +0x2f
	gopkg.in/yaml%2ev3.(*parser).mapping(0xc000036c00, 0x9)
		/tmp/gopath818249317/pkg/mod/gopkg.in/yaml.v3@v3.0.0-20200615113413-eeeca48fe776/decode.go:285 +0x1ad
	gopkg.in/yaml%2ev3.(*parser).parse(0xc000036c00, 0xc000000003)
		/tmp/gopath818249317/pkg/mod/gopkg.in/yaml.v3@v3.0.0-20200615113413-eeeca48fe776/decode.go:152 +0x10d
	gopkg.in/yaml%2ev3.(*parser).parseChild(...)
		/tmp/gopath818249317/pkg/mod/gopkg.in/yaml.v3@v3.0.0-20200615113413-eeeca48fe776/decode.go:194
	gopkg.in/yaml%2ev3.(*parser).document(0xc000036c00, 0x3)
		/tmp/gopath818249317/pkg/mod/gopkg.in/yaml.v3@v3.0.0-20200615113413-eeeca48fe776/decode.go:203 +0x8b
	gopkg.in/yaml%2ev3.(*parser).parse(0xc000036c00, 0x0)
		/tmp/gopath818249317/pkg/mod/gopkg.in/yaml.v3@v3.0.0-20200615113413-eeeca48fe776/decode.go:156 +0x87
	gopkg.in/yaml%2ev3.unmarshal(0xc00002c590, 0xa, 0xa, 0x50a080, 0xc000010320, 0x0, 0x0, 0x0)
		/tmp/gopath818249317/pkg/mod/gopkg.in/yaml.v3@v3.0.0-20200615113413-eeeca48fe776/yaml.go:161 +0x26a
	gopkg.in/yaml%2ev3.Unmarshal(...)
		/tmp/gopath818249317/pkg/mod/gopkg.in/yaml.v3@v3.0.0-20200615113413-eeeca48fe776/yaml.go:89
	main.main()
		/tmp/sandbox604520862/prog.go:9 +0x99

```