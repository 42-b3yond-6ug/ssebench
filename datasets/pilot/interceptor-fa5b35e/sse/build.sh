#!/bin/bash
set -euo pipefail


if [ -d "/src/interceptor/internal/rtpbuffer" ]; then
    rm -rf ./public/rtpbuffer
    mkdir -p ./public
    cp -r ./internal/rtpbuffer ./public/
fi

export GOPATH="/go"
export PATH="$GOPATH/bin:/usr/local/go/bin:$PATH"

go build
