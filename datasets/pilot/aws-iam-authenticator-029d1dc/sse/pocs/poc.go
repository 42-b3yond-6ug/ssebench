package main

import (
	"encoding/base64"
	"fmt"
	"strings"
	"os"

	"sigs.k8s.io/aws-iam-authenticator/pkg/token"
)
func toToken(url string) string {
	return "k8s-aws-v1." + base64.RawURLEncoding.EncodeToString([]byte(url))
}

func main() {
	maliciousURL := "https://sts.us-west-2.amazonaws.com/?" +
		"Action=GetCallerIdentity&" +
		"Version=2011-06-15&" +
		"X-Amz-Algorithm=AWS4-HMAC-SHA256&" +
		"X-Amz-Credential=ASIAVALIDKEY%2F20220601%2Fus-west-2%2Fsts%2Faws4_request&" + 
		"x-amz-credential=ASIAEVILKEY%2F20220601%2Fus-west-2%2Fsts%2Faws4_request&" + 
		"X-Amz-Date=20220601T000000Z&" +
		"X-Amz-Expires=900&" +
		"X-Amz-Security-Token=XXXXXXXXXXXXX&" +
		"X-Amz-SignedHeaders=host%3Bx-k8s-aws-id&" +
		"X-Amz-Signature=999999999999999999"

	maliciousToken := toToken(maliciousURL)
	verifier := token.NewVerifier("test-cluster", "aws")
	_, err := verifier.Verify(maliciousToken)
	if err != nil {
		if strings.Contains(err.Error(), "duplicate query parameter found") {
			fmt.Printf("Blocked by Sanitizer (PATCHED): %v\n", err)
			os.Exit(0)
		}
		fmt.Printf("VULNERABLE (Bypassed duplicate check, failed on signature): %v\n", err)
		os.Exit(1)
	} 
}