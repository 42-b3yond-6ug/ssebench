#!/bin/bash

/ssebench/scripts/build.sh

go test ./pkg/token/... -mod=vendor