ARG SSEBENCH_REGISTRY=ghcr.io/42-b3yond-6ug/ssebench
FROM ${SSEBENCH_REGISTRY}/base-generic-go:1.0.0

WORKDIR /src/aws-iam-authenticator

ENV GOPATH="/go"
ENV PATH="$GOPATH/bin:/usr/local/go/bin:$PATH"
ENV GOFLAGS="-mod=vendor"

RUN git clone https://github.com/kubernetes-sigs/aws-iam-authenticator.git /src/aws-iam-authenticator && \
    cd /src/aws-iam-authenticator && \
    git checkout 0a72c12090fb71ebefbc5036dc1b548b123a91a6 && \
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
    go mod init poc-authenticator && \
    go mod edit -replace sigs.k8s.io/aws-iam-authenticator=/src/aws-iam-authenticator && \
    go mod tidy

RUN chmod +x /ssebench/scripts/*.sh