#!/bin/bash

/ssebench/scripts/build.sh

go test ./... -short -mod=vendor -skip "TestSPRejectsMalformedResponse|TestGetSPMetadata|TestFetchMetadataRejectsInvalid"