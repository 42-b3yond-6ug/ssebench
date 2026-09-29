package main

import (
	"fmt"
	"os"
	"github.com/dgrijalva/jwt-go"
)

func main() {
	claims := jwt.MapClaims{
		"aud": []string{"admin"}, 
	}
	targetAudience := "user"
	required := false 

	if claims.VerifyAudience(targetAudience, required) {
		fmt.Printf("Vulnerability Reproduced: Verified audience '%s' against claim %v unexpectedly!\n", targetAudience, claims["aud"])
		os.Exit(1)
	} else {
		fmt.Println("Verification failed as expected (not vulnerable).")
		os.Exit(0)
	}
}