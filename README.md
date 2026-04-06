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

Aulinx replaces your Linux desktop (GNOME/KDE) with an AI-first interface. A local LLM running on your GPU is the primary way you interact with your computer.

```
aulinx > why is my computer slow right now?

  > process_list(sort_by=cpu)

  ┌─ Result ──────────────────────────────────────────┐
  │ firefox (42% CPU), code (18% CPU), slack (8% CPU) │
  └───────────────────────────────────────────────────┘

  Firefox is consuming 42% of your CPU. It has 47 tabs open.
  Want me to find the heaviest tabs, or kill some background processes?
```

Aulinx sees **every app** on your desktop simultaneously via AT-SPI (Linux accessibility API), can read UI elements, click buttons, type text, manage files, control system settings — all through natural language.

## How It Works

Aulinx combines three things nobody else has put together:

1. **AT-SPI** (Linux accessibility API) to read and control any app's UI — buttons, text, menus — semantically, not by screenshots
2. **Local LLM** (14B model on your GPU, ~30-50 tok/s) for natural language understanding and tool calling
3. **55 desktop tools** covering windows, files, apps, processes, network, audio, display, bluetooth, power, themes, clipboard, notifications, D-Bus, and persistent memory

```
┌──────────────────────────────────────────────────┐
│  CLI (interactive REPL or one-shot commands)      │
├──────────────────────────────────────────────────┤
│  Agent (streaming LLM + tool calling + audit)     │
├──────────────────────────────────────────────────┤
│  55 Tools across 17 modules                       │
│  AT-SPI, files, apps, process, network, audio...  │
├──────────────────────────────────────────────────┤
│  Linux desktop (GNOME, KDE, Sway, etc.)           │
│  UNTOUCHED — Aulinx runs on top                   │
└──────────────────────────────────────────────────┘
```

## Getting Started

> Phase 0 — works on any existing Linux desktop. No custom compositor needed.

### Prerequisites

- Linux with a running desktop (Wayland or X11)
- Python 3.10+
- [Ollama](https://ollama.ai) installed and running
- NVIDIA GPU recommended (RTX 3060+ for good performance)
- Optional: `python3-pyatspi` for GUI control (`apt install python3-pyatspi`)

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

# Use a different model
aulinx -m qwen2.5:7b

# Resume last conversation
aulinx --resume
```

### Slash Commands

```
/tools    — List all 55 available tools
/context  — Show current desktop context
/history  — Browse past conversation sessions
/audit    — Show recent tool calls with timing
/clear    — Clear conversation history
/help     — Show help
```

### Configuration

Config lives at `~/.config/aulinx/config.toml` (auto-created on first run):

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

55 tools across 17 modules, organized by permission tier:

| Category | Tools | Tier |
|----------|-------|------|
| **Window** | list, get_focused | Read |
| **AT-SPI** | get_tree, find_elements, read_text, do_action, set_text, screenshot | Read / Mutate |
| **Files** | read, write, edit, move, trash, list, search | Read / Mutate / Destructive |
| **Apps** | launch, list_running | Read / Mutate |
| **Process** | list, kill | Read / Destructive |
| **Network** | status, wifi_list, wifi_connect, wifi_disconnect | Read / Mutate / Destructive |
| **Audio** | get_volume, set_volume, mute | Read / Low-risk |
| **Display** | list, brightness | Read / Low-risk |
| **Power** | status, profile, suspend, shutdown | Read / Mutate / Irreversible |
| **Theme** | get, set_dark, wallpaper_set | Read / Low-risk |
| **Bluetooth** | status, scan, connect, disconnect, toggle | Read / Mutate |
| **Clipboard** | get, set | Read / Low-risk |
| **Notifications** | send | Low-risk |
| **Memory** | store, get, delete, list_namespaces | Read / Low-risk / Destructive |
| **D-Bus** | list_services, introspect, call | Read / Destructive |
| **System** | info, shell_exec | Read / Destructive |
| **Workflow** | context_get, wait, audit_recent | Read |

### Permission Tiers

| Tier | Behavior |
|------|----------|
| **Read** | Always auto-allowed |
| **Low-risk** | Auto-allowed, logged |
| **Mutate** | Confirms first time per session, then auto |
| **Destructive** | Always confirms |
| **Irreversible** | Always confirms with extra warning |

## Roadmap

- [x] Research & architecture design (15-part technical document)
- [x] **Phase 0**: AI agent + 55 tools + CLI + tests + CI
- [ ] **Phase 1**: Command palette overlay on existing Wayland compositor
- [ ] **Phase 2**: Custom Wayland compositor with AI IPC
- [ ] **Phase 3**: Full AI desktop environment (daily-drivable)
- [ ] **Phase 4**: Distributable Linux distro image

## Name

**Au** (gold, element 79) + **linx** (Linux / lynx). The gold standard of AI-powered Linux.

## Contributing

```bash
pip install -e ".[dev]"
pytest tests/ -v          # run tests
ruff check aulinx/ tests/ # lint
```

## License

MIT
