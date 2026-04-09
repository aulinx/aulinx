//! Change detection and semantic events.
//!
//! The diff engine compares scene graph states and emits events
//! describing what changed. AI agents subscribe to these events
//! instead of polling screenshots.

use std::collections::HashMap;

use serde::{Deserialize, Serialize};

use crate::node::{ElementRole, ElementState, NodeId, Rect, SemanticNode};

/// A semantic event describing a change on the desktop.
///
/// These events replace screenshot-based perception. Instead of
/// re-screenshotting the entire desktop, the AI receives targeted
/// notifications: "a dialog appeared", "text changed", "focus moved".
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "event", rename_all = "snake_case")]
pub enum SemanticEvent {
    WindowOpened {
        window_id: u64,
        app_id: String,
        title: String,
    },
    WindowClosed {
        window_id: u64,
    },
    WindowFocused {
        window_id: u64,
    },
    WindowMoved {
        window_id: u64,
        geometry: Rect,
    },
    WindowTitleChanged {
        window_id: u64,
        old: String,
        new: String,
    },
    ElementAppeared {
        window_id: u64,
        node_id: NodeId,
        role: ElementRole,
        label: String,
    },
    ElementDisappeared {
        window_id: u64,
        node_id: NodeId,
    },
    ElementChanged {
        window_id: u64,
        node_id: NodeId,
        property: String,
        old: serde_json::Value,
        new: serde_json::Value,
    },
    FocusChanged {
        window_id: u64,
        element_id: Option<NodeId>,
    },
}

/// A subscription filter for semantic events.
#[derive(Debug, Clone)]
pub struct EventFilter {
    pattern: String,
}

impl EventFilter {
    pub fn new(pattern: &str) -> Self {
        Self {
            pattern: pattern.to_string(),
        }
    }

    /// Check if an event matches this filter.
    pub fn matches(&self, event: &SemanticEvent) -> bool {
        if self.pattern == "*" {
            return true;
        }

        let event_type = match event {
            SemanticEvent::WindowOpened { .. } => "window.opened",
            SemanticEvent::WindowClosed { .. } => "window.closed",
            SemanticEvent::WindowFocused { .. } => "window.focused",
            SemanticEvent::WindowMoved { .. } => "window.moved",
            SemanticEvent::WindowTitleChanged { .. } => "window.title_changed",
            SemanticEvent::ElementAppeared { .. } => "element.appeared",
            SemanticEvent::ElementDisappeared { .. } => "element.disappeared",
            SemanticEvent::ElementChanged { .. } => "element.changed",
            SemanticEvent::FocusChanged { .. } => "focus.changed",
        };

        if self.pattern == event_type {
            return true;
        }

        // Support prefix matching: "window.*" matches all window events
        if let Some(prefix) = self.pattern.strip_suffix(".*") {
            return event_type.starts_with(prefix);
        }

        false
    }
}

/// A snapshot of window state for diffing.
#[derive(Debug, Clone)]
struct WindowSnapshot {
    window_id: u64,
    title: String,
    geometry: Rect,
    focused: bool,
    app_id: String,
}

/// A snapshot of element state for diffing.
#[derive(Debug, Clone)]
struct ElementSnapshot {
    window_id: u64,
    role: ElementRole,
    label: String,
    value: Option<String>,
    state: ElementState,
}

/// Tracks the previous state of the scene graph to detect changes.
///
/// Call `snapshot()` to capture current state, then `diff()` after
/// updates to get the list of semantic events.
pub struct DiffTracker {
    prev_windows: HashMap<u64, WindowSnapshot>,
    prev_elements: HashMap<NodeId, ElementSnapshot>,
    prev_focused_window: Option<u64>,
    prev_focused_element: Option<NodeId>,
}

impl DiffTracker {
    pub fn new() -> Self {
        Self {
            prev_windows: HashMap::new(),
            prev_elements: HashMap::new(),
            prev_focused_window: None,
            prev_focused_element: None,
        }
    }

    /// Capture a snapshot of the current graph state.
    /// Call this BEFORE making changes, then call `diff()` after.
    pub fn snapshot(&mut self, nodes: &HashMap<NodeId, SemanticNode>, focused: (Option<u64>, Option<NodeId>)) {
        self.prev_windows.clear();
        self.prev_elements.clear();

        for (node_id, node) in nodes {
            match node {
                SemanticNode::Window {
                    id,
                    title,
                    geometry,
                    focused,
                    app_id,
                    ..
                } => {
                    self.prev_windows.insert(
                        *id,
                        WindowSnapshot {
                            window_id: *id,
                            title: title.clone(),
                            geometry: *geometry,
                            focused: *focused,
                            app_id: app_id.clone(),
                        },
                    );
                }
                SemanticNode::Element {
                    role,
                    label,
                    value,
                    state,
                    ..
                } => {
                    // Find the owning window for this element
                    if let Some(win_id) = find_owning_window(nodes, *node_id) {
                        self.prev_elements.insert(
                            *node_id,
                            ElementSnapshot {
                                window_id: win_id,
                                role: role.clone(),
                                label: label.clone(),
                                value: value.clone(),
                                state: state.clone(),
                            },
                        );
                    }
                }
                _ => {}
            }
        }

        self.prev_focused_window = focused.0;
        self.prev_focused_element = focused.1;
    }

    /// Compare current graph state against the previous snapshot and emit events.
    pub fn diff(&self, nodes: &HashMap<NodeId, SemanticNode>, focused: (Option<u64>, Option<NodeId>)) -> Vec<SemanticEvent> {
        let mut events = Vec::new();

        // Collect current windows
        let mut cur_windows: HashMap<u64, WindowSnapshot> = HashMap::new();
        let mut cur_elements: HashMap<NodeId, ElementSnapshot> = HashMap::new();

        for (node_id, node) in nodes {
            match node {
                SemanticNode::Window {
                    id,
                    title,
                    geometry,
                    focused,
                    app_id,
                    ..
                } => {
                    cur_windows.insert(
                        *id,
                        WindowSnapshot {
                            window_id: *id,
                            title: title.clone(),
                            geometry: *geometry,
                            focused: *focused,
                            app_id: app_id.clone(),
                        },
                    );
                }
                SemanticNode::Element {
                    role,
                    label,
                    value,
                    state,
                    ..
                } => {
                    if let Some(win_id) = find_owning_window(nodes, *node_id) {
                        cur_elements.insert(
                            *node_id,
                            ElementSnapshot {
                                window_id: win_id,
                                role: role.clone(),
                                label: label.clone(),
                                value: value.clone(),
                                state: state.clone(),
                            },
                        );
                    }
                }
                _ => {}
            }
        }

        // Windows opened (in current but not in previous)
        for (win_id, snap) in &cur_windows {
            if !self.prev_windows.contains_key(win_id) {
                events.push(SemanticEvent::WindowOpened {
                    window_id: *win_id,
                    app_id: snap.app_id.clone(),
                    title: snap.title.clone(),
                });
            }
        }

        // Windows closed (in previous but not in current)
        for win_id in self.prev_windows.keys() {
            if !cur_windows.contains_key(win_id) {
                events.push(SemanticEvent::WindowClosed {
                    window_id: *win_id,
                });
            }
        }

        // Window property changes
        for (win_id, cur) in &cur_windows {
            if let Some(prev) = self.prev_windows.get(win_id) {
                if cur.title != prev.title {
                    events.push(SemanticEvent::WindowTitleChanged {
                        window_id: *win_id,
                        old: prev.title.clone(),
                        new: cur.title.clone(),
                    });
                }
                if cur.geometry != prev.geometry {
                    events.push(SemanticEvent::WindowMoved {
                        window_id: *win_id,
                        geometry: cur.geometry,
                    });
                }
            }
        }

        // Focus changes
        if focused.0 != self.prev_focused_window {
            if let Some(win_id) = focused.0 {
                events.push(SemanticEvent::WindowFocused { window_id: win_id });
            }
        }
        if focused != (self.prev_focused_window, self.prev_focused_element) {
            if let Some(win_id) = focused.0 {
                events.push(SemanticEvent::FocusChanged {
                    window_id: win_id,
                    element_id: focused.1,
                });
            }
        }

        // Elements appeared
        for (node_id, snap) in &cur_elements {
            if !self.prev_elements.contains_key(node_id) {
                events.push(SemanticEvent::ElementAppeared {
                    window_id: snap.window_id,
                    node_id: *node_id,
                    role: snap.role.clone(),
                    label: snap.label.clone(),
                });
            }
        }

        // Elements disappeared
        for (node_id, snap) in &self.prev_elements {
            if !cur_elements.contains_key(node_id) {
                events.push(SemanticEvent::ElementDisappeared {
                    window_id: snap.window_id,
                    node_id: *node_id,
                });
            }
        }

        // Element property changes
        for (node_id, cur) in &cur_elements {
            if let Some(prev) = self.prev_elements.get(node_id) {
                if cur.label != prev.label {
                    events.push(SemanticEvent::ElementChanged {
                        window_id: cur.window_id,
                        node_id: *node_id,
                        property: "label".to_string(),
                        old: serde_json::Value::String(prev.label.clone()),
                        new: serde_json::Value::String(cur.label.clone()),
                    });
                }
                if cur.value != prev.value {
                    events.push(SemanticEvent::ElementChanged {
                        window_id: cur.window_id,
                        node_id: *node_id,
                        property: "value".to_string(),
                        old: prev.value.as_ref().map_or(serde_json::Value::Null, |v| {
                            serde_json::Value::String(v.clone())
                        }),
                        new: cur.value.as_ref().map_or(serde_json::Value::Null, |v| {
                            serde_json::Value::String(v.clone())
                        }),
                    });
                }
                if cur.state != prev.state {
                    events.push(SemanticEvent::ElementChanged {
                        window_id: cur.window_id,
                        node_id: *node_id,
                        property: "state".to_string(),
                        old: serde_json::to_value(&prev.state).unwrap_or(serde_json::Value::Null),
                        new: serde_json::to_value(&cur.state).unwrap_or(serde_json::Value::Null),
                    });
                }
            }
        }

        events
    }
}

impl Default for DiffTracker {
    fn default() -> Self {
        Self::new()
    }
}

/// Walk up the graph to find which window owns a given element node.
fn find_owning_window(nodes: &HashMap<NodeId, SemanticNode>, target: NodeId) -> Option<u64> {
    // Check all windows to see if they contain this element
    for node in nodes.values() {
        if let SemanticNode::Window { id, elements, .. } = node {
            if contains_element(nodes, elements, target) {
                return Some(*id);
            }
        }
    }
    None
}

/// Recursively check if a list of element children contains the target node.
fn contains_element(
    nodes: &HashMap<NodeId, SemanticNode>,
    children: &[NodeId],
    target: NodeId,
) -> bool {
    for child_id in children {
        if *child_id == target {
            return true;
        }
        if let Some(SemanticNode::Element { children, .. }) = nodes.get(child_id) {
            if contains_element(nodes, children, target) {
                return true;
            }
        }
    }
    false
}
