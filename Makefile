IMAGE_NAME := ghcr.io/misha00025/pyapi-gate
VERSION   := $(shell git describe --tags --always --dirty)

.PHONY: build push

build:
	docker build -t $(IMAGE_NAME):$(VERSION) -t $(IMAGE_NAME):latest .

push:
	docker push $(IMAGE_NAME):$(VERSION)
	docker push $(IMAGE_NAME):latest
