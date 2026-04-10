.PHONY: install dev test lint clean run build-compositor test-all

# Python agent
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

run-headless:
	aulinx --mode core

run-7b:
	aulinx -m qwen2.5:7b

doctor:
	aulinx --doctor

# Rust compositor
build-compositor:
	cd compositor && cargo build -p aulinx-compositor -p aulinx-semanticd

build-compositor-release:
	cd compositor && cargo build --release -p aulinx-compositor -p aulinx-semanticd

test-compositor:
	cd compositor && cargo test

run-compositor:
	cd compositor && WAYLAND_DISPLAY=wayland-0 cargo run -p aulinx-compositor

demo:
	cd compositor && bash demo.sh

# All
test-all: test test-compositor

build-all: install build-compositor
