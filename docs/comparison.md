# How Aulinx Compares

## vs Claude Computer Use (Anthropic)

| | Claude Computer Use | Aulinx |
|---|---|---|
| **Approach** | Takes screenshots, guesses UI elements, clicks by coordinates | Owns the display stack — renders pixels, knows every element |
| **Speed** | ~2s per action (screenshot → OCR → decide → act) | <10ms per action (direct IPC) |
| **Accuracy** | ~87% on simple web tasks | Ground truth — no guessing |
| **Platform** | macOS only ($20-200/mo) | Linux, open source, free |
| **Offline** | No (requires Claude API) | Yes (Ollama local LLM) |
| **Text understanding** | OCR from screenshots | Direct access to window titles, UI trees |
| **Desktop description** | Not available | `scene.describe` — natural language from ground truth |

## vs Agent S3 (Simular AI)

| | Agent S3 | Aulinx |
|---|---|---|
| **OSWorld score** | 72.6% (surpasses human) | Not yet benchmarked |
| **Approach** | Screenshot + accessibility tree → action | Compositor scene graph + AT-SPI |
| **Accessibility** | Dropped AT-SPI in S2 (inconsistent) | Kept AT-SPI + own compositor (always consistent) |
| **Real-time events** | No (polls screenshots) | Yes (`scene.subscribe` push events) |
| **Input injection** | Via OS-level tools | Direct compositor keyboard injection |
| **Layout control** | No | Yes (`layout.set_ratio`, `layout.set_gap`) |
| **ASCII layout** | No | Yes (`scene.ascii` — text-only desktop view) |
| **Annotated screenshots** | Yes (Set-of-Marks) | Yes (from ground truth, not heuristic) |

## vs AIOS (AGI Research)

| | AIOS | Aulinx |
|---|---|---|
| **Focus** | LLM kernel (scheduling, memory) | Display stack (rendering, input, scene graph) |
| **Desktop control** | VM-based sandbox | Direct compositor control |
| **Computer use** | Via MCP Server + VM | Native — the compositor IS the agent interface |
| **Agent support** | Multi-agent scheduling | Single agent with 185 tools |
| **Maturity** | Research prototype | Working compositor + 174 tests |

## vs OpenHarness / OpenCode / Cline

| | Coding Agents | Aulinx |
|---|---|---|
| **Focus** | Code editing | Full OS control |
| **GUI control** | No | Yes (AT-SPI + compositor) |
| **Window management** | No | Yes (12 keyboard shortcuts + IPC) |
| **Screenshots** | No | Yes (plain, annotated, ASCII) |
| **Desktop understanding** | No | Yes (describe, suggest, scene graph) |
| **Server tools** | Limited (file, shell) | 119 tools (docker, journald, firewall, etc.) |

## Unique to Aulinx

Features no other AI desktop agent has:

1. **Own Wayland compositor** — ground truth scene graph, not reconstructed
2. **`scene.describe`** — natural language desktop description from ground truth
3. **`scene.suggest`** — compositor proactively suggests next actions
4. **`scene.ascii`** — ASCII art desktop map for text-only agents
5. **`scene.annotated_screenshot`** — Set-of-Marks from ground truth (not heuristic)
6. **`input.batch`** — atomic multi-step actions in single IPC call
7. **Three-tier architecture** — works headless (119 tools) to full compositor (185 tools)
8. **Dynamic layout control** — `layout.set_ratio`, `layout.set_gap` via IPC
9. **32 IPC commands** over Unix socket — the most comprehensive compositor API
10. **Mode-aware LLM prompts** — different instructions for headless vs desktop vs compositor
