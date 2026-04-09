//! Pluggable data sources that feed the semantic scene graph.
//!
//! A Source is a provider of semantic data. Different sources
//! handle different environments:
//!
//! - `atspi`: reads the AT-SPI accessibility tree (works on any compositor)
//! - `compositor_ipc`: reads window data from Sway/Hyprland/niri IPC
//! - `direct`: receives data directly from the Aulinx compositor (no IPC needed)

use crate::action::{ActionRequest, ActionResult};
use crate::graph::SceneGraph;

/// A source of semantic data for the scene graph.
///
/// Sources run alongside the scene graph and push updates into it
/// as the desktop state changes. Multiple sources can be active
/// simultaneously (e.g., AT-SPI for element data + compositor IPC
/// for window geometry).
pub trait Source: Send {
    /// Human-readable name of this source.
    fn name(&self) -> &str;

    /// Initialize the source and start feeding data into the graph.
    ///
    /// The source should populate the graph with initial state and
    /// then continue to update it as changes occur (via polling,
    /// event subscription, or callback).
    fn start(&mut self, graph: &mut SceneGraph) -> Result<(), Box<dyn std::error::Error>>;

    /// Poll for updates. Called periodically by the daemon/compositor.
    ///
    /// Sources that use event-driven updates can make this a no-op.
    fn poll(&mut self, graph: &mut SceneGraph) -> Result<(), Box<dyn std::error::Error>>;

    /// Execute a semantic action (e.g., activate a button).
    ///
    /// Returns ActionResult::NotSupported if this source doesn't
    /// handle the given element.
    fn execute_action(&self, request: &ActionRequest) -> ActionResult;

    /// Focus a window by its compositor window ID.
    /// Only supported by compositor-aware sources.
    fn focus_window(&self, _window_id: u64) -> ActionResult {
        ActionResult::NotSupported
    }

    /// Close a window by its compositor window ID.
    /// Only supported by compositor-aware sources.
    fn close_window(&self, _window_id: u64) -> ActionResult {
        ActionResult::NotSupported
    }
}

pub mod atspi;
pub mod compositor_ipc;
pub mod direct;
