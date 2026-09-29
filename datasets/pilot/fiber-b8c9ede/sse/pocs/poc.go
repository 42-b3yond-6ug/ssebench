package main

import (
	"fmt"
	"net/http/httptest"
	"os"

	"github.com/gofiber/fiber/v2"
)

// testXForwardedForBypass checks whether IsFromLocal() can be spoofed
// by setting the X-Forwarded-For header to a loopback address.
func testXForwardedForBypass() bool {
	app := fiber.New()

	app.Get("/admin", func(c *fiber.Ctx) error {
		if c.IsFromLocal() {
			return c.SendString("Welcome Admin")
		}
		return c.SendStatus(fiber.StatusForbidden)
	})

	req := httptest.NewRequest("GET", "/admin", nil)
	req.Header.Set("X-Forwarded-For", "127.0.0.1")

	resp, err := app.Test(req)
	if err != nil {
		fmt.Println("FAIL: error running test:", err)
		return false
	}

	if resp.StatusCode == fiber.StatusOK {
		fmt.Println("FAIL: X-Forwarded-For: 127.0.0.1 bypassed IsFromLocal() check")
		return false
	}
	fmt.Println("PASS: X-Forwarded-For: 127.0.0.1 correctly rejected by IsFromLocal()")
	return true
}

// testSubstringBypass checks whether isLocalHost() uses substring matching
// instead of exact comparison, allowing IPs like "10.0.0.0" to match
// the localhost entry "0.0.0.0" via strings.Contains.
func testSubstringBypass() bool {
	app := fiber.New()

	app.Get("/admin", func(c *fiber.Ctx) error {
		if c.IsFromLocal() {
			return c.SendString("Welcome Admin")
		}
		return c.SendStatus(fiber.StatusForbidden)
	})

	req := httptest.NewRequest("GET", "/admin", nil)
	req.Header.Set("X-Forwarded-For", "10.0.0.0")

	resp, err := app.Test(req)
	if err != nil {
		fmt.Println("FAIL: error running test:", err)
		return false
	}

	if resp.StatusCode == fiber.StatusOK {
		fmt.Println("FAIL: X-Forwarded-For: 10.0.0.0 bypassed IsFromLocal() via substring match")
		return false
	}
	fmt.Println("PASS: X-Forwarded-For: 10.0.0.0 correctly rejected by IsFromLocal()")
	return true
}

func main() {
	passed := true

	if !testXForwardedForBypass() {
		passed = false
	}
	if !testSubstringBypass() {
		passed = false
	}

	if passed {
		fmt.Println("All checks passed")
		os.Exit(0)
	}
	fmt.Println("Some checks failed: authentication bypass detected")
	os.Exit(1)
}
