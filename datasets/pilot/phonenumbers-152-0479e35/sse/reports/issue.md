**Description** 
Using the phonenumbers.Parse() function with a specific input makes the program to panic - runtime error: slice bounds out of range.

**Steps to Reproduce** 
```
package main

import (
	"fmt"

	"github.com/nyaruka/phonenumbers"
)

func main() {
	crash := "0;phone-context=+00000;"
	num, err := phonenumbers.Parse(crash, "US")
	if err != nil {
		fmt.Println(err)
	}
	fmt.Println(num)
}
```

**Expected Behavior** 
An error is expected - the phone number supplied is not a number.

**Actual Behavior** 
The program panics.

**Error Message**

```
panic: runtime error: slice bounds out of range [16:6]

goroutine 1 [running]:
github.com/nyaruka/phonenumbers.buildNationalNumberForParsing({0x5cc026, 0x17}, 0xc0000e8000)
	/tmp/gopath3780427806/pkg/mod/github.com/nyaruka/phonenumbers@v1.1.9/phonenumbers.go:3024 +0x4a5
github.com/nyaruka/phonenumbers.parseHelper({0x5cc026, 0x17}, {0x5c73ac, 0x2}, 0x0, 0x1, 0xc0000cbe60)
	/tmp/gopath3780427806/pkg/mod/github.com/nyaruka/phonenumbers@v1.1.9/phonenumbers.go:2895 +0xb9
github.com/nyaruka/phonenumbers.ParseToNumber(...)
	/tmp/gopath3780427806/pkg/mod/github.com/nyaruka/phonenumbers@v1.1.9/phonenumbers.go:2809
github.com/nyaruka/phonenumbers.Parse({0x5cc026, 0x17}, {0x5c73ac, 0x2})
	/tmp/gopath3780427806/pkg/mod/github.com/nyaruka/phonenumbers@v1.1.9/phonenumbers.go:2802 +0x58
main.main()
	/tmp/sandbox1858260411/prog.go:11 +0x2f
```
