#!/bin/bash

/ssebench/scripts/build.sh

cd /src/shoutrrr
go test ./... -short -mod=vendor