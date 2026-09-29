package main

import (
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"reflect"
	"time"

	"github.com/gin-gonic/gin"
)

func main() {
	gin.SetMode(gin.ReleaseMode)
	r := gin.New()
	v := reflect.ValueOf(r).Elem()
	f := v.FieldByName("TrustedProxies")
	if f.IsValid() && f.CanSet() {
		f.Set(reflect.ValueOf([]string{}))
	}

	r.GET("/", func(c *gin.Context) {
		ip := c.ClientIP()
		c.String(200, ip)
	})

	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		panic(err)
	}
	port := listener.Addr().(*net.TCPAddr).Port
	serverURL := fmt.Sprintf("http://127.0.0.1:%d/", port)

	go func() {
		if err := http.Serve(listener, r); err != nil && err != http.ErrServerClosed {
			panic(err)
		}
	}()

	time.Sleep(100 * time.Millisecond)
	client := &http.Client{}
	req, _ := http.NewRequest("GET", serverURL, nil)
	req.Header.Set("X-Forwarded-For", "8.8.8.8")
	resp, _ := client.Do(req)
	
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	detectedIP := string(body)

	if detectedIP == "8.8.8.8" {
		fmt.Println("Result: Vulnerable (Spoofing succeeded)")
		os.Exit(1)
	} else if detectedIP == "127.0.0.1" {
		fmt.Println("Result: Secure (Spoofing blocked, showed real IP)")
		os.Exit(0)
	}
}