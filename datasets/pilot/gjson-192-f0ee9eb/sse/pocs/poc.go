package main

import (
	"github.com/tidwall/gjson"
)

func main() {
testJson := `0.#[[{}]].@valid:"000`
gjson.Get(testJson, testJson)
}