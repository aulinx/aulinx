//! Compositor IPC server — unified semantic + compositor commands.
//!
//! Serves on $XDG_RUNTIME_DIR/aulinx/semantic.sock (same socket as daemon).
//! Clients get the same semantic API (scene.*, element.*) PLUS compositor-only
//! commands (window.move, input.*, screen.capture).

use std::collections::HashMap;
use std::io::{Read, Write};
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::{Path, PathBuf};

use aulinx_semantic::diff::{EventFilter, SemanticEvent};
use aulinx_semantic::protocol::*;
use aulinx_semantic::SceneGraph;

/// Subscription for event streaming.
struct Subscription {
    id: u64,
    client_id: u64,
    filter: EventFilter,
}

/// The compositor's IPC server.
pub struct CompositorIpc {
    listener: UnixListener,
    socket_path: PathBuf,
    clients: HashMap<u64, UnixStream>,
    next_client_id: u64,
    subscriptions: HashMap<u64, Subscription>,
    next_sub_id: u64,
}

impl CompositorIpc {
    /// Bind the IPC server to the socket path.
    pub fn new(socket_path: &Path) -> Result<Self, Box<dyn std::error::Error>> {
        if let Some(parent) = socket_path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        let _ = std::fs::remove_file(socket_path);

        let listener = UnixListener::bind(socket_path)?;
        listener.set_nonblocking(true)?;

        tracing::info!("Compositor IPC listening on {}", socket_path.display());

        Ok(Self {
            listener,
            socket_path: socket_path.to_owned(),
            clients: HashMap::new(),
            next_client_id: 1,
            subscriptions: HashMap::new(),
            next_sub_id: 1,
        })
    }

    /// Poll for new connections and incoming requests.
    /// Returns a list of (method, params, response_client_id) for compositor-specific commands.
    pub fn poll(&mut self, graph: &SceneGraph) -> Vec<CompositorCommand> {
        let mut commands = Vec::new();

        // Accept new connections
        loop {
            match self.listener.accept() {
                Ok((stream, _)) => {
                    stream.set_nonblocking(true).ok();
                    let id = self.next_client_id;
                    self.next_client_id += 1;
                    tracing::debug!("IPC: client {id} connected");
                    self.clients.insert(id, stream);
                }
                Err(ref e) if e.kind() == std::io::ErrorKind::WouldBlock => break,
                Err(e) => {
                    tracing::error!("IPC accept error: {e}");
                    break;
                }
            }
        }

        // Read from clients
        let client_ids: Vec<u64> = self.clients.keys().copied().collect();
        let mut disconnected = Vec::new();

        for &client_id in &client_ids {
            let stream = self.clients.get_mut(&client_id).unwrap();
            let mut buf = [0u8; 8192];
            match stream.read(&mut buf) {
                Ok(0) => {
                    tracing::debug!("IPC: client {client_id} disconnected");
                    disconnected.push(client_id);
                }
                Ok(n) => {
                    let data = String::from_utf8_lossy(&buf[..n]).to_string();
                    for line in data.lines() {
                        let line = line.trim();
                        if line.is_empty() {
                            continue;
                        }
                        match self.handle_request(graph, client_id, line) {
                            RequestResult::Response(resp) => {
                                let msg = format!("{resp}\n");
                                if let Some(s) = self.clients.get_mut(&client_id) {
                                    if let Err(e) = s.write_all(msg.as_bytes()) {
                                        tracing::debug!("IPC write error: {e}");
                                        disconnected.push(client_id);
                                    }
                                }
                            }
                            RequestResult::CompositorCommand(cmd) => {
                                commands.push(cmd);
                            }
                        }
                    }
                }
                Err(ref e) if e.kind() == std::io::ErrorKind::WouldBlock => {}
                Err(e) => {
                    tracing::debug!("IPC read error for client {client_id}: {e}");
                    disconnected.push(client_id);
                }
            }
        }

        for id in disconnected {
            self.clients.remove(&id);
            self.subscriptions.retain(|_, s| s.client_id != id);
        }

        commands
    }

    /// Push semantic events to subscribed clients.
    pub fn push_events(&mut self, events: &[SemanticEvent]) {
        for event in events {
            let matching_subs: Vec<(u64, u64)> = self
                .subscriptions
                .values()
                .filter(|s| s.filter.matches(event))
                .map(|s| (s.client_id, s.id))
                .collect();

            for (client_id, _) in matching_subs {
                let notification = serde_json::json!({
                    "jsonrpc": "2.0",
                    "method": "scene.event",
                    "params": event,
                });
                if let Ok(json) = serde_json::to_string(&notification) {
                    let msg = format!("{json}\n");
                    if let Some(stream) = self.clients.get_mut(&client_id) {
                        stream.write_all(msg.as_bytes()).ok();
                    }
                }
            }
        }
    }

    /// Send a response to a specific client.
    pub fn send_response(&mut self, client_id: u64, response: &str) {
        if let Some(stream) = self.clients.get_mut(&client_id) {
            let msg = format!("{response}\n");
            stream.write_all(msg.as_bytes()).ok();
        }
    }

    fn handle_request(
        &mut self,
        graph: &SceneGraph,
        client_id: u64,
        line: &str,
    ) -> RequestResult {
        let request: JsonRpcRequest = match serde_json::from_str(line) {
            Ok(r) => r,
            Err(e) => {
                let resp = JsonRpcResponse::error(None, PARSE_ERROR, format!("parse error: {e}"));
                return RequestResult::Response(serde_json::to_string(&resp).unwrap());
            }
        };

        let method = request.method.as_str();
        let params = &request.params;
        let id = request.id.clone();

        // Semantic query commands — handled directly
        if method.starts_with("scene.") && method != "scene.subscribe" && method != "scene.unsubscribe" {
            match aulinx_semantic::query::execute_query(graph, method, params) {
                Ok(result) => {
                    let resp = JsonRpcResponse::success(id, result);
                    return RequestResult::Response(serde_json::to_string(&resp).unwrap());
                }
                Err(e) if !e.starts_with("unknown") => {
                    let resp = JsonRpcResponse::error(id, INVALID_PARAMS, e);
                    return RequestResult::Response(serde_json::to_string(&resp).unwrap());
                }
                _ => {} // fall through
            }
        }

        match method {
            "scene.subscribe" => {
                let filter = params
                    .get("filter")
                    .and_then(|v| v.as_str())
                    .unwrap_or("*");
                let sub_id = self.next_sub_id;
                self.next_sub_id += 1;
                self.subscriptions.insert(
                    sub_id,
                    Subscription {
                        id: sub_id,
                        client_id,
                        filter: EventFilter::new(filter),
                    },
                );
                let resp = JsonRpcResponse::success(
                    id,
                    serde_json::json!({ "subscription_id": sub_id }),
                );
                RequestResult::Response(serde_json::to_string(&resp).unwrap())
            }

            "scene.unsubscribe" => {
                let sub_id = params.get("subscription_id").and_then(|v| v.as_u64());
                if let Some(sid) = sub_id {
                    self.subscriptions.remove(&sid);
                    let resp = JsonRpcResponse::success(id, serde_json::json!({ "ok": true }));
                    RequestResult::Response(serde_json::to_string(&resp).unwrap())
                } else {
                    let resp = JsonRpcResponse::error(id, INVALID_PARAMS, "missing subscription_id".into());
                    RequestResult::Response(serde_json::to_string(&resp).unwrap())
                }
            }

            // Compositor-specific commands — dispatch to state
            "window.move" | "window.focus" | "window.close" | "window.screenshot"
            | "input.type" | "input.key" | "input.mouse" | "screen.capture"
            | "element.activate" | "element.set_value" => {
                RequestResult::CompositorCommand(CompositorCommand {
                    client_id,
                    request_id: id,
                    method: method.to_string(),
                    params: params.clone(),
                })
            }

            _ => {
                let resp = JsonRpcResponse::error(
                    id,
                    METHOD_NOT_FOUND,
                    format!("unknown method: {method}"),
                );
                RequestResult::Response(serde_json::to_string(&resp).unwrap())
            }
        }
    }

    pub fn socket_path(&self) -> &Path {
        &self.socket_path
    }
}

impl Drop for CompositorIpc {
    fn drop(&mut self) {
        let _ = std::fs::remove_file(&self.socket_path);
    }
}

enum RequestResult {
    /// Fully handled — send this response.
    Response(String),
    /// Needs compositor state — dispatch to AulinxState.
    CompositorCommand(CompositorCommand),
}

/// A command that requires compositor state to handle.
pub struct CompositorCommand {
    pub client_id: u64,
    pub request_id: Option<serde_json::Value>,
    pub method: String,
    pub params: serde_json::Value,
}
