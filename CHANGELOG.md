# Changelog

All notable changes to Aulinx will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.4.0] - 2026-04-10

### Added
- **Compositor IPC** — 20 JSON-RPC commands over Unix socket for AI agent control
  - Scene queries: `scene.windows`, `scene.focused`, `scene.find`, `scene.graph`, `scene.element_at`, `scene.window_count`, `scene.screenshot`, `scene.list_commands`
  - Input injection: `input.type` (with shift for uppercase), `input.key`, `input.click`, `input.scroll`, `input.move`, `input.drag`
  - Window management: `window.focus`, `window.close`, `window.swap_master`, `window.spawn`
  - Event subscriptions: `scene.subscribe`, `scene.unsubscribe` with real-time push
- **DRM/udev backend** — compositor can run on bare metal (not just inside GNOME)
- **Master+stack tiling** — dwm-style layout with configurable gaps and master ratio
- **10 keyboard shortcuts** — Super+Return/Escape/J/K/Shift+Q/Space/F/1-9
- **11 Wayland protocols** — XDG shell, decorations (SSDs), primary selection, XDG activation, layer shell, fractional scale, viewporter
- **Compositor config** (`~/.config/aulinx/compositor.toml`) — gaps, master ratio, background color, terminal
- **Scene graph events** — window open/close/focus pushed to IPC subscribers
- **Python client library** (`aulinx_compositor.py`) — clean API for all 20 IPC commands
- **14 compositor tools** for the Python agent — `compositor_windows`, `compositor_click`, `compositor_type`, `compositor_screenshot`, `compositor_spawn`, etc.
- **IPC protocol docs** (`docs/compositor-ipc.md`) — full reference for all commands
- **Demo script** (`compositor/demo.sh`) — launches compositor + terminals + runs IPC demo
- **`--mode core|desktop|compositor`** — auto-detects environment, filters tools for LLM
- **Mode-aware system prompts** — different LLM instructions for headless vs desktop vs compositor
- **Mode-aware CORE_TOOLS** — native tool calling set adapts per tier (32/53/65 tools)
- **`--info` command** — shows capabilities, tool counts, and detected mode
- **8 server tools** — `journal_logs`, `docker_ps`, `docker_logs`, `port_list`, `firewall_status`, `cron_list`, `disk_health`, `system_logs_summary`
- **19 compositor tools** (was 14) — added `compositor_status`, `compositor_diff`, `compositor_wait_for`, `compositor_find_window`, `compositor_run_and_type`
- **`scene.diff` IPC** — get changes since last query (efficient agent loops)
- **`scene.wait_for` IPC** — check if a condition is met (window exists, count reached)
- **`scene.status` IPC** — full compositor overview (version, uptime, config)
- **`scene.find_window` IPC** — search windows by title/app_id
- **Doctor check** — shows detected tier, checks compositor IPC connectivity
- **29 new tests** — mode filtering, smoke tests, system prompt tests
- **CI for compositor** — GitHub Actions builds Rust compositor
- **Architecture docs** — full system diagram with three-tier architecture
- **README rewrite** — "AI-native Linux. Desktop to server." positioning

### Changed
- Tool count: 103 → 186 (29 compositor + 8 server + other additions)
- IPC commands: 7 → 34
- Keyboard shortcuts: 2 → 12
- Tests: 114 → 180 (149 unit + 31 integration)
- Window title/app_id now read from real XDG toplevel state (was hardcoded)
- Tiling layout: equal-split → master+stack with configurable gaps
- Cleaned up all Rust compiler warnings (zero warnings)

## [0.3.0] - 2026-04-08

### Added
- **OllamaClient refactor** — shared streaming LLM client in `llm.py`, eliminates code duplication
- **Streaming native tool calling** — tokens stream immediately, tool calls from final chunk
- **Multi-model routing** — small router model classifies intent, large model executes
- **Global hotkey daemon** (`aulinx --daemon`) — Super+Space opens palette, GNOME + evdev backends
- **Workflow automation** — create/run/trigger workflows (manual, app-based, time-based), 5 new tools
- **AI suggestion engine** — desktop notifications for uncommitted git, high CPU, low disk, low battery
- **Plugin system** — drop Python files in `~/.config/aulinx/plugins/` for custom tools
- **Long-term memory** — keyword-based RAG across sessions, auto-context in prompts, 5 new tools
- **MCP server** (`aulinx --mcp`) — expose all tools to Claude Desktop or any MCP client
- **Voice interface** (`aulinx --voice`) — speech-to-text via faster-whisper (local)
- **Web dashboard** — 5-tab React dashboard (stats, tools, audit, memory, settings)
- **REST API** — 7 endpoints over WebSocket for dashboard
- **atspi_focus_element** tool — focus any UI element, then type into it
- **ydotool support** — works on GNOME Mutter, auto-detects socket
- **Systemd service** — one-command install, auto-starts on login
- **Structured logging** — file + console with levels
- **Config validation** — range checks, format validation, warnings
- **Anti-loop detection** — prevents infinite retry of same failing tool
- **English-only responses** — stops multilingual model from responding in Thai/Chinese
- **Compositor scaffold** — Rust/Smithay project with IPC protocol spec

### Changed
- Agent now uses `OllamaClient` for all LLM communication (no more duplicated code)
- Tool parameter descriptions improved with concrete examples
- `input_sim.py` priority: ydotool > wtype > xdotool (ydotool works on GNOME)
- Registry strips unknown kwargs from tool calls (handles LLM hallucinated parameters)
- System prompt includes multi-step reasoning patterns

### Stats
- 103 tools across 26 modules
- 107 tests (36 new)
- 8,000+ lines of Python
- 6 run modes: CLI, WebSocket, daemon, MCP, voice, doctor

## [0.1.0] - 2026-04-06

### Added
- Initial release of Aulinx AI desktop agent
- Interactive CLI with streaming LLM responses (`aulinx` command)
- One-shot mode (`aulinx -c "command"`)
- Session resume (`aulinx --resume`)
- WebSocket server for UI palette (`aulinx --serve`)
- React command palette UI with dark gold theme
- 92 tools across 23 modules:
  - Window management (list, focus)
  - AT-SPI GUI control (read trees, find elements, click, type, screenshot)
  - File operations (read, write, edit, move, trash, list, search)
  - Text processing (count, grep, replace, head, tail)
  - Git operations (status, log, diff, commit, branch, stash)
  - Application management (launch, list running)
  - Process management (list, kill)
  - Service management (list, status, start, stop, restart)
  - Network (status, wifi scan/connect/disconnect)
  - Audio (get/set volume, mute)
  - Display (list monitors, brightness)
  - Power (battery status, power profiles, suspend, shutdown)
  - Theme (get/set dark mode, wallpaper)
  - Bluetooth (status, scan, connect, disconnect, toggle)
  - Input simulation (keyboard shortcuts, virtual typing)
  - Session info (user, uptime, disk usage, environment)
  - Package management (search, install, list installed)
  - XDG (open files/URLs, default apps, MIME types)
  - Timer/reminders (set, cancel, list)
  - Clipboard (get, set)
  - Notifications (send)
  - Persistent memory (store, get, delete, namespaces)
  - D-Bus (list services, introspect, call methods)
  - OCR (screenshot OCR, image OCR)
  - Date/time (now, convert, calendar)
  - Workflow (context snapshot, wait, audit history)
- 5-tier permission system (OBSERVE → IRREVERSIBLE)
- Session-level confirmation caching for MUTATE tier
- Audit log with secret redaction (~/.local/share/aulinx/audit.jsonl)
- Conversation history with session resume (~/.local/share/aulinx/history/)
- Persistent workflow memory (~/.local/share/aulinx/memory.json)
- Configuration via ~/.config/aulinx/config.toml
- Diagnostic check (`aulinx --doctor` / `/doctor`)
- Tab completion for /commands and @tool references
- Thinking spinner with contextual status
- 71 unit tests
- GitHub Actions CI (ruff lint + pytest on Python 3.10/3.11/3.12)
- Registered on PyPI, npm, GitHub org
