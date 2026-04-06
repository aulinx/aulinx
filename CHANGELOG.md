# Changelog

All notable changes to Aulinx will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

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
