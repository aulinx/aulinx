//! Semantic bridge — feeds compositor window data into the scene graph.

use aulinx_semantic::node::Rect;
use aulinx_semantic::sources::direct::DirectSource;
use aulinx_semantic::sources::Source;
use aulinx_semantic::SceneGraph;

pub struct SemanticBridge {
    source: DirectSource,
    next_window_id: u64,
}

impl SemanticBridge {
    pub fn new() -> Self {
        Self {
            source: DirectSource::new(),
            next_window_id: 1,
        }
    }

    pub fn init(&mut self, graph: &mut SceneGraph, width: i32, height: i32) {
        self.source.start(graph).ok();
        if let aulinx_semantic::SemanticNode::Screen { geometry, .. } =
            graph.get_mut(aulinx_semantic::NodeId(1)).unwrap()
        {
            *geometry = Rect::new(0, 0, width, height);
        }
        tracing::info!("Semantic bridge initialized ({width}x{height})");
    }

    pub fn window_opened(&mut self, graph: &mut SceneGraph, app_id: &str, title: &str) {
        let id = self.next_window_id;
        self.next_window_id += 1;
        self.source.window_opened(graph, id, 0, app_id, title, Rect::new(0, 0, 0, 0));
        tracing::debug!("Semantic: window opened id={id} app={app_id}");
    }
}
