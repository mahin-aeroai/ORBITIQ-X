# ============================================================
# ORBITIQ-X — Migration Makefile
# ============================================================
# Usage:
#   make db-up          Start local PostgreSQL via Docker Compose
#   make migrate        Apply all pending migrations
#   make migrate-down   Roll back one migration
#   make migrate-status Show current migration state
#   make migrate-sql    Preview SQL without applying
#   make migrate-new MSG="add index" Run autogenerate
#   make migrate-verify Check schema drift
#   make db-reset       Wipe dev DB and re-apply from scratch
#   make db-backup      Dump current DB to file
#   make db-restore F=backup.dump

SHELL := /bin/bash
.PHONY: all db-up db-down migrate migrate-down migrate-status \
        migrate-sql migrate-new migrate-verify migrate-history \
        db-reset db-backup db-restore help

# ── Environment ────────────────────────────────────────────────
include ../.env
export

POSTGRES_HOST     ?= localhost
POSTGRES_PORT     ?= 5432
POSTGRES_DB       ?= orbitiq_db
POSTGRES_USER     ?= orbitiq
POSTGRES_PASSWORD ?= orbitiq

BACKUP_DIR := backups
BACKUP_FILE := $(BACKUP_DIR)/orbitiq_$(shell date +%Y%m%d_%H%M%S).dump
PYTHON      := python3
ALEMBIC     := $(PYTHON) migrate.py
DOCKER_COMPOSE := docker compose -f ../deployment/docker/docker-compose.dev.yml

# ── Database lifecycle ─────────────────────────────────────────

db-up: ## Start PostgreSQL (and dependencies) via Docker Compose
	@echo "Starting PostgreSQL..."
	$(DOCKER_COMPOSE) up -d orbitiq-postgres
	@echo "Waiting for PostgreSQL to be ready..."
	@until $(DOCKER_COMPOSE) exec -T orbitiq-postgres \
		pg_isready -U $(POSTGRES_USER) -d $(POSTGRES_DB) -q; do \
		sleep 1; \
	done
	@echo "PostgreSQL is ready."

db-down: ## Stop PostgreSQL container
	$(DOCKER_COMPOSE) stop orbitiq-postgres

db-shell: ## Open psql shell in the PostgreSQL container
	$(DOCKER_COMPOSE) exec orbitiq-postgres \
		psql -U $(POSTGRES_USER) -d $(POSTGRES_DB)

db-logs: ## Tail PostgreSQL container logs
	$(DOCKER_COMPOSE) logs -f orbitiq-postgres

# ── Migration commands ─────────────────────────────────────────

migrate: ## Apply all pending migrations (safe to run repeatedly)
	@echo "==> Applying migrations to head..."
	$(ALEMBIC) upgrade head

migrate-one: ## Apply exactly one pending migration
	$(ALEMBIC) upgrade +1

migrate-down: ## Roll back one migration
	@echo "==> Rolling back one migration..."
	$(ALEMBIC) downgrade -1

migrate-down-to: ## Roll back to specific revision: make migrate-down-to REV=0004
	@[ -n "$(REV)" ] || (echo "Usage: make migrate-down-to REV=<revision_id>"; exit 1)
	$(ALEMBIC) downgrade $(REV)

migrate-status: ## Show current migration state
	$(ALEMBIC) status

migrate-history: ## Show full migration history
	$(ALEMBIC) history

migrate-sql: ## Preview SQL for pending migrations without applying
	@echo "==> SQL preview (no changes applied):"
	$(ALEMBIC) sql-preview

migrate-verify: ## Check that DB schema matches Alembic head
	$(ALEMBIC) verify

migrate-new: ## Autogenerate migration from model changes: make migrate-new MSG="add column"
	@[ -n "$(MSG)" ] || (echo "Usage: make migrate-new MSG='description of change'"; exit 1)
	@echo "==> Generating migration: $(MSG)"
	@echo "    IMPORTANT: Review the generated file before committing."
	$(ALEMBIC) revision "$(MSG)" --autogenerate

migrate-stamp: ## Mark current head without running: make migrate-stamp
	$(ALEMBIC) stamp head

rollback-help: ## Print rollback procedures
	$(ALEMBIC) rollback-help

# ── Dev database management ────────────────────────────────────

db-reset: ## DANGER: Wipe dev DB and re-apply all migrations from scratch
	@echo "WARNING: This will destroy all data in $(POSTGRES_DB)"
	@read -p "Type 'reset-dev' to confirm: " confirm; \
	[ "$$confirm" = "reset-dev" ] || (echo "Cancelled"; exit 1)
	$(ALEMBIC) downgrade base --force
	$(ALEMBIC) upgrade head
	@echo "Dev database reset complete"

db-seed: ## Load sample aerospace data (dev only)
	$(PYTHON) -m app.db.seed

# ── Backup and restore ─────────────────────────────────────────

db-backup: ## Dump current database to timestamped file
	@mkdir -p $(BACKUP_DIR)
	@echo "==> Backing up to $(BACKUP_FILE)..."
	pg_dump \
		-h $(POSTGRES_HOST) \
		-p $(POSTGRES_PORT) \
		-U $(POSTGRES_USER) \
		-d $(POSTGRES_DB) \
		-Fc \
		-f $(BACKUP_FILE)
	@echo "Backup complete: $(BACKUP_FILE)"
	@ls -lh $(BACKUP_FILE)

db-restore: ## Restore from backup: make db-restore F=backups/orbitiq_20260620.dump
	@[ -n "$(F)" ] || (echo "Usage: make db-restore F=<backup_file>"; exit 1)
	@echo "==> Restoring from $(F)..."
	pg_restore \
		-h $(POSTGRES_HOST) \
		-p $(POSTGRES_PORT) \
		-U $(POSTGRES_USER) \
		-d $(POSTGRES_DB) \
		--clean \
		--if-exists \
		$(F)
	@echo "Restore complete. Stamping Alembic state..."
	$(ALEMBIC) stamp head
	$(ALEMBIC) status

# ── CI/CD helpers ──────────────────────────────────────────────

ci-migrate: ## CI: apply migrations and verify (non-interactive)
	$(ALEMBIC) upgrade head
	$(ALEMBIC) verify

ci-check: ## CI: verify no uncommitted schema drift
	$(ALEMBIC) verify

# ── Help ───────────────────────────────────────────────────────

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-22s\033[0m %s\n", $$1, $$2}'
