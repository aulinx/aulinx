//! Input handling — dispatch keyboard/pointer events to clients.

pub mod injection;

use smithay::backend::input::{
    AbsolutePositionEvent, Axis, ButtonState, Event, InputBackend, InputEvent,
    KeyState, KeyboardKeyEvent, PointerAxisEvent, PointerButtonEvent,
};
use smithay::desktop::WindowSurfaceType;
use smithay::input::keyboard::FilterResult;
use smithay::input::pointer::{AxisFrame, ButtonEvent, MotionEvent};
use smithay::reexports::wayland_server::protocol::wl_surface::WlSurface;
use smithay::utils::SERIAL_COUNTER;

use crate::state::AulinxState;

/// Compositor keybinding actions.
enum KeyAction {
    SpawnTerminal,
    Quit,
    FocusNext,
    FocusPrev,
    CloseFocused,
    SwapMaster,
    FocusIndex(usize),
    ToggleFullscreen,
    GrowMaster,
    ShrinkMaster,
}

impl AulinxState {
    pub fn process_input_event<B: InputBackend>(&mut self, event: InputEvent<B>) {
        match event {
            InputEvent::Keyboard { event } => self.on_keyboard::<B>(event),
            InputEvent::PointerMotionAbsolute { event } => self.on_pointer_motion_absolute::<B>(event),
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

        let keyboard = self.seat.get_keyboard().unwrap();

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
                if !modifiers.logo {
                    return FilterResult::Forward;
                }

                let raw = keysym.modified_sym().raw();
                match raw {
                    // Super+Return: open terminal
                    0xff0d => FilterResult::Intercept(KeyAction::SpawnTerminal),
                    // Super+Escape: quit
                    0xff1b => FilterResult::Intercept(KeyAction::Quit),
                    // Super+j: focus next window
                    0x006a => FilterResult::Intercept(KeyAction::FocusNext),
                    // Super+k: focus previous window
                    0x006b => FilterResult::Intercept(KeyAction::FocusPrev),
                    // Super+q: close focused window
                    0x0071 if modifiers.shift => FilterResult::Intercept(KeyAction::CloseFocused),
                    // Super+Space: swap focused with master
                    0x0020 => FilterResult::Intercept(KeyAction::SwapMaster),
                    // Super+f: toggle fullscreen
                    0x0066 => FilterResult::Intercept(KeyAction::ToggleFullscreen),
                    // Super+l: grow master
                    0x006c => FilterResult::Intercept(KeyAction::GrowMaster),
                    // Super+h: shrink master
                    0x0068 => FilterResult::Intercept(KeyAction::ShrinkMaster),
                    // Super+1..9: focus window by index
                    0x0031..=0x0039 => FilterResult::Intercept(KeyAction::FocusIndex((raw - 0x0031) as usize)),
                    _ => FilterResult::Forward,
                }
            },
        );

        if let Some(action) = action {
            match action {
                KeyAction::SpawnTerminal => {
                    let terminal = self.config.terminal.clone();
                    std::process::Command::new(&terminal)
                        .env("WAYLAND_DISPLAY", &self.socket_name)
                        .spawn()
                        .ok();
                }
                KeyAction::Quit => {
                    self.loop_signal.stop();
                }
                KeyAction::FocusNext => {
                    self.focus_next_window();
                }
                KeyAction::FocusPrev => {
                    self.focus_prev_window();
                }
                KeyAction::CloseFocused => {
                    let _ = self.close_window(None);
                }
                KeyAction::SwapMaster => {
                    self.swap_with_master();
                }
                KeyAction::FocusIndex(idx) => {
                    self.focus_window_by_index(idx);
                }
                KeyAction::ToggleFullscreen => {
                    self.relayout();
                }
                KeyAction::GrowMaster => {
                    self.config.layout.master_ratio = (self.config.layout.master_ratio + 0.05).min(0.8);
                    self.relayout();
                }
                KeyAction::ShrinkMaster => {
                    self.config.layout.master_ratio = (self.config.layout.master_ratio - 0.05).max(0.2);
                    self.relayout();
                }
            }
        }
    }

    fn on_pointer_motion_absolute<B: InputBackend>(&mut self, event: B::PointerMotionAbsoluteEvent) {
        let Some(output) = self.space.outputs().next().cloned() else { return };
        let Some(output_geo) = self.space.output_geometry(&output) else { return };

        let pos = event.position_transformed(output_geo.size);
        let serial = SERIAL_COUNTER.next_serial();
        let time = Event::time_msec(&event);

        let pointer = self.seat.get_pointer().unwrap();

        let under = self.space.element_under((pos.x, pos.y));
        let focus = under.and_then(|(window, loc)| {
            window
                .surface_under((pos.x - loc.x as f64, pos.y - loc.y as f64), WindowSurfaceType::ALL)
                .map(|(surface, surface_loc)| {
                    let point = smithay::utils::Point::<f64, smithay::utils::Logical>::from((
                        (loc.x + surface_loc.x) as f64,
                        (loc.y + surface_loc.y) as f64,
                    ));
                    (surface, point)
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

        let pointer = self.seat.get_pointer().unwrap();
        let keyboard = self.seat.get_keyboard().unwrap();

        // Click-to-focus
        if button_state == ButtonState::Pressed {
            let pos = pointer.current_location();
            if let Some((window, _)) = self.space.element_under(pos) {
                let window = window.clone();
                self.space.raise_element(&window, true);
                if let Some(toplevel) = window.toplevel() {
                    keyboard.set_focus(self, Some(toplevel.wl_surface().clone()), serial);
                }
            } else {
                keyboard.set_focus(self, Option::<WlSurface>::None, serial);
            }
        }

        pointer.button(
            self,
            &ButtonEvent { button, state: button_state, serial, time },
        );
        pointer.frame(self);
    }

    fn on_pointer_axis<B: InputBackend>(&mut self, event: B::PointerAxisEvent) {
        let pointer = self.seat.get_pointer().unwrap();
        let time = Event::time_msec(&event);

        let mut frame = AxisFrame::new(time).source(event.source());
        if let Some(amount) = event.amount(Axis::Horizontal) {
            frame = frame.value(Axis::Horizontal, amount);
        }
        if let Some(amount) = event.amount(Axis::Vertical) {
            frame = frame.value(Axis::Vertical, amount);
        }

        pointer.axis(self, frame);
        pointer.frame(self);
    }
}
