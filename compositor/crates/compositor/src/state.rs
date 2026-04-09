//! AulinxState — the central compositor state struct.
//!
//! All Smithay delegate macros implement on this type. The calloop
//! event loop passes `&mut AulinxState` to every callback.
//!
//! This file will likely need adjustments when first compiled against
//! Smithay 0.7 on Linux, as exact type paths may vary.

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
use smithay::reexports::wayland_server::backend::{ClientData, ClientId, DisconnectReason};
use smithay::reexports::wayland_server::protocol::wl_surface::WlSurface;
use smithay::reexports::wayland_server::{Display, DisplayHandle};
use smithay::utils::{Clock, Monotonic, Serial, SERIAL_COUNTER};
use smithay::wayland::compositor::{CompositorClientState, CompositorHandler, CompositorState};
use smithay::wayland::output::OutputManagerState;
use smithay::wayland::selection::data_device::{
    ClientDndGrabHandler, DataDeviceHandler, DataDeviceState, ServerDndGrabHandler,
};
use smithay::wayland::shell::xdg::{ToplevelSurface, XdgShellHandler, XdgShellState};
use smithay::wayland::shm::{ShmHandler, ShmState};
use smithay::wayland::socket::ListeningSocketSource;

use crate::backend::BackendData;
use crate::ipc::CompositorIpc;
use crate::layout::{LayoutEngine, LayoutRect, WindowId};
use crate::semantic_bridge::SemanticBridge;
use crate::workspace::WorkspaceManager;

/// Per-client state stored by Smithay.
pub struct ClientState {
    pub compositor_state: CompositorClientState,
}

impl ClientData for ClientState {
    fn initialized(&self, _client_id: ClientId) {}
    fn disconnected(&self, _client_id: ClientId, _reason: DisconnectReason) {}
}

/// The central compositor state.
pub struct AulinxState {
    // -- Wayland core --
    pub display_handle: DisplayHandle,
    pub compositor_state: CompositorState,
    pub xdg_shell_state: XdgShellState,
    pub shm_state: ShmState,
    pub output_manager_state: OutputManagerState,
    pub data_device_state: DataDeviceState,
    pub layer_shell_state: smithay::wayland::shell::wlr_layer::WlrLayerShellState,
    pub xdg_decoration_state: smithay::wayland::shell::xdg::decoration::XdgDecorationState,

    // -- XWayland --
    pub xwayland_state: Option<crate::xwayland::XWaylandState>,

    // -- Input --
    pub seat_state: SeatState<Self>,
    pub seat_name: String,

    // -- Desktop --
    pub space: Space<Window>,
    pub workspaces: WorkspaceManager,
    pub next_window_id: WindowId,
    /// Maps Smithay Window to our WindowId.
    pub window_ids: std::collections::HashMap<Window, WindowId>,

    // -- Backend --
    pub backend_data: BackendData,

    // -- Loop --
    pub loop_handle: LoopHandle<'static, Self>,
    pub loop_signal: LoopSignal,
    pub clock: Clock<Monotonic>,

    // -- Misc --
    pub start_time: Instant,
    pub socket_name: String,

    // -- Semantic --
    pub scene_graph: aulinx_semantic::SceneGraph,
    pub semantic_bridge: SemanticBridge,
    pub ipc: Option<CompositorIpc>,
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

        // Initialize Wayland protocol states
        let compositor_state = CompositorState::new::<Self>(&display_handle);
        let xdg_shell_state = XdgShellState::new::<Self>(&display_handle);
        let shm_state = ShmState::new::<Self>(&display_handle, vec![]);
        let output_manager_state = OutputManagerState::new_with_xdg_output::<Self>(&display_handle);
        let data_device_state = DataDeviceState::new::<Self>(&display_handle);
        let layer_shell_state = Self::init_layer_shell(&display_handle);
        let xdg_decoration_state = Self::init_xdg_decoration(&display_handle);

        // Create seat
        let mut seat_state = SeatState::new();
        let seat_name = backend_data.seat_name();
        let mut seat = seat_state.new_wl_seat(&display_handle, seat_name.clone());
        seat.add_keyboard(Default::default(), 200, 25)
            .expect("Failed to add keyboard to seat");
        seat.add_pointer();

        // Listen for Wayland clients
        let socket_source = ListeningSocketSource::new_auto()
            .expect("Failed to create Wayland listening socket");
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

        // Insert the Wayland display source into calloop
        loop_handle
            .insert_source(
                Generic::new(display, Interest::READ, Mode::Level),
                |_, display, state: &mut Self| {
                    // Safety: we don't drop the display
                    unsafe {
                        display.get_mut().dispatch_clients(state).ok();
                    }
                    Ok(PostAction::Continue)
                },
            )
            .expect("Failed to insert display source");

        tracing::info!("Wayland socket: {socket_name}");

        // Map the output into the space
        if let BackendData::Winit(ref winit_data) = backend_data {
            // Will be done on first frame render
        }

        Self {
            display_handle,
            compositor_state,
            xdg_shell_state,
            shm_state,
            output_manager_state,
            data_device_state,
            layer_shell_state,
            xdg_decoration_state,
            xwayland_state: None,
            seat_state,
            seat_name,
            space: Space::default(),
            workspaces: WorkspaceManager::new(9),
            next_window_id: 1,
            window_ids: std::collections::HashMap::new(),
            backend_data,
            loop_handle,
            loop_signal,
            clock,
            start_time: Instant::now(),
            socket_name,
            scene_graph: aulinx_semantic::SceneGraph::new(),
            semantic_bridge: SemanticBridge::new(),
            ipc: None,
        }
    }

    /// Handle initial configure for XDG surfaces.
    /// Some clients wait for the first configure before drawing.
    fn handle_initial_configure(&self, surface: &WlSurface) {
        use smithay::wayland::shell::xdg;

        if let Some(toplevel) = self
            .xdg_shell_state
            .toplevel_surfaces()
            .find(|t| t.wl_surface() == surface)
        {
            if !toplevel.is_initial_configure_sent() {
                toplevel.send_configure();
            }
        }

        if let Some(popup) = self
            .xdg_shell_state
            .popup_surfaces()
            .find(|p| p.wl_surface() == surface)
        {
            if !popup.is_initial_configure_sent() {
                popup.send_configure().ok();
            }
        }
    }

    /// Apply the layout engine's calculated positions to all windows.
    pub fn apply_layout(&mut self) {
        let Some(output) = self.space.outputs().next().cloned() else {
            return;
        };
        let Some(geo) = self.space.output_geometry(&output) else {
            return;
        };

        let area = LayoutRect {
            x: geo.loc.x,
            y: geo.loc.y,
            width: geo.size.w,
            height: geo.size.h,
        };

        let ws = self.workspaces.active_workspace();
        let positions = ws.layout.calculate_layout(area);

        // Build a map from WindowId to layout rect
        let layout_map: std::collections::HashMap<WindowId, LayoutRect> =
            positions.into_iter().collect();

        // Apply to each window in the space
        let windows: Vec<Window> = self.space.elements().cloned().collect();
        for window in &windows {
            let Some(&wid) = self.window_ids.get(window) else {
                continue;
            };

            // Only show windows from the active workspace
            if !self.workspaces.active_workspace().contains(wid) {
                // TODO: hide windows from other workspaces
                continue;
            }

            if let Some(rect) = layout_map.get(&wid) {
                self.space
                    .map_element(window.clone(), (rect.x, rect.y), false);

                if let Some(toplevel) = window.toplevel() {
                    toplevel.with_pending_state(|state| {
                        state.size = Some((rect.width, rect.height).into());
                    });
                    toplevel.send_configure();
                }
            }
        }
    }

    /// Get the WindowId for a Smithay Window.
    pub fn window_id(&self, window: &Window) -> Option<WindowId> {
        self.window_ids.get(window).copied()
    }

    /// Toggle the focused window between tiling and floating.
    pub fn toggle_focused_floating(&mut self) {
        let Some(output) = self.space.outputs().next().cloned() else {
            return;
        };
        let Some(geo) = self.space.output_geometry(&output) else {
            return;
        };

        let ws = self.workspaces.active_workspace_mut();
        if let Some(wid) = ws.layout.focused_window {
            let area = LayoutRect {
                x: geo.loc.x,
                y: geo.loc.y,
                width: geo.size.w,
                height: geo.size.h,
            };
            ws.layout.toggle_floating(wid, area);
        }
        drop(ws);
        self.apply_layout();
    }

    /// Switch to a workspace by index (0-based).
    pub fn switch_workspace(&mut self, index: usize) {
        if self.workspaces.switch_to(index) {
            tracing::info!("Switched to workspace {}", index + 1);
            // Unmap all windows, then map windows from new workspace
            let all_windows: Vec<Window> = self.space.elements().cloned().collect();
            for window in &all_windows {
                self.space.unmap_elem(window);
            }

            // Re-map windows from the active workspace
            let active_ws = self.workspaces.active_workspace();
            let active_wids: Vec<WindowId> = active_ws.windows.clone();

            for window in &all_windows {
                if let Some(&wid) = self.window_ids.get(window) {
                    if active_wids.contains(&wid) {
                        self.space.map_element(window.clone(), (0, 0), false);
                    }
                }
            }

            self.apply_layout();
        }
    }

    /// Initialize the semantic bridge and IPC server.
    pub fn init_semantic(&mut self) {
        // Determine output size
        let (w, h) = self
            .space
            .outputs()
            .next()
            .and_then(|o| self.space.output_geometry(o))
            .map(|g| (g.size.w, g.size.h))
            .unwrap_or((1920, 1080));

        self.semantic_bridge.init(&mut self.scene_graph, w, h);

        // Start IPC server
        let socket_path = crate::ipc_socket_path();
        match CompositorIpc::new(&socket_path) {
            Ok(ipc) => {
                self.ipc = Some(ipc);
                tracing::info!("Compositor IPC ready on {}", socket_path.display());
            }
            Err(e) => tracing::error!("Failed to start IPC server: {e}"),
        }
    }

    /// Poll the IPC server and handle compositor commands.
    pub fn poll_ipc(&mut self) {
        let Some(ref mut ipc) = self.ipc else { return };

        let commands = ipc.poll(&self.scene_graph);

        for cmd in commands {
            let response = self.handle_compositor_command(&cmd);
            if let Some(ref mut ipc) = self.ipc {
                ipc.send_response(cmd.client_id, &response);
            }
        }

        // Push any pending semantic events
        let events = self.semantic_bridge.compute_events(&self.scene_graph);
        if !events.is_empty() {
            if let Some(ref mut ipc) = self.ipc {
                ipc.push_events(&events);
            }
        }
    }

    /// Handle a compositor-specific IPC command.
    fn handle_compositor_command(&mut self, cmd: &crate::ipc::CompositorCommand) -> String {
        use aulinx_semantic::protocol::*;

        let id = cmd.request_id.clone();
        let params = &cmd.params;

        let resp = match cmd.method.as_str() {
            "window.focus" => {
                let wid = params.get("window_id").and_then(|v| v.as_u64());
                match wid {
                    Some(wid) => {
                        // Find the window and focus it
                        let window = self.window_ids.iter()
                            .find(|(_, &id)| id == wid)
                            .map(|(w, _)| w.clone());
                        if let Some(window) = window {
                            self.space.raise_element(&window, true);
                            let serial = SERIAL_COUNTER.next_serial();
                            let seat = self.seat_state.seats().next().unwrap().clone();
                            if let Some(keyboard) = seat.get_keyboard() {
                                if let Some(toplevel) = window.toplevel() {
                                    keyboard.set_focus(self, Some(toplevel.wl_surface().clone()), serial);
                                }
                            }
                            self.semantic_bridge.window_focused(&mut self.scene_graph, wid);
                            JsonRpcResponse::success(id, serde_json::json!({ "ok": true }))
                        } else {
                            JsonRpcResponse::error(id, INVALID_PARAMS, format!("window {wid} not found"))
                        }
                    }
                    None => JsonRpcResponse::error(id, INVALID_PARAMS, "missing window_id".into()),
                }
            }

            "window.close" => {
                let wid = params.get("window_id").and_then(|v| v.as_u64());
                match wid {
                    Some(wid) => {
                        let window = self.window_ids.iter()
                            .find(|(_, &id)| id == wid)
                            .map(|(w, _)| w.clone());
                        if let Some(window) = window {
                            if let Some(toplevel) = window.toplevel() {
                                toplevel.send_close();
                            }
                            JsonRpcResponse::success(id, serde_json::json!({ "ok": true }))
                        } else {
                            JsonRpcResponse::error(id, INVALID_PARAMS, format!("window {wid} not found"))
                        }
                    }
                    None => JsonRpcResponse::error(id, INVALID_PARAMS, "missing window_id".into()),
                }
            }

            "window.move" => {
                let wid = params.get("window_id").and_then(|v| v.as_u64());
                let x = params.get("x").and_then(|v| v.as_i64()).unwrap_or(0) as i32;
                let y = params.get("y").and_then(|v| v.as_i64()).unwrap_or(0) as i32;
                let w = params.get("w").and_then(|v| v.as_i64()).unwrap_or(800) as i32;
                let h = params.get("h").and_then(|v| v.as_i64()).unwrap_or(600) as i32;

                match wid {
                    Some(wid) => {
                        // Set to floating and apply geometry
                        let ws = self.workspaces.active_workspace_mut();
                        if !ws.layout.is_floating(wid) {
                            let area = LayoutRect { x: 0, y: 0, width: 1920, height: 1080 };
                            ws.layout.toggle_floating(wid, area);
                        }
                        ws.layout.set_floating_geometry(wid, LayoutRect { x, y, width: w, height: h });
                        drop(ws);
                        self.apply_layout();
                        self.semantic_bridge.window_geometry_changed(
                            &mut self.scene_graph, wid, x, y, w, h,
                        );
                        JsonRpcResponse::success(id, serde_json::json!({ "ok": true }))
                    }
                    None => JsonRpcResponse::error(id, INVALID_PARAMS, "missing window_id".into()),
                }
            }

            "input.type" => {
                let text = params.get("text").and_then(|v| v.as_str()).unwrap_or("");
                match self.inject_text(text) {
                    Ok(()) => JsonRpcResponse::success(id, serde_json::json!({ "ok": true })),
                    Err(e) => JsonRpcResponse::error(id, INTERNAL_ERROR, e),
                }
            }

            "input.key" => {
                let combo = params.get("combo").and_then(|v| v.as_str()).unwrap_or("");
                match self.inject_key_combo(combo) {
                    Ok(()) => JsonRpcResponse::success(id, serde_json::json!({ "ok": true })),
                    Err(e) => JsonRpcResponse::error(id, INTERNAL_ERROR, e),
                }
            }

            "input.mouse" => {
                let x = params.get("x").and_then(|v| v.as_f64()).unwrap_or(0.0);
                let y = params.get("y").and_then(|v| v.as_f64()).unwrap_or(0.0);
                let button = params.get("button").and_then(|v| v.as_u64()).map(|b| b as u32);
                let action = params.get("action").and_then(|v| v.as_str());
                match self.inject_mouse(x, y, button, action) {
                    Ok(()) => JsonRpcResponse::success(id, serde_json::json!({ "ok": true })),
                    Err(e) => JsonRpcResponse::error(id, INTERNAL_ERROR, e),
                }
            }

            "window.screenshot" => {
                let wid = params.get("window_id").and_then(|v| v.as_u64());
                match wid {
                    Some(wid) => match self.capture_window(wid) {
                        Ok(b64) => JsonRpcResponse::success(
                            id,
                            serde_json::json!({ "format": "png", "data": b64 }),
                        ),
                        Err(e) => JsonRpcResponse::error(id, INTERNAL_ERROR, e),
                    },
                    None => JsonRpcResponse::error(id, INVALID_PARAMS, "missing window_id".into()),
                }
            }

            "screen.capture" => {
                match self.capture_screen() {
                    Ok(b64) => JsonRpcResponse::success(
                        id,
                        serde_json::json!({ "format": "png", "data": b64 }),
                    ),
                    Err(e) => JsonRpcResponse::error(id, INTERNAL_ERROR, e),
                }
            }

            "element.activate" | "element.set_value" => {
                // TODO: route through AT-SPI source if available
                JsonRpcResponse::error(id, METHOD_NOT_FOUND, format!("{} not yet implemented", cmd.method))
            }

            _ => {
                JsonRpcResponse::error(id, METHOD_NOT_FOUND, format!("unknown method: {}", cmd.method))
            }
        };

        serde_json::to_string(&resp).unwrap_or_default()
    }

    /// Close the focused window.
    pub fn close_focused(&mut self) {
        let seat = self.seat_state.seats().next().unwrap().clone();
        let keyboard = seat.get_keyboard().unwrap();

        if let Some(focus) = keyboard.current_focus() {
            // Find the window with this surface
            if let Some(window) = self
                .space
                .elements()
                .find(|w| {
                    w.toplevel()
                        .map(|t| t.wl_surface() == &focus)
                        .unwrap_or(false)
                })
                .cloned()
            {
                if let Some(toplevel) = window.toplevel() {
                    toplevel.send_close();
                }
            }
        }
    }
}

// ---- Handler implementations ----

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
        // Ensure the compositor handles buffer imports
        smithay::wayland::compositor::on_commit_buffer_handler::<Self>(surface);

        // Notify the window of the commit
        if let Some(window) = self
            .space
            .elements()
            .find(|w| {
                w.toplevel()
                    .map(|t| t.wl_surface() == surface)
                    .unwrap_or(false)
            })
            .cloned()
        {
            window.on_commit();
        }

        // Handle initial configure for newly committed surfaces
        self.handle_initial_configure(surface);
    }
}

impl XdgShellHandler for AulinxState {
    fn xdg_shell_state(&mut self) -> &mut XdgShellState {
        &mut self.xdg_shell_state
    }

    fn new_toplevel(&mut self, surface: ToplevelSurface) {
        let window = Window::new_wayland_window(surface);

        // Assign a window ID
        let wid = self.next_window_id;
        self.next_window_id += 1;
        self.window_ids.insert(window.clone(), wid);

        // Detect if this is a dialog (has parent)
        let is_dialog = window
            .toplevel()
            .and_then(|t| t.with_pending_state(|s| s.parent.is_some()))
            .unwrap_or(false);

        // Add to active workspace layout
        self.workspaces.active_workspace_mut().add_window(wid, is_dialog);

        // Map into space and apply layout
        self.space.map_element(window.clone(), (0, 0), false);
        self.apply_layout();

        // Focus the new window
        let serial = SERIAL_COUNTER.next_serial();
        let seat = self.seat_state.seats().next().unwrap().clone();
        if let Some(keyboard) = seat.get_keyboard() {
            if let Some(toplevel) = window.toplevel() {
                keyboard.set_focus(self, Some(toplevel.wl_surface().clone()), serial);
            }
        }
        self.workspaces
            .active_workspace_mut()
            .layout
            .set_focused(Some(wid));

        // Feed the semantic bridge
        let app_id = window
            .toplevel()
            .map(|t| t.app_id().unwrap_or_default())
            .unwrap_or_default();
        let title = window
            .toplevel()
            .map(|t| t.title().unwrap_or_default())
            .unwrap_or_default();
        self.semantic_bridge.window_opened(
            &mut self.scene_graph, wid, 0, &app_id, &title, 0, 0, 0, 0,
        );

        tracing::info!("New toplevel mapped (id={wid}, app={app_id}, dialog={is_dialog})");
    }

    fn toplevel_destroyed(&mut self, surface: ToplevelSurface) {
        // Find and remove the window
        if let Some(window) = self
            .space
            .elements()
            .find(|w| {
                w.toplevel()
                    .map(|t| t.wl_surface() == surface.wl_surface())
                    .unwrap_or(false)
            })
            .cloned()
        {
            if let Some(&wid) = self.window_ids.get(&window) {
                // Remove from workspace
                for ws in &mut self.workspaces.workspaces {
                    ws.remove_window(wid);
                }
                self.window_ids.remove(&window);
                // Feed the semantic bridge
                self.semantic_bridge.window_closed(&mut self.scene_graph, wid);
            }
            self.space.unmap_elem(&window);
        }

        tracing::info!("Toplevel destroyed");
        self.apply_layout();
    }

    fn new_popup(
        &mut self,
        _surface: smithay::wayland::shell::xdg::PopupSurface,
        _positioner: smithay::wayland::shell::xdg::PositionerState,
    ) {
    }

    fn grab(
        &mut self,
        _surface: smithay::wayland::shell::xdg::PopupSurface,
        _seat: smithay::reexports::wayland_server::protocol::wl_seat::WlSeat,
        _serial: Serial,
    ) {
    }

    fn reposition_request(
        &mut self,
        _surface: smithay::wayland::shell::xdg::PopupSurface,
        _positioner: smithay::wayland::shell::xdg::PositionerState,
        _token: u32,
    ) {
    }
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

    fn cursor_image(
        &mut self,
        _seat: &Seat<Self>,
        _image: smithay::input::pointer::CursorImageStatus,
    ) {
    }

    fn focus_changed(&mut self, _seat: &Seat<Self>, _target: Option<&WlSurface>) {}
}

impl DataDeviceHandler for AulinxState {
    fn data_device_state(&self) -> &DataDeviceState {
        &self.data_device_state
    }
}

impl ClientDndGrabHandler for AulinxState {}
impl ServerDndGrabHandler for AulinxState {}

// ---- Delegate macros ----
delegate_compositor!(AulinxState);
delegate_xdg_shell!(AulinxState);
delegate_shm!(AulinxState);
delegate_seat!(AulinxState);
delegate_data_device!(AulinxState);
delegate_output!(AulinxState);
