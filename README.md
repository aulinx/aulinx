<p align="center">
  <h1 align="center">Aulinx</h1>
  <p align="center"><strong>The AI-native Linux desktop.</strong></p>
  <p align="center">Cursor for your entire operating system.</p>
</p>

<p align="center">
  <a href="#what-is-aulinx">What is Aulinx?</a> |
  <a href="#architecture">Architecture</a> |
  <a href="#getting-started">Getting Started</a> |
  <a href="#roadmap">Roadmap</a>
</p>

---

## What is Aulinx?

Aulinx replaces your traditional Linux desktop (GNOME/KDE) with an AI-first interface. A local LLM running on your GPU is the primary way you interact with your computer.

Instead of clicking through menus, switching between apps, and copy-pasting data around, you tell Aulinx what you want:

```
> email the chart from this spreadsheet to Sarah
> why is my computer slow right now?
> do what I did last Tuesday with the client reports
> let's work on the presentation
```

Aulinx sees **every app** on your desktop simultaneously, understands what you're doing, and can act across applications — something no single app can do.

## How It Works

Aulinx combines three things nobody else has put together:

1. **AT-SPI** (Linux accessibility API) to read and control any app's UI — buttons, text, menus — semantically, not by screenshots
2. **Local LLM** (14B model on your GPU) for natural language understanding and tool calling
3. **Custom Wayland compositor** with privileged AI access for input injection and screen capture

```
You: "Put the numbers from this spreadsheet into an email to Sarah with a chart"

Aulinx:
  1. Reads spreadsheet data via AT-SPI (LibreOffice Table interface)
  2. Generates chart (Python/matplotlib)
  3. Opens email composer via D-Bus
  4. Sets recipient, subject, body, attaches chart
  5. Shows you a preview before sending
```

## Architecture

```
+----------------------------------------------------------+
|  AI Interface (Tauri + React, layer-shell overlay)        |
|  Command palette + chat + generated UI                    |
+----------------------------------------------------------+
|  AI Backend (Python/Rust)                                 |
|  Local LLM (Ollama) + AT-SPI client + 57 MCP tools       |
+----------------------------------------------------------+
|  Wayland Compositor (wlroots/Smithay)                     |
|  Window management + AI IPC + screen capture              |
+----------------------------------------------------------+
|  Linux (kernel, systemd, PipeWire, D-Bus)                 |
|  UNTOUCHED                                                |
+----------------------------------------------------------+
```

## Getting Started

> Phase 0 proof-of-concept — works on any existing Linux desktop (GNOME, KDE, Sway, etc.)

### Prerequisites

- Linux with a running desktop (Wayland or X11)
- Python 3.10+
- [Ollama](https://ollama.ai) with a 7B+ model
- NVIDIA GPU recommended (RTX 3060+ for good performance)

### Install

```bash
git clone https://github.com/aulinx/aulinx.git
cd aulinx
pip install -e .
ollama pull qwen2.5:14b
```

### Run

```bash
aulinx
```

## Roadmap

- [x] Research & architecture design
- [ ] **Phase 0**: AI agent controlling existing desktop via AT-SPI + Ollama
- [ ] **Phase 1**: Command palette overlay on existing Wayland compositor
- [ ] **Phase 2**: Custom Wayland compositor with AI IPC
- [ ] **Phase 3**: Full AI desktop environment (daily-drivable)
- [ ] **Phase 4**: Distributable Linux distro image

## Name

**Au** (gold, element 79) + **linx** (Linux / lynx).

The gold standard of AI-powered Linux.

## License

MIT
