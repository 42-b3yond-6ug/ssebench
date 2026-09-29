package main

import (
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"

	"github.com/gin-gonic/gin"
)

func main() {
	gin.SetMode(gin.ReleaseMode)
	r := gin.New()
	r.ForwardedByClientIP = true
	err := r.SetTrustedProxies([]string{"1.1.1.1"})
	if err != nil {
		//Warning: Failed to set trusted proxies:err
	}
	r.GET("/", func(c *gin.Context) {
		c.String(200, c.ClientIP())
	})

	req, _ := http.NewRequest("GET", "/", nil)
	spoofedIP := "7.7.7.7" 
	realIP := "6.6.6.6" 

	req.Header.Set("X-Forwarded-For", fmt.Sprintf("%s, %s", spoofedIP, realIP))

	req.RemoteAddr = "1.1.1.1:1234"

	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	clientIP := w.Body.String()
	fmt.Printf("ClientIP: %s\n", clientIP)
	
	if clientIP == spoofedIP {
		fmt.Println("Vulnerable: ClientIP was spoofed (returned left-most IP).")
		os.Exit(1)
	} else if clientIP == realIP {
		fmt.Println("Safe: ClientIP is correct (returned right-most untrusted IP).")
		os.Exit(0)
	} 
}