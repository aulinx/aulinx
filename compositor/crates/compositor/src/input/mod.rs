//! Input handling — physical dispatch and AI virtual injection.

pub mod injection;

use smithay::backend::input::{
    AbsolutePositionEvent, Axis, AxisSource, ButtonState, Event, InputBackend, InputEvent,
    KeyState, KeyboardKeyEvent, PointerAxisEvent, PointerButtonEvent,
    PointerMotionAbsoluteEvent,
};
use smithay::input::keyboard::FilterResult;
use smithay::input::pointer::{AxisFrame, ButtonEvent, MotionEvent};
use smithay::utils::SERIAL_COUNTER;

use crate::state::AulinxState;

/// Actions returned by keybinding checks.
enum KeyAction {
    /// Not a keybinding — forward to client.
    None,
    /// Close the focused window.
    Close,
    /// Open a terminal.
    Terminal,
    /// Toggle focused window floating/tiling.
    ToggleFloat,
    /// Switch to workspace N (0-based).
    Workspace(usize),
    /// Quit the compositor.
    Quit,
}

impl AulinxState {
    /// Process an input event from the backend.
    pub fn process_input_event<B: InputBackend>(&mut self, event: InputEvent<B>) {
        match event {
            InputEvent::Keyboard { event } => self.on_keyboard::<B>(event),
            InputEvent::PointerMotionAbsolute { event } => {
                self.on_pointer_motion_absolute::<B>(event)
            }
            InputEvent::PointerButton { event } => self.on_pointer_button::<B>(event),
            InputEvent::PointerAxis { event } => self.on_pointer_axis::<B>(event),
            _ => {}
        }
    }

    fn on_keyboard<B: InputBackend>(&mut self, event: B::KeyboardKeyEvent) {
        let serial = SERIAL_COUNTER.next_serial();
        let time = Event::time_msec(&event);
        let keycode = event.key_code();
        let key_state = event.state();

        let seat = self.seat.clone();
        let keyboard = seat.get_keyboard().unwrap();

        // We need to check keybindings and potentially act on the state after
        let action = keyboard.input::<KeyAction, _>(
            self,
            keycode,
            key_state,
            serial,
            time,
            |_state, modifiers, keysym| {
                if key_state != KeyState::Pressed {
                    return FilterResult::Forward;
                }

                // Only handle keybindings with Super (logo) modifier
                if !modifiers.logo {
                    return FilterResult::Forward;
                }

                let sym = keysym.modified_sym();
                // Match on raw keysym value (XKB keysym constants)
                let raw = sym.raw();
                match raw {
                    0xff0d => FilterResult::Intercept(KeyAction::Terminal),    // Return
                    0x0071 | 0x0051 => FilterResult::Intercept(KeyAction::Close), // q/Q
                    0x0066 | 0x0046 => FilterResult::Intercept(KeyAction::ToggleFloat), // f/F
                    0xff1b => FilterResult::Intercept(KeyAction::Quit),        // Escape
                    0x0031 => FilterResult::Intercept(KeyAction::Workspace(0)), // 1
                    0x0032 => FilterResult::Intercept(KeyAction::Workspace(1)), // 2
                    0x0033 => FilterResult::Intercept(KeyAction::Workspace(2)), // 3
                    0x0034 => FilterResult::Intercept(KeyAction::Workspace(3)), // 4
                    0x0035 => FilterResult::Intercept(KeyAction::Workspace(4)), // 5
                    0x0036 => FilterResult::Intercept(KeyAction::Workspace(5)), // 6
                    0x0037 => FilterResult::Intercept(KeyAction::Workspace(6)), // 7
                    0x0038 => FilterResult::Intercept(KeyAction::Workspace(7)), // 8
                    0x0039 => FilterResult::Intercept(KeyAction::Workspace(8)), // 9
                    _ => FilterResult::Forward,
                }
            },
        );

        // Act on keybinding result
        if let Some(action) = action {
            match action {
                KeyAction::Terminal => {
                    tracing::info!("Keybinding: open terminal");
                    std::process::Command::new("foot")
                        .env("WAYLAND_DISPLAY", &self.socket_name)
                        .spawn()
                        .ok();
                }
                KeyAction::Close => {
                    tracing::info!("Keybinding: close focused window");
                    self.close_focused();
                }
                KeyAction::ToggleFloat => {
                    tracing::info!("Keybinding: toggle floating");
                    self.toggle_focused_floating();
                }
                KeyAction::Workspace(idx) => {
                    self.switch_workspace(idx);
                }
                KeyAction::Quit => {
                    tracing::info!("Keybinding: quit compositor");
                    self.loop_signal.stop();
                }
                KeyAction::None => {}
            }
        }
    }

    fn on_pointer_motion_absolute<B: InputBackend>(
        &mut self,
        event: B::PointerMotionAbsoluteEvent,
    ) {
        let Some(output) = self.space.outputs().next().cloned() else {
            return;
        };
        let Some(output_geo) = self.space.output_geometry(&output) else {
            return;
        };

        let pos = event.position_transformed(output_geo.size);
        let serial = SERIAL_COUNTER.next_serial();
        let time = Event::time_msec(&event);

        let seat = self.seat.clone();
        let pointer = seat.get_pointer().unwrap();

        // Find surface under pointer
        let under = self.space.element_under((pos.x, pos.y));
        let focus = under.and_then(|(window, loc)| {
            window
                .surface_under(
                    (pos.x - loc.x as f64, pos.y - loc.y as f64),
                    smithay::desktop::WindowSurfaceType::ALL,
                )
                .map(|(surface, surface_loc)| {
                    (
                        surface,
                        smithay::utils::Point::from((
                            (loc.x + surface_loc.x) as f64,
                            (loc.y + surface_loc.y) as f64,
                        )),
                    )
                })
        });

        pointer.motion(
            self,
            focus,
            &MotionEvent {
                location: smithay::utils::Point::from((pos.x, pos.y)),
                serial,
                time,
            },
        );
        pointer.frame(self);
    }

    fn on_pointer_button<B: InputBackend>(&mut self, event: B::PointerButtonEvent) {
        let serial = SERIAL_COUNTER.next_serial();
        let time = Event::time_msec(&event);
        let button = event.button_code();
        let button_state = event.state();

        let seat = self.seat.clone();
        let pointer = seat.get_pointer().unwrap();
        let keyboard = seat.get_keyboard().unwrap();

        // Click-to-focus
        if button_state == ButtonState::Pressed {
            if let Some(pos) = pointer.current_location() {
                if let Some((window, _loc)) = self.space.element_under(pos) {
                    let window = window.clone();
                    self.space.raise_element(&window, true);
                    if let Some(toplevel) = window.toplevel() {
                        keyboard.set_focus(self, Some(toplevel.wl_surface().clone()), serial);
                    }
                    // Update layout engine focus
                    if let Some(&wid) = self.window_ids.get(&window) {
                        self.workspaces
                            .active_workspace_mut()
                            .layout
                            .set_focused(Some(wid));
                        if self.workspaces.active_workspace().layout.is_floating(wid) {
                            self.workspaces
                                .active_workspace_mut()
                                .layout
                                .raise_floating(wid);
                        }
                    }
                } else {
                    // Clicked on empty space — unfocus
                    keyboard.set_focus(self, Option::<WlSurface>::None, serial);
                    self.workspaces
                        .active_workspace_mut()
                        .layout
                        .set_focused(None);
                }
            }
        }

        pointer.button(
            self,
            &ButtonEvent {
                button,
                state: button_state,
                serial,
                time,
            },
        );
        pointer.frame(self);
    }

    fn on_pointer_axis<B: InputBackend>(&mut self, event: B::PointerAxisEvent) {
        let seat = self.seat.clone();
        let pointer = seat.get_pointer().unwrap();
        let time = Event::time_msec(&event);

        let mut frame = AxisFrame::new(time).source(event.source());

        if let Some(amount) = event.amount(Axis::Horizontal) {
            frame = frame.value(Axis::Horizontal, amount);
        }
        if let Some(amount) = event.amount(Axis::Vertical) {
            frame = frame.value(Axis::Vertical, amount);
        }
        if let Some(amount) = event.amount_v120(Axis::Horizontal) {
            frame = frame.v120(Axis::Horizontal, amount as i32);
        }
        if let Some(amount) = event.amount_v120(Axis::Vertical) {
            frame = frame.v120(Axis::Vertical, amount as i32);
        }

        pointer.axis(self, frame);
        pointer.frame(self);
    }
}

use smithay::reexports::wayland_server::protocol::wl_surface::WlSurface;
