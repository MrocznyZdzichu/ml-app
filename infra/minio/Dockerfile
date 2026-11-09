FROM golang:1.24.8-alpine AS build

RUN CGO_ENABLED=0 go install -p 2 github.com/minio/minio@RELEASE.2025-10-15T17-29-55Z

FROM alpine:3.22

RUN apk add --no-cache ca-certificates
COPY --from=build /go/bin/minio /usr/local/bin/minio

ENTRYPOINT ["minio"]
