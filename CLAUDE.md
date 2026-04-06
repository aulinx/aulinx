# Aulinx — AI-Native Linux Desktop

## Project Overview
Aulinx is an AI agent with 92 tools that controls a Linux desktop through natural language. Uses AT-SPI (accessibility API) for semantic GUI control + Ollama for local LLM inference with native tool calling.

## Architecture
```
aulinx/
├── cli.py              — Interactive REPL + one-shot + slash commands + --serve
├── agent.py            — Ollama native tool calling + text fallback + retry + audit
├── server.py           — WebSocket server for React UI palette
├── config.py           — ~/.config/aulinx/config.toml loader
├── audit.py            — JSONL audit log with secret redaction
├── history.py          — Session persistence + resume
├── completer.py        — Tab completion for /commands and @tools
├── doctor.py           — Dependency diagnostics (aulinx --doctor)
├── context/desktop.py  — AT-SPI + system state collector
└── tools/
    ├── base.py         — Tool + Tier types, Ollama schema generation
    ├── registry.py     — Registration, permission checking, kwarg stripping
    └── 23 tool modules (92 tools total)
```

## Key Patterns
- **Native tool calling**: Agent sends `tools` array to Ollama `/api/chat`. Model returns structured `tool_calls`. Falls back to regex JSON extraction for models without tool support.
- **Kwarg stripping**: `registry.execute()` uses `inspect.signature()` to strip hallucinated parameters before calling tool functions.
- **Permission tiers**: OBSERVE (auto), LOW_RISK (auto+log), MUTATE (confirm once), DESTRUCTIVE (always confirm), IRREVERSIBLE (always + warning).
- **Core tools**: Only 50 most-used tools sent to Ollama (fits in context window). All 92 still available via fallback.
- **Tool schema**: `Tool.to_ollama_schema()` auto-generates OpenAI function calling JSON Schema from parameter descriptions.

## Dev Setup
```bash
pip install -e ".[dev]"
make test    # 71 unit tests + 35 integration tests (Linux only)
make lint    # ruff
```

## Docker Desktop (for testing GUI)
```bash
docker compose -f docker/docker-compose.yml up
# Open http://localhost:6080/vnc.html (password: aulinx)
# Inside: aulinx -m qwen2.5:14b --base-url http://host.docker.internal:11434
```

## Code Style
- Python 3.10+ with type hints
- async/await for all tool functions
- Rich for terminal UI, react-markdown for web UI
- One file per tool domain in aulinx/tools/
- Tools return dicts/lists (JSON-serializable), `{"error": "..."}` on failure
