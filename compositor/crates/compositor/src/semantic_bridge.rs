//! Semantic bridge — feeds compositor surface data into the scene graph.
//!
//! When windows are created, destroyed, focused, moved, or renamed,
//! the bridge updates the aulinx-semantic SceneGraph in real time.
//! This gives AI agents zero-latency semantic understanding without
//! going through AT-SPI or screenshots.

use aulinx_semantic::node::{NodeId, Rect};
use aulinx_semantic::sources::direct::DirectSource;
use aulinx_semantic::sources::Source;
use aulinx_semantic::{DiffTracker, SceneGraph, SemanticEvent};
use smithay::desktop::Window;

use crate::layout::WindowId;

/// The semantic bridge between compositor and scene graph.
pub struct SemanticBridge {
    pub source: DirectSource,
    pub tracker: DiffTracker,
    pub screen_node: Option<NodeId>,
}

impl SemanticBridge {
    pub fn new() -> Self {
        Self {
            source: DirectSource::new(),
            tracker: DiffTracker::new(),
            screen_node: None,
        }
    }

    /// Initialize the bridge — creates the screen node.
    pub fn init(&mut self, graph: &mut SceneGraph, width: i32, height: i32) {
        self.source.start(graph).ok();
        // The DirectSource creates a default screen; find it
        if let aulinx_semantic::SemanticNode::Desktop { screens } = graph.root() {
            self.screen_node = screens.first().copied();
        }
        // Update screen geometry if needed
        if let Some(screen_id) = self.screen_node {
            if let Some(aulinx_semantic::SemanticNode::Screen { geometry, .. }) =
                graph.get_mut(screen_id)
            {
                *geometry = Rect::new(0, 0, width, height);
            }
        }
        graph.snapshot(&mut self.tracker);
        tracing::info!("Semantic bridge initialized ({width}x{height})");
    }

    /// Notify that a window was opened.
    pub fn window_opened(
        &self,
        graph: &mut SceneGraph,
        window_id: WindowId,
        pid: u32,
        app_id: &str,
        title: &str,
        x: i32,
        y: i32,
        width: i32,
        height: i32,
    ) {
        self.source.window_opened(
            graph,
            window_id,
            pid,
            app_id,
            title,
            Rect::new(x, y, width, height),
        );
    }

    /// Notify that a window was closed.
    pub fn window_closed(&self, graph: &mut SceneGraph, window_id: WindowId) {
        self.source.window_closed(graph, window_id);
    }

    /// Notify that a window gained focus.
    pub fn window_focused(&self, graph: &mut SceneGraph, window_id: WindowId) {
        self.source.window_focused(graph, window_id);
    }

    /// Notify that a window's title changed.
    pub fn window_title_changed(
        &self,
        graph: &mut SceneGraph,
        window_id: WindowId,
        title: &str,
    ) {
        self.source.window_title_changed(graph, window_id, title);
    }

    /// Notify that a window moved or resized.
    pub fn window_geometry_changed(
        &self,
        graph: &mut SceneGraph,
        window_id: WindowId,
        x: i32,
        y: i32,
        width: i32,
        height: i32,
    ) {
        self.source.window_geometry_changed(
            graph,
            window_id,
            Rect::new(x, y, width, height),
        );
    }

    /// Take a snapshot and compute semantic events since last snapshot.
    pub fn compute_events(&mut self, graph: &SceneGraph) -> Vec<SemanticEvent> {
        let events = graph.diff(&self.tracker);
        graph.snapshot(&mut self.tracker);
        events
    }
}
