ARG SSEBENCH_REGISTRY=ghcr.io/42-b3yond-6ug/ssebench
FROM ${SSEBENCH_REGISTRY}/base-generic-go:1.0.0

WORKDIR /src/dns

ENV GOPATH="/go"
ENV PATH="$GOPATH/bin:/usr/local/go/bin:$PATH"

ENV GOFLAGS="-mod=vendor"

RUN git clone https://github.com/miekg/dns.git /src/dns && \
    cd /src/dns && \
    git checkout 833bf76c282d338e307ff7ec181b95cfc117deb2 && \
    git submodule update --init --recursive && \
    git config --global user.name "tmp" && \
    git config --global user.email "tmp@example.com" && \
    rm -rf .git && git init && echo "/vendor/" >> .gitignore && git add --all && git commit -m "buggy commit" && \
    \
    (test -f go.mod || go mod init github.com/miekg/dns) && \
    sed -i '/^go /d' go.mod && \
    printf "\ngo 1.22\n" >> go.mod && \
    \
    GOFLAGS="-mod=mod" go get \
      golang.org/x/crypto@v0.6.0 \
      golang.org/x/net@v0.8.0 \
      golang.org/x/sync@v0.1.0 \
      golang.org/x/sys@v0.12.0 && \
    GOFLAGS="-mod=mod" go mod tidy && \
    \
    GOFLAGS="-mod=mod" go mod download && \
    GOFLAGS="-mod=mod" go mod vendor && \
    go mod verify

COPY sse/config.yaml /ssebench/config.yaml
COPY sse/build.sh /ssebench/scripts/build.sh
COPY sse/run.sh /ssebench/scripts/run.sh
COPY sse/test.sh /ssebench/scripts/test.sh
COPY sse/diffs /ssebench/diffs
COPY sse/pocs /ssebench/pocs
COPY sse/reports /ssebench/reports

RUN cd /ssebench/pocs && \
    go mod init poc-dns && \
    go mod edit -replace github.com/miekg/dns=/src/dns && \
    go mod tidy

RUN chmod +x /ssebench/scripts/*.sh
