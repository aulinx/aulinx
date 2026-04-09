//! Direct source — receives surface data from the Aulinx compositor.
//!
//! Unlike the AT-SPI and compositor IPC sources, this source doesn't
//! connect to external services. Instead, the compositor calls methods
//! on it directly when surfaces are created, destroyed, or changed.
//! This provides zero-latency window metadata updates.
//!
//! Used only by aulinx-compositor (Product 2), not by the standalone daemon.

use crate::action::{ActionRequest, ActionResult};
use crate::graph::SceneGraph;
use crate::node::Rect;
use crate::sources::Source;

/// Direct source for compositor integration.
///
/// The compositor calls `window_opened`, `window_closed`, etc. directly
/// instead of going through IPC or D-Bus.
pub struct DirectSource {
    screen_node: Option<crate::node::NodeId>,
}

impl DirectSource {
    pub fn new() -> Self {
        Self { screen_node: None }
    }

    /// Called by the compositor when a new window is mapped.
    pub fn window_opened(
        &self,
        graph: &mut SceneGraph,
        window_id: u64,
        pid: u32,
        app_id: &str,
        title: &str,
        geometry: Rect,
    ) {
        if let Some(screen_id) = self.screen_node {
            graph.add_window(screen_id, window_id, pid, app_id, title, geometry);
        }
    }

    /// Called by the compositor when a window is unmapped/destroyed.
    pub fn window_closed(&self, graph: &mut SceneGraph, window_id: u64) {
        if let Some(node_id) = graph.window_node_id(window_id) {
            graph.remove(node_id);
        }
    }

    /// Called by the compositor when a window gains focus.
    pub fn window_focused(&self, graph: &mut SceneGraph, window_id: u64) {
        graph.set_focused_window(Some(window_id));
    }

    /// Called by the compositor when a window's title changes.
    pub fn window_title_changed(&self, graph: &mut SceneGraph, window_id: u64, title: &str) {
        if let Some(node_id) = graph.window_node_id(window_id) {
            if let Some(crate::node::SemanticNode::Window {
                title: t, ..
            }) = graph.get_mut(node_id)
            {
                *t = title.to_string();
            }
        }
    }

    /// Called by the compositor when a window moves/resizes.
    pub fn window_geometry_changed(&self, graph: &mut SceneGraph, window_id: u64, geometry: Rect) {
        if let Some(node_id) = graph.window_node_id(window_id) {
            if let Some(crate::node::SemanticNode::Window {
                geometry: g, ..
            }) = graph.get_mut(node_id)
            {
                *g = geometry;
            }
        }
    }
}

impl Source for DirectSource {
    fn name(&self) -> &str {
        "direct"
    }

    fn start(&mut self, graph: &mut SceneGraph) -> Result<(), Box<dyn std::error::Error>> {
        // Create a default screen
        let screen_id = graph.add_screen("default", Rect::new(0, 0, 1920, 1080));
        self.screen_node = Some(screen_id);
        tracing::info!("Direct source: ready (compositor integration)");
        Ok(())
    }

    fn poll(&mut self, _graph: &mut SceneGraph) -> Result<(), Box<dyn std::error::Error>> {
        // Direct source is push-based, no polling needed
        Ok(())
    }

    fn execute_action(&self, _request: &ActionRequest) -> ActionResult {
        // TODO: compositor can handle actions directly (input injection, focus)
        ActionResult::NotSupported
    }
}
