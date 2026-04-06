.PHONY: install dev test lint clean run

install:
	pip install -e .

dev:
	pip install -e ".[dev]"

test:
	pytest tests/ -v

lint:
	ruff check aulinx/ tests/

fix:
	ruff check --fix aulinx/ tests/

clean:
	rm -rf dist/ build/ *.egg-info .pytest_cache .ruff_cache __pycache__
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

run:
	aulinx

run-7b:
	aulinx -m qwen2.5:7b
