#!/bin/bash
set -euo pipefail

export GOPATH="/go"
export PATH="$GOPATH/bin:/usr/local/go/bin:$PATH"

# Only build the package relevant to the vulnerability to avoid external dependency issues (like UI assets)
go build -mod=vendor github.com/argoproj/argo-workflows/v3/util/template/...