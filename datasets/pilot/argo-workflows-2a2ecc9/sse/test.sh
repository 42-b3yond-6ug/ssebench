#!/bin/bash

/ssebench/scripts/build.sh

# The fix makes Replace take a JSON document, and upstream rewrote these tests to
# match; the intent tests run the rewritten versions. While the tests still call
# Replace with a bare template, they check the old behaviour, so they are skipped.
SKIP='^$'
if grep -qF 'Replace("{{foo}}"' util/template/replace_test.go; then
    SKIP='^(Test_Replace|TestNestedReplaceString|TestReplaceStringWithWhiteSpace)$'
fi

# Run tests in the relevant package
# We target the package where the vulnerability exists: util/template
go test github.com/argoproj/argo-workflows/v3/util/template/... -v -short -mod=vendor -skip "$SKIP"
