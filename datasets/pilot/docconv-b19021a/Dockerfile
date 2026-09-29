ARG SSEBENCH_REGISTRY=ghcr.io/42-b3yond-6ug/ssebench
FROM ${SSEBENCH_REGISTRY}/base-generic-go:1.0.0

WORKDIR /src/docconv

ENV GOPATH="/go"
ENV PATH="$GOPATH/bin:/usr/local/go/bin:$PATH"
ENV GOFLAGS="-mod=vendor"

RUN apt-get update && \
    apt-get install -y poppler-utils libleptonica-dev libtesseract-dev tesseract-ocr && \
    rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/sajari/docconv.git /src/docconv && \
    cd /src/docconv && \
    git checkout 44d673994791482c8aec902e0f949c354ce8dc0f && \
    git config --global user.name "tmp" && \
    git config --global user.email "tmp@example.com" && \
    rm -rf .git && git init && echo "/vendor/" >> .gitignore && git add --all && git commit -m "buggy commit" && \
    go mod download && \
    go mod vendor && \
    go mod verify

# Copy config file
COPY sse/config.yaml /ssebench/config.yaml
# Copy interaction scripts
COPY sse/build.sh /ssebench/scripts/build.sh
COPY sse/run.sh /ssebench/scripts/run.sh
COPY sse/test.sh /ssebench/scripts/test.sh
# Copy related files
COPY sse/diffs /ssebench/diffs
COPY sse/pocs /ssebench/pocs
COPY sse/reports /ssebench/reports

RUN cd /ssebench/pocs && \
    go mod init poc-docconv && \
    go mod edit -replace github.com/sajari/docconv=/src/docconv && \
    go mod tidy

RUN chmod +x /ssebench/scripts/*.sh