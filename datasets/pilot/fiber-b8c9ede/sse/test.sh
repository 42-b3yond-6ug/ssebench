#!/bin/bash

/ssebench/scripts/build.sh

SKIP_TESTS="Test_Idempotency|Test_Limiter.*|Test_Sliding_Window|Test_Proxy_Do.*|Test_Logger_WithLatency_DefaultFormat|Test_Session_Save_Expiration|Test_Ctx_IsFromLocal$|Test_Memory|Test_Cache_Expired|Test_CustomExpiration|Test_Client_Agent_TLS"

go test ./... -short -mod=vendor -skip "$SKIP_TESTS"