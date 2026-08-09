TAG=dev
IMAGE_NAME=tcia/posda-api-ts
.PHONY: run test image push typecheck

default: typecheck

run:
	bun src/main.ts

test:
	bun test

typecheck:
	bunx tsc --noEmit

image: Dockerfile
	docker build . -t ${IMAGE_NAME}:${TAG} -t ${IMAGE_NAME}:latest

push: image
	docker image push ${IMAGE_NAME}:${TAG}
	docker image push ${IMAGE_NAME}:latest
