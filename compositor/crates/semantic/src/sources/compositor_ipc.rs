//! Compositor IPC source — reads window data from Sway/Hyprland/niri.
//!
//! Auto-detects the running compositor and connects to its IPC socket.
//! Provides window-level data (title, app_id, geometry, focus, workspace)
//! that supplements AT-SPI's element-level data.
//!
//! Supported compositors:
//! - **Sway**: `$SWAYSOCK`, JSON IPC, `swaymsg -t get_tree`
//! - **Hyprland**: `$HYPRLAND_INSTANCE_SIGNATURE`, JSON via `hyprctl`
//! - **niri**: `$NIRI_SOCKET`, JSON IPC

use std::collections::{HashMap, HashSet};
use std::process::Command;

use crate::action::{ActionRequest, ActionResult};
use crate::graph::SceneGraph;
use crate::node::*;
use crate::sources::Source;

/// Detected compositor type.
#[derive(Debug, Clone, PartialEq)]
enum CompositorType {
    Sway,
    Hyprland,
    Niri,
    Unknown,
}

/// Window data extracted from compositor IPC.
#[derive(Debug)]
struct WindowInfo {
    /// Compositor-assigned ID.
    id: u64,
    /// PID of the client process.
    pid: u32,
    /// Wayland app_id or X11 class.
    app_id: String,
    /// Window title.
    title: String,
    /// Position and size.
    geometry: Rect,
    /// Whether this window has input focus.
    focused: bool,
    /// Workspace index (0-based).
    workspace: usize,
    /// Whether the window is floating.
    floating: bool,
}

pub struct CompositorIpcSource {
    compositor: CompositorType,
    screen_node: Option<NodeId>,
    /// Maps compositor window IDs to our graph NodeIds.
    window_map: HashMap<u64, NodeId>,
}

impl CompositorIpcSource {
    pub fn new() -> Self {
        Self {
            compositor: CompositorType::Unknown,
            screen_node: None,
            window_map: HashMap::new(),
        }
    }

    /// Detect which compositor is running.
    fn detect_compositor() -> CompositorType {
        if std::env::var("SWAYSOCK").is_ok() {
            return CompositorType::Sway;
        }
        if std::env::var("HYPRLAND_INSTANCE_SIGNATURE").is_ok() {
            return CompositorType::Hyprland;
        }
        if std::env::var("NIRI_SOCKET").is_ok() {
            return CompositorType::Niri;
        }
        CompositorType::Unknown
    }

    /// Fetch window list from the detected compositor.
    fn fetch_windows(&self) -> Vec<WindowInfo> {
        match self.compositor {
            CompositorType::Sway => self.fetch_sway_windows(),
            CompositorType::Hyprland => self.fetch_hyprland_windows(),
            CompositorType::Niri => self.fetch_niri_windows(),
            CompositorType::Unknown => Vec::new(),
        }
    }

    // ---- Sway ----

    fn fetch_sway_windows(&self) -> Vec<WindowInfo> {
        let output = match Command::new("swaymsg")
            .args(["-t", "get_tree", "--raw"])
            .output()
        {
            Ok(o) => o,
            Err(e) => {
                tracing::debug!("swaymsg failed: {e}");
                return Vec::new();
            }
        };

        let json: serde_json::Value = match serde_json::from_slice(&output.stdout) {
            Ok(v) => v,
            Err(e) => {
                tracing::debug!("swaymsg parse error: {e}");
                return Vec::new();
            }
        };

        let mut windows = Vec::new();
        Self::walk_sway_tree(&json, &mut windows, 0);
        windows
    }

    fn walk_sway_tree(node: &serde_json::Value, windows: &mut Vec<WindowInfo>, workspace: usize) {
        let node_type = node.get("type").and_then(|v| v.as_str()).unwrap_or("");

        // Track workspace number
        let ws = if node_type == "workspace" {
            node.get("num").and_then(|v| v.as_u64()).unwrap_or(0) as usize
        } else {
            workspace
        };

        // Leaf nodes with a pid are application windows
        if node.get("pid").and_then(|v| v.as_u64()).is_some()
            && (node_type == "con" || node_type == "floating_con")
        {
            let rect = node.get("rect").unwrap_or(&serde_json::Value::Null);
            let window = WindowInfo {
                id: node.get("id").and_then(|v| v.as_u64()).unwrap_or(0),
                pid: node.get("pid").and_then(|v| v.as_u64()).unwrap_or(0) as u32,
                app_id: node
                    .get("app_id")
                    .and_then(|v| v.as_str())
                    .or_else(|| {
                        node.get("window_properties")
                            .and_then(|wp| wp.get("class"))
                            .and_then(|v| v.as_str())
                    })
                    .unwrap_or("")
                    .to_string(),
                title: node
                    .get("name")
                    .and_then(|v| v.as_str())
                    .unwrap_or("")
                    .to_string(),
                geometry: Rect::new(
                    rect.get("x").and_then(|v| v.as_i64()).unwrap_or(0) as i32,
                    rect.get("y").and_then(|v| v.as_i64()).unwrap_or(0) as i32,
                    rect.get("width").and_then(|v| v.as_i64()).unwrap_or(0) as i32,
                    rect.get("height").and_then(|v| v.as_i64()).unwrap_or(0) as i32,
                ),
                focused: node.get("focused").and_then(|v| v.as_bool()).unwrap_or(false),
                workspace: ws,
                floating: node_type == "floating_con",
            };
            windows.push(window);
        }

        // Recurse into children
        if let Some(nodes) = node.get("nodes").and_then(|v| v.as_array()) {
            for child in nodes {
                Self::walk_sway_tree(child, windows, ws);
            }
        }
        if let Some(nodes) = node.get("floating_nodes").and_then(|v| v.as_array()) {
            for child in nodes {
                Self::walk_sway_tree(child, windows, ws);
            }
        }
    }

    // ---- Hyprland ----

    fn fetch_hyprland_windows(&self) -> Vec<WindowInfo> {
        let output = match Command::new("hyprctl")
            .args(["clients", "-j"])
            .output()
        {
            Ok(o) => o,
            Err(e) => {
                tracing::debug!("hyprctl failed: {e}");
                return Vec::new();
            }
        };

        let clients: Vec<serde_json::Value> = match serde_json::from_slice(&output.stdout) {
            Ok(v) => v,
            Err(e) => {
                tracing::debug!("hyprctl parse error: {e}");
                return Vec::new();
            }
        };

        // Get focused window
        let active_addr = Command::new("hyprctl")
            .args(["activewindow", "-j"])
            .output()
            .ok()
            .and_then(|o| serde_json::from_slice::<serde_json::Value>(&o.stdout).ok())
            .and_then(|v| v.get("address").and_then(|a| a.as_str()).map(String::from))
            .unwrap_or_default();

        clients
            .iter()
            .map(|c| {
                let at = c.get("at").and_then(|v| v.as_array());
                let size = c.get("size").and_then(|v| v.as_array());
                let addr = c
                    .get("address")
                    .and_then(|v| v.as_str())
                    .unwrap_or("");

                WindowInfo {
                    id: u64::from_str_radix(addr.trim_start_matches("0x"), 16).unwrap_or(0),
                    pid: c.get("pid").and_then(|v| v.as_u64()).unwrap_or(0) as u32,
                    app_id: c
                        .get("class")
                        .and_then(|v| v.as_str())
                        .unwrap_or("")
                        .to_string(),
                    title: c
                        .get("title")
                        .and_then(|v| v.as_str())
                        .unwrap_or("")
                        .to_string(),
                    geometry: Rect::new(
                        at.and_then(|a| a.first())
                            .and_then(|v| v.as_i64())
                            .unwrap_or(0) as i32,
                        at.and_then(|a| a.get(1))
                            .and_then(|v| v.as_i64())
                            .unwrap_or(0) as i32,
                        size.and_then(|a| a.first())
                            .and_then(|v| v.as_i64())
                            .unwrap_or(0) as i32,
                        size.and_then(|a| a.get(1))
                            .and_then(|v| v.as_i64())
                            .unwrap_or(0) as i32,
                    ),
                    focused: addr == active_addr,
                    workspace: c
                        .get("workspace")
                        .and_then(|w| w.get("id"))
                        .and_then(|v| v.as_u64())
                        .unwrap_or(1) as usize
                        - 1,
                    floating: c
                        .get("floating")
                        .and_then(|v| v.as_bool())
                        .unwrap_or(false),
                }
            })
            .collect()
    }

    // ---- niri ----

    fn fetch_niri_windows(&self) -> Vec<WindowInfo> {
        // niri's IPC returns JSON when using `niri msg -j windows`
        let output_j = match Command::new("niri")
            .args(["msg", "-j", "windows"])
            .output()
        {
            Ok(o) => o,
            Err(_) => return Vec::new(),
        };

        let windows: Vec<serde_json::Value> = match serde_json::from_slice(&output_j.stdout) {
            Ok(v) => v,
            Err(e) => {
                tracing::debug!("niri parse error: {e}");
                return Vec::new();
            }
        };

        // Get focused window
        let focused_id = Command::new("niri")
            .args(["msg", "-j", "focused-window"])
            .output()
            .ok()
            .and_then(|o| serde_json::from_slice::<serde_json::Value>(&o.stdout).ok())
            .and_then(|v| v.get("id").and_then(|id| id.as_u64()))
            .unwrap_or(0);

        windows
            .iter()
            .map(|w| WindowInfo {
                id: w.get("id").and_then(|v| v.as_u64()).unwrap_or(0),
                pid: w.get("pid").and_then(|v| v.as_u64()).unwrap_or(0) as u32,
                app_id: w
                    .get("app_id")
                    .and_then(|v| v.as_str())
                    .unwrap_or("")
                    .to_string(),
                title: w
                    .get("title")
                    .and_then(|v| v.as_str())
                    .unwrap_or("")
                    .to_string(),
                geometry: Rect::new(0, 0, 0, 0), // niri doesn't expose geometry in window list
                focused: w.get("id").and_then(|v| v.as_u64()).unwrap_or(0) == focused_id,
                workspace: w
                    .get("workspace_id")
                    .and_then(|v| v.as_u64())
                    .unwrap_or(1) as usize
                    - 1,
                floating: false, // niri is tiling-only
            })
            .collect()
    }

    /// Sync fetched windows into the scene graph.
    fn sync_windows(&mut self, graph: &mut SceneGraph, windows: Vec<WindowInfo>) {
        let screen_id = match self.screen_node {
            Some(id) => id,
            None => return,
        };

        // Track which compositor IDs we've seen
        let mut seen_ids: HashSet<u64> = HashSet::new();

        for win in &windows {
            seen_ids.insert(win.id);

            if let Some(&node_id) = self.window_map.get(&win.id) {
                // Update existing window
                if let Some(SemanticNode::Window {
                    title,
                    geometry,
                    focused,
                    workspace,
                    floating,
                    ..
                }) = graph.get_mut(node_id)
                {
                    *title = win.title.clone();
                    *geometry = win.geometry;
                    *focused = win.focused;
                    *workspace = win.workspace;
                    *floating = win.floating;
                }
            } else {
                // New window
                let node_id = graph.add_window(
                    screen_id,
                    win.id,
                    win.pid,
                    &win.app_id,
                    &win.title,
                    win.geometry,
                );
                // Set additional fields
                if let Some(SemanticNode::Window {
                    focused,
                    workspace,
                    floating,
                    ..
                }) = graph.get_mut(node_id)
                {
                    *focused = win.focused;
                    *workspace = win.workspace;
                    *floating = win.floating;
                }
                self.window_map.insert(win.id, node_id);
            }

            // Update focus tracking
            if win.focused {
                graph.set_focused_window(Some(win.id));
            }
        }

        // Remove windows that no longer exist
        let removed: Vec<u64> = self
            .window_map
            .keys()
            .filter(|id| !seen_ids.contains(id))
            .copied()
            .collect();
        for id in removed {
            graph.remove_window(id);
            self.window_map.remove(&id);
        }
    }

    /// Focus a window via compositor IPC.
    fn do_focus_window(&self, window_id: u64) -> ActionResult {
        let result = match self.compositor {
            CompositorType::Sway => Command::new("swaymsg")
                .args(["[con_id=".to_string() + &window_id.to_string() + "]", "focus".into()])
                .output(),
            CompositorType::Hyprland => Command::new("hyprctl")
                .args(["dispatch", "focuswindow", &format!("address:0x{window_id:x}")])
                .output(),
            CompositorType::Niri => Command::new("niri")
                .args(["msg", "action", "focus-window", "--id", &window_id.to_string()])
                .output(),
            CompositorType::Unknown => return ActionResult::NotSupported,
        };

        match result {
            Ok(o) if o.status.success() => ActionResult::Success,
            Ok(o) => ActionResult::Failed(String::from_utf8_lossy(&o.stderr).into()),
            Err(e) => ActionResult::Failed(e.to_string()),
        }
    }

    /// Close a window via compositor IPC.
    fn do_close_window(&self, window_id: u64) -> ActionResult {
        let result = match self.compositor {
            CompositorType::Sway => Command::new("swaymsg")
                .args([
                    format!("[con_id={window_id}]"),
                    "kill".into(),
                ])
                .output(),
            CompositorType::Hyprland => Command::new("hyprctl")
                .args(["dispatch", "closewindow", &format!("address:0x{window_id:x}")])
                .output(),
            CompositorType::Niri => Command::new("niri")
                .args(["msg", "action", "close-window", "--id", &window_id.to_string()])
                .output(),
            CompositorType::Unknown => return ActionResult::NotSupported,
        };

        match result {
            Ok(o) if o.status.success() => ActionResult::Success,
            Ok(o) => ActionResult::Failed(String::from_utf8_lossy(&o.stderr).into()),
            Err(e) => ActionResult::Failed(e.to_string()),
        }
    }
}

impl Source for CompositorIpcSource {
    fn name(&self) -> &str {
        "compositor_ipc"
    }

    fn start(&mut self, graph: &mut SceneGraph) -> Result<(), Box<dyn std::error::Error>> {
        self.compositor = Self::detect_compositor();

        if self.compositor == CompositorType::Unknown {
            return Err("No supported compositor detected (need Sway, Hyprland, or niri)".into());
        }

        tracing::info!(
            "Compositor IPC source: detected {:?} compositor",
            self.compositor
        );

        // Create a screen if the graph is empty
        if graph.is_empty() {
            self.screen_node = Some(graph.add_screen("default", Rect::new(0, 0, 1920, 1080)));
        } else {
            // Use the first existing screen
            if let SemanticNode::Desktop { screens } = graph.root() {
                self.screen_node = screens.first().copied();
            }
        }

        // Initial window fetch
        self.poll(graph)?;
        Ok(())
    }

    fn poll(&mut self, graph: &mut SceneGraph) -> Result<(), Box<dyn std::error::Error>> {
        let windows = self.fetch_windows();
        tracing::debug!(
            "Compositor IPC: fetched {} windows from {:?}",
            windows.len(),
            self.compositor
        );
        self.sync_windows(graph, windows);
        Ok(())
    }

    fn execute_action(&self, _request: &ActionRequest) -> ActionResult {
        ActionResult::NotSupported
    }

    fn focus_window(&self, window_id: u64) -> ActionResult {
        self.do_focus_window(window_id)
    }

    fn close_window(&self, window_id: u64) -> ActionResult {
        self.do_close_window(window_id)
    }
}
