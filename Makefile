IMAGE ?= clorraine-installer-builder

.PHONY: image test smoke demo

image:
	docker build -t $(IMAGE) docker

test:
	IMAGE=$(IMAGE) docker/run.sh python3 -m unittest discover -s tools/tests -t . -v

smoke:
	IMAGE=$(IMAGE) docker/run.sh tools/smoke-online-install.sh

demo:
	IMAGE=$(IMAGE) docker/run.sh tools/demo-online-install.sh
