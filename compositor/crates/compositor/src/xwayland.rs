//! XWayland — X11 application compatibility.
//!
//! Spawns an XWayland server and manages X11 windows via X11Wm.
//! X11 surfaces are wrapped in WindowElement::X11 and participate
//! in the same layout as native Wayland windows.

use smithay::reexports::calloop::LoopHandle;
use smithay::reexports::wayland_server::DisplayHandle;
use smithay::xwayland::{XWayland, XWaylandEvent, X11Wm, XwmHandler};

use crate::state::AulinxState;

/// XWayland state held in the compositor.
pub struct XWaylandState {
    pub xwayland: XWayland,
    pub wm: Option<X11Wm>,
    pub display_num: u32,
}

impl AulinxState {
    /// Start XWayland. Call after the compositor is initialized.
    pub fn start_xwayland(&mut self) {
        let display_handle = self.display_handle.clone();
        let loop_handle = self.loop_handle.clone();

        let (xwayland, channel) = XWayland::spawn(
            &display_handle,
            None,   // auto-select display number
            vec![], // no extra env
            true,   // lazy start
            |_| {}, // user data callback
        ).unwrap_or_else(|e| {
            tracing::error!("Failed to spawn XWayland: {e}");
            panic!("XWayland spawn failed");
        });

        // Listen for XWayland events
        loop_handle
            .insert_source(channel, move |event, _, state: &mut AulinxState| {
                match event {
                    XWaylandEvent::Ready {
                        x11_socket,
                        display_number,
                    } => {
                        tracing::info!("XWayland ready on DISPLAY=:{display_number}");

                        // Start the X11 window manager
                        match X11Wm::start_wm(
                            state.loop_handle.clone(),
                            x11_socket,
                            state.display_handle.clone(),
                        ) {
                            Ok(wm) => {
                                tracing::info!("X11 window manager started");
                                if let Some(ref mut xw) = state.xwayland_state {
                                    xw.wm = Some(wm);
                                    xw.display_num = display_number;
                                }
                                // Set DISPLAY for child processes
                                std::env::set_var("DISPLAY", format!(":{display_number}"));
                            }
                            Err(e) => {
                                tracing::error!("Failed to start X11 WM: {e}");
                            }
                        }
                    }
                    XWaylandEvent::Error => {
                        tracing::error!("XWayland encountered an error");
                    }
                }
            })
            .expect("Failed to insert XWayland event source");

        self.xwayland_state = Some(XWaylandState {
            xwayland,
            wm: None,
            display_num: 0,
        });
    }
}

impl XwmHandler for AulinxState {
    fn xwm_state(&mut self, _xwm: smithay::xwayland::xwm::XwmId) -> &mut X11Wm {
        self.xwayland_state
            .as_mut()
            .and_then(|xs| xs.wm.as_mut())
            .expect("X11Wm not initialized")
    }

    fn new_window(&mut self, _xwm: smithay::xwayland::xwm::XwmId, window: smithay::xwayland::X11Surface) {
        tracing::info!(
            "X11 window created: {:?} (class={:?})",
            window.title(),
            window.class(),
        );
        // TODO: Map X11 surfaces into the space similar to Wayland windows
        // For now, X11 windows are created but not yet rendered
    }

    fn map_window_request(&mut self, _xwm: smithay::xwayland::xwm::XwmId, window: smithay::xwayland::X11Surface) {
        tracing::info!("X11 map request: {:?}", window.title());
        window.set_mapped(true).ok();
        // TODO: Create a Window wrapper and add to space + layout
    }

    fn map_window_notify(&mut self, _xwm: smithay::xwayland::xwm::XwmId, _window: smithay::xwayland::X11Surface) {}

    fn mapped_override_redirect_window(&mut self, _xwm: smithay::xwayland::xwm::XwmId, _window: smithay::xwayland::X11Surface) {}

    fn unmapped_window(&mut self, _xwm: smithay::xwayland::xwm::XwmId, window: smithay::xwayland::X11Surface) {
        tracing::info!("X11 window unmapped: {:?}", window.title());
        // TODO: Remove from space + layout
    }

    fn destroyed_window(&mut self, _xwm: smithay::xwayland::xwm::XwmId, _window: smithay::xwayland::X11Surface) {}

    fn configure_request(
        &mut self,
        _xwm: smithay::xwayland::xwm::XwmId,
        window: smithay::xwayland::X11Surface,
        _x: Option<i32>,
        _y: Option<i32>,
        _w: Option<u32>,
        _h: Option<u32>,
        _reorder: Option<smithay::xwayland::xwm::Reorder>,
    ) {
        // Accept the requested configuration
        window.configure(None).ok();
    }

    fn configure_notify(
        &mut self,
        _xwm: smithay::xwayland::xwm::XwmId,
        _window: smithay::xwayland::X11Surface,
        _geometry: smithay::utils::Rectangle<i32, smithay::utils::Logical>,
        _above: Option<smithay::xwayland::xwm::X11Surface>,
    ) {
    }

    fn resize_request(
        &mut self,
        _xwm: smithay::xwayland::xwm::XwmId,
        _window: smithay::xwayland::X11Surface,
        _button: u32,
        _resize_edge: smithay::xwayland::xwm::ResizeEdge,
    ) {
    }

    fn move_request(
        &mut self,
        _xwm: smithay::xwayland::xwm::XwmId,
        _window: smithay::xwayland::X11Surface,
        _button: u32,
    ) {
    }
}
