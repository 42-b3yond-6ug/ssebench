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