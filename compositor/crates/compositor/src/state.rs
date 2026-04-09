//! AulinxState — the central compositor state struct.
//!
//! Minimal version — focused on getting a compilable compositor first.
//! Features will be re-enabled as the Smithay API is verified.

use std::sync::Arc;
use std::time::Instant;

use smithay::delegate_compositor;
use smithay::delegate_data_device;
use smithay::delegate_output;
use smithay::delegate_seat;
use smithay::delegate_shm;
use smithay::delegate_xdg_shell;
use smithay::desktop::{Space, Window};
use smithay::input::{Seat, SeatHandler, SeatState};
use smithay::reexports::calloop::generic::Generic;
use smithay::reexports::calloop::{Interest, LoopHandle, LoopSignal, Mode, PostAction};
use std::os::unix::io::AsFd;
use smithay::reexports::wayland_server::backend::{ClientData, ClientId, DisconnectReason};
use smithay::reexports::wayland_server::protocol::wl_surface::WlSurface;
use smithay::reexports::wayland_server::{Display, DisplayHandle};
use smithay::utils::{Clock, Monotonic, Serial, SERIAL_COUNTER};
use smithay::wayland::compositor::{CompositorClientState, CompositorHandler, CompositorState};
use smithay::wayland::output::OutputManagerState;
use smithay::wayland::selection::data_device::{DataDeviceHandler, DataDeviceState};
use smithay::wayland::shell::xdg::{ToplevelSurface, XdgShellHandler, XdgShellState};
use smithay::wayland::shm::{ShmHandler, ShmState};
use smithay::wayland::socket::ListeningSocketSource;

use smithay::backend::renderer::glow::GlowRenderer;
use crate::backend::BackendData;

pub struct ClientState {
    pub compositor_state: CompositorClientState,
}

impl ClientData for ClientState {
    fn initialized(&self, _client_id: ClientId) {}
    fn disconnected(&self, _client_id: ClientId, _reason: DisconnectReason) {}
}

pub struct AulinxState {
    pub display: Option<Display<Self>>,
    pub display_handle: DisplayHandle,
    pub compositor_state: CompositorState,
    pub xdg_shell_state: XdgShellState,
    pub shm_state: ShmState,
    pub output_manager_state: OutputManagerState,
    pub data_device_state: DataDeviceState,
    pub seat_state: SeatState<Self>,
    pub seat: Seat<Self>,
    pub space: Space<Window>,
    pub backend_data: BackendData,
    pub loop_handle: LoopHandle<'static, Self>,
    pub loop_signal: LoopSignal,
    pub clock: Clock<Monotonic>,
    pub start_time: Instant,
    pub socket_name: String,
    pub scene_graph: aulinx_semantic::SceneGraph,
}

impl AulinxState {
    pub fn new(
        display: Display<Self>,
        loop_handle: LoopHandle<'static, Self>,
        loop_signal: LoopSignal,
        backend_data: BackendData,
    ) -> Self {
        let display_handle = display.handle();
        let clock = Clock::new();

        let compositor_state = CompositorState::new::<Self>(&display_handle);
        let xdg_shell_state = XdgShellState::new::<Self>(&display_handle);
        let shm_state = ShmState::new::<Self>(&display_handle, vec![]);
        let output_manager_state = OutputManagerState::new_with_xdg_output::<Self>(&display_handle);
        let data_device_state = DataDeviceState::new::<Self>(&display_handle);

        let mut seat_state = SeatState::new();
        let seat_name = backend_data.seat_name();
        let mut seat = seat_state.new_wl_seat(&display_handle, seat_name);
        seat.add_keyboard(Default::default(), 200, 25)
            .expect("Failed to add keyboard");
        seat.add_pointer();

        let socket_source = ListeningSocketSource::new_auto()
            .expect("Failed to create Wayland socket");
        let socket_name = socket_source.socket_name().to_string_lossy().to_string();
        loop_handle
            .insert_source(socket_source, move |client, _, state: &mut Self| {
                state
                    .display_handle
                    .insert_client(
                        client,
                        Arc::new(ClientState {
                            compositor_state: CompositorClientState::default(),
                        }),
                    )
                    .ok();
            })
            .expect("Failed to insert socket source");

        tracing::info!("Wayland socket: {socket_name}");

        // Advertise the output to clients
        if let BackendData::Winit(ref winit_data) = backend_data {
            winit_data.output.create_global::<Self>(&display_handle);
        }

        Self {
            display: Some(display),
            display_handle,
            compositor_state,
            xdg_shell_state,
            shm_state,
            output_manager_state,
            data_device_state,
            seat_state,
            seat,
            space: Space::default(),
            backend_data,
            loop_handle,
            loop_signal,
            clock,
            start_time: Instant::now(),
            socket_name,
            scene_graph: aulinx_semantic::SceneGraph::new(),
        }
    }
}

// ---- Handlers ----

impl CompositorHandler for AulinxState {
    fn compositor_state(&mut self) -> &mut CompositorState {
        &mut self.compositor_state
    }

    fn client_compositor_state<'a>(
        &self,
        client: &'a smithay::reexports::wayland_server::Client,
    ) -> &'a CompositorClientState {
        &client.get_data::<ClientState>().unwrap().compositor_state
    }

    fn commit(&mut self, surface: &WlSurface) {
        // Import buffers into the renderer
        smithay::backend::renderer::utils::on_commit_buffer_handler::<Self>(surface);

        if let Some(window) = self.space.elements()
            .find(|w| w.toplevel().map(|t| t.wl_surface() == surface).unwrap_or(false))
            .cloned()
        {
            window.on_commit();
        }
        // Send initial configure to XDG toplevels that haven't received one
        for toplevel in self.xdg_shell_state.toplevel_surfaces().iter() {
            if toplevel.wl_surface() == surface && !toplevel.is_initial_configure_sent() {
                toplevel.send_configure();
            }
        }
    }
}

impl XdgShellHandler for AulinxState {
    fn xdg_shell_state(&mut self) -> &mut XdgShellState {
        &mut self.xdg_shell_state
    }

    fn new_toplevel(&mut self, surface: ToplevelSurface) {
        // Send initial configure so client starts drawing
        surface.with_pending_state(|state| {
            state.size = Some((800, 600).into());
        });
        surface.send_configure();

        let window = Window::new_wayland_window(surface);
        self.space.map_element(window, (0, 0), false);
        tracing::info!("New toplevel mapped (800x600)");
    }

    fn toplevel_destroyed(&mut self, _surface: ToplevelSurface) {
        tracing::info!("Toplevel destroyed");
    }

    fn new_popup(
        &mut self,
        _surface: smithay::wayland::shell::xdg::PopupSurface,
        _positioner: smithay::wayland::shell::xdg::PositionerState,
    ) {}

    fn grab(
        &mut self,
        _surface: smithay::wayland::shell::xdg::PopupSurface,
        _seat: smithay::reexports::wayland_server::protocol::wl_seat::WlSeat,
        _serial: Serial,
    ) {}

    fn reposition_request(
        &mut self,
        _surface: smithay::wayland::shell::xdg::PopupSurface,
        _positioner: smithay::wayland::shell::xdg::PositionerState,
        _token: u32,
    ) {}
}

impl ShmHandler for AulinxState {
    fn shm_state(&self) -> &ShmState {
        &self.shm_state
    }
}

impl SeatHandler for AulinxState {
    type KeyboardFocus = WlSurface;
    type PointerFocus = WlSurface;
    type TouchFocus = WlSurface;

    fn seat_state(&mut self) -> &mut SeatState<Self> {
        &mut self.seat_state
    }

    fn cursor_image(&mut self, _seat: &Seat<Self>, _image: smithay::input::pointer::CursorImageStatus) {}
    fn focus_changed(&mut self, _seat: &Seat<Self>, _target: Option<&WlSurface>) {}
}

impl DataDeviceHandler for AulinxState {
    fn data_device_state(&mut self) -> &mut DataDeviceState {
        &mut self.data_device_state
    }
}

impl smithay::wayland::selection::SelectionHandler for AulinxState {
    type SelectionUserData = ();
}

impl smithay::wayland::selection::data_device::WaylandDndGrabHandler for AulinxState {}

impl smithay::wayland::buffer::BufferHandler for AulinxState {
    fn buffer_destroyed(&mut self, _buffer: &smithay::reexports::wayland_server::protocol::wl_buffer::WlBuffer) {}
}

impl smithay::wayland::output::OutputHandler for AulinxState {}

// ---- Delegates ----
delegate_compositor!(AulinxState);
delegate_xdg_shell!(AulinxState);
delegate_shm!(AulinxState);
delegate_seat!(AulinxState);
delegate_data_device!(AulinxState);
delegate_output!(AulinxState);
