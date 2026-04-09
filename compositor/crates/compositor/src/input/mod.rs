//! Input handling — dispatch keyboard/pointer events to clients.

use smithay::backend::input::{
    AbsolutePositionEvent, Axis, AxisSource, ButtonState, Event, InputBackend, InputEvent,
    KeyState, KeyboardKeyEvent, PointerAxisEvent, PointerButtonEvent,
    PointerMotionAbsoluteEvent,
};
use smithay::desktop::WindowSurfaceType;
use smithay::input::keyboard::FilterResult;
use smithay::input::pointer::{AxisFrame, ButtonEvent, MotionEvent};
use smithay::reexports::wayland_server::protocol::wl_surface::WlSurface;
use smithay::utils::SERIAL_COUNTER;

use crate::state::AulinxState;

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

        let action = keyboard.input::<bool, _>(
            self,
            keycode,
            key_state,
            serial,
            time,
            |_state, modifiers, keysym| {
                if key_state != KeyState::Pressed || !modifiers.logo {
                    return FilterResult::Forward;
                }
                let raw = keysym.modified_sym().raw();
                match raw {
                    0xff0d => FilterResult::Intercept(true), // Super+Return
                    0xff1b => FilterResult::Intercept(false), // Super+Escape = quit
                    _ => FilterResult::Forward,
                }
            },
        );

        if let Some(intercept) = action {
            if intercept {
                // Super+Return: open terminal
                std::process::Command::new("foot")
                    .env("WAYLAND_DISPLAY", &self.socket_name)
                    .spawn()
                    .ok();
            } else {
                // Super+Escape: quit
                self.loop_signal.stop();
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
