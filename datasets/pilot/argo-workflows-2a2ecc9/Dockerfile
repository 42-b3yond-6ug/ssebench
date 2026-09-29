ARG SSEBENCH_REGISTRY=ghcr.io/42-b3yond-6ug/ssebench
FROM ${SSEBENCH_REGISTRY}/base-generic-go:1.0.0

WORKDIR /src/argo-workflows

ENV GOPATH="/go"
ENV PATH="$GOPATH/bin:/usr/local/go/bin:$PATH"
ENV GOFLAGS="-mod=vendor"

RUN apt-get update && \
    apt-get install -y python3 python3-yaml && \
    rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/argoproj/argo-workflows.git /src/argo-workflows && \
    cd /src/argo-workflows && \
    git checkout 7bf825bfcdcd894ba12ef160cd9913a26844d6b6 && \
    # [FIX] Inject dummy static assets to bypass UI build requirements
    echo 'package static\n\nimport "net/http"\n\nconst Hash = "dummy"\nfunc ServeHTTP(w http.ResponseWriter, r *http.Request) {}' > server/static/dummy_assets.go && \
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
    go mod init poc-argo && \
    go mod edit -replace github.com/argoproj/argo-workflows/v3=/src/argo-workflows && \
    go mod tidy

RUN chmod +x /ssebench/scripts/*.sh
