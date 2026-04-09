//! The semantic scene graph — a live, structured representation of the desktop.
//!
//! This is the core data structure. It stores all semantic nodes in an arena
//! and provides fast lookup by ID, window ID, and text search.

use std::collections::HashMap;

use crate::diff::{DiffTracker, SemanticEvent};
use crate::node::{ActionType, ElementRole, ElementState, NodeId, Rect, SemanticNode};

/// The semantic scene graph.
///
/// Arena-based storage: nodes are stored in a HashMap keyed by NodeId.
/// The root is always a Desktop node at NodeId(0).
pub struct SceneGraph {
    nodes: HashMap<NodeId, SemanticNode>,
    next_id: u64,
    /// Maps window IDs (from the compositor) to their NodeId in the graph.
    window_index: HashMap<u64, NodeId>,
    /// The currently focused window.
    focused_window: Option<u64>,
    /// The currently focused element within the focused window.
    focused_element: Option<NodeId>,
}

impl SceneGraph {
    /// Create a new scene graph with a root Desktop node.
    pub fn new() -> Self {
        let mut nodes = HashMap::new();
        nodes.insert(
            NodeId(0),
            SemanticNode::Desktop {
                screens: Vec::new(),
            },
        );
        Self {
            nodes,
            next_id: 1,
            window_index: HashMap::new(),
            focused_window: None,
            focused_element: None,
        }
    }

    /// Allocate a new NodeId.
    pub fn alloc_id(&mut self) -> NodeId {
        let id = NodeId(self.next_id);
        self.next_id += 1;
        id
    }

    /// Insert a node into the graph.
    pub fn insert(&mut self, id: NodeId, node: SemanticNode) {
        // Update window index if this is a Window node
        if let SemanticNode::Window {
            id: window_id, ..
        } = &node
        {
            self.window_index.insert(*window_id, id);
        }
        self.nodes.insert(id, node);
    }

    /// Remove a node from the graph.
    pub fn remove(&mut self, id: NodeId) -> Option<SemanticNode> {
        let node = self.nodes.remove(&id)?;
        if let SemanticNode::Window {
            id: window_id, ..
        } = &node
        {
            self.window_index.remove(window_id);
        }
        Some(node)
    }

    /// Get a node by ID.
    pub fn get(&self, id: NodeId) -> Option<&SemanticNode> {
        self.nodes.get(&id)
    }

    /// Get a mutable reference to a node by ID.
    pub fn get_mut(&mut self, id: NodeId) -> Option<&mut SemanticNode> {
        self.nodes.get_mut(&id)
    }

    /// Get the root Desktop node.
    pub fn root(&self) -> &SemanticNode {
        self.nodes.get(&NodeId(0)).expect("root node must exist")
    }

    /// Get a window node by its compositor window ID.
    pub fn window(&self, window_id: u64) -> Option<&SemanticNode> {
        let node_id = self.window_index.get(&window_id)?;
        self.nodes.get(node_id)
    }

    /// Get a window's NodeId by its compositor window ID.
    pub fn window_node_id(&self, window_id: u64) -> Option<NodeId> {
        self.window_index.get(&window_id).copied()
    }

    /// List all windows (summary: id, title, app_id, focused, geometry).
    pub fn windows(&self) -> Vec<&SemanticNode> {
        self.window_index
            .values()
            .filter_map(|nid| self.nodes.get(nid))
            .collect()
    }

    /// Find elements whose label contains the query string (case-insensitive).
    pub fn find(&self, query: &str) -> Vec<(NodeId, &SemanticNode)> {
        let query_lower = query.to_lowercase();
        self.nodes
            .iter()
            .filter(|(_, node)| match node {
                SemanticNode::Element { label, .. } => {
                    label.to_lowercase().contains(&query_lower)
                }
                SemanticNode::Window { title, .. } => {
                    title.to_lowercase().contains(&query_lower)
                }
                _ => false,
            })
            .map(|(id, node)| (*id, node))
            .collect()
    }

    /// Find elements by role.
    pub fn find_by_role(&self, role: &ElementRole) -> Vec<(NodeId, &SemanticNode)> {
        self.nodes
            .iter()
            .filter(|(_, node)| match node {
                SemanticNode::Element {
                    role: r, ..
                } => r == role,
                _ => false,
            })
            .map(|(id, node)| (*id, node))
            .collect()
    }

    /// Get the currently focused window and element.
    pub fn focused(&self) -> (Option<u64>, Option<NodeId>) {
        (self.focused_window, self.focused_element)
    }

    /// Set the focused window.
    pub fn set_focused_window(&mut self, window_id: Option<u64>) {
        // Unfocus the old window
        if let Some(old_id) = self.focused_window {
            if let Some(node_id) = self.window_index.get(&old_id) {
                if let Some(SemanticNode::Window { focused, .. }) = self.nodes.get_mut(node_id) {
                    *focused = false;
                }
            }
        }
        // Focus the new window
        if let Some(new_id) = window_id {
            if let Some(node_id) = self.window_index.get(&new_id) {
                if let Some(SemanticNode::Window { focused, .. }) = self.nodes.get_mut(node_id) {
                    *focused = true;
                }
            }
        }
        self.focused_window = window_id;
    }

    /// Set the focused element within the focused window.
    pub fn set_focused_element(&mut self, element_id: Option<NodeId>) {
        self.focused_element = element_id;
    }

    /// Serialize the full graph to JSON.
    pub fn to_json(&self) -> serde_json::Value {
        self.serialize_node(NodeId(0))
    }

    /// Serialize a subtree starting from a node.
    fn serialize_node(&self, id: NodeId) -> serde_json::Value {
        let Some(node) = self.nodes.get(&id) else {
            return serde_json::Value::Null;
        };

        let mut val = serde_json::to_value(node).unwrap_or(serde_json::Value::Null);

        // Recursively serialize children
        if let serde_json::Value::Object(ref mut map) = val {
            match node {
                SemanticNode::Desktop { screens } => {
                    let children: Vec<_> = screens.iter().map(|id| self.serialize_node(*id)).collect();
                    map.insert("screens".to_string(), serde_json::Value::Array(children));
                }
                SemanticNode::Screen { windows, .. } => {
                    let children: Vec<_> = windows.iter().map(|id| self.serialize_node(*id)).collect();
                    map.insert("windows".to_string(), serde_json::Value::Array(children));
                }
                SemanticNode::Window { elements, .. } => {
                    let children: Vec<_> = elements.iter().map(|id| self.serialize_node(*id)).collect();
                    map.insert("elements".to_string(), serde_json::Value::Array(children));
                }
                SemanticNode::Element { children, .. } => {
                    let child_vals: Vec<_> = children.iter().map(|id| self.serialize_node(*id)).collect();
                    map.insert("children".to_string(), serde_json::Value::Array(child_vals));
                }
            }
        }

        val
    }

    /// Serialize a single window subtree to JSON.
    pub fn window_to_json(&self, window_id: u64) -> Option<serde_json::Value> {
        let node_id = self.window_index.get(&window_id)?;
        Some(self.serialize_node(*node_id))
    }

    /// Get the total number of nodes.
    pub fn len(&self) -> usize {
        self.nodes.len()
    }

    /// Check if the graph is empty (only root).
    pub fn is_empty(&self) -> bool {
        self.nodes.len() <= 1
    }

    /// Add a screen to the desktop.
    pub fn add_screen(&mut self, name: &str, geometry: Rect) -> NodeId {
        let id = self.alloc_id();
        self.insert(
            id,
            SemanticNode::Screen {
                name: name.to_string(),
                geometry,
                windows: Vec::new(),
            },
        );
        if let Some(SemanticNode::Desktop { screens }) = self.nodes.get_mut(&NodeId(0)) {
            screens.push(id);
        }
        id
    }

    /// Add a window to a screen.
    pub fn add_window(
        &mut self,
        screen_id: NodeId,
        window_id: u64,
        pid: u32,
        app_id: &str,
        title: &str,
        geometry: Rect,
    ) -> NodeId {
        let id = self.alloc_id();
        self.insert(
            id,
            SemanticNode::Window {
                id: window_id,
                pid,
                app_id: app_id.to_string(),
                title: title.to_string(),
                geometry,
                focused: false,
                workspace: 0,
                floating: false,
                elements: Vec::new(),
            },
        );
        if let Some(SemanticNode::Screen { windows, .. }) = self.nodes.get_mut(&screen_id) {
            windows.push(id);
        }
        id
    }

    /// Add an element to a window.
    pub fn add_element(
        &mut self,
        window_node_id: NodeId,
        role: ElementRole,
        label: &str,
        actions: Vec<ActionType>,
    ) -> NodeId {
        let id = self.alloc_id();
        self.insert(
            id,
            SemanticNode::Element {
                role,
                label: label.to_string(),
                value: None,
                state: ElementState::default(),
                bounds: Rect::new(0, 0, 0, 0),
                actions,
                children: Vec::new(),
            },
        );
        if let Some(SemanticNode::Window { elements, .. }) = self.nodes.get_mut(&window_node_id) {
            elements.push(id);
        }
        id
    }

    /// Add a child element to a parent element.
    pub fn add_child_element(
        &mut self,
        parent_id: NodeId,
        role: ElementRole,
        label: &str,
        actions: Vec<ActionType>,
    ) -> NodeId {
        let id = self.alloc_id();
        self.insert(
            id,
            SemanticNode::Element {
                role,
                label: label.to_string(),
                value: None,
                state: ElementState::default(),
                bounds: Rect::new(0, 0, 0, 0),
                actions,
                children: Vec::new(),
            },
        );
        if let Some(SemanticNode::Element { children, .. }) = self.nodes.get_mut(&parent_id) {
            children.push(id);
        }
        id
    }

    /// Remove a window and all its elements from the graph.
    pub fn remove_window(&mut self, window_id: u64) {
        let Some(node_id) = self.window_index.get(&window_id).copied() else {
            return;
        };

        // Collect element IDs to remove
        let element_ids = self.collect_descendants(node_id);
        for eid in element_ids {
            self.nodes.remove(&eid);
        }

        // Remove from parent screen
        for node in self.nodes.values_mut() {
            if let SemanticNode::Screen { windows, .. } = node {
                windows.retain(|id| *id != node_id);
            }
        }

        self.remove(node_id);

        if self.focused_window == Some(window_id) {
            self.focused_window = None;
            self.focused_element = None;
        }
    }

    /// Collect all descendant node IDs of a given node.
    fn collect_descendants(&self, id: NodeId) -> Vec<NodeId> {
        let mut result = Vec::new();
        let children: Vec<NodeId> = match self.nodes.get(&id) {
            Some(SemanticNode::Window { elements, .. }) => elements.clone(),
            Some(SemanticNode::Element { children, .. }) => children.clone(),
            _ => return result,
        };
        for child_id in children {
            result.push(child_id);
            result.extend(self.collect_descendants(child_id));
        }
        result
    }

    /// Access the internal nodes map (for the diff tracker).
    pub fn nodes(&self) -> &HashMap<NodeId, SemanticNode> {
        &self.nodes
    }

    /// Take a snapshot of current state for diff tracking.
    pub fn snapshot(&self, tracker: &mut DiffTracker) {
        tracker.snapshot(&self.nodes, self.focused());
    }

    /// Compute diff against a previous snapshot.
    pub fn diff(&self, tracker: &DiffTracker) -> Vec<SemanticEvent> {
        tracker.diff(&self.nodes, self.focused())
    }
}

impl Default for SceneGraph {
    fn default() -> Self {
        Self::new()
    }
}
