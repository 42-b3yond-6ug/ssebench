# Build from the repository root, so that the dataset manifest is in the
# context:
#   docker build -f catalog/Dockerfile --build-arg VERSION="$(cat VERSION)" .
# catalog/Dockerfile.dockerignore trims the context to the files read here.
FROM golang:1.26-alpine AS build

WORKDIR /src/catalog
COPY catalog/go.mod catalog/go.sum ./
RUN go mod download
COPY catalog/ ./
ARG VERSION=dev
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w -X main.version=${VERSION}" -o /out/ssebench-catalog ./cmd/ssebench-catalog

FROM alpine:3.22

ARG DATASET=pilot
COPY --from=build /out/ssebench-catalog /usr/local/bin/
COPY datasets/${DATASET}/manifest.json /srv/manifest.json

ENV SSEBENCH_MANIFEST=/srv/manifest.json \
    SSEBENCH_CATALOG_PORT=8080
USER nobody
EXPOSE 8080
ENTRYPOINT ["ssebench-catalog"]
CMD ["serve"]
