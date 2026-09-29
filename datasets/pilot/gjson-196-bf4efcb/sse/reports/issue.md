```
package main

import (
"fmt"
"github.com/tidwall/gjson"
)

func main() {
testJson := [#.@pretty.@join:{""[]""preserve"3,"][{]]]
gjson.Get(testJson, testJson)
fmt.Println("hello")
}
```