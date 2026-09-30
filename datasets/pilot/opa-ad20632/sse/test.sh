#!/bin/bash
/ssebench/scripts/build.sh

# The fix stops reporting the timer_rego_query_parse_ns metric, and upstream
# removed it from the metrics these tests expect; the intent tests run the
# changed versions. While the tests still expect the metric, they are skipped.
SKIP='TestCertPoolReloading|TestCertReloading'
if grep -A1 -F '"timer_rego_input_parse_ns",' v1/server/server_test.go | grep -qF '"timer_rego_query_parse_ns"'; then
    SKIP="$SKIP|^TestDataMetricsEval\$"
fi
if grep -A1 -F 'compileStageKeys := []string{' v1/test/e2e/metrics/metrics_test.go | grep -qF '"timer_rego_query_parse_ns"'; then
    SKIP="$SKIP|^TestRequestWithInstrumentationV1DataAPI\$"
fi

PACKAGES=$(go list ./... | grep -v "github.com/open-policy-agent/opa/cmd$" | grep -v "github.com/open-policy-agent/opa/v1/runtime$" | grep -v "github.com/open-policy-agent/opa/v1/plugins/rest$")
# Upstream tests such as TestInterQueryCache_ClientError (an http.send that times
# out after 10 ms) and TestGraphQLParseSchemaAlloc (heap growth) fail when other
# parallel tests or a busy host take their time; one at a time they pass.
go test $PACKAGES -short -mod=vendor -parallel 1 -skip "$SKIP"
