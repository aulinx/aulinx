# Aulinx — AI-Native Linux Desktop

## Project Overview
Aulinx replaces the traditional Linux desktop (GNOME/KDE) with an AI-first interface powered by a local LLM. Currently in Phase 0 (proof of concept).

## Architecture
- `aulinx/cli.py` — Interactive REPL entry point
- `aulinx/agent.py` — Core agent (LLM chat + tool calling loop)
- `aulinx/context/desktop.py` — Desktop state collection (AT-SPI, system info, clipboard)
- `aulinx/tools/registry.py` — Tool registration with permission tiers (T0-T4)
- `aulinx/tools/*.py` — Individual tool modules (window, atspi, files, apps, system, clipboard, notify)

## Key Patterns
- Tools are registered in each module's `TOOLS` list as `Tool` objects with a `Tier` level
- The agent streams responses from Ollama and extracts JSON tool calls
- Tool calls use the format: `{"tool": "name", "args": {"key": "value"}}`
- AT-SPI (pyatspi) is the primary way to read/control GUI apps — prefer it over shell commands
- Permission tiers: OBSERVE (auto), LOW_RISK (auto+log), MUTATE (confirm once), DESTRUCTIVE (always confirm)

## Dev Setup
Runs on Linux with a desktop environment. Requires Python 3.10+, Ollama, and optionally pyatspi.
```bash
pip install -e .
ollama pull qwen2.5:14b
aulinx
```

## Code Style
- Python 3.10+ with type hints
- async/await for all tool functions
- Rich library for terminal UI
- Keep tool modules focused — one file per domain
