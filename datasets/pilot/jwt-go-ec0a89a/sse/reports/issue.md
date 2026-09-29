if m["aud"] happens to be []string{}, as allowed by the spec, the type assertion fails and the value of aud is "". This can cause audience verification to succeed even if the audiences being passed are incorrect if required is set to false.
https://github.com/dgrijalva/jwt-go/blob/master/map_claims.go#L16
// Compares the aud claim against cmp.// If required is false, this method will return true if the value matches or is unsetfunc (m MapClaims) VerifyAudience(cmp string, req bool) bool {
	aud, _ := m["aud"].(string)
	return verifyAud(aud, cmp, req)
}

https://play.golang.org/p/Pnvvqfehl9K