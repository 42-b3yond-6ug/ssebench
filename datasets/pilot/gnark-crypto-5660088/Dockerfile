ARG SSEBENCH_REGISTRY=ghcr.io/42-b3yond-6ug/ssebench
FROM ${SSEBENCH_REGISTRY}/base-generic-go:1.0.0

WORKDIR /src/gnark-crypto

ENV GOPATH="/go"
ENV PATH="$GOPATH/bin:/usr/local/go/bin:$PATH"
ENV GOFLAGS="-mod=vendor"

RUN git clone https://github.com/Consensys/gnark-crypto.git /src/gnark-crypto && \
    cd /src/gnark-crypto && \
    git checkout 1873045cbd7d0e690a74c0c30c4a00335776de5f && \
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
    go mod init poc-gnark-crypto && \
    go mod edit -replace github.com/Consensys/gnark-crypto=/src/gnark-crypto && \
    GOFLAGS="" go mod tidy && \
    go mod edit -toolchain=$(cd /src/gnark-crypto && grep '^toolchain ' go.mod | awk '{print $2}')

RUN chmod +x /ssebench/scripts/*.sh
