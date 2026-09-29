#!/bin/bash

/ssebench/scripts/build.sh

if [ -d "testdata" ] && [ ! -d "testapp" ]; then
    cp -r testdata testapp
    grep -rl "github.com/revel/revel/testdata" . | xargs -r sed -i 's|github.com/revel/revel/testdata|github.com/revel/revel/testapp|g'
fi

SKIP_LIST="TestBenchmarkCompressed|TestSetAction|TestRedirect|TestCookieSessionExpire|TestBenchmarkRender|TestComputeRoute|TestFakeServer|TestOnAppStart|TestOnAppStop|TestContentTypeByFilename|TestValidateMessageKey|TestMemcachedCache|TestRedisCache|TestGetCustom|TestInMemoryCache_Replace|TestBinder"

go test ./... -short -mod=vendor -vet=off -skip "$SKIP_LIST"