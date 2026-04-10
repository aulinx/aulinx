# Aulinx Compositor

A Wayland compositor with a built-in semantic scene graph for AI agent control. Built on [Smithay](https://github.com/Smithay/smithay).

**Other AI agents look at your screen. Aulinx IS the screen.**

## Quick Start

```bash
# Build
cargo build -p aulinx-compositor

# Run inside existing desktop (auto-detects winit backend)
./target/debug/aulinx-compositor

# Run on bare metal (DRM backend — from a TTY)
AULINX_BACKEND=udev ./target/debug/aulinx-compositor

# Launch apps inside the compositor
WAYLAND_DISPLAY=wayland-1 foot
```

## 35 IPC Commands

Connect via Unix socket at `$XDG_RUNTIME_DIR/aulinx/semantic.sock`:

| Category | Commands |
|----------|----------|
| **Scene** | windows, focused, find, find_window, graph, element_at, window_count, screenshot, annotated_screenshot, ascii, describe, suggest, summary, diff, wait_for, status, config, subscribe, unsubscribe, list_commands, keyboard_shortcuts, ping, help_text |
| **Input** | type, key, click, drag, scroll, move, batch |
| **Window** | focus, close, minimize, swap_master, spawn, list |
| **Layout** | set_ratio, set_gap |

See [docs/compositor-ipc.md](../docs/compositor-ipc.md) for the full protocol reference.

## Python Client

```python
from aulinx_compositor import connect

with connect() as c:
    print(c.describe())          # "2 windows in master+stack layout..."
    print(c.suggest())           # [{"action": "...", "reason": "..."}]
    c.spawn("firefox")           # Launch app
    c.type_text("hello")         # Type into focused window
    c.click(640, 400)            # Click at coordinates
    c.screenshot("screen.png")   # Capture output
    c.batch([                    # Atomic multi-step
        {"method": "input.type", "params": {"text": "ls"}},
        {"method": "input.key", "params": {"combo": "return"}},
    ])
```

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Super+Return | Open terminal |
| Super+Escape | Quit |
| Super+J/K | Focus next/prev |
| Super+H/L | Shrink/grow master |
| Super+Shift+Q | Close window |
| Super+Space | Swap with master |
| Super+F | Toggle fullscreen |
| Super+1-9 | Focus by index |

## Configuration

Copy `compositor.toml.example` to `~/.config/aulinx/compositor.toml`:

```toml
terminal = "foot"

[layout]
gap = 4
outer_gap = 4
master_ratio = 0.6

[appearance]
background = [0.08, 0.08, 0.12, 1.0]
```

## Architecture

```
src/
├── main.rs              Entry point, event loop
├── state.rs             Protocol handlers, window management
├── config.rs            TOML configuration
├── ipc.rs               JSON-RPC IPC server (31 commands)
├── semantic_bridge.rs   Window → scene graph sync
├── input/
│   ├── mod.rs           Keyboard shortcuts (12 bindings)
│   └── injection.rs     AI input injection (type, click, drag, scroll, batch)
└── backend/
    ├── winit.rs          Window-in-window mode (development)
    └── udev.rs           Bare metal DRM/KMS (production)
```

## Demo

```bash
# Full demo with terminals + IPC showcase
./demo.sh

# AI agent demo (autonomous compositor control)
python3 examples/ai_agent.py

# IPC integration tests
python3 tests/test_ipc_integration.py
```

## 30 Python Compositor Tools

When the Python agent runs inside this compositor, it gains 30 compositor-specific tools:

`compositor_summary`, `compositor_describe`, `compositor_ascii`, `compositor_suggest`, `compositor_status`, `compositor_config`, `compositor_ping`, `compositor_windows`, `compositor_focused`, `compositor_find_window`, `compositor_element_at`, `compositor_screenshot`, `compositor_annotated_screenshot`, `compositor_window_count`, `compositor_type`, `compositor_key`, `compositor_click`, `compositor_drag`, `compositor_scroll`, `compositor_spawn`, `compositor_focus`, `compositor_close`, `compositor_minimize`, `compositor_swap_master`, `compositor_set_ratio`, `compositor_set_gap`, `compositor_batch`, `compositor_diff`, `compositor_wait_for`, `compositor_run_and_type`
