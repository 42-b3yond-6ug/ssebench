#!/bin/bash

/ssebench/scripts/build.sh

go list -mod=vendor ./... | grep -v "test/e2e" | xargs go test -v -short -mod=vendor