<p align="center">
  <h1 align="center">Aulinx</h1>
  <p align="center"><strong>AI-native Linux. Desktop to server.</strong></p>
  <p align="center">Other AI agents look at your screen. Aulinx IS the screen.</p>
</p>

<p align="center">
  <a href="https://github.com/aulinx/aulinx/actions"><img src="https://github.com/aulinx/aulinx/workflows/CI/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/aulinx/"><img src="https://img.shields.io/pypi/v/aulinx" alt="PyPI"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python"></a>
  <a href="https://www.rust-lang.org/"><img src="https://img.shields.io/badge/rust-1.75+-orange.svg" alt="Rust"></a>
</p>

<p align="center">
  <a href="#what-is-aulinx">What is it?</a> |
  <a href="#how-it-works">How it works</a> |
  <a href="#getting-started">Getting started</a> |
  <a href="#compositor">Compositor</a> |
  <a href="#tools">Tools</a> |
  <a href="#roadmap">Roadmap</a>
</p>

---

## What is Aulinx?

Aulinx is an AI layer for Linux that works at three levels:

```
┌─────────────────────────────────────────────────────────┐
│  Tier 3: Aulinx Compositor                              │
│  Custom Wayland compositor with semantic scene graph     │
│  AI sees every pixel because it rendered them            │
├─────────────────────────────────────────────────────────┤
│  Tier 2: Aulinx Desktop                                 │
│  AT-SPI GUI control on any desktop (GNOME/KDE/Sway)     │
│  Click buttons, read menus, type text — semantically     │
├─────────────────────────────────────────────────────────┤
│  Tier 1: Aulinx Core                                    │
│  Files, git, process, network, docker, system, packages  │
│  Works headless — servers, WSL, Docker, SSH              │
└─────────────────────────────────────────────────────────┘
```

**187 tools** across all tiers. A **Wayland compositor** (Rust) with 33 IPC commands. **Semantic desktop understanding** — not screenshots, not OCR.

```
aulinx > why is my computer slow right now?

  > process_list(sort_by=cpu)

  ┌─ Result (9ms) ────────────────────────────────────┐
  │ firefox (42% CPU), code (18% CPU), slack (8% CPU)  │
  └────────────────────────────────────────────────────┘

  Firefox is consuming 42% of your CPU with 47 tabs open.
  Want me to kill background processes?

aulinx > search for "wayland compositor" in Firefox

  > atspi_set_text(app_name=firefox, element_name=Search, text=wayland compositor)

  ┌─ Result (40ms) ──────────────────────────────────┐
  │ "Set text on 'Search': 'wayland compositor'"      │
  └────────────────────────────────────────────────────┘
```

Unlike other AI desktop agents that use screenshots, Aulinx reads the actual UI structure — **semantic, not pixel-based. No OCR needed.**

## How It Works

Aulinx has two deployment modes:

```
Mode 1: Agent on any desktop          Mode 2: Full AI compositor
(works today on GNOME/KDE/Sway)       (custom Wayland compositor)

┌─────────────────────────────┐      ┌─────────────────────────────┐
│  CLI / Web UI / Voice / MCP │      │  CLI / Web UI / Voice / MCP │
├─────────────────────────────┤      ├─────────────────────────────┤
│  Agent (187 tools + LLM)    │      │  Agent (187 tools + LLM)    │
├─────────────────────────────┤      ├─────────────────────────────┤
│  aulinx-semanticd (daemon)  │      │  aulinx-compositor (Rust)   │
│  AT-SPI → Scene Graph → IPC │      │  Smithay + Scene Graph      │
├─────────────────────────────┤      │  + Input Injection + IPC    │
│  GNOME / KDE / Sway / Xfce  │      │  Wayland compositor IS the  │
│  Your existing desktop       │      │  AI-native desktop          │
└─────────────────────────────┘      └─────────────────────────────┘
```

**The scene graph** is the key abstraction — a structured representation of every window, UI element, and action on your desktop. Both modes expose the same IPC protocol:

```json
{"method": "scene.windows"}         // list all windows with metadata
{"method": "scene.find", "params": {"role": "button", "name": "Save"}}
{"method": "input.type", "params": {"text": "hello"}}
{"method": "input.key", "params": {"combo": "ctrl+s"}}
{"method": "window.focus", "params": {"window_id": 1}}
{"method": "window.close", "params": {"window_id": 1}}
```

## Getting Started

### Mode 1: Agent on your existing desktop

> Works on any Linux desktop (GNOME, KDE, Sway, Xfce). No custom compositor needed.

#### Prerequisites

- Linux with a running desktop (Wayland or X11)
- Python 3.10+
- [Ollama](https://ollama.ai) with a model that supports tool calling
- `python3-pyatspi` for GUI control (`apt install python3-pyatspi`)

#### Install

```bash
git clone https://github.com/aulinx/aulinx.git
cd aulinx
pip install -e .
ollama pull qwen2.5:14b
```

#### Run

```bash
# Interactive mode
aulinx

# One-shot command
aulinx -c "what windows do I have open?"

# Use a specific model
aulinx -m qwen2.5:14b

# Start the web UI
aulinx --serve
cd ui && npm install && npm run dev
# Open http://localhost:5173

# Resume last conversation
aulinx --resume

# Background daemon with global hotkey (Super+Space)
aulinx --daemon

# Voice input mode (requires faster-whisper)
aulinx --voice

# MCP server for Claude Desktop
aulinx --mcp

# Check system dependencies
aulinx --doctor
```

### Docker (test with a full desktop)

```bash
docker compose -f docker/docker-compose.yml up
# Open http://localhost:6080/vnc.html (password: aulinx)
# Inside container: aulinx -m qwen2.5:14b --base-url http://host.docker.internal:11434
```

### Mode 2: AI compositor (Rust)

> The custom Wayland compositor with built-in AI understanding.

#### Prerequisites

- Linux with Wayland support
- Rust 1.75+ (nightly recommended)
- System libs: `libwayland-dev libinput-dev libudev-dev libgbm-dev libxkbcommon-dev libseat-dev`

#### Build

```bash
cd compositor
cargo build -p aulinx-compositor -p aulinx-semanticd
```

#### Run

```bash
# Inside an existing Wayland session (opens as a window)
WAYLAND_DISPLAY=wayland-0 ./target/debug/aulinx-compositor

# Launch apps inside the compositor
WAYLAND_DISPLAY=wayland-1 foot    # terminal
WAYLAND_DISPLAY=wayland-1 firefox # browser

# Connect an AI agent via IPC
python3 test_client.py
```

## Compositor

The Aulinx compositor is a Wayland compositor built on [Smithay](https://github.com/Smithay/smithay) with a semantic scene graph baked in. Every window, UI element, and layout change is exposed as structured data over a Unix socket IPC.

### What makes it different

| Feature | Traditional WM | Aulinx Compositor |
|---------|---------------|-------------------|
| Window info | EWMH/IPC hacks | Semantic scene graph |
| UI elements | Not accessible | AT-SPI bridge built-in |
| AI input | xdotool/ydotool | Native keyboard injection |
| Events | Poll-based | Push subscriptions |
| Data format | Mixed protocols | Single JSON-RPC API |

### IPC protocol

```bash
# Connect to the compositor's IPC socket
# Default: $XDG_RUNTIME_DIR/aulinx/semantic.sock

# Query windows
echo '{"jsonrpc":"2.0","id":1,"method":"scene.windows","params":{}}' | \
  socat - UNIX-CONNECT:$XDG_RUNTIME_DIR/aulinx/semantic.sock

# Response:
# {"result": [{"id": 1, "app_id": "foot", "title": "foot", 
#   "geometry": {"x": 0, "y": 0, "width": 1280, "height": 800}}]}

# Inject text into the focused window
echo '{"jsonrpc":"2.0","id":2,"method":"input.type","params":{"text":"hello"}}' | ...

# Inject key combos
echo '{"jsonrpc":"2.0","id":3,"method":"input.key","params":{"combo":"ctrl+s"}}' | ...

# Focus a window
echo '{"jsonrpc":"2.0","id":4,"method":"window.focus","params":{"window_id":1}}' | ...

# Close a window
echo '{"jsonrpc":"2.0","id":5,"method":"window.close","params":{"window_id":1}}' | ...

# Subscribe to window events (open/close/focus)
echo '{"jsonrpc":"2.0","id":6,"method":"scene.subscribe","params":{"filter":"*"}}' | ...
```

### Architecture

```
aulinx-compositor (Rust, ~7,900 LOC)
├── Smithay Wayland compositor (winit + DRM backends)
├── Semantic bridge (window → scene graph sync)
├── IPC server (JSON-RPC over Unix socket)
├── Input injection (xkbcommon keymap → keyboard events)
└── Tiling layout (equal-width horizontal split)

aulinx-semantic (Rust library)
├── Scene graph (windows, elements, actions)
├── AT-SPI source (reads GNOME/KDE UI trees)
├── Direct source (compositor integration)
├── Diff engine (push events on changes)
└── Query engine (scene.windows, scene.find, etc.)
```

## Tools

187 tools across 43 modules. Selected highlights below — run `aulinx --doctor` or `/tools` for the full list:

| Category | Tools | Count |
|----------|-------|-------|
| **Window** | list, get_focused | 2 |
| **AT-SPI** | get_tree, find_elements, do_action, read_text, set_text, screenshot | 6 |
| **Files** | read, write, edit, move, trash, list, search | 7 |
| **Text** | count, grep, replace, head, tail | 5 |
| **Git** | status, log, diff, commit, branch, stash | 6 |
| **Apps** | launch, list_running | 2 |
| **Process** | list, kill | 2 |
| **Services** | list, status, start, stop, restart | 5 |
| **Network** | status, wifi_list, wifi_connect, wifi_disconnect | 4 |
| **Audio** | get_volume, set_volume, mute | 3 |
| **Display** | list, brightness | 2 |
| **Power** | status, profile, suspend, shutdown | 4 |
| **Theme** | get, set_dark, wallpaper_set | 3 |
| **Bluetooth** | status, scan, connect, disconnect, toggle | 5 |
| **Input** | key_combo, type_text | 2 |
| **Session** | who_am_i, uptime, disk_usage, env_get | 4 |
| **Packages** | search, install, list_installed | 3 |
| **XDG** | open, default_app_get, default_app_set, mime_type_of | 4 |
| **Timer** | set_timer, cancel_timer, list_timers | 3 |
| **Clipboard** | get, set | 2 |
| **Notifications** | send | 1 |
| **Memory** | store, get, delete, list_namespaces | 4 |
| **D-Bus** | list_services, introspect, call | 3 |
| **OCR** | screenshot_ocr, image_ocr | 2 |
| **DateTime** | now, convert, calendar_show | 3 |
| **System** | info, shell_exec | 2 |
| **Workflow** | context_get, wait, audit_recent | 3 |
| **Workflows** | create, list, run, delete, toggle | 5 |
| **Long Memory** | remember, recall, recall_recent, forget, memory_count | 5 |
| **Server** | journal_logs, docker_ps, docker_logs, port_list, firewall_status, cron_list, disk_health, system_logs_summary | 8 |
| **Compositor** | summary, describe, ascii, suggest, status, config, ping, windows, focused, find_window, element_at, screenshot, annotated_screenshot, window_count, type, key, click, drag, scroll, spawn, focus, close, minimize, swap_master, set_ratio, set_gap, batch, diff, wait_for, run_and_type | 30 |

> The table lists representative tools per category; remaining tools (clipboard, archive, calc, schedule, sysadmin, productivity, AI, and more) bring the total to 187.

### Permission Tiers

| Tier | Behavior |
|------|----------|
| **Read** | Always auto-allowed |
| **Low-risk** | Auto-allowed, logged |
| **Mutate** | Confirms first time per session, then auto |
| **Destructive** | Always confirms |
| **Irreversible** | Always confirms with extra warning |

### Slash Commands

```
/tools    - List all available tools
/context  - Show current desktop context
/history  - Browse past conversation sessions
/audit    - Show recent tool calls with timing
/doctor   - Check system dependencies
/clear    - Clear conversation history
/help     - Show help
```

### Configuration

Config at `~/.config/aulinx/config.toml` (auto-created on first run):

```toml
[llm]
model = "qwen2.5:14b"
base_url = "http://localhost:11434"
temperature = 0.3

[permissions]
# Override tool permission tiers
# shell_exec = "mutate"  # uncomment to lower confirmation requirement
```

## Roadmap

**Released:**

- [x] **v0.1–v0.3**: 92→103 tools + CLI + web UI + tests + audit + long-term memory + daemon + voice + MCP + plugins
- [x] **v0.4.0**: Semantic compositor — Wayland compositor with scene graph, 20 IPC commands, input injection, DRM/udev backend
- [x] **v0.5.0** *(current)*: Multi-provider LLM (Ollama/OpenAI/Anthropic/Gemini/Qwen), ReAct planner, error recovery, OSWorld benchmark harness, hybrid perception, action grounding, dynamic tool selection, task decomposition, sandboxed execution, history summarization, learning from outcomes, multi-agent delegation, Python SDK, autonomous mode, portal-first screen capture

**Planned:**

- [ ] **v1.0**: Daily-drivable compositor, full OSWorld-Verified benchmark run, cross-platform stubs, one-command install

See [CHANGELOG.md](CHANGELOG.md) for the detailed per-release history.

## Name

**Au** (gold, element 79) + **linx** (Linux / lynx). The gold standard of AI-powered Linux.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, code style, and how to add new tools.

```bash
# Python agent
pip install -e ".[dev]"
make test   # run tests
make lint   # check code style

# Rust compositor
cd compositor
cargo build
cargo test
```

## License

MIT
