FROM node:16-alpine AS dashboard-builder
RUN apk --update add make
COPY dashboard /dashboard
RUN cd /dashboard && \
    make

FROM node:16-alpine AS quince-builder
RUN apk --update add make
COPY quince /quince
RUN cd /quince && \
	make

FROM node:16-alpine AS roots-builder
RUN apk --update add make
COPY dicom-root /roots
RUN cd /roots && \
	make

FROM node:16-alpine AS kohlrabi-builder
RUN apk --update add make
COPY Kohlrabi /kohlrabi
RUN cd /kohlrabi && \
  make

#FROM node:16-alpine AS mirabelle-builder
FROM oven/bun:1.3-alpine AS mirabelle-builder
RUN apk --update add make
# receive commit from env and re-export to container
ARG MIRABELLE_COMMIT=unknown
ENV MIRABELLE_COMMIT=$MIRABELLE_COMMIT
COPY mirabelle /mirabelle
RUN cd /mirabelle && \
  make build

#FROM nginx:1.13.10-alpine
#FROM bitnamilegacy/nginx:1.21
# Change to an officialy supported nonroot image, pinned on nginx version
# and alpine version. Pass --user to specify the UID/GID to use
FROM nginxinc/nginx-unprivileged:1.31-alpine3.23
ARG MIRABELLE_COMMIT=unknown
LABEL org.opencontainers.image.revision=$MIRABELLE_COMMIT

COPY default.conf /opt/bitnami/nginx/conf/server_blocks/
COPY www /www


COPY --from=dashboard-builder /dashboard/dist/posda-dashboard /www/dashboard
COPY --from=quince-builder /quince/dist /www/quince
COPY --from=roots-builder /roots/dist/dicom-root /www/roots
COPY --from=kohlrabi-builder /kohlrabi/build /www/kohlrabi
#COPY --from=ohif/viewer:builder /usr/src/app/platform/viewer/dist /www/ohif
COPY --from=mirabelle-builder /mirabelle/dist /www/mira
