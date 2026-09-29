#!/bin/bash
set -euo pipefail

/ssebench/scripts/build.sh

export GOFLAGS=""

TARGET_PACKAGES=(
    "k8s.io/cli-runtime/pkg/printers"
    "k8s.io/kubectl/pkg/cmd/events"
    "k8s.io/kubectl/pkg/cmd/get"
    "k8s.io/kubectl/pkg/describe"
)

go test -v -short -count=1 -mod=mod "${TARGET_PACKAGES[@]}"