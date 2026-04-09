//! wlr-layer-shell — overlay surfaces for panels, notifications, AI palette.
//!
//! Layer shell surfaces are not part of the window layout. They occupy
//! reserved screen edges (exclusive zones) and render above or below
//! regular windows depending on their layer.
//!
//! Layers (bottom to top):
//! - Background: wallpaper
//! - Bottom: desktop widgets
//! - Top: panels, bars, notifications
//! - Overlay: AI command palette, lock screen

use smithay::delegate_layer_shell;
use smithay::desktop::{LayerSurface, layer_map_for_output};
use smithay::output::Output;
use smithay::reexports::wayland_server::protocol::wl_output::WlOutput;
use smithay::wayland::shell::wlr_layer::{
    Layer, LayerSurfaceData, WlrLayerShellHandler, WlrLayerShellState,
};

use crate::state::AulinxState;

impl AulinxState {
    /// Initialize layer shell protocol support.
    pub fn init_layer_shell(display_handle: &smithay::reexports::wayland_server::DisplayHandle) -> WlrLayerShellState {
        WlrLayerShellState::new::<Self>(display_handle)
    }

    /// Arrange layer surfaces for an output.
    /// Computes exclusive zones and returns the usable area for windows.
    pub fn arrange_layers(&mut self, output: &Output) {
        let mut map = layer_map_for_output(output);
        let output_geo = output
            .current_mode()
            .map(|m| {
                smithay::utils::Rectangle::from_loc_and_size((0, 0), m.size)
            })
            .unwrap_or_default();

        map.arrange();

        // The layer map automatically handles exclusive zones.
        // After arrange(), non_exclusive_zone() returns the area available for windows.
    }

    /// Get the usable area for windows after layer surfaces claim their exclusive zones.
    pub fn usable_area(&self, output: &Output) -> smithay::utils::Rectangle<i32, smithay::utils::Logical> {
        let map = layer_map_for_output(output);
        map.non_exclusive_zone()
    }
}

impl WlrLayerShellHandler for AulinxState {
    fn shell_state(&mut self) -> &mut WlrLayerShellState {
        &mut self.layer_shell_state
    }

    fn new_layer_surface(
        &mut self,
        surface: LayerSurface,
        output: Option<WlOutput>,
        _layer: Layer,
        namespace: String,
    ) {
        // Assign to the first output if none specified
        let target_output = output
            .as_ref()
            .and_then(|o| {
                self.space.outputs().find(|out| {
                    out.with_state(|s| s.wl_output() == Some(o))
                        .unwrap_or(false)
                })
            })
            .or_else(|| self.space.outputs().next())
            .cloned();

        if let Some(output) = target_output {
            let mut map = layer_map_for_output(&output);
            map.map_layer(&surface).ok();
            drop(map);
            self.arrange_layers(&output);
        }

        tracing::info!("Layer surface mapped: namespace={namespace}");
    }

    fn layer_destroyed(&mut self, surface: LayerSurface) {
        // Remove from all outputs
        for output in self.space.outputs().cloned().collect::<Vec<_>>() {
            let mut map = layer_map_for_output(&output);
            map.unmap_layer(&surface);
            drop(map);
            self.arrange_layers(&output);
        }

        tracing::info!("Layer surface destroyed");
    }
}

delegate_layer_shell!(AulinxState);
