//! XWayland — X11 application compatibility.

use smithay::xwayland::{XWayland, XWaylandEvent, X11Wm, XwmHandler, X11Surface};
use smithay::xwayland::xwm::{XwmId, Reorder, ResizeEdge};
use smithay::utils::Rectangle;

use crate::state::AulinxState;

/// XWayland state held in the compositor.
pub struct XWaylandState {
    pub xwayland: XWayland,
    pub wm: Option<X11Wm>,
    pub display_num: u32,
}

impl AulinxState {
    /// Start XWayland.
    pub fn start_xwayland(&mut self) {
        // XWayland startup requires careful API usage that varies
        // between Smithay versions. This will be implemented when
        // testing on the VM with the exact Smithay API available.
        tracing::info!("XWayland: startup deferred (needs API verification on target)");
    }
}

impl XwmHandler for AulinxState {
    fn xwm_state(&mut self, _xwm: XwmId) -> &mut X11Wm {
        self.xwayland_state
            .as_mut()
            .and_then(|xs| xs.wm.as_mut())
            .expect("X11Wm not initialized")
    }

    fn new_window(&mut self, _xwm: XwmId, window: X11Surface) {
        tracing::info!("X11 window created: {:?}", window.title());
    }

    fn new_override_redirect_window(&mut self, _xwm: XwmId, _window: X11Surface) {}

    fn map_window_request(&mut self, _xwm: XwmId, window: X11Surface) {
        tracing::info!("X11 map request: {:?}", window.title());
        let _ = window.set_mapped(true);
    }

    fn map_window_notify(&mut self, _xwm: XwmId, _window: X11Surface) {}

    fn mapped_override_redirect_window(&mut self, _xwm: XwmId, _window: X11Surface) {}

    fn unmapped_window(&mut self, _xwm: XwmId, window: X11Surface) {
        tracing::info!("X11 window unmapped: {:?}", window.title());
    }

    fn destroyed_window(&mut self, _xwm: XwmId, _window: X11Surface) {}

    fn configure_request(
        &mut self,
        _xwm: XwmId,
        window: X11Surface,
        _x: Option<i32>,
        _y: Option<i32>,
        _w: Option<u32>,
        _h: Option<u32>,
        _reorder: Option<Reorder>,
    ) {
        let _ = window.configure(None);
    }

    fn configure_notify(
        &mut self,
        _xwm: XwmId,
        _window: X11Surface,
        _geometry: Rectangle<i32, smithay::utils::Logical>,
        _above: Option<u32>,
    ) {
    }

    fn resize_request(
        &mut self,
        _xwm: XwmId,
        _window: X11Surface,
        _button: u32,
        _resize_edge: ResizeEdge,
    ) {
    }

    fn move_request(
        &mut self,
        _xwm: XwmId,
        _window: X11Surface,
        _button: u32,
    ) {
    }
}
