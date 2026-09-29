#!/bin/bash

/ssebench/scripts/build.sh

rm -f ./foo

go test ./... -short -mod=vendor -tags ocr -skip "TestConvertHTML_readabilityUseClasses|TestConvertRTF"