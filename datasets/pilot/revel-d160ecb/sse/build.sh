#!/bin/bash
set -euo pipefail

export GOPATH="/go"
export PATH="$GOPATH/bin:/usr/local/go/bin:$PATH"

go build