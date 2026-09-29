#!/bin/bash

/ssebench/scripts/build.sh

go list ./pipeline/... | \
  grep -v "pipeline/log" | \
  grep -v "pipeline/backend/dummy" | \
  xargs go test -short -mod=vendor