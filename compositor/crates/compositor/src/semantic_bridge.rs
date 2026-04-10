//! Semantic bridge — feeds compositor window data into the scene graph.

use smithay::reexports::wayland_server::protocol::wl_surface::WlSurface;

use aulinx_semantic::diff::SemanticEvent;
use aulinx_semantic::node::Rect;
use aulinx_semantic::sources::direct::DirectSource;
use aulinx_semantic::sources::Source;
use aulinx_semantic::SceneGraph;

pub struct SemanticBridge {
    source: DirectSource,
    next_window_id: u64,
    /// Maps WlSurface → semantic window ID for close tracking.
    surface_ids: Vec<(WlSurface, u64)>,
    /// Pending events to push to IPC subscribers.
    pending_events: Vec<SemanticEvent>,
}

impl SemanticBridge {
    pub fn new() -> Self {
        Self {
            source: DirectSource::new(),
            next_window_id: 1,
            surface_ids: Vec::new(),
            pending_events: Vec::new(),
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

    pub fn window_opened(
        &mut self,
        graph: &mut SceneGraph,
        surface: &WlSurface,
        app_id: &str,
        title: &str,
    ) {
        let id = self.next_window_id;
        self.next_window_id += 1;
        self.surface_ids.push((surface.clone(), id));
        self.source.window_opened(graph, id, 0, app_id, title, Rect::new(0, 0, 0, 0));
        self.pending_events.push(SemanticEvent::WindowOpened {
            window_id: id,
            app_id: app_id.to_string(),
            title: title.to_string(),
        });
        tracing::debug!("Semantic: window opened id={id} app={app_id}");
    }

    pub fn window_closed(&mut self, graph: &mut SceneGraph, surface: &WlSurface) {
        if let Some(pos) = self.surface_ids.iter().position(|(s, _)| s == surface) {
            let (_, id) = self.surface_ids.remove(pos);
            self.source.window_closed(graph, id);
            self.pending_events.push(SemanticEvent::WindowClosed { window_id: id });
            tracing::debug!("Semantic: window closed id={id}");
        }
    }

    pub fn window_title_changed(
        &mut self,
        graph: &mut SceneGraph,
        surface: &WlSurface,
        _app_id: &str,
        title: &str,
    ) {
        if let Some((_, id)) = self.surface_ids.iter().find(|(s, _)| s == surface) {
            self.source.window_title_changed(graph, *id, title);
            tracing::debug!("Semantic: title changed id={id} title={title}");
        }
    }

    pub fn window_geometry_changed(
        &mut self,
        graph: &mut SceneGraph,
        surface: &WlSurface,
        geometry: Rect,
    ) {
        if let Some((_, id)) = self.surface_ids.iter().find(|(s, _)| s == surface) {
            self.source.window_geometry_changed(graph, *id, geometry);
        }
    }

    pub fn window_focused(&mut self, graph: &mut SceneGraph, surface: &WlSurface) {
        if let Some((_, id)) = self.surface_ids.iter().find(|(s, _)| s == surface) {
            let id = *id;
            self.source.window_focused(graph, id);
            self.pending_events.push(SemanticEvent::WindowFocused { window_id: id });
            tracing::debug!("Semantic: window focused id={id}");
        }
    }

    /// Look up the semantic window ID for a surface.
    pub fn window_id_for_surface(&self, surface: &WlSurface) -> Option<u64> {
        self.surface_ids.iter().find(|(s, _)| s == surface).map(|(_, id)| *id)
    }

    /// Drain pending events for IPC push.
    pub fn drain_events(&mut self) -> Vec<SemanticEvent> {
        std::mem::take(&mut self.pending_events)
    }
}
