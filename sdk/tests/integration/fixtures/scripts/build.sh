#!/bin/bash
set -e

cd /src/buggy
go mod tidy

cd /ssebench/pocs
rm -f go.mod go.sum
go mod init poc-buggy
go mod edit -replace buggy=/src/buggy
go mod tidy
