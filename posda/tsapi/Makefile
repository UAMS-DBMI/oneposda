TAG=dev
IMAGE_NAME=tcia/posda-api-ts
# The deployment targets are x86; build for amd64 even on arm64 hosts.
PLATFORM=linux/amd64
.PHONY: run test image push typecheck openapi openapi-check validate-live

default: typecheck

run:
	bun src/main.ts

test:
	bun test

typecheck:
	bunx tsc --noEmit

# Regenerate the OpenAPI document from the route annotations. Writes
# both this copy and the one goapi embeds.
openapi:
	bun scripts/genopenapi.ts

# Fails if the checked-in document is stale with respect to the sources.
openapi-check: openapi
	@git diff --quiet --exit-code -- openapi.json ../goapi/internal/docs/openapi.json \
	  || { echo "openapi.json is out of date; commit the regenerated file"; exit 1; }
	@echo "openapi.json is up to date"

# Validates the document against a running server's actual responses.
# API_BASE defaults to the local dev server; endpoints come from stdin.
validate-live:
	bun scripts/validatelive.ts

image: Dockerfile
	docker build --platform ${PLATFORM} . -t ${IMAGE_NAME}:${TAG} -t ${IMAGE_NAME}:latest

push: image
	docker image push ${IMAGE_NAME}:${TAG}
	docker image push ${IMAGE_NAME}:latest
