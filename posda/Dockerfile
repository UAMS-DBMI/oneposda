# syntax=docker/dockerfile:1

###############################################################################
# Build pydicom-background-editor
###############################################################################
FROM astral/uv:python3.14-trixie AS pydicom-bg-builder

RUN <<EOF
set -e
mkdir /build
cd /build
git clone https://github.com/quasarj/pydicom-background-editor.git
cd pydicom-background-editor
uv build
EOF

###############################################################################
# Build Dicom 3 tools
###############################################################################
FROM buildpack-deps:trixie AS d3tbuild

RUN <<EOF
	set -e
	apt-get update
	apt-get install -y xutils-dev
EOF

RUN mkdir /build
RUN git clone https://code.imphub.org/scm/pt/dicom3tools.git /build/dicom3tools

RUN <<EOF
	set -e
	cd /build/dicom3tools/src
	./Configure
	imake -I./config
	make -j $(nproc) World
	make -j $(nproc)
	make install
EOF

################################################################################
## Build dcm2niix (for covnerting to nifti)
################################################################################

FROM buildpack-deps:trixie AS dcm2niixbuild

RUN <<EOF
set -e
apt-get update
apt-get install -y cmake git
EOF

RUN git clone https://github.com/rordenlab/dcm2niix.git
RUN <<EOF
set -e
cd dcm2niix
mkdir build
cd build
cmake -DUSE_JPEGLS=ON ..
make
EOF

################################################################################
################################################################################
################################################################################
## the real container starts here
################################################################################
################################################################################
################################################################################
################################################################################
FROM python:3.14-slim-trixie

# Base system deps and runtime libraries.
# make is required by cpanm below, even for pure-Perl modules.
# libopenslide0 is the runtime library for the openslide-python pip package.
RUN <<EOF
set -e
apt-get update
apt-get install -y --no-install-recommends \
	git \
	time \
	file \
	vim \
	wget \
	make \
	postgresql-client \
	tzdata \
	unzip \
	redis-tools \
	procps \
	rclone \
	less \
	imagemagick \
	libgdcm-tools \
	libopenslide0
rm -rf /var/lib/apt/lists/*
EOF

# Some scripts have a hardcoded #!/usr/bin/python3, which the python
# base image does not provide
RUN ln -s /usr/local/bin/python3 /usr/bin/python3


# Perl modules from repos
RUN <<EOF
set -e
apt-get update
apt-get install -y \
	libdata-uuid-perl \
	libdbd-pg-perl \
	libdbd-mysql-perl \
	libswitch-perl \
	libterm-readkey-perl \
	libtext-csv-perl \
	libtext-csv-xs-perl \
	libregexp-common-perl \
	libtry-tiny-perl \
	libnet-ldap-perl \
	libdatetime-perl \
	libfile-slurp-perl \
	libunicode-map-perl \
	librest-client-perl \
	libtext-markdown-perl \
	libmodern-perl-perl \
	libredis-perl \
	libjson-perl \
	libtext-diff-perl \
	cpanminus
rm -rf /var/lib/apt/lists/*
EOF


# Perl modules that are not in system repositories
RUN cpanm --notest \
				   K/KE/KEN/xls2csv-1.07.tar.gz \
				   HTTP::Request::StreamingUpload


# Install needed python utils
RUN pip3 install --no-cache-dir \
	xlsx2csv \
	mysql-connector \
	python-box \
	pydicom \
	psycopg2-binary \
	redis \
	tifffile \
	imagecodecs \
	openslide-python \
	pandas \
	numpy \
	nibabel \
	pyarrow \
	storable \
	Pillow

COPY --from=pydicom-bg-builder /build/pydicom-background-editor/dist/*.whl /
RUN pip install --no-cache-dir /*.whl

RUN addgroup --gid 2123 fakeposda
RUN adduser --system --ingroup fakeposda --uid 1000 posda

COPY --chown=posda:fakeposda fastapi/app /fastapi/
COPY --chown=posda:fakeposda fastapi/start_api.sh /
RUN pip3 install --no-cache-dir -r /fastapi/requirements.txt

# Work around issue with volume persmissions
RUN mkdir -p /home/posda/cache
RUN chown posda:fakeposda /home/posda/cache
VOLUME ["/home/posda/cache"]

COPY docker-entrypoint /
COPY --chown=posda:fakeposda posda.env /home/posda/posdatools/

WORKDIR /home/posda
ENV PYTHONPATH=/home/posda/posdatools/python

# Only these two dicom3tools binaries are actually used
COPY --from=d3tbuild /usr/local/bin/dciodvfy /usr/local/bin/dcentvfy /usr/local/bin/

# copy dcm2niix into place
COPY --from=dcm2niixbuild /dcm2niix/build/bin/dcm2niix /usr/local/bin/dcm2niix

# Copy actual posdatools last, to speed up rebuilds
COPY --chown=posda:fakeposda posdatools /home/posda/posdatools

USER posda:fakeposda
ENTRYPOINT ["/docker-entrypoint"]
CMD ["main"]
