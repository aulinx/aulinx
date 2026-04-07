<p align="center">
  <h1 align="center">Aulinx</h1>
  <p align="center"><strong>The AI-native Linux desktop.</strong></p>
  <p align="center">Cursor for your entire operating system.</p>
</p>

<p align="center">
  <a href="https://github.com/aulinx/aulinx/actions"><img src="https://github.com/aulinx/aulinx/workflows/CI/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/aulinx/"><img src="https://img.shields.io/pypi/v/aulinx" alt="PyPI"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python"></a>
</p>

<p align="center">
  <a href="#what-is-aulinx">What is it?</a> |
  <a href="#how-it-works">How it works</a> |
  <a href="#getting-started">Getting started</a> |
  <a href="#tools">Tools</a> |
  <a href="#roadmap">Roadmap</a>
</p>

---

## What is Aulinx?

Aulinx is an AI agent that controls your entire Linux desktop through natural language. It sees every app via AT-SPI, reads UI elements, clicks buttons, types text, manages files, and controls system settings — with 103 tools and a local LLM.

```
aulinx > why is my computer slow right now?

  > process_list(sort_by=cpu)

  ┌─ Result (9ms) ────────────────────────────────────┐
  │ firefox (42% CPU), code (18% CPU), slack (8% CPU)  │
  └────────────────────────────────────────────────────┘

  Firefox is consuming 42% of your CPU with 47 tabs open.
  Want me to kill background processes?

aulinx > type "Hello from Aulinx!" in gedit

  > atspi_set_text(app_name=gedit, element_name=Search, text=Hello from Aulinx!)

  ┌─ Result (40ms) ──────────────────────────────────┐
  │ "Set text on 'Search': 'Hello from Aulinx!'"      │
  └────────────────────────────────────────────────────┘
```

Unlike other AI desktop agents that use screenshots, Aulinx reads the actual UI structure via AT-SPI — **3x faster, works semantically, no OCR needed**.

## How It Works

```
┌──────────────────────────────────────────────────┐
│  Command Palette UI (React + WebSocket)           │
│  Or CLI (interactive REPL / one-shot)             │
├──────────────────────────────────────────────────┤
│  Agent (Ollama native tool calling + audit)        │
├──────────────────────────────────────────────────┤
│  92 Tools across 26 modules                       │
│  AT-SPI, files, git, process, network, audio...   │
├──────────────────────────────────────────────────┤
│  Linux desktop (GNOME, KDE, Sway, Xfce)           │
│  UNTOUCHED — Aulinx runs on top                   │
└──────────────────────────────────────────────────┘
```

1. **AT-SPI** (Linux accessibility API) reads and controls any app's UI — buttons, text, menus — semantically
2. **Ollama native tool calling** with qwen2.5:14b or any compatible model
3. **92 desktop tools** covering every aspect of a Linux desktop
4. **5-tier permission system** — read-only auto-allowed, destructive always confirms

## Getting Started

> Works on any existing Linux desktop (GNOME, KDE, Sway, Xfce). No custom compositor needed.

### Prerequisites

- Linux with a running desktop (Wayland or X11)
- Python 3.10+
- [Ollama](https://ollama.ai) with a model that supports tool calling
- NVIDIA GPU recommended (RTX 3060+ for good performance)
- `python3-pyatspi` for GUI control (`apt install python3-pyatspi`)

### Install

```bash
git clone https://github.com/aulinx/aulinx.git
cd aulinx
pip install -e .
ollama pull qwen2.5:14b
```

### Run

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

### Slash Commands

```
/tools    — List all 92 available tools
/context  — Show current desktop context
/history  — Browse past conversation sessions
/audit    — Show recent tool calls with timing
/doctor   — Check system dependencies
/clear    — Clear conversation history
/help     — Show help
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

## Tools

103 tools across 26 modules:

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

### Permission Tiers

| Tier | Behavior |
|------|----------|
| **Read** | Always auto-allowed |
| **Low-risk** | Auto-allowed, logged |
| **Mutate** | Confirms first time per session, then auto |
| **Destructive** | Always confirms |
| **Irreversible** | Always confirms with extra warning |

## Roadmap

- [x] Research & architecture design
- [x] **Phase 0**: 103 tools + CLI + tests + CI + audit + memory
- [x] **Phase 1**: Web command palette UI + WebSocket server
- [x] **Tested**: AT-SPI GUI control on real Linux (Docker + VMware + VNC)
- [x] Daemon mode, voice interface, MCP server, plugin system
- [x] Workflow automation, long-term memory, web dashboard
- [x] 107 tests, systemd service, ydotool GNOME support
- [ ] **Phase 2**: Custom Wayland compositor with AI IPC
- [ ] **Phase 3**: Full AI desktop environment (daily-drivable)
- [ ] **Phase 4**: Distributable Linux distro image

## Name

**Au** (gold, element 79) + **linx** (Linux / lynx). The gold standard of AI-powered Linux.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, code style, and how to add new tools.

```bash
pip install -e ".[dev]"
make test   # run tests
make lint   # check code style
```

## License

MIT
