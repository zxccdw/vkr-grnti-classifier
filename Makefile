.PHONY: help install lint format typecheck test docker-build docker-run clean

help:
	@echo "Available commands:"
	@echo "  make install      - Install dependencies"
	@echo "  make lint         - Run ruff linter"
	@echo "  make format       - Format code with ruff"
	@echo "  make typecheck    - Run mypy type checker"
	@echo "  make test         - Run tests"
	@echo "  make check        - Run all checks (lint + typecheck)"
	@echo "  make docker-build - Build Docker image"
	@echo "  make docker-run   - Run Docker container"
	@echo "  make clean        - Remove cache and temp files"

install:
	uv pip install --system -r pyproject.toml
	uv pip install --system ruff mypy black

lint:
	ruff check backend/

format:
	ruff format backend/

format-check:
	ruff format --check backend/

typecheck:
	mypy backend/ --ignore-missing-imports

test:
	@echo "Tests not implemented yet"

check: lint format-check typecheck
	@echo "✅ All checks passed"

docker-build:
	docker build -t grnti-web:latest .

docker-run:
	docker-compose up -d

docker-logs:
	docker-compose logs -f

docker-stop:
	docker-compose down

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
