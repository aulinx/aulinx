//! wlr-layer-shell — overlay surfaces for panels, notifications, AI palette.

use smithay::delegate_layer_shell;
use smithay::desktop::layer_map_for_output;
use smithay::output::Output;
use smithay::reexports::wayland_server::protocol::wl_output::WlOutput;
use smithay::wayland::shell::wlr_layer::{
    Layer, WlrLayerShellHandler, WlrLayerShellState,
    LayerSurface as WlrLayerSurface,
};

use crate::state::AulinxState;

impl WlrLayerShellHandler for AulinxState {
    fn shell_state(&mut self) -> &mut WlrLayerShellState {
        &mut self.layer_shell_state
    }

    fn new_layer_surface(
        &mut self,
        surface: WlrLayerSurface,
        output: Option<WlOutput>,
        _layer: Layer,
        namespace: String,
    ) {
        let target_output = output
            .as_ref()
            .and_then(|_o| self.space.outputs().next())
            .or_else(|| self.space.outputs().next())
            .cloned();

        if let Some(output) = target_output {
            let mut map = layer_map_for_output(&output);
            let _ = map.map_layer(&smithay::desktop::LayerSurface::new(
                surface,
                namespace.clone(),
            ));
        }

        tracing::info!("Layer surface mapped: namespace={namespace}");
    }

    fn layer_destroyed(&mut self, surface: WlrLayerSurface) {
        tracing::info!("Layer surface destroyed");
    }
}

delegate_layer_shell!(AulinxState);
