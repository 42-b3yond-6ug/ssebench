# Build from the repository root, so that the dataset manifest is in the
# context:
#   docker build -f catalog/Dockerfile --build-arg VERSION="$(cat VERSION)" .
# catalog/Dockerfile.dockerignore trims the context to the files read here.
# The binary is cross-compiled on the build platform, so a multi-platform build
# needs no emulation.
FROM --platform=$BUILDPLATFORM golang:1.26-alpine AS build

WORKDIR /src/catalog
COPY catalog/go.mod catalog/go.sum ./
RUN go mod download
COPY catalog/ ./
ARG TARGETOS TARGETARCH VERSION=dev
RUN CGO_ENABLED=0 GOOS=$TARGETOS GOARCH=$TARGETARCH go build -trimpath -ldflags="-s -w -X main.version=${VERSION}" -o /out/ssebench-catalog ./cmd/ssebench-catalog

FROM alpine:3.22

ARG DATASET=pilot
COPY --from=build /out/ssebench-catalog /usr/local/bin/
# The images lock is optional: a dataset without published images has none. The
# service reads it from next to the manifest.
COPY datasets/${DATASET}/manifest.json datasets/${DATASET}/images.lock.jso[n] /srv/

ENV SSEBENCH_MANIFEST=/srv/manifest.json \
    SSEBENCH_CATALOG_PORT=8080
USER nobody
EXPOSE 8080
ENTRYPOINT ["ssebench-catalog"]
CMD ["serve"]
