.PHONY: up down detect-arch

ARCH := $(shell uname -m)

DOCKER_PLATFORM :=
ifeq ($(ARCH),x86_64)
  DOCKER_PLATFORM = linux/amd64
else ifeq ($(ARCH),aarch64)
  DOCKER_PLATFORM = linux/arm64
else ifeq ($(ARCH),arm64)
  DOCKER_PLATFORM = linux/arm64
else
  $(error Unsupported architecture: $(ARCH))
endif

up:
	@echo "Using arch: $(ARCH)"
	@echo "Using platform: $(DOCKER_PLATFORM)"
	@DOCKER_PLATFORM=$(DOCKER_PLATFORM) docker compose up --build

dev:
	@echo "Using arch: $(ARCH)"
	@echo "Using platform: $(DOCKER_PLATFORM)"
	@DOCKER_PLATFORM=$(DOCKER_PLATFORM) docker compose up --build -d app db adminer
	@docker compose logs -f app db

down:
	@docker compose down

down-hard:
	@docker compose down -v

clean: down-hard
	@rm -rf log.file || true

fclean: clean
	@docker system prune -a -f

logs:
	@docker compose logs -f app

redo: clean up
