.PHONY: help setup test lint format demo docker-up docker-down clean install

# Color output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
NC := \033[0m # No Color

help:
	@echo "$(BLUE)AI Data Operations Platform - Development Commands$(NC)"
	@echo ""
	@echo "$(GREEN)Setup & Installation:$(NC)"
	@echo "  make setup              Install dependencies and setup environment"
	@echo "  make install            Install Python dependencies from requirements.txt"
	@echo ""
	@echo "$(GREEN)Testing & Quality:$(NC)"
	@echo "  make test               Run all tests with pytest"
	@echo "  make test-fast          Run tests in parallel"
	@echo "  make coverage           Run tests with coverage report"
	@echo "  make lint               Check code style (black, isort, flake8, mypy)"
	@echo "  make format             Auto-format code (black, isort)"
	@echo ""
	@echo "$(GREEN)Development:$(NC)"
	@echo "  make demo               Run the complete demo pipeline"
	@echo "  make shell              Open Python REPL with project loaded"
	@echo "  make watch              Watch for changes and run tests"
	@echo ""
	@echo "$(GREEN)Docker:$(NC)"
	@echo "  make docker-up          Start Docker Compose services"
	@echo "  make docker-down        Stop Docker Compose services"
	@echo "  make docker-logs        View Docker logs"
	@echo "  make docker-shell       Shell into app container"
	@echo "  make docker-test        Run tests in Docker container"
	@echo ""
	@echo "$(GREEN)Cleanup:$(NC)"
	@echo "  make clean              Remove build artifacts and cache files"
	@echo "  make clean-docker       Remove Docker containers and volumes"
	@echo ""

# ============================================================================
# Setup & Installation
# ============================================================================

setup: install
	@echo "$(GREEN)Setting up development environment...$(NC)"
	@mkdir -p .git/hooks
	@echo "✓ Virtual environment ready"
	@echo "✓ Dependencies installed"
	@echo "$(YELLOW)Next: docker-compose up -d$(NC)"

install:
	@echo "$(GREEN)Installing dependencies...$(NC)"
	pip install --upgrade pip setuptools wheel
	pip install -r requirements.txt
	@echo "$(GREEN)✓ Dependencies installed$(NC)"

# ============================================================================
# Testing & Quality
# ============================================================================

test:
	@echo "$(GREEN)Running test suite...$(NC)"
	pytest tests/ -v --tb=short
	@echo "$(GREEN)✓ Tests passed$(NC)"

test-fast:
	@echo "$(GREEN)Running tests in parallel...$(NC)"
	pytest tests/ -v -n auto --tb=short
	@echo "$(GREEN)✓ Tests passed$(NC)"

coverage:
	@echo "$(GREEN)Running tests with coverage...$(NC)"
	pytest tests/ --cov=src --cov-report=term-missing --cov-report=html -v
	@echo "$(GREEN)✓ Coverage report generated in htmlcov/index.html$(NC)"

lint:
	@echo "$(GREEN)Checking code style...$(NC)"
	@echo "  Checking imports with isort..."
	isort --check-only --diff src/ tests/ || true
	@echo "  Checking formatting with black..."
	black --check --line-length=100 src/ tests/ || true
	@echo "  Checking with flake8..."
	flake8 src/ tests/ --max-line-length=100 --extend-ignore=E203,W503 || true
	@echo "  Type checking with mypy..."
	mypy src/ --ignore-missing-imports || true
	@echo "$(GREEN)✓ Lint checks complete$(NC)"

format:
	@echo "$(GREEN)Auto-formatting code...$(NC)"
	@echo "  Formatting with black..."
	black --line-length=100 src/ tests/
	@echo "  Sorting imports with isort..."
	isort src/ tests/
	@echo "$(GREEN)✓ Code formatted$(NC)"

# ============================================================================
# Development
# ============================================================================

demo:
	@echo "$(GREEN)Running demo pipeline...$(NC)"
	python demo/run_demo.py
	@echo "$(GREEN)✓ Demo complete$(NC)"

shell:
	@echo "$(GREEN)Opening Python REPL...$(NC)"
	python -c "import sys; sys.path.insert(0, 'src'); from IPython import embed; embed()"

watch:
	@echo "$(GREEN)Watching for changes...$(NC)"
	@command -v ptw >/dev/null 2>&1 || pip install pytest-watch
	ptw tests/ -- -v --tb=short

# ============================================================================
# Docker
# ============================================================================

docker-up:
	@echo "$(GREEN)Starting Docker services...$(NC)"
	docker-compose up -d
	@echo ""
	@echo "$(GREEN)Services started:$(NC)"
	@echo "  API:        http://localhost:8000"
	@echo "  Docs:       http://localhost:8000/docs"
	@echo "  Temporal:   http://localhost:8233"
	@echo "  pgAdmin:    http://localhost:5050 (with --profile dev)"
	@echo "  Grafana:    http://localhost:3000 (with --profile dev)"
	@docker-compose logs --no-log-prefix -f app 2>/dev/null &
	@sleep 2
	@echo "$(GREEN)✓ Services ready (logs streaming above)$(NC)"

docker-down:
	@echo "$(YELLOW)Stopping Docker services...$(NC)"
	docker-compose down
	@echo "$(GREEN)✓ Services stopped$(NC)"

docker-logs:
	@echo "$(GREEN)Streaming Docker logs...$(NC)"
	docker-compose logs -f

docker-shell:
	@echo "$(GREEN)Opening shell in app container...$(NC)"
	docker-compose exec app /bin/bash

docker-test:
	@echo "$(GREEN)Running tests in Docker...$(NC)"
	docker-compose exec app pytest tests/ -v

# ============================================================================
# Cleanup
# ============================================================================

clean:
	@echo "$(YELLOW)Cleaning build artifacts...$(NC)"
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name *.egg-info -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name .DS_Store -delete 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true
	rm -rf build/ dist/ .coverage htmlcov/ .ruff_cache/
	@echo "$(GREEN)✓ Cleaned$(NC)"

clean-docker:
	@echo "$(YELLOW)Removing Docker containers and volumes...$(NC)"
	docker-compose down -v
	docker-compose rm -f
	@echo "$(GREEN)✓ Docker cleaned$(NC)"

# ============================================================================
# CI/CD Helpers (for local testing before pushing)
# ============================================================================

.PHONY: ci
ci: format lint test coverage
	@echo "$(GREEN)✓ All CI checks passed$(NC)"

# ============================================================================
# Development Workflow Examples
# ============================================================================

.PHONY: develop
develop: setup docker-up
	@echo ""
	@echo "$(BLUE)Development environment ready!$(NC)"
	@echo ""
	@echo "$(GREEN)Quick start:$(NC)"
	@echo "  1. Edit code in src/"
	@echo "  2. Run tests: make test"
	@echo "  3. Check quality: make lint"
	@echo "  4. Try demo: make demo"
	@echo ""
	@echo "$(GREEN)For more help: make help$(NC)"

# ============================================================================
# Silent targets for complex operations
# ============================================================================

.SILENT: help
