.PHONY: dev up dup logs down fdown clean prod prod-down config help

# ==============================================================================
# btc_stamps compose targets (canonical base + override structure)
#
#   dev / up   -> docker compose up                (base + override.yml, auto)
#   prod       -> base + docker-compose.prod.yml    (managed RDS; NOT yet deployed)
#
# Validation:
#   make config -> `docker compose config` parse/merge check (starts nothing)
# ==============================================================================

help:
	@echo "Targets:"
	@echo "  make dev / make up   Start the local dev stack (indexer + mysql)"
	@echo "  make dup             Same, detached"
	@echo "  make logs            Follow indexer logs"
	@echo "  make down            Stop the stack"
	@echo "  make fdown / clean   Stop, remove volumes, and clean local artifacts"
	@echo "  make prod            Start the prod overlay (managed RDS; NOT deployed)"
	@echo "  make config          Parse/merge check (does not start anything)"

# --- Development (default): base + auto-applied docker-compose.override.yml ---
dev up:
	docker compose up --build

dup:
	docker compose up --build -d

logs:
	docker compose logs -f indexer

down:
	docker compose down

fdown:
	docker compose down -v
	@rm -rf db_data || true
	@rm -rf files indexer/files || true
	@rm -rf indexer/log.file || true
	@rm -rf */__pycache__ */*/__pycache__ || true

clean: fdown

# --- Production overlay (explicit; production currently runs via systemd) -----
prod:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

prod-down:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml down

# --- Validation: parse/merge only, starts nothing -----------------------------
config:
	docker compose config
	docker compose -f docker-compose.yml -f docker-compose.prod.yml config
