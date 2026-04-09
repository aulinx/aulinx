# Aulinx Semantic Compositor — Design Spec

## Context

Aulinx is an AI-native Linux desktop OS ("Cursor for the entire OS"). The Python agent (v0.3.0, 151 tools) already controls a Linux desktop via AT-SPI, ydotool, and CLI tools. Phase 2 calls for a custom Wayland compositor.

**The problem:** Every AI desktop agent in 2026 (Claude Computer Use, OpenAI Operator, Google Mariner, Microsoft UFO3) works the same way — screenshot → vision model → click coordinates → repeat. This costs 1,200-5,000 tokens per perception cycle, is fragile, and re-perceives everything from scratch each step.

**The insight:** A Wayland compositor already knows every surface, buffer, window position, and input focus. Nobody has built a compositor that exposes this as semantic understanding to AI agents. Aulinx will be the first.

**The approach:** Build two products from one codebase:
1. `aulinx-semantic` — a Rust library + standalone daemon that provides AI-native semantic desktop understanding on any existing Wayland compositor
2. `aulinx-compositor` — a full Wayland compositor (Smithay 0.7) with the semantic layer built in natively

## Architecture

### Workspace Structure

```
compositor/                     ← Cargo workspace root
├── Cargo.toml                  ← workspace members
├── crates/
│   ├── semantic/               ← aulinx-semantic (core library)
│   │   ├── Cargo.toml
│   │   └── src/
│   │       ├── lib.rs          ← public API
│   │       ├── graph.rs        ← semantic scene graph
│   │       ├── node.rs         ← SemanticNode types
│   │       ├── diff.rs         ← change detection + events
│   │       ├── query.rs        ← scene.query(), scene.find()
│   │       ├── action.rs       ← element.activate(), semantic intents
│   │       └── sources/
│   │           ├── mod.rs      ← Source trait
│   │           ├── atspi.rs    ← AT-SPI → scene graph
│   │           ├── compositor_ipc.rs  ← Sway/Hyprland/niri IPC
│   │           └── direct.rs   ← direct surface injection (compositor)
│   ├── daemon/                 ← aulinx-semanticd (Product 1)
│   │   ├── Cargo.toml
│   │   └── src/
│   │       ├── main.rs         ← daemon entry, source orchestration
│   │       ├── ipc.rs          ← Unix socket JSON-RPC server
│   │       └── events.rs       ← event stream subscriptions
│   └── compositor/             ← aulinx-compositor (Product 2)
│       ├── Cargo.toml
│       └── src/
│           ├── main.rs         ← entry, backend selection, event loop
│           ├── state.rs        ← AulinxState + Smithay delegates
│           ├── config.rs       ← runtime config
│           ├── window.rs       ← WindowElement enum (Wayland | X11)
│           ├── workspace.rs    ← workspace management
│           ├── focus.rs        ← keyboard/pointer focus
│           ├── cursor.rs       ← xcursor theme
│           ├── xwayland.rs     ← X11Wm + XwmHandler
│           ├── semantic_bridge.rs  ← feeds surface data into aulinx-semantic
│           ├── ipc.rs          ← unified IPC (semantic + compositor)
│           ├── backend/
│           │   ├── mod.rs      ← BackendData enum
│           │   ├── winit.rs    ← dev backend (nested)
│           │   └── udev.rs     ← production backend (DRM/KMS)
│           ├── shell/
│           │   ├── mod.rs
│           │   ├── xdg.rs      ← XDG Shell handler
│           │   ├── layer.rs    ← wlr-layer-shell (AI palette)
│           │   └── decoration.rs ← server-side decorations
│           ├── layout/
│           │   ├── mod.rs      ← LayoutEngine
│           │   ├── tiling.rs   ← n-ary tree (COSMIC pattern, id_tree)
│           │   └── floating.rs ← z-stack floating
│           ├── input/
│           │   ├── mod.rs      ← physical input dispatch
│           │   └── injection.rs ← AI virtual input
│           └── render/
│               ├── mod.rs
│               └── renderer.rs ← Glow + damage tracking
```

### Crate Dependencies

```
aulinx-semantic (library, no runtime)
    ├── serde + serde_json
    ├── tracing
    └── (optional) atspi, zbus (for AT-SPI source)

aulinx-semanticd (binary, Product 1)
    ├── aulinx-semantic
    ├── calloop
    ├── serde_json
    └── tracing-subscriber

aulinx-compositor (binary, Product 2)
    ├── aulinx-semantic
    ├── smithay 0.7 (desktop, wayland_frontend, backend_drm, backend_udev,
    │                 backend_winit, backend_gbm, backend_egl,
    │                 backend_session_libseat, backend_libinput,
    │                 renderer_glow, renderer_multi, use_system_lib,
    │                 xwayland)
    ├── calloop 0.14
    ├── id_tree
    ├── xkbcommon
    ├── image (PNG encoding)
    ├── base64
    ├── serde + serde_json
    ├── tracing + tracing-subscriber
    └── libc
```

## Product 1: aulinx-semantic + aulinx-semanticd

### Semantic Scene Graph

The core data structure that represents everything visible on the desktop with meaning, not just pixels.

```rust
/// A node in the semantic scene graph
pub enum SemanticNode {
    Desktop {
        screens: Vec<NodeId>,
    },
    Screen {
        name: String,
        geometry: Rect,
        windows: Vec<NodeId>,
    },
    Window {
        id: u64,
        pid: u32,
        app_id: String,
        title: String,
        geometry: Rect,
        focused: bool,
        workspace: usize,
        floating: bool,
        elements: Vec<NodeId>,
    },
    Element {
        role: ElementRole,        // Button, TextField, Label, Menu, etc.
        label: String,
        value: Option<String>,
        state: ElementState,      // Enabled, Disabled, Checked, etc.
        bounds: Rect,             // relative to window
        actions: Vec<ActionType>, // Activate, SetValue, Scroll, etc.
        children: Vec<NodeId>,
    },
}

pub enum ElementRole {
    Button, TextField, Label, CheckBox, RadioButton,
    Menu, MenuItem, Tab, TabPanel, ScrollBar,
    List, ListItem, Tree, TreeItem, Table, TableCell,
    Dialog, Alert, Toolbar, StatusBar, ProgressBar,
    Image, Link, Heading, Paragraph, Unknown(String),
}
```

### Source Trait

Pluggable data providers that feed the scene graph:

```rust
pub trait Source: Send {
    /// Human-readable name
    fn name(&self) -> &str;

    /// Start the source, call `sink.update_window()` / `sink.remove_window()` as state changes
    fn start(&mut self, sink: GraphSink) -> Result<()>;

    /// Execute a semantic action (e.g., activate a button)
    fn execute_action(&self, node_id: NodeId, action: ActionType) -> Result<()>;
}
```

Three source implementations:
- **`atspi.rs`** — connects to AT-SPI D-Bus, maps accessible nodes to SemanticNodes. Used by the daemon on any compositor.
- **`compositor_ipc.rs`** — connects to Sway (`swaymsg -t subscribe`), Hyprland (`hyprctl`), or niri IPC to get window geometry, focus, workspace info. Supplements AT-SPI.
- **`direct.rs`** — used by the compositor. Receives surface data directly from Smithay (window title, app_id, geometry, focus) without going through IPC. Combined with AT-SPI for element-level detail.

### Diff Engine

Detects changes between scene graph states and emits semantic events:

```rust
pub enum SemanticEvent {
    WindowOpened { window_id: u64, app_id: String, title: String },
    WindowClosed { window_id: u64 },
    WindowFocused { window_id: u64 },
    WindowMoved { window_id: u64, geometry: Rect },
    WindowTitleChanged { window_id: u64, old: String, new: String },
    ElementAppeared { window_id: u64, node_id: NodeId, role: ElementRole, label: String },
    ElementDisappeared { window_id: u64, node_id: NodeId },
    ElementChanged { window_id: u64, node_id: NodeId, property: String, old: Value, new: Value },
    FocusChanged { window_id: u64, element_id: Option<NodeId> },
}
```

### Query Engine

```rust
impl SceneGraph {
    /// Full scene graph
    fn graph(&self) -> &SemanticNode;

    /// Single window
    fn window(&self, id: u64) -> Option<&SemanticNode>;

    /// Find elements matching a text query
    fn find(&self, query: &str) -> Vec<&SemanticNode>;

    /// Find elements by role
    fn find_by_role(&self, role: ElementRole) -> Vec<&SemanticNode>;

    /// Currently focused window + element
    fn focused(&self) -> (Option<u64>, Option<NodeId>);

    /// All windows
    fn windows(&self) -> Vec<&SemanticNode>;
}
```

### IPC Protocol (JSON-RPC over Unix socket)

Shared by both products. Socket at `$XDG_RUNTIME_DIR/aulinx/semantic.sock`.

**Query commands:**
- `scene.graph()` → full scene graph as JSON
- `scene.window(window_id)` → single window tree
- `scene.find(query)` → elements matching text query
- `scene.find_by_role(role)` → elements by role
- `scene.focused()` → focused window + element
- `scene.windows()` → all windows (summary)

**Action commands:**
- `element.activate(node_id)` → click/press the element
- `element.set_value(node_id, value)` → set text field value
- `element.scroll(node_id, direction, amount)` → scroll
- `window.focus(window_id)` → focus a window
- `window.close(window_id)` → close a window

**Subscription commands:**
- `scene.subscribe(filter)` → start event stream (filter: `"*"`, `"window.*"`, `"element.changed"`, etc.)
- `scene.unsubscribe(subscription_id)` → stop event stream

**Compositor-only commands (Product 2 adds these):**
- `window.move(id, x, y, w, h)` → move/resize
- `window.screenshot(id)` → capture window as PNG
- `input.type(text)` → virtual keyboard
- `input.key(combo)` → keyboard shortcut
- `input.mouse(x, y, button, action)` → mouse event
- `screen.capture(region?)` → screenshot

## Product 2: aulinx-compositor

### Compositor Architecture

Built with Smithay 0.7. All design decisions verified against Anvil, COSMIC (cosmic-comp), and niri.

**Central state struct:** `AulinxState` holds all Smithay protocol states, window registry, layout engine, and a reference to the `aulinx-semantic` `SceneGraph`. All Smithay delegate macros implement on this type.

**Backend:** `BackendData` enum with `Winit` (dev) and `Udev` (prod) variants. Winit for development (nested in GNOME), DRM/KMS + libseat for production.

**Event loop:** Calloop-only. No Tokio. Sources: Wayland display fd, backend events, IPC socket, XWayland.

**Window management:** Hybrid tiling/floating. N-ary tree via `id_tree` (COSMIC pattern) for tiling. Z-stack for floating. Dialogs auto-float.

**Semantic bridge:** `semantic_bridge.rs` implements the `Source` trait from `aulinx-semantic`. When a surface commits, the bridge updates the scene graph directly with window metadata (title, app_id, geometry, focus). For element-level data, it falls back to AT-SPI via the library's AT-SPI source.

**Rendering:** Glow/OpenGL primary. Multi-renderer support for software fallback.

**Protocols implemented:**
- Core: wl_compositor, wl_seat, wl_output, wl_shm
- Shell: xdg-shell, wlr-layer-shell-v1
- Decoration: xdg-decoration-unstable-v1
- Buffer: linux-dmabuf-v1
- Display: wp-viewporter, wp-fractional-scale-v1, wp-presentation-time
- Input: virtual-keyboard-v1, wlr-virtual-pointer, pointer-constraints, relative-pointer, keyboard-shortcuts-inhibit
- Clipboard: data-device, primary-selection, wlr-data-control
- Security: ext-session-lock-v1
- Idle: ext-idle-notify-v1
- Activation: xdg-activation-v1
- Cursor: cursor-shape-v1
- Compat: XWayland

## Verification

### Testing the daemon (Product 1)
1. Start Sway/Hyprland on Ubuntu VM
2. Run `aulinx-semanticd`
3. Open foot terminal + Firefox
4. Python script connects to semantic.sock, sends `scene.graph()`
5. Verify: response contains both windows with titles, geometry, focus state
6. Send `scene.find("Close")` → verify returns button elements
7. Send `element.activate(close_button_id)` → verify window closes
8. Subscribe to events, open a new window → verify `WindowOpened` event received

### Testing the compositor (Product 2)
1. On Ubuntu VM, run `aulinx-compositor` (Winit backend)
2. Open `WAYLAND_DISPLAY=aulinx-0 foot`
3. Verify: terminal window appears, tiled
4. Python connects to semantic.sock, sends `scene.graph()`
5. Verify: same semantic data as daemon, but with direct source (no AT-SPI latency)
6. Send `input.type("hello")` → verify text appears in terminal
7. Send `screen.capture()` → verify PNG returned
8. Open multiple windows → verify tiling layout works
