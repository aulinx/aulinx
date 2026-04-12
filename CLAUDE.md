# Aulinx — AI-Native Linux Desktop

## Project Overview
Aulinx is an AI agent with 207 tools that controls a Linux desktop through natural language. Uses AT-SPI (accessibility API) + custom Wayland compositor for semantic GUI control, with multi-provider LLM support (Ollama, OpenAI, Anthropic, Gemini).

## Architecture
```
aulinx/
├── cli.py              — Interactive REPL + one-shot + slash commands + --serve
├── agent.py            — Multi-provider LLM tool calling + planner + recovery + audit
├── llm.py              — LLMClient abstraction: Ollama, OpenAI, Anthropic, Gemini
├── planner.py          — ReAct-style structured planning (3-8 step plans)
├── recovery.py         — Error recovery with tool alternatives + strategy fallback
├── perception.py       — Hybrid observation: semantic tree vs screenshot decision
├── grounding.py        — Action grounding: element names → exact (x,y) coordinates
├── tool_selector.py    — Dynamic tool selection based on task intent
├── summarizer.py       — History compression to reduce token usage
├── outcomes.py         — Learning from outcomes across sessions
├── multi_agent.py      — Multi-agent task delegation + parallel execution
├── server.py           — WebSocket server for React UI palette
├── config.py           — ~/.config/aulinx/config.toml loader
├── audit.py            — JSONL audit log with secret redaction
├── history.py          — Session persistence + resume
├── long_memory.py      — Keyword-based RAG across sessions
├── completer.py        — Tab completion for /commands and @tools
├── doctor.py           — Dependency diagnostics (aulinx --doctor)
├── mcp_server.py       — MCP server for Claude Desktop integration
├── plugins.py          — Plugin system with manifest support (~/.config/aulinx/plugins/)
├── context/desktop.py  — AT-SPI + system state collector
└── tools/
    ├── base.py         — Tool + Tier types, Ollama schema generation
    ├── registry.py     — Registration, permission checking, kwarg stripping
    └── 42 tool modules (207 tools total)
```

## Three-Tier Architecture
- **Core** (119 tools): Headless — files, git, process, network, docker, services, system
- **Desktop** (157 tools): + AT-SPI GUI control, screenshots, audio, display, input sim
- **Compositor** (207 tools): + Custom Wayland compositor IPC, scene graph, input injection

## Key Patterns
- **Multi-provider LLM**: `create_client(provider, model)` factory in `llm.py`. Supports Ollama, OpenAI, Anthropic, Gemini with streaming + tool calling.
- **ReAct planning**: `planner.py` generates 3-8 step plans before tool execution, injects plan context into system prompt, re-plans after observations.
- **Error recovery**: `recovery.py` tracks failures, suggests alternative tools (e.g., atspi_do_action → compositor_click), switches strategy after 3 consecutive failures.
- **Hybrid perception**: `perception.py` decides per-step whether to use semantic tree, screenshot, or both based on app type and tree density.
- **Action grounding**: `grounding.py` resolves element references ("Save button") to exact screen coordinates from the a11y tree, eliminating coordinate hallucination.
- **Dynamic tool selection**: `tool_selector.py` picks task-relevant tools instead of static CORE_TOOLS set. "manage files" → file tools, "browse web" → browser tools.
- **History summarization**: `summarizer.py` compresses old conversation turns to reduce token usage (384K → ~150K tokens/task).
- **Learning from outcomes**: `outcomes.py` records task results (goal, plan, actions, success/failure) and retrieves relevant past experience for similar future tasks.
- **Native tool calling**: Agent sends `tools` array to LLM. Model returns structured `tool_calls`. Falls back to regex JSON extraction for models without tool support.
- **Kwarg stripping**: `registry.execute()` uses `inspect.signature()` to strip hallucinated parameters before calling tool functions.
- **Permission tiers**: OBSERVE (auto), LOW_RISK (auto+log), MUTATE (confirm once), DESTRUCTIVE (always confirm), IRREVERSIBLE (always + warning).
- **Core tools**: ~50 most-used tools sent to LLM (fits in context window). All 207 still available via fallback.
- **Tool schema**: `Tool.to_ollama_schema()` auto-generates OpenAI function calling JSON Schema from parameter descriptions.

## Dev Setup
```bash
pip install -e ".[dev]"
make test    # 301 tests (Linux-specific tests skip on other platforms)
make lint    # ruff
```

## Docker Desktop (for testing GUI)
```bash
docker compose -f docker/docker-compose.yml up
# Open http://localhost:6080/vnc.html (password: aulinx)
# Inside: aulinx -m qwen2.5:14b --base-url http://host.docker.internal:11434
```

## Benchmark (OSWorld)
```bash
# Dry run (no VM needed)
python -m benchmark.run_benchmark --dry-run

# With model profiles
python -m benchmark.run_benchmark --profile cloud   # Claude Sonnet
python -m benchmark.run_benchmark --profile best    # Claude Opus
python -m benchmark.run_benchmark --profile local   # Qwen/Ollama
```

## Code Style
- Python 3.10+ with type hints
- async/await for all tool functions
- Rich for terminal UI, react-markdown for web UI
- One file per tool domain in aulinx/tools/
- Tools return dicts/lists (JSON-serializable), `{"error": "..."}` on failure
