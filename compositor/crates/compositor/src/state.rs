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
use smithay::reexports::calloop::{LoopHandle, LoopSignal};
use smithay::reexports::wayland_server::backend::{ClientData, ClientId, DisconnectReason};
use smithay::reexports::wayland_server::protocol::wl_surface::WlSurface;
use smithay::reexports::wayland_server::{Display, DisplayHandle};
use smithay::utils::{Serial, SERIAL_COUNTER};
use smithay::wayland::compositor::{CompositorClientState, CompositorHandler, CompositorState};
use smithay::wayland::output::OutputManagerState;
use smithay::wayland::selection::data_device::{DataDeviceHandler, DataDeviceState};
use smithay::wayland::fractional_scale::{FractionalScaleHandler, FractionalScaleManagerState};
use smithay::wayland::selection::primary_selection::{PrimarySelectionHandler, PrimarySelectionState};
use smithay::wayland::xdg_activation::{XdgActivationHandler, XdgActivationState, XdgActivationToken, XdgActivationTokenData};
use smithay::wayland::compositor as wl_compositor;
use smithay::wayland::shell::xdg::{ToplevelSurface, XdgShellHandler, XdgShellState, XdgToplevelSurfaceData};
use smithay::wayland::shell::xdg::decoration::{XdgDecorationHandler, XdgDecorationState};
use smithay::wayland::shell::wlr_layer::{Layer, LayerSurface, WlrLayerShellHandler, WlrLayerShellState};
use smithay::wayland::shm::{ShmHandler, ShmState};
use smithay::wayland::socket::ListeningSocketSource;
use smithay::wayland::viewporter::ViewporterState;

use smithay::reexports::wayland_protocols::xdg::decoration::zv1::server::zxdg_toplevel_decoration_v1::Mode as DecorationMode;

use base64::Engine;

use crate::backend::BackendData;
use crate::config::Config;

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
    pub data_device_state: DataDeviceState,
    pub primary_selection_state: PrimarySelectionState,
    pub xdg_activation_state: XdgActivationState,
    pub layer_shell_state: WlrLayerShellState,
    pub seat_state: SeatState<Self>,
    pub seat: Seat<Self>,
    pub space: Space<Window>,
    pub backend_data: BackendData,
    pub loop_handle: LoopHandle<'static, Self>,
    pub loop_signal: LoopSignal,
    pub start_time: Instant,
    pub socket_name: String,
    pub config: Config,
    pub scene_graph: aulinx_semantic::SceneGraph,
    pub semantic_bridge: Option<crate::semantic_bridge::SemanticBridge>,
}

impl AulinxState {
    pub fn new(
        display: Display<Self>,
        loop_handle: LoopHandle<'static, Self>,
        loop_signal: LoopSignal,
        backend_data: BackendData,
    ) -> Self {
        let display_handle = display.handle();

        let compositor_state = CompositorState::new::<Self>(&display_handle);
        let xdg_shell_state = XdgShellState::new::<Self>(&display_handle);
        let shm_state = ShmState::new::<Self>(&display_handle, vec![]);
        let _output_manager_state = OutputManagerState::new_with_xdg_output::<Self>(&display_handle);
        let _xdg_decoration_state = XdgDecorationState::new::<Self>(&display_handle);
        let primary_selection_state = PrimarySelectionState::new::<Self>(&display_handle);
        let xdg_activation_state = XdgActivationState::new::<Self>(&display_handle);
        let _fractional_scale_state = FractionalScaleManagerState::new::<Self>(&display_handle);
        let layer_shell_state = WlrLayerShellState::new::<Self>(&display_handle);
        let _viewporter_state = ViewporterState::new::<Self>(&display_handle);
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
            data_device_state,
            primary_selection_state,
            xdg_activation_state,
            layer_shell_state,
            seat_state,
            seat,
            space: Space::default(),
            backend_data,
            loop_handle,
            loop_signal,
            start_time: Instant::now(),
            socket_name,
            config: Config::load(),
            scene_graph: aulinx_semantic::SceneGraph::new(),
            semantic_bridge: None,
        }
    }
}

impl AulinxState {
    /// Tile windows in a master+stack layout with configurable gaps and ratio.
    pub fn relayout(&mut self) {
        let Some(output) = self.space.outputs().next().cloned() else { return };
        let Some(geo) = self.space.output_geometry(&output) else { return };

        let windows: Vec<Window> = self.space.elements().cloned().collect();
        let count = windows.len();
        if count == 0 { return; }

        let gap = self.config.layout.gap;
        let outer = self.config.layout.outer_gap;
        let ratio = self.config.layout.master_ratio;

        // Usable area (inside outer gaps)
        let ux = outer;
        let uy = outer;
        let uw = geo.size.w - outer * 2;
        let uh = geo.size.h - outer * 2;

        // Calculate layout geometries
        let layouts: Vec<(i32, i32, i32, i32)> = if count == 1 {
            vec![(ux, uy, uw, uh)]
        } else {
            let master_w = (uw as f32 * ratio) as i32 - gap / 2;
            let stack_w = uw - master_w - gap;
            let stack_x = ux + master_w + gap;
            let stack_count = (count - 1) as i32;
            let stack_h = (uh - gap * (stack_count - 1)) / stack_count;

            let mut layouts = vec![(ux, uy, master_w, uh)];
            for i in 0..stack_count {
                let y = uy + (stack_h + gap) * i;
                let h = if i == stack_count - 1 { uy + uh - y } else { stack_h };
                layouts.push((stack_x, y, stack_w, h));
            }
            layouts
        };

        for (i, window) in windows.iter().enumerate() {
            let (x, y, w, h) = layouts[i];
            self.space.map_element(window.clone(), (x, y), false);
            if let Some(toplevel) = window.toplevel() {
                toplevel.with_pending_state(|state| {
                    state.size = Some((w, h).into());
                });
                toplevel.send_configure();

                // Update semantic bridge with new geometry
                if let Some(ref mut bridge) = self.semantic_bridge {
                    bridge.window_geometry_changed(
                        &mut self.scene_graph,
                        toplevel.wl_surface(),
                        aulinx_semantic::node::Rect::new(x, y, w, h),
                    );
                }
            }
        }

        if count == 1 {
            tracing::info!("Layout: 1 window fullscreen");
        } else {
            tracing::info!("Layout: master+stack with {} windows", count);
        }
    }
}

impl AulinxState {
    /// Focus the next window in the stack.
    pub fn focus_next_window(&mut self) {
        let windows: Vec<Window> = self.space.elements().cloned().collect();
        if windows.len() < 2 { return; }

        let keyboard = self.seat.get_keyboard().unwrap();
        let current_focus = keyboard.current_focus();

        let current_idx = windows.iter().position(|w| {
            w.toplevel().map(|t| Some(t.wl_surface().clone()) == current_focus).unwrap_or(false)
        }).unwrap_or(0);

        let next_idx = (current_idx + 1) % windows.len();
        let next = &windows[next_idx];
        self.space.raise_element(next, true);
        if let Some(toplevel) = next.toplevel() {
            let serial = SERIAL_COUNTER.next_serial();
            keyboard.set_focus(self, Some(toplevel.wl_surface().clone()), serial);
        }
    }

    /// Focus the previous window in the stack.
    pub fn focus_prev_window(&mut self) {
        let windows: Vec<Window> = self.space.elements().cloned().collect();
        if windows.len() < 2 { return; }

        let keyboard = self.seat.get_keyboard().unwrap();
        let current_focus = keyboard.current_focus();

        let current_idx = windows.iter().position(|w| {
            w.toplevel().map(|t| Some(t.wl_surface().clone()) == current_focus).unwrap_or(false)
        }).unwrap_or(0);

        let prev_idx = if current_idx == 0 { windows.len() - 1 } else { current_idx - 1 };
        let prev = &windows[prev_idx];
        self.space.raise_element(prev, true);
        if let Some(toplevel) = prev.toplevel() {
            let serial = SERIAL_COUNTER.next_serial();
            keyboard.set_focus(self, Some(toplevel.wl_surface().clone()), serial);
        }
    }

    /// Swap the focused window with the master (first) window.
    pub fn swap_with_master(&mut self) {
        let windows: Vec<Window> = self.space.elements().cloned().collect();
        if windows.len() < 2 { return; }

        let keyboard = self.seat.get_keyboard().unwrap();
        let current_focus = keyboard.current_focus();

        let current_idx = windows.iter().position(|w| {
            w.toplevel().map(|t| Some(t.wl_surface().clone()) == current_focus).unwrap_or(false)
        }).unwrap_or(0);

        if current_idx == 0 { return; } // Already master

        // Unmap all, re-map with swapped order
        let mut new_order = windows.clone();
        new_order.swap(0, current_idx);

        for window in &windows {
            self.space.unmap_elem(window);
        }
        for window in &new_order {
            self.space.map_element(window.clone(), (0, 0), false);
        }

        self.relayout();
        tracing::info!("Swapped window {} with master", current_idx);
    }

    /// Focus a window by its index in the layout (0-based).
    pub fn focus_window_by_index(&mut self, index: usize) {
        let windows: Vec<Window> = self.space.elements().cloned().collect();
        if index >= windows.len() { return; }

        let window = &windows[index];
        self.space.raise_element(window, true);
        if let Some(toplevel) = window.toplevel() {
            let keyboard = self.seat.get_keyboard().unwrap();
            let serial = SERIAL_COUNTER.next_serial();
            keyboard.set_focus(self, Some(toplevel.wl_surface().clone()), serial);
        }
    }

    /// Swap a window (by semantic ID) with the master window.
    pub fn swap_window_to_master(&mut self, window_id: u64) -> Result<(), String> {
        let target = self.find_window_by_semantic_id(window_id)?;
        let windows: Vec<Window> = self.space.elements().cloned().collect();
        if windows.len() < 2 {
            return Err("need at least 2 windows to swap".into());
        }

        let target_idx = windows.iter().position(|w| w == &target)
            .ok_or("window not in layout")?;

        if target_idx == 0 {
            return Ok(()); // Already master
        }

        let mut new_order = windows;
        new_order.swap(0, target_idx);
        for window in self.space.elements().cloned().collect::<Vec<_>>() {
            self.space.unmap_elem(&window);
        }
        for window in &new_order {
            self.space.map_element(window.clone(), (0, 0), false);
        }
        self.relayout();
        tracing::info!("Swapped window_id={window_id} to master");
        Ok(())
    }

    /// Close a window by semantic ID. If None, close the focused window.
    pub fn close_window(&mut self, window_id: Option<u64>) -> Result<(), String> {
        let window = if let Some(id) = window_id {
            self.find_window_by_semantic_id(id)?
        } else {
            // Close the focused window (last raised)
            self.space.elements().last().cloned()
                .ok_or_else(|| "no windows to close".to_string())?
        };

        if let Some(toplevel) = window.toplevel() {
            toplevel.send_close();
            tracing::info!("window.close: sent close request");
            Ok(())
        } else {
            Err("window has no toplevel".into())
        }
    }

    /// Focus a window by semantic ID.
    pub fn focus_window(&mut self, window_id: u64) -> Result<(), String> {
        let window = self.find_window_by_semantic_id(window_id)?;
        self.space.raise_element(&window, true);

        if let Some(toplevel) = window.toplevel() {
            let keyboard = self.seat.get_keyboard().unwrap();
            let serial = SERIAL_COUNTER.next_serial();
            keyboard.set_focus(self, Some(toplevel.wl_surface().clone()), serial);
            tracing::info!("window.focus: focused window_id={window_id}");
            Ok(())
        } else {
            Err("window has no toplevel".into())
        }
    }

    /// Generate an ASCII art map of the desktop layout.
    /// Text-only AI agents can "see" the desktop without screenshots.
    pub fn ascii_layout(&self) -> String {
        let Some(output) = self.space.outputs().next().cloned() else {
            return "No output".to_string();
        };
        let Some(geo) = self.space.output_geometry(&output) else {
            return "No geometry".to_string();
        };

        let windows: Vec<_> = self.space.elements().cloned().collect();
        if windows.is_empty() {
            return format!(
                "┌{}┐\n│{:^width$}│\n│{:^width$}│\n└{}┘",
                "─".repeat(40), "Empty Desktop", format!("{}x{}", geo.size.w, geo.size.h),
                "─".repeat(40), width = 40
            );
        }

        // Scale to ~60 char width, ~20 lines
        let scale_x = 60.0 / geo.size.w as f64;
        let scale_y = 20.0 / geo.size.h as f64;

        // Create a character grid
        let grid_w = 62;
        let grid_h = 22;
        let mut grid = vec![vec![' '; grid_w]; grid_h];

        // Draw outer border
        for x in 0..grid_w { grid[0][x] = '─'; grid[grid_h-1][x] = '─'; }
        for y in 0..grid_h { grid[y][0] = '│'; grid[y][grid_w-1] = '│'; }
        grid[0][0] = '┌'; grid[0][grid_w-1] = '┐';
        grid[grid_h-1][0] = '└'; grid[grid_h-1][grid_w-1] = '┘';

        // Draw each window
        for window in &windows {
            if let Some(wgeo) = self.space.element_geometry(window) {
                let x1 = ((wgeo.loc.x as f64 * scale_x) as usize + 1).min(grid_w - 2);
                let y1 = ((wgeo.loc.y as f64 * scale_y) as usize + 1).min(grid_h - 2);
                let x2 = (((wgeo.loc.x + wgeo.size.w) as f64 * scale_x) as usize + 1).min(grid_w - 2);
                let y2 = (((wgeo.loc.y + wgeo.size.h) as f64 * scale_y) as usize + 1).min(grid_h - 2);

                if x2 <= x1 || y2 <= y1 { continue; }

                // Draw window border
                for x in x1..=x2 { grid[y1][x] = '─'; grid[y2][x] = '─'; }
                for y in y1..=y2 { grid[y][x1] = '│'; grid[y][x2] = '│'; }
                grid[y1][x1] = '┌'; grid[y1][x2] = '┐';
                grid[y2][x1] = '└'; grid[y2][x2] = '┘';

                // Draw window label
                let (title, wid) = window.toplevel().map(|t| {
                    let title = wl_compositor::with_states(t.wl_surface(), |states| {
                        states.data_map.get::<XdgToplevelSurfaceData>()
                            .unwrap().lock().unwrap()
                            .title.clone().unwrap_or_default()
                    });
                    let wid = self.semantic_bridge.as_ref()
                        .and_then(|b| b.window_id_for_surface(t.wl_surface()))
                        .unwrap_or(0);
                    (title, wid)
                }).unwrap_or_default();

                let label = format!("[{}]{}", wid, if title.len() > 8 { &title[..8] } else { &title });
                if y1 + 1 < y2 && x1 + 1 < x2 {
                    let label_y = y1 + 1;
                    for (i, ch) in label.chars().enumerate() {
                        if x1 + 1 + i < x2 { grid[label_y][x1 + 1 + i] = ch; }
                    }
                }
            }
        }

        grid.iter().map(|row| row.iter().collect::<String>()).collect::<Vec<_>>().join("\n")
    }

    /// Generate a natural language description of the desktop state.
    /// This is the bridge between semantic understanding and AI agents.
    pub fn describe_desktop(&self) -> String {
        let windows: Vec<_> = self.space.elements().cloned().collect();
        let focused = self.seat.get_keyboard().unwrap().current_focus();
        let focused_id = focused.and_then(|s| {
            self.semantic_bridge.as_ref().and_then(|b| b.window_id_for_surface(&s))
        });

        if windows.is_empty() {
            return "Empty desktop. No windows open. Press Super+Return to open a terminal.".to_string();
        }

        let mut desc = Vec::new();

        // Layout description
        let layout = if windows.len() == 1 {
            "single window (fullscreen)".to_string()
        } else {
            format!("master+stack layout ({} windows, {:.0}% master ratio)",
                windows.len(), self.config.layout.master_ratio * 100.0)
        };
        desc.push(format!("{} in {}.", windows.len(), layout));

        // Window details
        for (i, window) in windows.iter().enumerate() {
            if let Some(toplevel) = window.toplevel() {
                let (app_id, title) = wl_compositor::with_states(toplevel.wl_surface(), |states| {
                    let attrs = states.data_map.get::<XdgToplevelSurfaceData>().unwrap().lock().unwrap();
                    (attrs.app_id.clone().unwrap_or_default(), attrs.title.clone().unwrap_or_default())
                });

                let wid = self.semantic_bridge.as_ref()
                    .and_then(|b| b.window_id_for_surface(toplevel.wl_surface()))
                    .unwrap_or(0);

                let geo = self.space.element_geometry(window);
                let position = if i == 0 && windows.len() > 1 { "master" } else if windows.len() > 1 { "stack" } else { "fullscreen" };
                let is_focused = focused_id == Some(wid);

                let size_str = geo.map(|g| format!("{}x{}", g.size.w, g.size.h)).unwrap_or_default();

                let title_str = if title.is_empty() { app_id.clone() } else { title };
                let focus_str = if is_focused { " (focused)" } else { "" };

                desc.push(format!("  Window {} [{}]: \"{}\" — {}, {}{}", wid, position, title_str, size_str, app_id, focus_str));
            }
        }

        desc.push(format!("Gap: {}px. Terminal: {}.", self.config.layout.gap, self.config.terminal));

        desc.join("\n")
    }

    /// Suggest actions the AI agent could take based on current state.
    pub fn suggest_actions(&self) -> Vec<serde_json::Value> {
        let windows: Vec<_> = self.space.elements().collect();
        let mut suggestions = Vec::new();

        if windows.is_empty() {
            suggestions.push(serde_json::json!({
                "action": "window.spawn",
                "params": {"command": &self.config.terminal},
                "reason": "No windows open — spawn a terminal to get started"
            }));
        }

        if windows.len() == 1 {
            suggestions.push(serde_json::json!({
                "action": "window.spawn",
                "params": {"command": &self.config.terminal},
                "reason": "Only 1 window — spawn another for side-by-side work"
            }));
        }

        if windows.len() >= 2 {
            suggestions.push(serde_json::json!({
                "action": "scene.screenshot",
                "reason": "Multiple windows open — take a screenshot to see current state"
            }));
        }

        let focused = self.seat.get_keyboard().unwrap().current_focus();
        if focused.is_none() && !windows.is_empty() {
            suggestions.push(serde_json::json!({
                "action": "window.focus",
                "params": {"window_id": 1},
                "reason": "No window is focused — focus one to interact with it"
            }));
        }

        if windows.len() > 3 {
            suggestions.push(serde_json::json!({
                "action": "layout.set_ratio",
                "params": {"ratio": 0.5},
                "reason": "Many windows — consider adjusting layout ratio"
            }));
        }

        suggestions
    }

    /// Get a full status overview of the compositor.
    pub fn get_status(&self) -> serde_json::Value {
        let windows: Vec<_> = self.space.elements().collect();
        let focused = self.seat.get_keyboard().unwrap().current_focus();

        let focused_id = focused.and_then(|surface| {
            self.semantic_bridge.as_ref()
                .and_then(|b| b.window_id_for_surface(&surface))
        });

        let uptime = self.start_time.elapsed().as_secs();

        serde_json::json!({
            "version": env!("CARGO_PKG_VERSION"),
            "uptime_seconds": uptime,
            "window_count": windows.len(),
            "focused_window_id": focused_id,
            "backend": if matches!(self.backend_data, BackendData::Winit(_)) { "winit" } else { "udev" },
            "socket": self.socket_name,
            "config": {
                "gap": self.config.layout.gap,
                "outer_gap": self.config.layout.outer_gap,
                "master_ratio": self.config.layout.master_ratio,
                "terminal": self.config.terminal,
            },
        })
    }

    /// Take an annotated screenshot — raw screenshot with window boundaries and labels overlaid.
    /// This is the "Set of Marks" approach: AI agents with vision can see both content AND structure.
    pub fn take_annotated_screenshot(&mut self) -> Result<String, String> {
        let BackendData::Winit(ref mut winit_data) = self.backend_data else {
            return Err("annotated screenshot only on winit backend".into());
        };

        use smithay::reexports::glow::{self, HasContext};

        let size = winit_data.backend.window_size();
        let w = size.w as u32;
        let h = size.h as u32;

        // Read pixels
        let renderer = winit_data.backend.renderer();
        let pixels = renderer.with_context(|gl| {
            let mut buf = vec![0u8; (w * h * 4) as usize];
            unsafe {
                gl.read_pixels(0, 0, w as i32, h as i32, glow::RGBA, glow::UNSIGNED_BYTE,
                    glow::PixelPackData::Slice(Some(&mut buf)));
            }
            buf
        }).map_err(|e| format!("GL error: {:?}", e))?;

        // Flip vertically
        let row_bytes = (w * 4) as usize;
        let mut flipped = vec![0u8; pixels.len()];
        for y in 0..h as usize {
            let src = &pixels[y * row_bytes..(y + 1) * row_bytes];
            let dst = &mut flipped[(h as usize - 1 - y) * row_bytes..(h as usize - y) * row_bytes];
            dst.copy_from_slice(src);
        }

        // Draw annotations on the image
        let windows: Vec<_> = self.space.elements().cloned().collect();
        for window in &windows {
            if let Some(geo) = self.space.element_geometry(window) {
                let (title, wid) = window.toplevel().map(|t| {
                    let title = wl_compositor::with_states(t.wl_surface(), |states| {
                        states.data_map.get::<XdgToplevelSurfaceData>()
                            .unwrap().lock().unwrap()
                            .title.clone().unwrap_or_default()
                    });
                    let wid = self.semantic_bridge.as_ref()
                        .and_then(|b| b.window_id_for_surface(t.wl_surface()))
                        .unwrap_or(0);
                    (title, wid)
                }).unwrap_or_default();

                let x1 = geo.loc.x.max(0) as u32;
                let y1 = geo.loc.y.max(0) as u32;
                let x2 = ((geo.loc.x + geo.size.w) as u32).min(w - 1);
                let y2 = ((geo.loc.y + geo.size.h) as u32).min(h - 1);

                // Draw border rectangle (bright green)
                let color = [0u8, 255, 100, 255];
                for x in x1..=x2 {
                    for t in 0..2u32 { // 2px border
                        if y1 + t < h { set_pixel(&mut flipped, w, x, y1 + t, &color); }
                        if y2 >= t && y2 - t < h { set_pixel(&mut flipped, w, x, y2 - t, &color); }
                    }
                }
                for y in y1..=y2 {
                    for t in 0..2u32 {
                        if x1 + t < w { set_pixel(&mut flipped, w, x1 + t, y, &color); }
                        if x2 >= t && x2 - t < w { set_pixel(&mut flipped, w, x2 - t, y, &color); }
                    }
                }

                // Draw label background (top-left corner)
                let label = format!("[{}] {}", wid, title);
                let label_w = (label.len() as u32 * 7).min(x2 - x1);
                let label_h = 16u32;
                for ly in 0..label_h {
                    for lx in 0..label_w {
                        let px = x1 + lx;
                        let py = y1 + ly;
                        if px < w && py < h {
                            set_pixel(&mut flipped, w, px, py, &[0, 0, 0, 200]);
                        }
                    }
                }
            }
        }

        // Encode as PNG
        let mut png_data = Vec::new();
        let encoder = image::codecs::png::PngEncoder::new(&mut png_data);
        image::ImageEncoder::write_image(encoder, &flipped, w, h, image::ExtendedColorType::Rgba8)
            .map_err(|e| format!("PNG error: {e}"))?;

        Ok(base64::engine::general_purpose::STANDARD.encode(&png_data))
    }

    /// Check if a wait condition is met (window exists with matching title/app_id/count).
    pub fn check_wait_condition(
        &self,
        title: Option<&str>,
        app_id: Option<&str>,
        count: Option<usize>,
    ) -> bool {
        let windows: Vec<_> = self.space.elements().collect();

        // Check window count
        if let Some(expected_count) = count {
            if windows.len() < expected_count {
                return false;
            }
        }

        // Check title/app_id match
        if title.is_some() || app_id.is_some() {
            for window in &windows {
                if let Some(toplevel) = window.toplevel() {
                    let (win_app, win_title) = wl_compositor::with_states(toplevel.wl_surface(), |states| {
                        let attrs = states.data_map.get::<XdgToplevelSurfaceData>().unwrap().lock().unwrap();
                        (
                            attrs.app_id.clone().unwrap_or_default(),
                            attrs.title.clone().unwrap_or_default(),
                        )
                    });

                    let title_match = title.map(|t| win_title.contains(t)).unwrap_or(true);
                    let app_match = app_id.map(|a| win_app.contains(a)).unwrap_or(true);

                    if title_match && app_match {
                        return true;
                    }
                }
            }
            return false;
        }

        true
    }

    /// Get recent semantic events (for scene.diff).
    pub fn get_recent_events(&mut self) -> Vec<aulinx_semantic::diff::SemanticEvent> {
        if let Some(ref mut bridge) = self.semantic_bridge {
            bridge.drain_events()
        } else {
            Vec::new()
        }
    }

    /// Query what window is at the given coordinates.
    pub fn element_at(&self, x: f64, y: f64) -> serde_json::Value {
        if let Some((window, loc)) = self.space.element_under((x, y)) {
            let (app_id, title) = window.toplevel().map(|t| {
                wl_compositor::with_states(t.wl_surface(), |states| {
                    let attrs = states.data_map.get::<XdgToplevelSurfaceData>().unwrap().lock().unwrap();
                    (
                        attrs.app_id.clone().unwrap_or_default(),
                        attrs.title.clone().unwrap_or_default(),
                    )
                })
            }).unwrap_or_default();

            let window_id = window.toplevel().and_then(|t| {
                self.semantic_bridge.as_ref()
                    .and_then(|b| b.window_id_for_surface(t.wl_surface()))
            }).unwrap_or(0);

            let geo = self.space.element_geometry(&window);

            serde_json::json!({
                "window_id": window_id,
                "app_id": app_id,
                "title": title,
                "position": {"x": loc.x, "y": loc.y},
                "geometry": geo.map(|g| serde_json::json!({
                    "x": g.loc.x, "y": g.loc.y,
                    "width": g.size.w, "height": g.size.h,
                })),
            })
        } else {
            serde_json::json!(null)
        }
    }

    /// Take a screenshot of the current compositor output (winit backend only).
    pub fn take_screenshot(&mut self) -> Result<String, String> {
        let BackendData::Winit(ref mut winit_data) = self.backend_data else {
            return Err("screenshot only supported on winit backend".into());
        };

        let size = winit_data.backend.window_size();
        let w = size.w as u32;
        let h = size.h as u32;

        // Read pixels from the renderer's current framebuffer
        use smithay::reexports::glow::{self, HasContext};

        let renderer = winit_data.backend.renderer();
        let pixels = renderer.with_context(|gl| {
            let mut buf = vec![0u8; (w * h * 4) as usize];
            unsafe {
                gl.read_pixels(
                    0, 0,
                    w as i32, h as i32,
                    glow::RGBA,
                    glow::UNSIGNED_BYTE,
                    glow::PixelPackData::Slice(Some(&mut buf)),
                );
            }
            buf
        }).map_err(|e| format!("GL error: {:?}", e))?;

        // Flip vertically (OpenGL reads bottom-up)
        let row_bytes = (w * 4) as usize;
        let mut flipped = vec![0u8; pixels.len()];
        for y in 0..h as usize {
            let src_row = &pixels[y * row_bytes..(y + 1) * row_bytes];
            let dst_row = &mut flipped[(h as usize - 1 - y) * row_bytes..(h as usize - y) * row_bytes];
            dst_row.copy_from_slice(src_row);
        }

        // Encode as PNG
        let mut png_data = Vec::new();
        let encoder = image::codecs::png::PngEncoder::new(&mut png_data);
        image::ImageEncoder::write_image(
            encoder,
            &flipped,
            w, h,
            image::ExtendedColorType::Rgba8,
        ).map_err(|e| format!("PNG encode error: {e}"))?;

        // Base64 encode
        Ok(base64::engine::general_purpose::STANDARD.encode(&png_data))
    }

    /// Find a compositor Window by its semantic bridge ID.
    pub fn find_window_by_semantic_id(&self, window_id: u64) -> Result<Window, String> {
        let bridge = self.semantic_bridge.as_ref()
            .ok_or_else(|| "no semantic bridge".to_string())?;

        for window in self.space.elements() {
            if let Some(toplevel) = window.toplevel() {
                if bridge.window_id_for_surface(toplevel.wl_surface()) == Some(window_id) {
                    return Ok(window.clone());
                }
            }
        }
        Err(format!("window_id {window_id} not found"))
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
        let window = Window::new_wayland_window(surface.clone());
        self.space.map_element(window, (0, 0), false);

        // Read real app_id and title from client-set attributes
        let (app_id, title) = wl_compositor::with_states(surface.wl_surface(), |states| {
            let attrs = states.data_map.get::<XdgToplevelSurfaceData>().unwrap().lock().unwrap();
            (
                attrs.app_id.clone().unwrap_or_default(),
                attrs.title.clone().unwrap_or_default(),
            )
        });

        // Feed semantic bridge
        if let Some(ref mut bridge) = self.semantic_bridge {
            bridge.window_opened(&mut self.scene_graph, surface.wl_surface(), &app_id, &title);
        }

        self.relayout();
        tracing::info!("New toplevel mapped: app={app_id} title={title}");
    }

    fn app_id_changed(&mut self, surface: ToplevelSurface) {
        let (app_id, title) = wl_compositor::with_states(surface.wl_surface(), |states| {
            let attrs = states.data_map.get::<XdgToplevelSurfaceData>().unwrap().lock().unwrap();
            (
                attrs.app_id.clone().unwrap_or_default(),
                attrs.title.clone().unwrap_or_default(),
            )
        });
        if let Some(ref mut bridge) = self.semantic_bridge {
            bridge.window_title_changed(&mut self.scene_graph, surface.wl_surface(), &app_id, &title);
        }
        tracing::debug!("App ID changed: {app_id}");
    }

    fn title_changed(&mut self, surface: ToplevelSurface) {
        let (app_id, title) = wl_compositor::with_states(surface.wl_surface(), |states| {
            let attrs = states.data_map.get::<XdgToplevelSurfaceData>().unwrap().lock().unwrap();
            (
                attrs.app_id.clone().unwrap_or_default(),
                attrs.title.clone().unwrap_or_default(),
            )
        });
        if let Some(ref mut bridge) = self.semantic_bridge {
            bridge.window_title_changed(&mut self.scene_graph, surface.wl_surface(), &app_id, &title);
        }
        tracing::debug!("Title changed: {title}");
    }

    fn toplevel_destroyed(&mut self, surface: ToplevelSurface) {
        // Notify semantic bridge before unmapping
        if let Some(ref mut bridge) = self.semantic_bridge {
            bridge.window_closed(&mut self.scene_graph, surface.wl_surface());
        }

        // Collect first to avoid borrow conflict
        let to_remove: Vec<Window> = self.space.elements()
            .filter(|w| w.toplevel().map(|t| t.wl_surface() == surface.wl_surface()).unwrap_or(false))
            .cloned()
            .collect();
        for window in to_remove {
            self.space.unmap_elem(&window);
        }
        self.relayout();
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
    fn focus_changed(&mut self, _seat: &Seat<Self>, target: Option<&WlSurface>) {
        if let Some(ref mut bridge) = self.semantic_bridge {
            if let Some(surface) = target {
                if let Some(id) = bridge.window_id_for_surface(surface) {
                    bridge.window_focused(&mut self.scene_graph, surface);
                    tracing::debug!("Focus changed to window {id}");
                }
            }
        }
    }
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

impl PrimarySelectionHandler for AulinxState {
    fn primary_selection_state(&mut self) -> &mut PrimarySelectionState {
        &mut self.primary_selection_state
    }
}

impl smithay::wayland::buffer::BufferHandler for AulinxState {
    fn buffer_destroyed(&mut self, _buffer: &smithay::reexports::wayland_server::protocol::wl_buffer::WlBuffer) {}
}

impl smithay::wayland::output::OutputHandler for AulinxState {}

impl XdgActivationHandler for AulinxState {
    fn activation_state(&mut self) -> &mut XdgActivationState {
        &mut self.xdg_activation_state
    }

    fn request_activation(
        &mut self,
        _token: XdgActivationToken,
        _token_data: XdgActivationTokenData,
        _surface: WlSurface,
    ) {
        // TODO: bring the requesting surface to focus
    }
}

impl FractionalScaleHandler for AulinxState {
    fn new_fractional_scale(&mut self, _surface: WlSurface) {}
}

impl WlrLayerShellHandler for AulinxState {
    fn shell_state(&mut self) -> &mut WlrLayerShellState {
        &mut self.layer_shell_state
    }

    fn new_layer_surface(
        &mut self,
        surface: LayerSurface,
        _output: Option<smithay::reexports::wayland_server::protocol::wl_output::WlOutput>,
        _layer: Layer,
        namespace: String,
    ) {
        // Send initial configure to layer surface
        surface.send_configure();
        tracing::info!("Layer surface: namespace={namespace}");
    }
}

impl XdgDecorationHandler for AulinxState {
    fn new_decoration(&mut self, toplevel: ToplevelSurface) {
        toplevel.with_pending_state(|state| {
            state.decoration_mode = Some(DecorationMode::ServerSide);
        });
        toplevel.send_configure();
    }

    fn request_mode(&mut self, toplevel: ToplevelSurface, mode: DecorationMode) {
        toplevel.with_pending_state(|state| {
            state.decoration_mode = Some(mode);
        });
        toplevel.send_configure();
    }

    fn unset_mode(&mut self, toplevel: ToplevelSurface) {
        toplevel.with_pending_state(|state| {
            state.decoration_mode = Some(DecorationMode::ServerSide);
        });
        toplevel.send_configure();
    }
}

// ---- Helpers ----

/// Set a pixel in an RGBA buffer with alpha blending.
fn set_pixel(buf: &mut [u8], width: u32, x: u32, y: u32, color: &[u8; 4]) {
    let idx = ((y * width + x) * 4) as usize;
    if idx + 3 < buf.len() {
        let alpha = color[3] as f32 / 255.0;
        buf[idx] = (color[0] as f32 * alpha + buf[idx] as f32 * (1.0 - alpha)) as u8;
        buf[idx + 1] = (color[1] as f32 * alpha + buf[idx + 1] as f32 * (1.0 - alpha)) as u8;
        buf[idx + 2] = (color[2] as f32 * alpha + buf[idx + 2] as f32 * (1.0 - alpha)) as u8;
        buf[idx + 3] = 255;
    }
}

// ---- Delegates ----
delegate_compositor!(AulinxState);
delegate_xdg_shell!(AulinxState);
delegate_shm!(AulinxState);
delegate_seat!(AulinxState);
delegate_data_device!(AulinxState);
delegate_output!(AulinxState);
smithay::delegate_xdg_decoration!(AulinxState);
smithay::delegate_primary_selection!(AulinxState);
smithay::delegate_xdg_activation!(AulinxState);
smithay::delegate_fractional_scale!(AulinxState);
smithay::delegate_layer_shell!(AulinxState);
smithay::delegate_viewporter!(AulinxState);
