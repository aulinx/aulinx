# Aulinx Architecture

## Three-Tier System

```
┌──────────────────────────────────────────────────────────────────┐
│                        User Interface                            │
│  CLI (REPL)  │  Web Dashboard  │  Voice  │  MCP  │  Daemon      │
├──────────────────────────────────────────────────────────────────┤
│                      Python Agent (aulinx/)                      │
│  Mode Detection → Tool Registry → LLM (Ollama) → Tool Execution │
│  Three modes: core (119) │ desktop (157) │ compositor (187) tools│
├──────────────┬───────────────────────┬───────────────────────────┤
│ Tier 1: Core │ Tier 2: Desktop       │ Tier 3: Compositor        │
│              │                       │                           │
│ files, git   │ AT-SPI (pyatspi)      │ aulinx-compositor (Rust)  │
│ process      │ window control        │ Smithay Wayland compositor │
│ network      │ GUI element access    │ Semantic scene graph       │
│ packages     │ screenshot (grim)     │ 23 IPC commands            │
│ docker       │ input sim (wtype)     │ Input injection            │
│ services     │ audio/display/theme   │ Real-time events           │
│ system, cron │                       │ DRM/udev backend           │
├──────────────┴───────────────────────┴───────────────────────────┤
│                    Linux Kernel + Hardware                        │
└──────────────────────────────────────────────────────────────────┘
```

## Python Agent

### Core Components

| Component | File | Purpose |
|-----------|------|---------|
| **Agent** | `aulinx/agent.py` | LLM chat loop with streaming tool calling |
| **Tool Registry** | `aulinx/tools/registry.py` | Mode-filtered tool registration + execution |
| **Desktop Context** | `aulinx/context/desktop.py` | Gathers system state for LLM prompt |
| **CLI** | `aulinx/cli.py` | Mode detection, argument parsing, REPL |
| **Config** | `aulinx/config.py` | TOML config for model, permissions |
| **Audit** | `aulinx/audit.py` | Tool call logging with timing |
| **LLM Client** | `aulinx/llm.py` | Ollama streaming with native tool calling |
| **WebSocket Server** | `aulinx/server.py` | Bridges React UI to agent |
| **MCP Server** | `aulinx/mcp_server.py` | Expose tools to Claude Desktop |
| **Doctor** | `aulinx/doctor.py` | System dependency checker |

### Mode-Aware Design

```python
# Auto-detects environment
mode = detect_mode()  # → "core" | "desktop" | "compositor"

# Filters tools — headless server won't see GUI tools
registry = ToolRegistry(mode=mode)

# Mode-specific system prompt
prompt = SYSTEM_PROMPTS[mode]  # Different instructions per tier
```

### Data Flow

```
User input → Agent builds prompt (context + tools) → Ollama streams response
→ Extract tool calls → Permission check → Execute → Feed result back → Loop
```

## Compositor (Rust)

### Module Structure

```
compositor/crates/compositor/src/
├── main.rs              Entry point, event loop
├── state.rs             AulinxState: protocol handlers, window management
├── config.rs            TOML configuration
├── ipc.rs               JSON-RPC server (23 commands)
├── semantic_bridge.rs   Window events → scene graph sync
├── input/
│   ├── mod.rs           Keyboard shortcuts (10 bindings)
│   └── injection.rs     Type, click, drag, scroll, move
└── backend/
    ├── mod.rs            Backend abstraction
    ├── winit.rs          Window-in-window mode
    └── udev.rs           Bare metal (DRM/KMS/GBM)
```

### Scene Graph (aulinx-semantic)

```
compositor/crates/semantic/src/
├── graph.rs             Tree data structure
├── node.rs              Screen → Window → Element hierarchy
├── query.rs             JSON-RPC query engine
├── diff.rs              Change detection + event types
└── sources/
    ├── direct.rs         Compositor integration (zero-latency)
    ├── atspi.rs          AT-SPI source (GNOME/KDE)
    └── compositor_ipc.rs External compositor IPC (Sway/Hyprland)
```

### IPC Protocol

23 JSON-RPC commands over Unix socket. See [compositor-ipc.md](compositor-ipc.md).

| Category | Commands |
|----------|----------|
| **Scene** | windows, focused, find, graph, element_at, window_count, screenshot, diff, wait_for, status, subscribe, unsubscribe, list_commands |
| **Input** | type, key, click, drag, scroll, move |
| **Window** | focus, close, swap_master, spawn |

### Wayland Protocols (11)

XDG shell, SHM, compositor, data device, output, XDG decoration, primary selection, XDG activation, fractional scale, wlr-layer-shell, viewporter

## Key Design Decisions

1. **Semantic over screenshot**: AT-SPI reads the actual UI tree. No OCR, no pixel parsing.
2. **Own compositor = ground truth**: The scene graph is always accurate because we rendered it.
3. **Mode filtering**: Don't send 187 tool schemas to an LLM on a headless server.
4. **JSON-RPC over Unix socket**: Simple, fast, language-agnostic.
5. **Event-driven**: Subscribe to changes instead of polling screenshots.
6. **Graceful degradation**: Every tool fails with a clear error, never crashes.
