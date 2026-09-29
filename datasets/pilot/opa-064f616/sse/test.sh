#!/bin/bash

/ssebench/scripts/build.sh

SKIP_TESTS="TestJSONSerialization|TestClientCert|TestTopdownJWTEncodeSignECWithSeedReturnsSameSignature"

go test ./... -short -mod=vendor -skip "$SKIP_TESTS"