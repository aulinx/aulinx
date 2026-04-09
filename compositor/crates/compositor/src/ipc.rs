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
    filter: EventFilter,
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
    WindowClose { client_id: u64, req_id: Option<serde_json::Value> },
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
    pub fn push_events(&mut self, events: &[SemanticEvent]) {
        for event in events {
            let matching: Vec<u64> = self.subscriptions.values()
                .filter(|s| s.filter.matches(event))
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
                    filter: EventFilter::new(filter),
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
