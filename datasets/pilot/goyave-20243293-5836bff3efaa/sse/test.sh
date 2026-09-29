#!/bin/bash

/ssebench/scripts/build.sh

go test ./... -short -mod=vendor -skip='^TestOpenFileError$|^TestErrors/String|^TestErrors/FileLine'
