Here is the vulnerability report formatted in Markdown:

# Denial of Service (DoS) via Slice Parameter Manipulation in Revel

Once the [slices parameter](https://revel.github.io/manual/parameters.html#slices) feature is used, the website will be suffering from DoS attack.

When we need to get a slice parameter, we may use the following code snippet in our controller:

```go
func (c App) DoS1(name []string) revel.Result {
    return c.RenderText(fmt.Sprint(name))
}

func (c App) DoS2() revel.Result {
    var name []string
    c.Params.Bind(&name, "name")
    return c.RenderText(fmt.Sprint(name))
}

```

It looks like everything is OK. However, we can exhaust the server's MEM with only one request.

**Example:**
When simply visiting `http://localhost:9000/dos1?name[1234567890]=1`, the server's CPU and memory usage will soar, and the OOM killer will be triggered eventually.

## Root Cause

This vulnerability was caused by the following code:

**File:** [`revel/binder.go`](https://www.google.com/search?q=%5Bhttps://github.com/revel/revel/blob/a3d7a7c23ca885cc5036d3641ede49ce4a14ee2e/binder.go%23L210-L277%5D(https://github.com/revel/revel/blob/a3d7a7c23ca885cc5036d3641ede49ce4a14ee2e/binder.go%23L210-L277))

**Vulnerable Code Snippet:**

```go
func bindSlice(params *Params, name string, typ reflect.Type) reflect.Value {
    // Collect an array of slice elements with their indexes (and the max index).
    maxIndex := -1
    numNoIndex := 0
    sliceValues := []sliceValue{}

    // Factor out the common slice logic (between form values and files).
    processElement := func(key string, vals []string, files []*multipart.FileHeader) {
        if !strings.HasPrefix(key, name+"[") {
            return
        }

        // Extract the index, and the index where a sub-key starts. (e.g. field[0].subkey)
        index := -1
        leftBracket, rightBracket := len(name), strings.Index(key[len(name):], "]")+len(name)
        if rightBracket > leftBracket+1 {
            index, _ = strconv.Atoi(key[leftBracket+1 : rightBracket])
        }
        subKeyIndex := rightBracket + 1

        // Handle the indexed case.
        if index > -1 {
            if index > maxIndex {
                maxIndex = index
            }
            sliceValues = append(sliceValues, sliceValue{
                index: index,
                value: Bind(params, key[:subKeyIndex], typ.Elem()),
            })
            return
        }

        // It's an un-indexed element. (e.g. element[])
        numNoIndex += len(vals) + len(files)
        for _, val := range vals {
            // Unindexed values can only be direct-bound.
            sliceValues = append(sliceValues, sliceValue{
                index: -1,
                value: BindValue(val, typ.Elem()),
            })
        }

        for _, fileHeader := range files {
            sliceValues = append(sliceValues, sliceValue{
                index: -1,
                value: BindFile(fileHeader, typ.Elem()),
            })
        }
    }

    for key, vals := range params.Values {
        processElement(key, vals, nil)
    }
    for key, fileHeaders := range params.Files {
        processElement(key, nil, fileHeaders)
    }

    // VULNERABILITY: maxIndex is controlled by user input
    resultArray := reflect.MakeSlice(typ, maxIndex+1, maxIndex+1+numNoIndex)
    
    for _, sv := range sliceValues {
        if sv.index != -1 {
            resultArray.Index(sv.index).Set(sv.value)
        } else {
            resultArray = reflect.Append(resultArray, sv.value)
        }
    }

    return resultArray
}

```

When the function above is invoked, Revel will calculate the `maxIndex` from the user's input. Thus, the attacker could make the `maxIndex` as large as possible. When `reflect.MakeSlice` is called, Golang will attempt to allocate a large amount of memory corresponding to the `maxIndex` needed.

## Mitigation

A possible solution for this vulnerability is to specify the upper bound of the `maxIndex` in the code or configuration file.

**Recommendation:** Before the problem is fixed, please avoid using the slices parameter feature.