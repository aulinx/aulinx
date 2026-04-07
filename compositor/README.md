# Aulinx Compositor

AI-native Wayland compositor for Aulinx. Phase 2 of the project.

## Status

Under development. Use the Python agent (`aulinx`) for now.

## Architecture

```
Python Agent ←→ Unix Socket (JSON-RPC) ←→ Rust Compositor
                /run/aulinx/ai.sock
```

## IPC Protocol

The compositor exposes a JSON-RPC API over a Unix domain socket:

### Window Management
- `windows.list` — list all windows with titles, geometry, workspace
- `windows.focus(window_id)` — focus a window
- `windows.move(window_id, x, y, w, h)` — move/resize
- `windows.close(window_id)` — close
- `windows.screenshot(window_id)` — capture window pixels

### Input Injection
- `input.type(text)` — virtual keyboard (works on ALL Wayland clients)
- `input.key(combo)` — keyboard shortcuts
- `input.mouse(x, y, button, action)` — mouse events

### Screen
- `screen.capture(region?)` — screenshot any region

## Building

Requires Rust 1.75+ and Wayland development libraries.

```bash
cd compositor
cargo build --release
```

## Technology

Built with [Smithay](https://github.com/Smithay/smithay), a Rust library for building Wayland compositors.
