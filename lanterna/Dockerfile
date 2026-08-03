FROM alpine:3.17
# magicka.py renders projections in-process with pydicom + numpy + Pillow.
# thumbs.py still shells out to dcm4che's dcm2jpg, so the JRE + dcm4che stay.
RUN apk --update add \
	python3 \
	py3-pip \
	py3-numpy \
	py3-pillow \
	redis \
	openjdk8-jre-base \
    py3-psycopg2

COPY dcm4che-5.22.1-bin.zip /
RUN unzip /dcm4che-5.22.1-bin.zip -d /opt && rm -f /dcm4che-5.22.1-bin.zip

ENV PATH="/opt/dcm4che-5.22.1/bin:${PATH}"

COPY requirements.txt /
RUN pip3 install -r /requirements.txt

COPY *.py /scripts/

# FROM node-builder as quince-builder
# COPY quince /quince
# RUN cd /quince && \
# 	make


# FROM nginx:1.13.10-alpine

# COPY default.conf /etc/nginx/conf.d/
# COPY www /www


# COPY --from=dashboard-builder /dashboard/dist/posda-dashboard /www/dashboard
# COPY --from=quince-builder /quince/dist /www/quince

# EXPOSE 80
