# The web UI: the client, the API server, the terminal helper (pty-proxy) and
# the docker CLI that the server runs. Build from the repository root:
#
#   docker buildx build -f webui/Dockerfile --build-arg VERSION="$(cat VERSION)" -t ssebench-webui .
#
# The server manages the run containers of the Docker daemon it talks to, so
# it needs that daemon's socket, and it reaches the SSEBench daemon in each run
# container by the container's IP address. Run it on the host network with the
# socket mounted:
#
#   docker run --rm --network host -v /var/run/docker.sock:/var/run/docker.sock ssebench-webui
#
# Every build step runs on the build platform, so a multi-platform build needs
# no emulation.

FROM --platform=$BUILDPLATFORM oven/bun:1.3.13 AS web
WORKDIR /src
COPY package.json bun.lock bunfig.toml ./
COPY webui/package.json webui/
COPY docs/package.json docs/
RUN bun install --frozen-lockfile --filter ssebench-webui
COPY webui/ webui/
RUN bun run --cwd webui build && \
    bun build webui/server/index.ts --target=bun --outfile=/out/server/index.js


FROM --platform=$BUILDPLATFORM golang:1.26-alpine AS pty-proxy
WORKDIR /build
COPY webui/pty-proxy/go.mod webui/pty-proxy/go.sum ./
RUN go mod download
COPY webui/pty-proxy/ ./
ARG TARGETOS TARGETARCH VERSION=dev
RUN CGO_ENABLED=0 GOOS=$TARGETOS GOARCH=$TARGETARCH \
    go build -trimpath -ldflags="-s -w -X main.version=${VERSION}" -o /pty-proxy .


FROM docker:29.8.1-cli AS docker-cli


FROM oven/bun:1.3.13-slim
COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker
# The server serves ./dist and runs ../pty-proxy/pty-proxy relative to its own
# directory.
WORKDIR /app
COPY --from=web /src/webui/dist/ dist/
COPY --from=web /out/server/ server/
COPY --from=pty-proxy /pty-proxy pty-proxy/pty-proxy
# Runs as root: whoever can use the Docker socket is root on its host anyway,
# and the socket's group differs between hosts.
ENV PORT=3001
EXPOSE 3001
CMD ["bun", "server/index.js"]
