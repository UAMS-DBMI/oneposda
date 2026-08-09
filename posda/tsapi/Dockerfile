# Bun runs the TypeScript sources directly; there is no build step.
# The runtime stage uses the posda image because the DICOM dump and
# report-macro endpoints shell out to the perl tooling it provides
# (IheDumpFile.pl, dciodvfymacro, phimacro) via the mounted posdatools.
FROM oven/bun:1.3 AS bun

FROM tcia/posda:1.0.4
COPY --from=bun /usr/local/bin/bun /usr/local/bin/bun
COPY dump_dicom.sh /fastapi/dump_dicom.sh
WORKDIR /tsapi
COPY package.json bun.lock tsconfig.json ./
RUN bun install --frozen-lockfile --production
COPY src ./src
# The OpenAPI document and the vendored Swagger UI served at /docs.
COPY openapi.json ./openapi.json
COPY vendor ./vendor
ENTRYPOINT ["bun", "src/main.ts"]
CMD []
