# Build from the repository root, so the dataset is in the context and its
# catalog is generated into the image:
#   docker build -f catalog/Dockerfile .
# catalog/Dockerfile.dockerignore trims the context to the files read here.
FROM golang:1.25-alpine AS build

WORKDIR /src/catalog
COPY catalog/go.mod catalog/go.sum ./
RUN go mod download
COPY catalog/ ./
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/ssebench-catalog ./cmd/ssebench-catalog

ARG DATASET=pilot
ARG SSEBENCH_REGISTRY=ghcr.io/42-b3yond-6ug/ssebench
COPY datasets/${DATASET}/ /src/datasets/${DATASET}/
RUN /out/ssebench-catalog generate --dataset "${DATASET}" --output /out/catalog.json "/src/datasets/${DATASET}"

FROM alpine:3.22

COPY --from=build /out/ssebench-catalog /usr/local/bin/
COPY --from=build /out/catalog.json /srv/catalog.json

ENV SSEBENCH_CATALOG_FILE=/srv/catalog.json \
    SSEBENCH_CATALOG_PORT=8080
USER nobody
EXPOSE 8080
ENTRYPOINT ["ssebench-catalog"]
CMD ["serve"]
