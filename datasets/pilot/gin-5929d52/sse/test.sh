#!/bin/bash
/ssebench/scripts/build.sh

# The fix changes which address ClientIP returns when only the remote address is
# trusted, and upstream changed TestContextClientIP to match; the intent tests
# run the changed version. While the test still expects the old address, it is
# skipped.
SKIP='TestContextFormFileFailed17'
if grep -A1 -F 'SetTrustedProxies([]string{"40.40.40.40"})' context_test.go | grep -qF '"20.20.20.20", c.ClientIP()'; then
    SKIP="$SKIP|^TestContextClientIP\$"
fi
go test ./... -short -mod=vendor -skip "$SKIP"
