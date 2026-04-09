//! Unix socket JSON-RPC server.
//!
//! Listens on $XDG_RUNTIME_DIR/aulinx/semantic.sock and serves
//! scene graph queries, actions, and event subscriptions.

use std::collections::HashMap;
use std::io::{Read, Write};
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::Path;

use aulinx_semantic::protocol::*;

use crate::events::SubscriptionManager;

/// Process a raw JSON-RPC request line and return the response.
pub struct RequestHandler;

impl RequestHandler {
    pub fn handle(
        graph: &aulinx_semantic::SceneGraph,
        sources: &[Box<dyn aulinx_semantic::sources::Source>],
        subscriptions: &mut SubscriptionManager,
        client_id: u64,
        line: &str,
    ) -> String {
        let request: JsonRpcRequest = match serde_json::from_str(line) {
            Ok(r) => r,
            Err(e) => {
                let resp = JsonRpcResponse::error(None, PARSE_ERROR, format!("parse error: {e}"));
                return serde_json::to_string(&resp).unwrap_or_default();
            }
        };

        let response = Self::dispatch_request(graph, sources, subscriptions, client_id, &request);
        serde_json::to_string(&response).unwrap_or_default()
    }

    /// Dispatch a parsed JSON-RPC request to the appropriate handler.
    fn dispatch_request(
        graph: &aulinx_semantic::SceneGraph,
        sources: &[Box<dyn aulinx_semantic::sources::Source>],
        subscriptions: &mut SubscriptionManager,
        client_id: u64,
        request: &JsonRpcRequest,
    ) -> JsonRpcResponse {
        let method = request.method.as_str();
        let params = &request.params;
        let id = request.id.clone();

        // Query commands
        if method.starts_with("scene.") {
            match aulinx_semantic::query::execute_query(graph, method, params) {
                Ok(result) => return JsonRpcResponse::success(id, result),
                Err(e) if e.starts_with("unknown query") => {} // fall through to check other handlers
                Err(e) => return JsonRpcResponse::error(id, INVALID_PARAMS, e),
            }
        }

        match method {
            // Subscription commands
            "scene.subscribe" => {
                let filter = params
                    .get("filter")
                    .and_then(|v| v.as_str())
                    .unwrap_or("*");
                let sub_id = subscriptions.subscribe(client_id, filter);
                JsonRpcResponse::success(
                    id,
                    serde_json::json!({ "subscription_id": sub_id }),
                )
            }

            "scene.unsubscribe" => {
                let sub_id = params
                    .get("subscription_id")
                    .and_then(|v| v.as_u64());
                match sub_id {
                    Some(sid) => {
                        subscriptions.unsubscribe(sid);
                        JsonRpcResponse::success(id, serde_json::json!({ "ok": true }))
                    }
                    None => JsonRpcResponse::error(
                        id,
                        INVALID_PARAMS,
                        "missing subscription_id".into(),
                    ),
                }
            }

            // Action commands
            "element.activate" | "element.set_value" | "element.scroll" => {
                let node_id = match params.get("node_id").and_then(|v| v.as_u64()) {
                    Some(nid) => aulinx_semantic::NodeId(nid),
                    None => {
                        return JsonRpcResponse::error(
                            id,
                            INVALID_PARAMS,
                            "missing node_id".into(),
                        )
                    }
                };

                let action = match method {
                    "element.activate" => aulinx_semantic::ActionType::Activate,
                    "element.set_value" => aulinx_semantic::ActionType::SetValue,
                    "element.scroll" => aulinx_semantic::ActionType::Scroll,
                    _ => unreachable!(),
                };

                let value = params
                    .get("value")
                    .and_then(|v| v.as_str())
                    .map(String::from);

                let request = aulinx_semantic::ActionRequest {
                    node_id,
                    action,
                    value,
                };

                // Try each source until one handles it
                for source in sources {
                    match source.execute_action(&request) {
                        aulinx_semantic::ActionResult::Success => {
                            return JsonRpcResponse::success(
                                id,
                                serde_json::json!({ "ok": true }),
                            )
                        }
                        aulinx_semantic::ActionResult::Failed(msg) => {
                            return JsonRpcResponse::error(id, INTERNAL_ERROR, msg)
                        }
                        aulinx_semantic::ActionResult::NotFound
                        | aulinx_semantic::ActionResult::NotSupported => continue,
                    }
                }

                JsonRpcResponse::error(id, METHOD_NOT_FOUND, "no source can handle this action".into())
            }

            "window.focus" => {
                let window_id = match params.get("window_id").and_then(|v| v.as_u64()) {
                    Some(wid) => wid,
                    None => {
                        return JsonRpcResponse::error(
                            id,
                            INVALID_PARAMS,
                            "missing window_id".into(),
                        )
                    }
                };
                for source in sources {
                    match source.focus_window(window_id) {
                        aulinx_semantic::ActionResult::Success => {
                            return JsonRpcResponse::success(id, serde_json::json!({ "ok": true }))
                        }
                        aulinx_semantic::ActionResult::Failed(msg) => {
                            return JsonRpcResponse::error(id, INTERNAL_ERROR, msg)
                        }
                        _ => continue,
                    }
                }
                JsonRpcResponse::error(id, INTERNAL_ERROR, "no compositor source available for window.focus".into())
            }

            "window.close" => {
                let window_id = match params.get("window_id").and_then(|v| v.as_u64()) {
                    Some(wid) => wid,
                    None => {
                        return JsonRpcResponse::error(
                            id,
                            INVALID_PARAMS,
                            "missing window_id".into(),
                        )
                    }
                };
                for source in sources {
                    match source.close_window(window_id) {
                        aulinx_semantic::ActionResult::Success => {
                            return JsonRpcResponse::success(id, serde_json::json!({ "ok": true }))
                        }
                        aulinx_semantic::ActionResult::Failed(msg) => {
                            return JsonRpcResponse::error(id, INTERNAL_ERROR, msg)
                        }
                        _ => continue,
                    }
                }
                JsonRpcResponse::error(id, INTERNAL_ERROR, "no compositor source available for window.close".into())
            }

            // Query fallthrough
            _ => {
                // Try query engine one more time for non-scene prefixed queries
                match aulinx_semantic::query::execute_query(graph, method, params) {
                    Ok(result) => JsonRpcResponse::success(id, result),
                    Err(_) => JsonRpcResponse::error(
                        id,
                        METHOD_NOT_FOUND,
                        format!("unknown method: {method}"),
                    ),
                }
            }
        }
    }

}

/// Run a synchronous IPC server loop.
/// This is simpler than the calloop integration and works well for the daemon.
pub fn run_sync_server(
    socket_path: &Path,
    graph: &mut aulinx_semantic::SceneGraph,
    sources: &mut [Box<dyn aulinx_semantic::sources::Source>],
    tracker: &mut aulinx_semantic::DiffTracker,
    poll_interval: std::time::Duration,
) -> Result<(), Box<dyn std::error::Error>> {
    // Ensure parent directory exists
    if let Some(parent) = socket_path.parent() {
        std::fs::create_dir_all(parent)?;
    }

    // Remove stale socket
    let _ = std::fs::remove_file(socket_path);

    let listener = UnixListener::bind(socket_path)?;
    listener.set_nonblocking(true)?;
    tracing::info!("IPC server listening on {}", socket_path.display());

    let mut subscriptions = SubscriptionManager::new();
    let mut clients: HashMap<u64, UnixStream> = HashMap::new();
    let mut next_client_id: u64 = 1;
    let mut last_poll = std::time::Instant::now();

    loop {
        // Accept new connections
        match listener.accept() {
            Ok((stream, _)) => {
                stream.set_nonblocking(true).ok();
                let client_id = next_client_id;
                next_client_id += 1;
                tracing::info!("IPC: client {client_id} connected");
                clients.insert(client_id, stream);
            }
            Err(ref e) if e.kind() == std::io::ErrorKind::WouldBlock => {}
            Err(e) => tracing::error!("Accept error: {e}"),
        }

        // Read from clients
        let client_ids: Vec<u64> = clients.keys().copied().collect();
        let mut disconnected = Vec::new();

        for &client_id in &client_ids {
            let stream = clients.get_mut(&client_id).unwrap();
            let mut buf = [0u8; 8192];
            match stream.read(&mut buf) {
                Ok(0) => {
                    tracing::info!("IPC: client {client_id} disconnected");
                    disconnected.push(client_id);
                }
                Ok(n) => {
                    let data = String::from_utf8_lossy(&buf[..n]);
                    // Process each line as a JSON-RPC request
                    for line in data.lines() {
                        let line = line.trim();
                        if line.is_empty() {
                            continue;
                        }
                        let response = RequestHandler::handle(
                            graph,
                            sources,
                            &mut subscriptions,
                            client_id,
                            line,
                        );
                        // Send response + newline
                        let response_line = format!("{response}\n");
                        if let Err(e) = stream.write_all(response_line.as_bytes()) {
                            tracing::error!("IPC: write error for client {client_id}: {e}");
                            disconnected.push(client_id);
                        }
                    }
                }
                Err(ref e) if e.kind() == std::io::ErrorKind::WouldBlock => {}
                Err(e) => {
                    tracing::error!("IPC: read error for client {client_id}: {e}");
                    disconnected.push(client_id);
                }
            }
        }

        // Clean up disconnected clients
        for id in disconnected {
            clients.remove(&id);
            subscriptions.remove_client(id);
        }

        // Periodic poll of sources
        if last_poll.elapsed() >= poll_interval {
            graph.snapshot(tracker);

            for source in sources.iter_mut() {
                if let Err(e) = source.poll(graph) {
                    tracing::error!("Source '{}' poll error: {e}", source.name());
                }
            }

            // Compute events and push to subscribers
            let events = graph.diff(tracker);
            if !events.is_empty() {
                tracing::debug!("{} semantic events", events.len());
                let notifications = subscriptions.match_events(&events);
                for (client_id, event_json) in notifications {
                    if let Some(stream) = clients.get_mut(&client_id) {
                        let line = format!("{event_json}\n");
                        if let Err(e) = stream.write_all(line.as_bytes()) {
                            tracing::debug!("Failed to push event to client {client_id}: {e}");
                        }
                    }
                }
            }

            last_poll = std::time::Instant::now();
        }

        // Small sleep to avoid busy-looping
        std::thread::sleep(std::time::Duration::from_millis(50));
    }
}
