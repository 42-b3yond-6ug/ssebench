#!/bin/bash

/ssebench/scripts/build.sh

# Run tests in the relevant package
# We target the package where the vulnerability exists: util/template
go test github.com/argoproj/argo-workflows/v3/util/template/... -v -short -mod=vendor