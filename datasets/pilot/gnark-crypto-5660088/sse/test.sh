#!/bin/bash

/ssebench/scripts/build.sh
PACKAGES=$(go list ./... | grep -v "ecc/bls12-377/fr/fft" | grep -v "ecc/bls24-315/fr/fft")

go test $PACKAGES -short -mod=vendor -skip "TestIntegration"