#!/bin/bash
set -e

cd /src/buggy
go test ./... -v
