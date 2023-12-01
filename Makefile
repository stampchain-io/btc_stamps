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
	@cd docker && DOCKER_PLATFORM=$(DOCKER_PLATFORM) docker compose up --build

dup:
	@echo "Using arch: $(ARCH)"
	@echo "Using platform: $(DOCKER_PLATFORM)"
	@cd docker && DOCKER_PLATFORM=$(DOCKER_PLATFORM) docker compose up --build -d

logs: dup
	@cd docker && docker compose logs -f indexer

db: 
	@echo "Using arch: $(ARCH)"
	@echo "Using platform: $(DOCKER_PLATFORM)"
	@cd docker && DOCKER_PLATFORM=$(DOCKER_PLATFORM) docker compose up --build -d db adminer
app: db 
	@echo "Using arch: $(ARCH)"
	@echo "Using platform: $(DOCKER_PLATFORM)"
	@cd docker && DOCKER_PLATFORM=$(DOCKER_PLATFORM) docker compose up --build -d app
	@cd docker && docker compose logs -f app

dev:
	@echo "Using arch: $(ARCH)"
	@echo "Using platform: $(DOCKER_PLATFORM)"
	@cd docker && DOCKER_PLATFORM=$(DOCKER_PLATFORM) docker compose up --build -d indexer db adminer
	@docker compose logs -f indexer db

down:
	@cd docker && docker compose down

fdown:
	@cd docker && docker compose down -v
	@rm -rf files || true
	@rm -rf indexer/files || true
	@rm -rf */__pycache__ || true
	@rm -rf */*/__pycache__ || true
	@rm -rf indexer/log.file || true
	@rm -rf docker/db_data || true

clean: fdown
	@rm -rf files || true
	@rm -rf indexer/files || true
	@rm -rf */__pycache__ || true
	@rm -rf */*/__pycache__ || true
	@rm -rf indexer/log.file || true
	@rm -rf docker/db_data || true

fclean: clean
	@cd docker && docker system prune -a -f

redo: clean up
