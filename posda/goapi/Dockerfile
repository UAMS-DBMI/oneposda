FROM golang:1.26 AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /posda-api ./cmd/posda-api

FROM debian:bookworm-slim
# The DICOM dump endpoint shells out to this script, which in turn
# expects the posdatools perl code to be available (mounted or baked
# in), exactly like the Python image.
COPY dump_dicom.sh /fastapi/dump_dicom.sh
COPY --from=build /posda-api /usr/local/bin/posda-api
CMD ["posda-api"]
