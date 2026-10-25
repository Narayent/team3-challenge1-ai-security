# Smart Lab Access System - Challenge 1 lab harness.
# Everything runs locally in Docker, bound to 127.0.0.1 only.

TEAM ?= 00
IMAGE = labaccess:latest
PROJ = $(shell pwd)
# Run containers as the host user (non-root) so bind-mounted dirs are writable.
export LAB_UID := $(shell id -u)
export LAB_GID := $(shell id -g)
COMPOSE = docker compose -f docker/docker-compose.yml
RUN = docker run --rm --user $(LAB_UID):$(LAB_GID) -e HOME=/tmp -v "$(PROJ)":/project

.PHONY: help build models up down logs redteam-original redteam-secured retest \
        all clean zip status

help:
	@echo "make build              # build the shared Docker image"
	@echo "make models             # generate model files for original + secured"
	@echo "make up                 # start both containers (loopback only)"
	@echo "make down               # stop containers"
	@echo "make redteam-original   # run PoC suite vs vulnerable app -> evidence/original"
	@echo "make redteam-secured    # retest same PoCs vs hardened app -> evidence/secured"
	@echo "make retest             # alias for redteam-secured"
	@echo "make all                # build + models + up + both test passes"
	@echo "make zip TEAM=07        # package Team07_Challenge1_Code.zip"

build:
	docker build -t $(IMAGE) -f docker/Dockerfile .

models:
	$(RUN) -w /project/original $(IMAGE) python generate_models.py
	$(RUN) -w /project/secured  $(IMAGE) python generate_models_safe.py

up: models
	$(COMPOSE) up -d
	@echo "original -> http://127.0.0.1:8080   secured -> http://127.0.0.1:8000"

down:
	$(COMPOSE) down

status:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs --tail=50

redteam-original:
	bash redteam/run_redteam.sh original

redteam-secured:
	bash redteam/run_redteam.sh secured

retest: redteam-secured

all: build up
	@sleep 3
	$(MAKE) redteam-original
	$(MAKE) redteam-secured

zip:
	@rm -f Team$(TEAM)_Challenge1_Code.zip
	zip -r Team$(TEAM)_Challenge1_Code.zip \
	    original secured redteam docker evidence report README.md Makefile \
	    -x '*/__pycache__/*' -x '*.pyc' >/dev/null
	@echo "wrote Team$(TEAM)_Challenge1_Code.zip"

clean:
	$(COMPOSE) down 2>/dev/null || true
	rm -f original/PWNED_TRAVERSAL.txt sandbox/PWNED_*.txt sandbox/evil_model.pkl sandbox/valid.jpg
	find . -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
