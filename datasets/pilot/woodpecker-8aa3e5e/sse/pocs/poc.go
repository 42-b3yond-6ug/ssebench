package main

import (
	"fmt"
	"strings"
	"os"

	"go.woodpecker-ci.org/woodpecker/v2/pipeline/frontend/yaml"
	"go.woodpecker-ci.org/woodpecker/v2/pipeline/frontend/yaml/linter"
)

func main() {
	maliciousYaml := []byte(`
steps:
  - name: publish
    image: plugins/docker
    settings:
      repo: foo/bar
      tags: latest
    environment:
      LD_PRELOAD: /tmp/malicious.so
`)
	workflow, err := yaml.ParseBytes(maliciousYaml)
	if err != nil {
		return
	}
	l := linter.New(linter.WithTrusted(false))
	lintConfigs := []*linter.WorkflowConfig{
		{
			File:     "poc.yaml",
			Workflow: workflow,
		},
	}
	err = l.Lint(lintConfigs)

	if err != nil {
		errStr := err.Error()
		if strings.Contains(errStr, "Cannot configure both environment and settings") {
			fmt.Printf("FIXED: Linter correctly blocked the exploit.\nDetails: %v\n", err)
			os.Exit(0)
		} else {
			fmt.Printf("VULNERABLE: The specific protection error was NOT found (ignored unrelated errors).\nActual Error: %v\n", err)
			os.Exit(1)
		}
	}
}