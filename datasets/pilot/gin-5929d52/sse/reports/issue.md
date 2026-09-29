## Description

`X-Forwarded-For`/ trusted proxy handling is incorrect, which makes it possible for anyone to force the value of `c.ClientIP()`, if:

-   the app has trusted proxies defined
-   and the trusted proxy handles `X-Forwarded-For` in the usual way, by appending IP addresses at the end

(the default configuration trusts every proxy and is of course also vulnerable, in a very trivial way).

This was reported in [#2473](https://github.com/gin-gonic/gin/issues/2473) with a fix at [#2474](https://github.com/gin-gonic/gin/pull/2474). That PR did not get merged, and the one that did ([#2632](https://github.com/gin-gonic/gin/pull/2632)) does not fix the issue.

There is a fix for this already at [#2844](https://github.com/gin-gonic/gin/pull/2844).

## How to reproduce

You actually have that in your tests already, see [https://github.com/gin-gonic/gin/pull/2844/files#diff-e6ce689a25eaef174c2dd51fe869fabbe04a6c6afbd416b23eda138c82e761baR1432](https://github.com/gin-gonic/gin/pull/2844/files#diff-e6ce689a25eaef174c2dd51fe869fabbe04a6c6afbd416b23eda138c82e761baR1432)

But here's a standalone version

package main

import (
	"fmt"
	"net/http"
	"net/http/httptest"

	"github.com/gin-gonic/gin"
)

func main() {
	r := gin.Default()
	r.TrustedProxies \= \[\]string{"1.1.1.1"}
	r.GET("/", func(c \*gin.Context) { c.String(200, "ClientIP: %s", c.ClientIP()) })
	r.Run("XXXX") // to work around https://github.com/gin-gonic/gin/pull/2692 not being released yet

	req, \_ := http.NewRequest("GET", "/", nil)

	// client IP: 7.7.7.7, as reported by 6.6.6.6 (which is untrusted)
	// all of this proxied through 1.1.1.1 (which is trusted)
	req.Header.Set("X-Forwarded-For", "7.7.7.7, 6.6.6.6")
	req.RemoteAddr \= "1.1.1.1:1234"

	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	// This should print 6.6.6.6, which is the last IP a trusted proxy
	// actually connected to. But it prints 7.7.7.7, which can be spoofed
	// by the completly untrusted 6.6.6.6
	fmt.Println(w.Body.String())
}

## Expectations

    $ go run main.go
    ClientIP: 6.6.6.6
    

## Actual result

    $ go run main.go
    ClientIP: 7.7.7.7
    

## Environment

-   go version: 1.17
-   gin version (or commit ref): 1.7.4
-   operating system: macOS