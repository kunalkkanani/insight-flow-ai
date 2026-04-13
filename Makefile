.PHONY: help install install-backend install-frontend dev dev-backend dev-frontend \
        build up down logs test lint format clean

PYTHON  ?= python3
PIP     ?= pip3
NPM     ?= npm

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ── Setup ──────────────────────────────────────────────────────────────────

venv:  ## Create Python virtual environment using pyenv Python 3.11.9
	$(shell pyenv which python3.11 2>/dev/null || echo python3.11) -m venv venv
	@echo "✓ venv created. Activate with: source venv/bin/activate"

install: install-backend install-frontend  ## Install all dependencies (run after: source venv/bin/activate)

install-backend:  ## Install Python deps into active venv
	$(PIP) install -r backend/requirements.txt

install-frontend:  ## Install Node deps
	cd frontend && $(NPM) install

# ── Development ────────────────────────────────────────────────────────────

dev: ## Start backend + frontend in dev mode (requires two terminals or use make dev-backend + dev-frontend)
	@echo "Run in two separate terminals:"
	@echo "  make dev-backend"
	@echo "  make dev-frontend"

dev-backend:  ## Start FastAPI dev server
	@cp -n .env.example backend/.env 2>/dev/null || true
	uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

dev-frontend:  ## Start Next.js dev server
	cd frontend && $(NPM) run dev

# ── Docker ─────────────────────────────────────────────────────────────────

build:  ## Build Docker images
	docker-compose build

up:  ## Start all services
	docker-compose up

up-d:  ## Start all services (detached)
	docker-compose up -d

down:  ## Stop all services
	docker-compose down

logs:  ## Follow logs
	docker-compose logs -f

# ── Quality ────────────────────────────────────────────────────────────────

test:  ## Run backend tests
	pytest tests/ -v

lint:  ## Lint Python
	flake8 backend/
	cd frontend && $(NPM) run lint

format:  ## Format Python
	black backend/
	isort backend/

# ── Utilities ──────────────────────────────────────────────────────────────

sample:  ## Generate sample dataset
	$(PYTHON) examples/generate_sample.py

clean:  ## Remove build artifacts and temp files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf frontend/.next frontend/node_modules
	rm -rf /tmp/insight_flow_uploads
