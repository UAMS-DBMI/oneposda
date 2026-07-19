FROM alpine:3.24
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

COPY requirements.frozen.txt /
RUN pip3 install --break-system-packages -r /requirements.frozen.txt

COPY *.py /scripts/
