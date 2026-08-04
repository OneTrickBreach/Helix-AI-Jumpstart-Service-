# =============================================================================
# AI Jumpstart Service — Makefile (Phase 0+)
# =============================================================================
# One-command entrypoints for the Helix SCO prototype on GB10.
# Docker Compose v2 plugin syntax (space, not hyphen).
# =============================================================================

.PHONY: up down build web web-check test test-data logs ps clean data run bench bench-all scale-study rag cli cli-list check-api-running demo demo-data

SEED ?= 12345
SCENARIO ?= baseline
DATA_OUTPUT_DIR ?= data/generated/$(SCENARIO)
HORIZON ?= 8
PPO_TIMESTEPS ?= 128
TOP_K ?= 5

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

## Build and start the web UI at http://localhost:8081
web:
	docker compose up -d --build web

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

## Run only the Phase 1 synthetic data generator tests inside the api container
test-data: check-api-running
	docker compose exec api python3 -m pytest tests/test_data_generator.py -v --tb=short

## Run a specific test file (usage: make test-file FILE=tests/test_service_health.py)
test-file:
	docker compose exec api python3 -m pytest $(FILE) -v --tb=short

## Run tests from the host (requires services to be up, tests hit endpoints)
test-host:
	python3 -m pytest tests/ -v --tb=short -k "not container_internal"

# ---------------------------------------------------------------------------
# Synthetic data generation
# ---------------------------------------------------------------------------

check-api-running:
	@docker compose ps --status running --services | grep -qx api || (echo "ERROR: api container is not running. Run 'make up' first."; exit 1)

## Generate seeded synthetic Manufacturing data inside the running api container
data: check-api-running
	docker compose exec api python3 data/generator/generate.py --seed $(SEED) --scenario $(SCENARIO) --output-dir $(DATA_OUTPUT_DIR)

## Run Phase 2 ingest -> forecast -> baseline optimize pipeline
run: check-api-running data
	docker compose exec api python3 -m src.pipeline.run --scenario $(SCENARIO)

## Run Phase 3 baseline vs tuned-classical vs PPO benchmark
bench: check-api-running data
	docker compose exec api python3 -m src.pipeline.bench --scenario $(SCENARIO)

## Run Phase 6 all-scenario benchmark, including RAG/LLM and device-memory sampling
bench-all: check-api-running
	@for scenario in baseline component-shortage-shock demand-surge stress-large; do \
		docker compose exec api python3 data/generator/generate.py --seed $(SEED) --scenario $$scenario --output-dir data/generated/$$scenario || exit 1; \
	done
	docker compose exec api python3 -m src.bench.suite --horizon $(HORIZON) --ppo-timesteps $(PPO_TIMESTEPS) --top-k $(TOP_K)

## Run Phase 5 single-node scale ceiling study
scale-study: check-api-running
	docker compose exec api python3 -m src.bench.scale_study --timeout 600

## Run Phase 4 RAG advisory rationale for the benchmark-selected plan
rag: check-api-running data
	docker compose exec api python3 -m src.rag.advisory --scenario $(SCENARIO)

# ---------------------------------------------------------------------------
# Iteration 5 (BETA) — conversational analyst
# ---------------------------------------------------------------------------

CHAT_QUESTION ?= How many distribution centers are there?

## Ask one grounded question (usage: make chat-ask SCENARIO=baseline CHAT_QUESTION="...")
chat-ask: check-api-running
	@docker compose exec api python3 -m src.chat.ask --scenario "$(SCENARIO)" --question "$(CHAT_QUESTION)"

## Run the committed evaluation set against the real on-device LLM
chat-eval: check-api-running
	docker compose exec api python3 -m src.chat.eval

## Run the same evaluation set on the deterministic path (no model, fast)
chat-eval-template: check-api-running
	docker compose exec api python3 -m src.chat.eval --no-llm

## Read one what-if sentence into a validated perturbation (does NOT run it)
chat-parse: check-api-running
	@docker compose exec api python3 -m src.chat.parse --scenario "$(SCENARIO)" --question "$(CHAT_QUESTION)"

## Run the committed parser evaluation set (deterministic rules + LLM fallback)
parse-eval: check-api-running
	docker compose exec api python3 -m src.chat.parse_eval

## Run the parser evaluation set with the deterministic rules only
parse-eval-template: check-api-running
	docker compose exec api python3 -m src.chat.parse_eval --no-llm

# ---------------------------------------------------------------------------
# Web unit tests — from the committed lockfile, with the repo root mounted so
# the glossary parity test can read src/chat/glossary.json. The host
# web/node_modules is stale and would use the wrong vitest.
# ---------------------------------------------------------------------------
WEB_TEST_IMAGE ?= node:22-bookworm-slim

## Run the web Vitest suite in a scratch container from the committed lockfile
web-test:
	docker run --rm -v "$$(pwd)":/repo -w /repo/web $(WEB_TEST_IMAGE) \
		sh -c "npm ci --silent && npx vitest run"

# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

DEMO_SCENARIO ?= component-shortage-shock

## Generate synthetic data for all four demo scenarios (idempotent)
demo-data: check-api-running
	@for scenario in baseline component-shortage-shock demand-surge stress-large; do \
		docker compose exec api python3 data/generator/generate.py --seed $(SEED) --scenario $$scenario --output-dir data/generated/$$scenario || exit 1; \
	done
	@echo "✓ Demo data generated for all four scenarios"

## One-command demo launcher: rebuild web, generate data, print URL
demo: demo-data
	docker compose up -d --build web
	@echo ""
	@echo "═══════════════════════════════════════════════════════════════"
	@echo "  HELIX AI JUMPSTART DEMO"
	@echo "═══════════════════════════════════════════════════════════════"
	@echo ""
	@echo "  Live demo:     http://localhost:8081"
	@echo "  Recorded demo: http://localhost:8081?replay=true"
	@echo ""
	@echo "  Dataset view:  http://localhost:8081?view=dataset&scenario=$(DEMO_SCENARIO)"
	@echo "  ...recorded:   http://localhost:8081?view=dataset&replay=true"
	@echo ""
	@echo "  Recommended:   pick '$(DEMO_SCENARIO)' from the dropdown"
	@echo "  Parameters:    horizon=8, PPO timesteps=128, top-k=5"
	@echo ""
	@echo "  Remote access: localhost only resolves ON the GB10 — see the"
	@echo "                 'Remote Access' section of docs/DEMO_GUIDE.md"
	@echo "  Full guide:    docs/DEMO_GUIDE.md"
	@echo "═══════════════════════════════════════════════════════════════"

# ---------------------------------------------------------------------------
# Web verification (headless browser)
# ---------------------------------------------------------------------------

PLAYWRIGHT_IMAGE ?= mcr.microsoft.com/playwright:v1.49.1-noble
WEB_SHOT_DIR ?= web/e2e/shots

## Render the dataset view in a real browser: fold height, console errors, screenshots
web-check:
	@mkdir -p $(WEB_SHOT_DIR)
	docker run --rm --network $$(basename $$(pwd) | tr '[:upper:]' '[:lower:]')_default \
		-v "$$(pwd)/web/e2e":/work -v "$$(pwd)/$(WEB_SHOT_DIR)":/shots -w /work \
		$(PLAYWRIGHT_IMAGE) \
		sh -c "npm i playwright@1.49.1 --silent >/dev/null 2>&1 && node dataset-view.check.mjs"
	@echo "✓ screenshots written to $(WEB_SHOT_DIR)/"

## List scenarios through the secure API using the thin CLI
cli-list: check-api-running
	docker compose exec api python3 -m src.cli.scenario_comparison list

## Run Phase 5 scenario comparison through the secure API using the thin CLI
cli: check-api-running
	docker compose exec api python3 -m src.cli.scenario_comparison run --scenario $(SCENARIO) --horizon $(HORIZON) --ppo-timesteps $(PPO_TIMESTEPS) --top-k $(TOP_K)

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
