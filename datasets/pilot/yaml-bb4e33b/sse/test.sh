#!/bin/bash

/ssebench/scripts/build.sh

go test ./... -mod=vendor -timeout 10s