# Project Atlas — Makefile
# Synthetic, defensive, local-only. See PROJECT_ATLAS_BIBLE.md §19.

SHELL := /bin/bash
PYTHON ?= python3
PIP ?= pip
NPM ?= npm

# Default mode is public per CLAUDE.md.
export DEMO_MODE ?= public

# Web app lives under app/web; FastAPI under app/api.
WEB_DIR := app/web
API_MODULE := app.api.main:app
API_HOST ?= 127.0.0.1
API_PORT ?= 8000

.PHONY: help setup setup-python setup-web seed train run-rounds build-replay \
        test safety-scan demo-api demo-web clean

help:
	@echo "Project Atlas commands:"
	@echo "  make setup         install Python and Node dependencies"
	@echo "  make seed          generate synthetic data (Phase 2)"
	@echo "  make train         train baseline mock scorer (Phase 4)"
	@echo "  make run-rounds    run three red-team/defense rounds (Phase 8)"
	@echo "  make build-replay  build web replay JSON (Phase 8)"
	@echo "  make test          run pytest"
	@echo "  make safety-scan   run public-mode safety scan"
	@echo "  make demo-api      start local FastAPI (Phase 4)"
	@echo "  make demo-web      start Next.js frontend (Phase 1)"
	@echo "  make clean         remove caches and build artifacts"

setup: setup-python setup-web

setup-python:
	$(PIP) install -e ".[dev]"

setup-web:
	@if [ -f $(WEB_DIR)/package.json ]; then \
		cd $(WEB_DIR) && $(NPM) install; \
	else \
		echo "TODO Phase 1: $(WEB_DIR)/package.json not present yet."; \
	fi

seed:
	PYTHONPATH=src $(PYTHON) scripts/generate_synthetic.py

train:
	PYTHONPATH=src $(PYTHON) scripts/train_baseline.py

run-rounds:
	@echo "TODO Phase 8: implement scripts/run_rounds.py"

build-replay:
	@echo "TODO Phase 8: implement scripts/build_replay.py"

test:
	@if [ -d tests ] && find tests -name 'test_*.py' -o -name '*_test.py' | grep -q .; then \
		$(PYTHON) -m pytest; \
	else \
		echo "TODO: no tests yet; phase 0 skeleton only."; \
	fi

safety-scan:
	$(PYTHON) scripts/safety_scan.py

demo-api:
	@if [ -f app/api/main.py ]; then \
		PYTHONPATH=src $(PYTHON) -m uvicorn $(API_MODULE) --host $(API_HOST) --port $(API_PORT) --reload; \
	else \
		echo "TODO Phase 4: app/api/main.py not present yet."; \
	fi

demo-web:
	@if [ -f $(WEB_DIR)/package.json ]; then \
		cd $(WEB_DIR) && $(NPM) run dev; \
	else \
		echo "TODO Phase 1: $(WEB_DIR)/package.json not present yet."; \
	fi

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache build dist *.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
