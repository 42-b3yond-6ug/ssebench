ARG SSEBENCH_REGISTRY=ghcr.io/42-b3yond-6ug/ssebench
FROM ${SSEBENCH_REGISTRY}/base-generic-c:1.0.0

RUN mkdir /src

RUN git clone https://github.com/wireshark/wireshark.git /src/wireshark && \
    cd /src/wireshark && \
    git checkout 10e9024c12ba35fcd213f8b8aa6d68ef9dd802c2 && \
    git submodule update --init --recursive && \
    git config --global user.name "tmp" && \
    git config --global user.email "tmp@example.com" && \
    rm -rf .git && git init && git add --all && git commit -m "buggy commit"

RUN DEBIAN_FRONTEND=noninteractive apt-get update && \
    apt-get install -y \
    build-essential \
    lemon \
    && rm -rf /var/lib/apt/lists/*

RUN sed -i 's/apt-get install /apt-get install -y /' /src/wireshark/tools/debian-setup.sh && \
    DEBIAN_FRONTEND=noninteractive /src/wireshark/tools/debian-setup.sh --install-all

RUN cd /src/wireshark && \
    git restore tools/debian-setup.sh

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
