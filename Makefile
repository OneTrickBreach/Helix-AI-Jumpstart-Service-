# =============================================================================
# AI Jumpstart Service — Makefile (Phase 0+)
# =============================================================================
# One-command entrypoints for the Helix SCO prototype on GB10.
# Docker Compose v2 plugin syntax (space, not hyphen).
# =============================================================================

.PHONY: up down build test logs ps clean

# ---------------------------------------------------------------------------
# Docker Compose commands
# ---------------------------------------------------------------------------

## Bring up all services (build first, detached)
up:
	docker compose up -d --build

## Bring up without rebuilding
start:
	docker compose up -d

## Tear down all services
down:
	docker compose down

## Rebuild all images
build:
	docker compose build

## Show running services
ps:
	docker compose ps

## Follow logs for all services
logs:
	docker compose logs -f

## Follow logs for a specific service (usage: make log-api, make log-llm, etc.)
log-%:
	docker compose logs -f $*

# ---------------------------------------------------------------------------
# Testing
# ---------------------------------------------------------------------------

## Run the full Phase 0 smoke test suite inside the api container
test:
	docker compose exec api python3 -m pytest tests/ -v --tb=short

## Run a specific test file (usage: make test-file FILE=tests/test_service_health.py)
test-file:
	docker compose exec api python3 -m pytest $(FILE) -v --tb=short

## Run tests from the host (requires services to be up, tests hit endpoints)
test-host:
	python3 -m pytest tests/ -v --tb=short -k "not container_internal"

# ---------------------------------------------------------------------------
# Service-specific
# ---------------------------------------------------------------------------

## Check GPU inside the api container
gpu-check:
	docker compose exec api nvidia-smi
	docker compose exec api nvcc --version

## Check LLM models loaded
llm-check:
	curl -s http://localhost:8000/v1/models | python3 -m json.tool

## Check embeddings health
embed-check:
	curl -s http://localhost:8080/embeddings/health | python3 -m json.tool

## Check Qdrant health
qdrant-check:
	curl -s http://localhost:6333/healthz

## Check cuOpt/fallback health
cuopt-check:
	curl -s http://localhost:8080/cuopt/health | python3 -m json.tool

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

## Remove containers, volumes, and images
clean:
	docker compose down -v --rmi local
