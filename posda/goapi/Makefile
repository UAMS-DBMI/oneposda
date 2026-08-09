TAG=dev
IMAGE_NAME=tcia/posda-api-go
# The deployment targets are x86; build for amd64 even on arm64 hosts.
PLATFORM=linux/amd64
GOFILES=$(shell find . -name '*.go')
.PHONY: build test push clean

default: build

build: posda-api

posda-api: $(GOFILES) go.mod go.sum
	go build -o posda-api ./cmd/posda-api

test:
	go test ./...

image: Dockerfile $(GOFILES)
	docker build --platform ${PLATFORM} . -t ${IMAGE_NAME}:${TAG} -t ${IMAGE_NAME}:latest

push: image
	docker image push ${IMAGE_NAME}:${TAG}
	docker image push ${IMAGE_NAME}:latest

clean:
	rm -f posda-api
