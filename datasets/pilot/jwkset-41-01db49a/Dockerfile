ARG SSEBENCH_REGISTRY=ghcr.io/42-b3yond-6ug/ssebench
FROM ${SSEBENCH_REGISTRY}/base-generic-go:latest

WORKDIR /src/jwkset

ENV GOPATH="/go"
ENV PATH="$GOPATH/bin:/usr/local/go/bin:$PATH"

ENV GOFLAGS="-mod=vendor"

RUN git clone https://github.com/MicahParks/jwkset.git /src/jwkset && \
    cd /src/jwkset && \
    git checkout ce57ded280d99191ea54e3c4c5460c58207c3bbf && \
    git submodule update --init --recursive && \
    git config --global user.name "tmp" && \
    git config --global user.email "tmp@example.com" && \
    rm -rf .git && git init && echo "/vendor/" >> .gitignore && git add --all && git commit -m "buggy commit" && \
    go mod download && \
    go mod vendor && \
    go mod verify

COPY sse/config.yaml /ssebench/config.yaml
COPY sse/build.sh /ssebench/scripts/build.sh
COPY sse/run.sh /ssebench/scripts/run.sh
COPY sse/test.sh /ssebench/scripts/test.sh
COPY sse/diffs /ssebench/diffs
COPY sse/pocs /ssebench/pocs
COPY sse/reports /ssebench/reports

RUN cd /ssebench/pocs && \
    go mod init poc-jwkset && \
    go mod edit -replace github.com/MicahParks/jwkset=/src/jwkset && \
    go mod tidy

RUN chmod +x /ssebench/scripts/*.sh
