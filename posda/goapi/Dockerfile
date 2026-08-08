FROM golang:1.26 AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /posda-api ./cmd/posda-api

# The runtime stage uses the posda image because the DICOM dump and
# report-macro endpoints shell out to the perl tooling it provides
# (IheDumpFile.pl, dciodvfymacro, phimacro) via the mounted posdatools.
FROM tcia/posda:1.0.4
COPY dump_dicom.sh /fastapi/dump_dicom.sh
COPY --from=build /posda-api /usr/local/bin/posda-api
ENTRYPOINT ["/usr/local/bin/posda-api"]
CMD []
