# Architecture

## Overview

```
┌──────────────────────────────────────────────────┐
│  UI (React + Vite)                                │
│  Command palette at localhost:5173                │
│  Connects via WebSocket to backend                │
├──────────────────────────────────────────────────┤
│  WebSocket Server (aulinx --serve, port 8765)     │
│  Bridges UI ↔ Agent                               │
├──────────────────────────────────────────────────┤
│  Agent (aulinx/agent.py)                          │
│  Streaming LLM chat + tool call extraction        │
│  Retry logic, error handling, audit logging       │
├──────────────────────────────────────────────────┤
│  Tool Registry (aulinx/tools/registry.py)         │
│  92 tools across 23 modules                       │
│  5-tier permission system                         │
├──────────────────────────────────────────────────┤
│  Ollama (local LLM server)                        │
│  Runs gemma3:12b, qwen2.5:14b, etc.              │
├──────────────────────────────────────────────────┤
│  Linux Desktop (GNOME, KDE, Sway, etc.)           │
│  Accessed via AT-SPI, D-Bus, CLI tools            │
└──────────────────────────────────────────────────┘
```

## Key Components

### Agent (`aulinx/agent.py`)
The core loop: receives user text → builds system prompt with context + tools → streams response from Ollama → extracts JSON tool calls → executes tools → feeds results back to LLM → repeats.

### Tool Registry (`aulinx/tools/registry.py`)
Imports all tool modules, registers `Tool` objects, handles permission checking and execution. Tools are defined in `aulinx/tools/base.py` with a `Tier` enum for permission levels.

### Desktop Context (`aulinx/context/desktop.py`)
Collects current desktop state (focused window, running apps, clipboard, system info) for the LLM system prompt. Uses AT-SPI when available, falls back to CLI tools.

### WebSocket Server (`aulinx/server.py`)
Bridges the React UI to the agent. Streams tokens, tool calls, and results as JSON events over WebSocket.

### Config (`aulinx/config.py`)
Loads `~/.config/aulinx/config.toml` with model, temperature, and permission overrides.

### Audit (`aulinx/audit.py`)
Logs every tool call to `~/.local/share/aulinx/audit.jsonl` with timestamps, arguments (secrets redacted), results, and duration.

## Data Flow

1. User types in UI or CLI
2. Agent builds system prompt with desktop context + compact tool list
3. Ollama streams response tokens
4. Agent extracts `{"tool": "...", "args": {...}}` from response
5. Permission check (auto-allow, confirm, or deny based on tier)
6. Tool executes (AT-SPI, subprocess, file I/O, etc.)
7. Result fed back to LLM for interpretation
8. LLM may call another tool or respond with text
9. Everything logged to audit trail
