#!/bin/bash

/ssebench/scripts/build.sh

PACKAGES=$(go list ./... | grep -v "github.com/open-policy-agent/opa/cmd$" | grep -v "github.com/open-policy-agent/opa/v1/runtime$" | grep -v "github.com/open-policy-agent/opa/v1/plugins/rest$")

go test $PACKAGES -short -mod=vendor -skip "TestCertPoolReloading|TestCertReloading"