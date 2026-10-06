# The web UI: the client, the API server, the terminal helper (pty-proxy), the
# ssebench CLI with its Kubernetes client, and the docker and kubectl CLIs. Build from the repository root:
#
#   docker buildx build -f webui/Dockerfile --build-arg VERSION="$(cat VERSION)" -t ssebench-webui .
#
# The server finds and reaches runs through `ssebench runs`, which uses the
# Docker backend unless SSEBENCH_BACKEND says otherwise. That backend manages the
# run containers of the Docker daemon it talks to, so it needs that daemon's
# socket, and it reaches the SSEBench daemon in each run container by the
# container's IP address. Run it on the host network with the socket mounted:
#
#   docker run --rm --network host -v /var/run/docker.sock:/var/run/docker.sock ssebench-webui
#
# On Kubernetes, SSEBENCH_BACKEND=kubernetes needs neither the socket nor the
# host network; see deploy/helm/ssebench.
#
# Most build steps run on the build platform, so a multi-platform build needs
# little emulation; the CLI is pure Python and installs on the target platform.

FROM --platform=$BUILDPLATFORM oven/bun:1.4.2 AS web
WORKDIR /src
COPY package.json bun.lock bunfig.toml ./
COPY webui/package.json webui/
COPY docs/package.json docs/
RUN bun install --frozen-lockfile --filter ssebench-webui
COPY webui/ webui/
RUN bun run --cwd webui build && \
    bun build webui/server/index.ts --target=bun --outfile=/out/server/index.js


FROM --platform=$BUILDPLATFORM golang:1.27-alpine AS pty-proxy
WORKDIR /build
COPY webui/pty-proxy/go.mod webui/pty-proxy/go.sum ./
RUN go mod download
COPY webui/pty-proxy/ ./
ARG TARGETOS TARGETARCH VERSION=dev
RUN CGO_ENABLED=0 GOOS=$TARGETOS GOARCH=$TARGETARCH \
    go build -trimpath -ldflags="-s -w -X main.version=${VERSION}" -o /pty-proxy .


FROM ghcr.io/astral-sh/uv:0.12.23@sha256:61d393e44e249f2e4b526b6c7ddcecce245946826e608e11c93ad4f5bba55b21 AS uv


# The uv of the build platform: the target's uv would run under emulation and
# fetch a Python for the target, which the build stage cannot run.
FROM --platform=$BUILDPLATFORM ghcr.io/astral-sh/uv:0.12.23@sha256:61d393e44e249f2e4b526b6c7ddcecce245946826e608e11c93ad4f5bba55b21 AS build-uv


FROM --platform=$BUILDPLATFORM oven/bun:1.4.2-slim AS cli-wheel
# The wheel of the CLI carries the assets it needs (see bench/hatch_build.py).
COPY --from=build-uv /uv /usr/local/bin/uv
WORKDIR /repo
COPY . .
RUN uv build --package ssebench --wheel --out-dir /wheel


FROM docker:29.8.2-cli AS docker-cli


FROM registry.k8s.io/kubectl:v1.37.1@sha256:b7cab618e281b1ee7484e7b706a96e2135fbb6e072c2a573a7dab4e87d7f2385 AS kubectl


FROM oven/bun:1.4.2-slim
COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker
# `ssebench runs endpoint` and `runs exec` run kubectl on the Kubernetes backend.
COPY --from=kubectl /bin/kubectl /usr/local/bin/kubectl
# The ssebench CLI, in an environment of its own with its own Python, at
# /usr/local/bin/ssebench. The kubernetes extra is the Python client of the
# Kubernetes backend.
COPY --from=uv /uv /usr/local/bin/uv
COPY --from=cli-wheel /wheel/ /tmp/wheel/
RUN UV_TOOL_DIR=/opt/ssebench/tool UV_TOOL_BIN_DIR=/usr/local/bin \
    UV_PYTHON_INSTALL_DIR=/opt/ssebench/python \
    uv tool install --python 3.12 "ssebench[kubernetes] @ file://$(ls /tmp/wheel/*.whl)" && \
    rm -rf /tmp/wheel /root/.cache/uv
# The server serves ./dist and runs ../pty-proxy/pty-proxy relative to its own
# directory.
WORKDIR /app
COPY --from=web /src/webui/dist/ dist/
COPY --from=web /out/server/ server/
COPY --from=pty-proxy /pty-proxy pty-proxy/pty-proxy
# The launch wizard lists the models and agents by reading these directories.
COPY models/ models/
COPY agents/ agents/
# Runs as root: whoever can use the Docker socket is root on its host anyway,
# and the socket's group differs between hosts.
# The CLI runs in /app, so its results/ is /app/results.
ENV PORT=3001 \
    SSEBENCH_CLI=ssebench \
    SSEBENCH_PATH=/app
EXPOSE 3001
CMD ["bun", "server/index.js"]
