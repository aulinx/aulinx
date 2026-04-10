//! Compositor IPC — serves semantic queries + compositor commands.

use std::collections::HashMap;
use std::io::{Read, Write};
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::{Path, PathBuf};

use aulinx_semantic::diff::{EventFilter, SemanticEvent};
use aulinx_semantic::protocol::*;
use aulinx_semantic::SceneGraph;

struct Subscription {
    client_id: u64,
    _filter: EventFilter,
}

pub struct CompositorIpc {
    listener: UnixListener,
    socket_path: PathBuf,
    clients: HashMap<u64, UnixStream>,
    next_id: u64,
    subscriptions: HashMap<u64, Subscription>,
    next_sub_id: u64,
}

/// Commands that need compositor state to execute.
pub enum CompositorCmd {
    InputType { client_id: u64, req_id: Option<serde_json::Value>, text: String },
    InputKey { client_id: u64, req_id: Option<serde_json::Value>, combo: String },
    InputClick { client_id: u64, req_id: Option<serde_json::Value>, x: f64, y: f64, button: u32 },
    InputDrag { client_id: u64, req_id: Option<serde_json::Value>, x1: f64, y1: f64, x2: f64, y2: f64, button: u32 },
    InputScroll { client_id: u64, req_id: Option<serde_json::Value>, x: f64, y: f64, dx: f64, dy: f64 },
    InputMove { client_id: u64, req_id: Option<serde_json::Value>, x: f64, y: f64 },
    WindowSpawn { client_id: u64, req_id: Option<serde_json::Value>, command: String, args: Vec<String> },
    WindowMinimize { client_id: u64, req_id: Option<serde_json::Value>, window_id: u64 },
    InputBatch { client_id: u64, req_id: Option<serde_json::Value>, actions: Vec<serde_json::Value> },
    LayoutSetRatio { client_id: u64, req_id: Option<serde_json::Value>, ratio: f32 },
    LayoutSetGap { client_id: u64, req_id: Option<serde_json::Value>, gap: i32 },
    WindowClose { client_id: u64, req_id: Option<serde_json::Value>, window_id: Option<u64> },
    WindowFocus { client_id: u64, req_id: Option<serde_json::Value>, window_id: u64 },
    WindowSwapMaster { client_id: u64, req_id: Option<serde_json::Value>, window_id: u64 },
    Screenshot { client_id: u64, req_id: Option<serde_json::Value> },
    Status { client_id: u64, req_id: Option<serde_json::Value> },
    Describe { client_id: u64, req_id: Option<serde_json::Value> },
    AsciiLayout { client_id: u64, req_id: Option<serde_json::Value> },
    Summary { client_id: u64, req_id: Option<serde_json::Value> },
    Suggest { client_id: u64, req_id: Option<serde_json::Value> },
    GetConfig { client_id: u64, req_id: Option<serde_json::Value> },
    AnnotatedScreenshot { client_id: u64, req_id: Option<serde_json::Value> },
    SceneDiff { client_id: u64, req_id: Option<serde_json::Value> },
    SceneWaitFor { client_id: u64, req_id: Option<serde_json::Value>, title: Option<String>, app_id: Option<String>, count: Option<usize> },
    ElementAt { client_id: u64, req_id: Option<serde_json::Value>, x: f64, y: f64 },
}

impl CompositorIpc {
    pub fn new(socket_path: &Path) -> Result<Self, Box<dyn std::error::Error>> {
        if let Some(parent) = socket_path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        let _ = std::fs::remove_file(socket_path);
        let listener = UnixListener::bind(socket_path)?;
        listener.set_nonblocking(true)?;
        tracing::info!("IPC server listening on {}", socket_path.display());
        Ok(Self {
            listener,
            socket_path: socket_path.to_owned(),
            clients: HashMap::new(),
            next_id: 1,
            subscriptions: HashMap::new(),
            next_sub_id: 1,
        })
    }

    pub fn poll(&mut self, graph: &SceneGraph) -> Vec<CompositorCmd> {
        let mut commands = Vec::new();

        // Accept
        loop {
            match self.listener.accept() {
                Ok((stream, _)) => {
                    stream.set_nonblocking(true).ok();
                    let id = self.next_id;
                    self.next_id += 1;
                    tracing::info!("IPC: client {id} connected");
                    self.clients.insert(id, stream);
                }
                Err(ref e) if e.kind() == std::io::ErrorKind::WouldBlock => break,
                Err(e) => { tracing::error!("IPC accept: {e}"); break; }
            }
        }

        // Read data from clients first (collect to avoid borrow conflict)
        let ids: Vec<u64> = self.clients.keys().copied().collect();
        let mut disconnected = Vec::new();
        let mut incoming: Vec<(u64, String)> = Vec::new();

        for &id in &ids {
            let stream = self.clients.get_mut(&id).unwrap();
            let mut buf = [0u8; 8192];
            match stream.read(&mut buf) {
                Ok(0) => { disconnected.push(id); }
                Ok(n) => {
                    incoming.push((id, String::from_utf8_lossy(&buf[..n]).to_string()));
                }
                Err(ref e) if e.kind() == std::io::ErrorKind::WouldBlock => {}
                Err(_) => { disconnected.push(id); }
            }
        }

        // Process requests
        for (id, data) in incoming {
            for line in data.lines() {
                let line = line.trim();
                if line.is_empty() { continue; }
                match self.handle(graph, id, line) {
                    HandleResult::Response(resp) => {
                        self.respond(id, &resp);
                    }
                    HandleResult::Command(cmd) => {
                        commands.push(cmd);
                    }
                }
            }
        }

        for id in disconnected {
            self.clients.remove(&id);
            self.subscriptions.retain(|_, s| s.client_id != id);
        }

        commands
    }

    /// Send a response to a specific client.
    pub fn respond(&mut self, client_id: u64, response: &str) {
        if let Some(stream) = self.clients.get_mut(&client_id) {
            let msg = format!("{response}\n");
            stream.write_all(msg.as_bytes()).ok();
        }
    }

    /// Push semantic events to subscribed clients.
    #[allow(dead_code)]
    pub fn push_events(&mut self, events: &[SemanticEvent]) {
        for event in events {
            let matching: Vec<u64> = self.subscriptions.values()
                .filter(|s| s._filter.matches(event))
                .map(|s| s.client_id)
                .collect();
            for client_id in matching {
                let notification = serde_json::json!({
                    "jsonrpc": "2.0",
                    "method": "scene.event",
                    "params": event,
                });
                if let Ok(json) = serde_json::to_string(&notification) {
                    self.respond(client_id, &json);
                }
            }
        }
    }

    fn handle(&mut self, graph: &SceneGraph, client_id: u64, line: &str) -> HandleResult {
        let request: JsonRpcRequest = match serde_json::from_str(line) {
            Ok(r) => r,
            Err(e) => {
                let resp = JsonRpcResponse::error(None, PARSE_ERROR, format!("{e}"));
                return HandleResult::Response(serde_json::to_string(&resp).unwrap());
            }
        };

        let id = request.id.clone();
        let method = request.method.as_str();
        let params = &request.params;

        match method {
            // Subscriptions
            "scene.subscribe" => {
                let filter = params.get("filter").and_then(|v| v.as_str()).unwrap_or("*");
                let sub_id = self.next_sub_id;
                self.next_sub_id += 1;
                self.subscriptions.insert(sub_id, Subscription {
                    client_id,
                    _filter: EventFilter::new(filter),
                });
                let resp = JsonRpcResponse::success(id, serde_json::json!({"subscription_id": sub_id}));
                HandleResult::Response(serde_json::to_string(&resp).unwrap())
            }
            "scene.unsubscribe" => {
                if let Some(sid) = params.get("subscription_id").and_then(|v| v.as_u64()) {
                    self.subscriptions.remove(&sid);
                }
                let resp = JsonRpcResponse::success(id, serde_json::json!({"ok": true}));
                HandleResult::Response(serde_json::to_string(&resp).unwrap())
            }

            // Compositor commands
            "input.type" => {
                let text = params.get("text").and_then(|v| v.as_str()).unwrap_or("").to_string();
                HandleResult::Command(CompositorCmd::InputType { client_id, req_id: id, text })
            }
            "input.key" => {
                let combo = params.get("combo").and_then(|v| v.as_str()).unwrap_or("").to_string();
                HandleResult::Command(CompositorCmd::InputKey { client_id, req_id: id, combo })
            }
            "input.batch" => {
                let actions = params.get("actions")
                    .and_then(|v| v.as_array())
                    .cloned()
                    .unwrap_or_default();
                HandleResult::Command(CompositorCmd::InputBatch { client_id, req_id: id, actions })
            }
            "input.drag" => {
                let x1 = params.get("x1").and_then(|v| v.as_f64()).unwrap_or(0.0);
                let y1 = params.get("y1").and_then(|v| v.as_f64()).unwrap_or(0.0);
                let x2 = params.get("x2").and_then(|v| v.as_f64()).unwrap_or(0.0);
                let y2 = params.get("y2").and_then(|v| v.as_f64()).unwrap_or(0.0);
                let button = params.get("button").and_then(|v| v.as_u64()).unwrap_or(1) as u32;
                HandleResult::Command(CompositorCmd::InputDrag { client_id, req_id: id, x1, y1, x2, y2, button })
            }
            "window.spawn" => {
                let command = params.get("command").and_then(|v| v.as_str()).unwrap_or("").to_string();
                let args: Vec<String> = params.get("args")
                    .and_then(|v| v.as_array())
                    .map(|arr| arr.iter().filter_map(|v| v.as_str().map(String::from)).collect())
                    .unwrap_or_default();
                HandleResult::Command(CompositorCmd::WindowSpawn { client_id, req_id: id, command, args })
            }
            "input.scroll" => {
                let x = params.get("x").and_then(|v| v.as_f64()).unwrap_or(0.0);
                let y = params.get("y").and_then(|v| v.as_f64()).unwrap_or(0.0);
                let dx = params.get("dx").and_then(|v| v.as_f64()).unwrap_or(0.0);
                let dy = params.get("dy").and_then(|v| v.as_f64()).unwrap_or(0.0);
                HandleResult::Command(CompositorCmd::InputScroll { client_id, req_id: id, x, y, dx, dy })
            }
            "input.move" => {
                let x = params.get("x").and_then(|v| v.as_f64()).unwrap_or(0.0);
                let y = params.get("y").and_then(|v| v.as_f64()).unwrap_or(0.0);
                HandleResult::Command(CompositorCmd::InputMove { client_id, req_id: id, x, y })
            }
            "input.click" => {
                let x = params.get("x").and_then(|v| v.as_f64()).unwrap_or(0.0);
                let y = params.get("y").and_then(|v| v.as_f64()).unwrap_or(0.0);
                let button = params.get("button").and_then(|v| v.as_u64()).unwrap_or(1) as u32; // 1=left, 2=middle, 3=right
                HandleResult::Command(CompositorCmd::InputClick { client_id, req_id: id, x, y, button })
            }
            "window.close" => {
                let window_id = params.get("window_id").and_then(|v| v.as_u64());
                HandleResult::Command(CompositorCmd::WindowClose { client_id, req_id: id, window_id })
            }
            "window.focus" => {
                let window_id = params.get("window_id").and_then(|v| v.as_u64()).unwrap_or(0);
                HandleResult::Command(CompositorCmd::WindowFocus { client_id, req_id: id, window_id })
            }
            "scene.list_commands" | "help" => {
                let commands = serde_json::json!({"version": env!("CARGO_PKG_VERSION"), "commands": [
                    {"method": "scene.windows", "description": "List all windows with metadata"},
                    {"method": "scene.focused", "description": "Get the focused window"},
                    {"method": "scene.find", "params": {"query": "string"}, "description": "Search UI elements"},
                    {"method": "scene.graph", "description": "Get full scene graph tree"},
                    {"method": "scene.element_at", "params": {"x": 0, "y": 0}, "description": "Window at coordinates"},
                    {"method": "scene.screenshot", "description": "Capture screen as base64 PNG"},
                    {"method": "scene.subscribe", "params": {"filter": "*"}, "description": "Subscribe to events"},
                    {"method": "scene.unsubscribe", "params": {"subscription_id": 0}, "description": "Remove subscription"},
                    {"method": "scene.window_count", "description": "Count open windows"},
                    {"method": "scene.diff", "description": "Get changes since last query"},
                    {"method": "scene.wait_for", "params": {"title": "foo", "count": 2}, "description": "Check if condition is met (title/app_id/count)"},
                    {"method": "scene.status", "description": "Full compositor status overview"},
                    {"method": "scene.describe", "description": "Natural language desktop description"},
                    {"method": "scene.suggest", "description": "Suggested next actions for AI agent"},
                    {"method": "scene.ping", "description": "Health check"},
                    {"method": "scene.keyboard_shortcuts", "description": "List keyboard shortcuts"},
                    {"method": "scene.config", "description": "Get current compositor config"},
                    {"method": "scene.ascii", "description": "ASCII art map of desktop layout"},
                    {"method": "scene.summary", "description": "Complete context in one call (description + ASCII + suggestions + status)"},
                    {"method": "scene.annotated_screenshot", "description": "Screenshot with window boundaries and labels overlaid"},
                    {"method": "window.list", "description": "Concise window list (id, title, geometry)"},
                    {"method": "scene.list_commands", "description": "List available commands"},
                    {"method": "input.type", "params": {"text": "string"}, "description": "Type text into focused window"},
                    {"method": "input.key", "params": {"combo": "ctrl+s"}, "description": "Inject key combination"},
                    {"method": "input.click", "params": {"x": 0, "y": 0, "button": 1}, "description": "Click at coordinates"},
                    {"method": "input.scroll", "params": {"x": 0, "y": 0, "dx": 0, "dy": -3}, "description": "Scroll at coordinates"},
                    {"method": "input.move", "params": {"x": 0, "y": 0}, "description": "Move pointer to coordinates"},
                    {"method": "window.focus", "params": {"window_id": 0}, "description": "Focus window by ID"},
                    {"method": "window.close", "params": {"window_id": 0}, "description": "Close window by ID"},
                    {"method": "window.minimize", "params": {"window_id": 0}, "description": "Minimize window (remove from layout)"},
                    {"method": "window.swap_master", "params": {"window_id": 0}, "description": "Swap window to master position"},
                    {"method": "window.spawn", "params": {"command": "foot", "args": []}, "description": "Launch app inside compositor"},
                    {"method": "input.drag", "params": {"x1": 0, "y1": 0, "x2": 100, "y2": 100}, "description": "Drag from (x1,y1) to (x2,y2)"},
                    {"method": "input.batch", "params": {"actions": [{"method": "input.type", "params": {"text": "hi"}}, {"method": "input.key", "params": {"combo": "return"}}]}, "description": "Execute multiple actions atomically"},
                    {"method": "layout.set_ratio", "params": {"ratio": 0.6}, "description": "Set master window width ratio (0.2-0.8)"},
                    {"method": "layout.set_gap", "params": {"gap": 4}, "description": "Set gap between windows (0-32px)"},
                ]});
                let resp = JsonRpcResponse::success(id, commands);
                HandleResult::Response(serde_json::to_string(&resp).unwrap())
            }
            "layout.set_ratio" => {
                let ratio = params.get("ratio").and_then(|v| v.as_f64()).unwrap_or(0.6) as f32;
                HandleResult::Command(CompositorCmd::LayoutSetRatio { client_id, req_id: id, ratio })
            }
            "layout.set_gap" => {
                let gap = params.get("gap").and_then(|v| v.as_i64()).unwrap_or(4) as i32;
                HandleResult::Command(CompositorCmd::LayoutSetGap { client_id, req_id: id, gap })
            }
            "window.minimize" => {
                let window_id = params.get("window_id").and_then(|v| v.as_u64()).unwrap_or(0);
                HandleResult::Command(CompositorCmd::WindowMinimize { client_id, req_id: id, window_id })
            }
            "window.list" => {
                // Concise window list — just id, title, app_id, geometry
                let windows: Vec<serde_json::Value> = graph.windows().iter().map(|w| {
                    let val = serde_json::to_value(w).unwrap_or(serde_json::Value::Null);
                    serde_json::json!({
                        "id": val.get("id"),
                        "title": val.get("title"),
                        "app_id": val.get("app_id"),
                        "geometry": val.get("geometry"),
                    })
                }).collect();
                let resp = JsonRpcResponse::success(id, serde_json::Value::Array(windows));
                HandleResult::Response(serde_json::to_string(&resp).unwrap())
            }
            "window.swap_master" => {
                let window_id = params.get("window_id").and_then(|v| v.as_u64()).unwrap_or(0);
                HandleResult::Command(CompositorCmd::WindowSwapMaster { client_id, req_id: id, window_id })
            }
            "scene.element_at" => {
                let x = params.get("x").and_then(|v| v.as_f64()).unwrap_or(0.0);
                let y = params.get("y").and_then(|v| v.as_f64()).unwrap_or(0.0);
                HandleResult::Command(CompositorCmd::ElementAt { client_id, req_id: id, x, y })
            }
            "scene.wait_for" | "input.wait_for" => {
                let title = params.get("title").and_then(|v| v.as_str()).map(String::from);
                let app_id = params.get("app_id").and_then(|v| v.as_str()).map(String::from);
                let count = params.get("count").and_then(|v| v.as_u64()).map(|v| v as usize);
                HandleResult::Command(CompositorCmd::SceneWaitFor { client_id, req_id: id, title, app_id, count })
            }
            "scene.suggest" => {
                HandleResult::Command(CompositorCmd::Suggest { client_id, req_id: id })
            }
            "scene.summary" => {
                HandleResult::Command(CompositorCmd::Summary { client_id, req_id: id })
            }
            "scene.ascii" => {
                HandleResult::Command(CompositorCmd::AsciiLayout { client_id, req_id: id })
            }
            "scene.describe" => {
                HandleResult::Command(CompositorCmd::Describe { client_id, req_id: id })
            }
            "scene.status" => {
                HandleResult::Command(CompositorCmd::Status { client_id, req_id: id })
            }
            "scene.diff" => {
                HandleResult::Command(CompositorCmd::SceneDiff { client_id, req_id: id })
            }
            "scene.config" => {
                HandleResult::Command(CompositorCmd::GetConfig { client_id, req_id: id })
            }
            "scene.help_text" => {
                let text = format!(
                    "Aulinx Compositor v{ver}\n\n\
                    Scene: windows, focused, find, find_window, graph, element_at, window_count,\n\
                    \x20      screenshot, annotated_screenshot, ascii, describe, suggest, summary,\n\
                    \x20      diff, wait_for, status, config, subscribe, unsubscribe, list_commands,\n\
                    \x20      keyboard_shortcuts, ping, help_text\n\n\
                    Input: type, key, click, drag, scroll, move, batch\n\n\
                    Window: focus, close, swap_master, spawn, list\n\n\
                    Layout: set_ratio, set_gap\n\n\
                    Keys: Super+Return=term, Esc=quit, J/K=focus, H/L=resize, Space=swap,\n\
                    \x20     Shift+Q=close, F=fullscreen, 1-9=index",
                    ver = env!("CARGO_PKG_VERSION"),
                );
                let resp = JsonRpcResponse::success(id, serde_json::json!({"text": text}));
                HandleResult::Response(serde_json::to_string(&resp).unwrap())
            }
            "scene.ping" | "ping" => {
                let resp = JsonRpcResponse::success(id, serde_json::json!({"pong": true, "version": env!("CARGO_PKG_VERSION")}));
                HandleResult::Response(serde_json::to_string(&resp).unwrap())
            }
            "scene.keyboard_shortcuts" => {
                let shortcuts = serde_json::json!([
                    {"key": "Super+Return", "action": "Open terminal"},
                    {"key": "Super+Escape", "action": "Quit compositor"},
                    {"key": "Super+J", "action": "Focus next window"},
                    {"key": "Super+K", "action": "Focus previous window"},
                    {"key": "Super+Shift+Q", "action": "Close focused window"},
                    {"key": "Super+Space", "action": "Swap focused with master"},
                    {"key": "Super+F", "action": "Toggle fullscreen"},
                    {"key": "Super+1..9", "action": "Focus window by index"},
                ]);
                let resp = JsonRpcResponse::success(id, shortcuts);
                HandleResult::Response(serde_json::to_string(&resp).unwrap())
            }
            "scene.annotated_screenshot" => {
                HandleResult::Command(CompositorCmd::AnnotatedScreenshot { client_id, req_id: id })
            }
            "scene.screenshot" => {
                HandleResult::Command(CompositorCmd::Screenshot { client_id, req_id: id })
            }

            // Semantic queries
            _ => {
                match aulinx_semantic::query::execute_query(graph, method, params) {
                    Ok(result) => {
                        let resp = JsonRpcResponse::success(id, result);
                        HandleResult::Response(serde_json::to_string(&resp).unwrap())
                    }
                    Err(e) => {
                        let resp = JsonRpcResponse::error(id, METHOD_NOT_FOUND, e);
                        HandleResult::Response(serde_json::to_string(&resp).unwrap())
                    }
                }
            }
        }
    }
}

impl Drop for CompositorIpc {
    fn drop(&mut self) {
        let _ = std::fs::remove_file(&self.socket_path);
    }
}

enum HandleResult {
    Response(String),
    Command(CompositorCmd),
}

pub fn ipc_socket_path() -> PathBuf {
    if let Ok(path) = std::env::var("AULINX_SOCKET") {
        return PathBuf::from(path);
    }
    if let Ok(runtime_dir) = std::env::var("XDG_RUNTIME_DIR") {
        return PathBuf::from(runtime_dir).join("aulinx").join("semantic.sock");
    }
    PathBuf::from("/tmp/aulinx-semantic.sock")
}
