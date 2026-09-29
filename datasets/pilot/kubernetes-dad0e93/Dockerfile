ARG SSEBENCH_REGISTRY=ghcr.io/42-b3yond-6ug/ssebench
FROM ${SSEBENCH_REGISTRY}/base-generic-go:latest

WORKDIR /src/kubernetes

ENV GOPATH="/go"
ENV PATH="$GOPATH/bin:/usr/local/go/bin:$PATH"
ENV GOFLAGS="-mod=vendor"

RUN git clone https://github.com/kubernetes/kubernetes.git /src/kubernetes && \
    cd /src/kubernetes && \
    git checkout 90f50488c7b1ab810dd98061d196568e61c47adb && \
    git submodule update --init --recursive && \
    go mod download && \
    go mod vendor && \
    git config --global user.name "tmp" && \
    git config --global user.email "tmp@example.com" && \
    rm -rf .git && git init && git add --all && git commit -m "buggy commit"

COPY sse/config.yaml /ssebench/config.yaml
COPY sse/build.sh /ssebench/scripts/build.sh
COPY sse/run.sh /ssebench/scripts/run.sh
COPY sse/test.sh /ssebench/scripts/test.sh
COPY sse/diffs /ssebench/diffs
COPY sse/pocs /ssebench/pocs
COPY sse/reports /ssebench/reports

RUN cd /ssebench/pocs && \
    go mod init poc-kubectl && \
    go mod edit -replace k8s.io/kubectl=/src/kubernetes/staging/src/k8s.io/kubectl && \
    go mod edit -replace k8s.io/cli-runtime=/src/kubernetes/staging/src/k8s.io/cli-runtime && \
    go mod edit -replace k8s.io/apimachinery=/src/kubernetes/staging/src/k8s.io/apimachinery && \
    go mod edit -replace k8s.io/client-go=/src/kubernetes/staging/src/k8s.io/client-go && \
    go mod edit -replace k8s.io/api=/src/kubernetes/staging/src/k8s.io/api && \
    go mod edit -replace k8s.io/code-generator=/src/kubernetes/staging/src/k8s.io/code-generator && \
    go mod edit -replace k8s.io/component-base=/src/kubernetes/staging/src/k8s.io/component-base && \
    go mod edit -replace k8s.io/component-helpers=/src/kubernetes/staging/src/k8s.io/component-helpers && \
    go mod edit -replace k8s.io/metrics=/src/kubernetes/staging/src/k8s.io/metrics && \
    GOFLAGS="" go mod tidy

RUN chmod +x /ssebench/scripts/*.sh
