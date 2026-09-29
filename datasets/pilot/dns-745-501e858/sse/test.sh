#!/bin/bash

/ssebench/scripts/build.sh

grep -q '^//go:build !skip_msg' msg_test.go || \
sed -i '1i\//go:build !skip_msg\n// +build !skip_msg\n' msg_test.go

go test -tags skip_msg ./... -short -mod=mod -skip "TestDoHExchange|TestClientRemote|TestTCPRtt"
