//! Server-side decorations — title bars with close/maximize buttons.
//!
//! When a client supports xdg-decoration, we force server-side mode.
//! The compositor draws the title bar during rendering.
//!
//! TODO: implement SSD rendering in the render pass.

use smithay::delegate_xdg_decoration;
use smithay::reexports::wayland_server::protocol::wl_surface::WlSurface;
use smithay::wayland::shell::xdg::decoration::{
    XdgDecorationHandler, XdgDecorationState,
};
use smithay::wayland::shell::xdg::ToplevelSurface;

use crate::state::AulinxState;

impl AulinxState {
    pub fn init_xdg_decoration(
        display_handle: &smithay::reexports::wayland_server::DisplayHandle,
    ) -> XdgDecorationState {
        XdgDecorationState::new::<Self>(display_handle)
    }
}

impl XdgDecorationHandler for AulinxState {
    fn new_decoration(&mut self, toplevel: ToplevelSurface) {
        // Request server-side decorations
        use smithay::wayland::shell::xdg::decoration::Mode as DecMode;
        toplevel.with_pending_state(|state| {
            state.decoration_mode = Some(DecMode::ServerSide);
        });
        toplevel.send_configure();
    }

    fn request_mode(&mut self, _toplevel: ToplevelSurface, _mode: smithay::wayland::shell::xdg::decoration::Mode) {
        // We always force server-side
    }

    fn unset_mode(&mut self, _toplevel: ToplevelSurface) {}
}

delegate_xdg_decoration!(AulinxState);
