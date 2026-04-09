//! Compositor IPC — serves semantic queries + compositor commands.

use std::collections::HashMap;
use std::io::{Read, Write};
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::{Path, PathBuf};

use aulinx_semantic::protocol::*;
use aulinx_semantic::SceneGraph;

pub struct CompositorIpc {
    listener: UnixListener,
    socket_path: PathBuf,
    clients: HashMap<u64, UnixStream>,
    next_id: u64,
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
        })
    }

    /// Poll for connections and requests. Returns responses to send.
    pub fn poll(&mut self, graph: &SceneGraph) {
        // Accept new connections
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

        // Read from clients
        let ids: Vec<u64> = self.clients.keys().copied().collect();
        let mut disconnected = Vec::new();

        for &id in &ids {
            let stream = self.clients.get_mut(&id).unwrap();
            let mut buf = [0u8; 8192];
            match stream.read(&mut buf) {
                Ok(0) => { disconnected.push(id); }
                Ok(n) => {
                    let data = String::from_utf8_lossy(&buf[..n]).to_string();
                    for line in data.lines() {
                        let line = line.trim();
                        if line.is_empty() { continue; }
                        let response = Self::handle(graph, line);
                        let msg = format!("{response}\n");
                        if stream.write_all(msg.as_bytes()).is_err() {
                            disconnected.push(id);
                        }
                    }
                }
                Err(ref e) if e.kind() == std::io::ErrorKind::WouldBlock => {}
                Err(_) => { disconnected.push(id); }
            }
        }

        for id in disconnected {
            self.clients.remove(&id);
        }
    }

    fn handle(graph: &SceneGraph, line: &str) -> String {
        let request: JsonRpcRequest = match serde_json::from_str(line) {
            Ok(r) => r,
            Err(e) => {
                let resp = JsonRpcResponse::error(None, PARSE_ERROR, format!("{e}"));
                return serde_json::to_string(&resp).unwrap();
            }
        };

        let id = request.id.clone();
        match aulinx_semantic::query::execute_query(graph, &request.method, &request.params) {
            Ok(result) => {
                let resp = JsonRpcResponse::success(id, result);
                serde_json::to_string(&resp).unwrap()
            }
            Err(e) => {
                let resp = JsonRpcResponse::error(id, METHOD_NOT_FOUND, e);
                serde_json::to_string(&resp).unwrap()
            }
        }
    }
}

impl Drop for CompositorIpc {
    fn drop(&mut self) {
        let _ = std::fs::remove_file(&self.socket_path);
    }
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
