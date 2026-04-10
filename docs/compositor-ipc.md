# Aulinx Compositor IPC Protocol

The Aulinx compositor exposes a JSON-RPC 2.0 API over a Unix domain socket. AI agents connect to this socket to query the desktop scene graph, inject input, manage windows, and subscribe to real-time events.

## Connection

```bash
# Default socket path
$XDG_RUNTIME_DIR/aulinx/semantic.sock

# Override with environment variable
AULINX_SOCKET=/path/to/socket
```

Connect via any Unix socket client:

```python
import socket, json

s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.connect("/run/user/1000/aulinx/semantic.sock")

def rpc(method, params={}):
    req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    s.sendall((req + "\n").encode())
    return json.loads(s.recv(65536).decode().strip())
```

## Scene Graph Queries

### `scene.windows`

List all windows with metadata and geometry.

```json
// Request
{"jsonrpc": "2.0", "id": 1, "method": "scene.windows", "params": {}}

// Response
{"jsonrpc": "2.0", "id": 1, "result": [
  {
    "id": 1,
    "app_id": "foot",
    "title": "foot",
    "type": "Window",
    "geometry": {"x": 0, "y": 0, "width": 768, "height": 800},
    "focused": true,
    "floating": false,
    "workspace": 0,
    "pid": 0,
    "elements": []
  }
]}
```

### `scene.focused`

Get the currently focused window.

```json
{"jsonrpc": "2.0", "id": 1, "method": "scene.focused", "params": {}}
```

### `scene.find`

Search for UI elements by query string.

```json
{"jsonrpc": "2.0", "id": 1, "method": "scene.find", "params": {"query": "Save"}}
```

### `scene.graph`

Get the full scene graph tree.

```json
{"jsonrpc": "2.0", "id": 1, "method": "scene.graph", "params": {}}
```

### `scene.element_at`

Query what window is at a given screen coordinate. Returns window metadata or `null` if nothing is there.

```json
// Request
{"jsonrpc": "2.0", "id": 1, "method": "scene.element_at", "params": {"x": 640, "y": 400}}

// Response
{"jsonrpc": "2.0", "id": 1, "result": {
  "window_id": 1,
  "app_id": "foot",
  "title": "foot",
  "position": {"x": 0, "y": 0},
  "geometry": {"x": 0, "y": 0, "width": 1280, "height": 800}
}}
```

### `scene.screenshot`

Capture the compositor output as a base64-encoded PNG.

```json
// Request
{"jsonrpc": "2.0", "id": 1, "method": "scene.screenshot", "params": {}}

// Response
{"jsonrpc": "2.0", "id": 1, "result": {
  "format": "png",
  "data": "iVBORw0KGgoAAAANSUhEUg..."
}}
```

### `scene.diff`

Get changes since the last call. Returns a list of semantic events (window opened/closed/focused). Efficient for agent loops — don't re-screenshot, just get the diff.

```json
// Request
{"jsonrpc": "2.0", "id": 1, "method": "scene.diff", "params": {}}

// Response
{"jsonrpc": "2.0", "id": 1, "result": {
  "events": [
    {"event": "window_opened", "window_id": 2, "app_id": "firefox", "title": "Mozilla Firefox"},
    {"event": "window_focused", "window_id": 2}
  ]
}}
```

### `scene.wait_for`

Check if a condition is met (window with matching title/app_id exists, or minimum window count). The client polls this endpoint — returns immediately with `matched: true/false`.

```json
// Wait for a window with "Firefox" in the title
{"jsonrpc": "2.0", "id": 1, "method": "scene.wait_for", "params": {"title": "Firefox"}}

// Wait for at least 3 windows
{"jsonrpc": "2.0", "id": 1, "method": "scene.wait_for", "params": {"count": 3}}

// Response
{"jsonrpc": "2.0", "id": 1, "result": {"matched": true}}
```

### `scene.status`

Get a full system overview in one call — version, window count, focused window, uptime.

```json
{"jsonrpc": "2.0", "id": 1, "method": "scene.status", "params": {}}
```

## Input Injection

### `input.type`

Type text into the focused window. Each character is converted to key press/release events using xkbcommon keymap scanning.

```json
{"jsonrpc": "2.0", "id": 1, "method": "input.type", "params": {"text": "hello world"}}
```

### `input.key`

Inject a key combination. Supports modifier keys (ctrl, alt, shift, super) and named keys.

```json
{"jsonrpc": "2.0", "id": 1, "method": "input.key", "params": {"combo": "ctrl+s"}}
```

Supported key names: `ctrl`, `alt`, `shift`, `super`, `return`, `escape`, `tab`, `backspace`, `delete`, `space`, `up`, `down`, `left`, `right`, `home`, `end`, `pageup`, `pagedown`, `F1`-`F12`, and single characters.

### `input.click`

Inject a mouse click at screen coordinates. Moves the pointer, focuses the window under the cursor, and sends press+release.

```json
{"jsonrpc": "2.0", "id": 1, "method": "input.click", "params": {"x": 640, "y": 400, "button": 1}}
```

Button values: `1` = left (default), `2` = middle, `3` = right.

### `input.move`

Move the pointer to screen coordinates without clicking.

```json
{"jsonrpc": "2.0", "id": 1, "method": "input.move", "params": {"x": 640, "y": 400}}
```

### `input.scroll`

Inject scroll events at screen coordinates. Positive `dy` scrolls down, negative scrolls up.

```json
{"jsonrpc": "2.0", "id": 1, "method": "input.scroll", "params": {"x": 640, "y": 400, "dx": 0, "dy": -3}}
```

### `input.drag`

Drag from one point to another. Press at (x1,y1), move through intermediate steps, release at (x2,y2).

```json
{"jsonrpc": "2.0", "id": 1, "method": "input.drag", "params": {"x1": 100, "y1": 100, "x2": 500, "y2": 400, "button": 1}}
```

## Window Management

### `window.spawn`

Launch an application inside the compositor. Returns the process PID.

```json
// Request
{"jsonrpc": "2.0", "id": 1, "method": "window.spawn", "params": {"command": "firefox", "args": []}}

// Response
{"jsonrpc": "2.0", "id": 1, "result": {"ok": true, "pid": 12345}}
```

### `window.focus`

Focus a window by its semantic ID (from `scene.windows`).

```json
{"jsonrpc": "2.0", "id": 1, "method": "window.focus", "params": {"window_id": 1}}
```

### `window.close`

Close a window. If `window_id` is omitted, closes the focused window.

```json
{"jsonrpc": "2.0", "id": 1, "method": "window.close", "params": {"window_id": 1}}
{"jsonrpc": "2.0", "id": 1, "method": "window.close", "params": {}}
```

### `window.swap_master`

Swap a window to the master (largest) position in the tiling layout.

```json
{"jsonrpc": "2.0", "id": 1, "method": "window.swap_master", "params": {"window_id": 2}}
```

## Event Subscriptions

### `scene.subscribe`

Subscribe to real-time desktop events. Returns a subscription ID.

```json
// Request
{"jsonrpc": "2.0", "id": 1, "method": "scene.subscribe", "params": {"filter": "*"}}

// Response
{"jsonrpc": "2.0", "id": 1, "result": {"subscription_id": 1}}
```

After subscribing, the server pushes events as JSON-RPC notifications:

```json
{"jsonrpc": "2.0", "method": "scene.event", "params": {
  "event": "window_opened",
  "window_id": 2,
  "app_id": "foot",
  "title": "foot"
}}

{"jsonrpc": "2.0", "method": "scene.event", "params": {
  "event": "window_closed",
  "window_id": 2
}}

{"jsonrpc": "2.0", "method": "scene.event", "params": {
  "event": "window_focused",
  "window_id": 1
}}
```

### `scene.unsubscribe`

Remove a subscription.

```json
{"jsonrpc": "2.0", "id": 1, "method": "scene.unsubscribe", "params": {"subscription_id": 1}}
```

## Keyboard Shortcuts

The compositor handles these key combinations:

| Shortcut | Action |
|----------|--------|
| `Super+Return` | Open foot terminal |
| `Super+Escape` | Quit compositor |
| `Super+J` | Focus next window |
| `Super+K` | Focus previous window |
| `Super+Shift+Q` | Close focused window |
| `Super+Space` | Swap focused window with master |
| `Super+F` | Toggle fullscreen |
| `Super+H` | Shrink master |
| `Super+L` | Grow master |
| `Super+1..9` | Focus window by index |

## Layout

The compositor uses a master+stack tiling layout:

- **1 window**: fullscreen (with outer gaps)
- **2+ windows**: master (configurable ratio, default 60%) + stack (right side, split vertically)
- **Gaps**: configurable inner and outer gaps (default 4px)

### `layout.set_ratio`

Dynamically adjust the master window width ratio (0.2-0.8).

```json
{"jsonrpc": "2.0", "id": 1, "method": "layout.set_ratio", "params": {"ratio": 0.75}}
```

### `layout.set_gap`

Dynamically adjust the gap between windows (0-32px).

```json
{"jsonrpc": "2.0", "id": 1, "method": "layout.set_gap", "params": {"gap": 8}}
```

### `scene.keyboard_shortcuts`

Returns the list of available keyboard shortcuts.

```json
{"jsonrpc": "2.0", "id": 1, "method": "scene.keyboard_shortcuts", "params": {}}
```

## Discovery

### `scene.list_commands`

Returns all available IPC commands with descriptions. Useful for AI agents to discover capabilities at runtime.

```json
{"jsonrpc": "2.0", "id": 1, "method": "scene.list_commands", "params": {}}
```

Also accessible as `help`.

## Error Responses

```json
{"jsonrpc": "2.0", "id": 1, "error": {"code": -32603, "message": "error description"}}
```

| Code | Meaning |
|------|---------|
| `-32700` | Parse error (invalid JSON) |
| `-32601` | Method not found |
| `-32603` | Internal error |
