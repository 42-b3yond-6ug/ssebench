package main

import (
	"fmt"
	"io/ioutil"
	"os"

	"gopkg.in/yaml.v2"
)

type PolicyRule struct {
	Verbs         []string `yaml:"verbs"`
	APIGroups     []string `yaml:"apiGroups"`
	Resources     []string `yaml:"resources"`
	ResourceNames []string `yaml:"resourceNames,omitempty"`
}

type ClusterRole struct {
	Kind  string       `yaml:"kind"`
	Rules []PolicyRule `yaml:"rules"`
}

func main() {
	targetFile := "/src/submariner-operator/config/rbac/submariner-operator/cluster_role.yaml"

	data, err := ioutil.ReadFile(targetFile)
	if err != nil {
		fmt.Printf("Error reading file: %v\n", err)
		os.Exit(1)
	}

	var role ClusterRole
	err = yaml.Unmarshal(data, &role)
	if err != nil {
		fmt.Printf("Error parsing YAML: %v\n", err)
		os.Exit(1)
	}

	vulnerable := false
	for _, rule := range role.Rules {
		hasClusterRoles := false
		for _, res := range rule.Resources {
			if res == "clusterroles" || res == "*" {
				hasClusterRoles = true
				break
			}
		}
		hasDelete := false
		for _, verb := range rule.Verbs {
			if verb == "delete" || verb == "*" {
				hasDelete = true
				break
			}
		}

		if hasClusterRoles && hasDelete {
			if len(rule.ResourceNames) == 0 {
				vulnerable = true
				break
			}
		}
	}

	if vulnerable {
		fmt.Println("Vulnerability successfully reproduced")
		os.Exit(1)
	} else {
		fmt.Println("Vulnerability reproduction failed")
		os.Exit(0)
	}
}