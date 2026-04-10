//! AI virtual input injection — synthesize keyboard events for focused clients.

use smithay::backend::input::KeyState;
use smithay::input::keyboard::{xkb, FilterResult, Keycode, Keysym};
use smithay::utils::SERIAL_COUNTER;

use crate::state::AulinxState;

impl AulinxState {
    /// Inject a text string as a sequence of key press/release events.
    pub fn inject_text(&mut self, text: &str) -> Result<(), String> {
        let keyboard = self.seat.get_keyboard().unwrap();

        for ch in text.chars() {
            let keysym = xkb::utf32_to_keysym(ch as u32);
            if keysym.raw() == 0 {
                return Err(format!("no keysym for char '{ch}'"));
            }

            // Find keycode by scanning the keymap (checks all levels for shifted chars)
            let result = keyboard.with_xkb_state(self, |ctx| {
                let xkb_guard = ctx.xkb().lock().unwrap();
                let keymap = unsafe { xkb_guard.keymap() };
                find_keycode_for_keysym_any_level(keymap, keysym)
            });

            let (keycode, needs_shift) = result.ok_or_else(|| {
                format!("no keycode for '{ch}' (keysym {})", xkb::keysym_get_name(keysym))
            })?;

            let time = self.start_time.elapsed().as_millis() as u32;

            // If needs shift, press Shift first
            if needs_shift {
                let shift_keycode = keyboard.with_xkb_state(self, |ctx| {
                    let xkb_guard = ctx.xkb().lock().unwrap();
                    let keymap = unsafe { xkb_guard.keymap() };
                    find_keycode_for_keysym(keymap, xkb::keysym_from_name("Shift_L", xkb::KEYSYM_NO_FLAGS))
                }).ok_or("no keycode for Shift")?;

                let serial = SERIAL_COUNTER.next_serial();
                keyboard.input::<(), _>(self, shift_keycode, KeyState::Pressed, serial, time, |_, _, _| {
                    FilterResult::Forward
                });
            }

            // Press key
            let serial = SERIAL_COUNTER.next_serial();
            keyboard.input::<(), _>(self, keycode, KeyState::Pressed, serial, time, |_, _, _| {
                FilterResult::Forward
            });
            // Release key
            let serial = SERIAL_COUNTER.next_serial();
            keyboard.input::<(), _>(self, keycode, KeyState::Released, serial, time, |_, _, _| {
                FilterResult::Forward
            });

            // Release shift if needed
            if needs_shift {
                let shift_keycode = keyboard.with_xkb_state(self, |ctx| {
                    let xkb_guard = ctx.xkb().lock().unwrap();
                    let keymap = unsafe { xkb_guard.keymap() };
                    find_keycode_for_keysym(keymap, xkb::keysym_from_name("Shift_L", xkb::KEYSYM_NO_FLAGS))
                }).ok_or("no keycode for Shift")?;

                let serial = SERIAL_COUNTER.next_serial();
                keyboard.input::<(), _>(self, shift_keycode, KeyState::Released, serial, time, |_, _, _| {
                    FilterResult::Forward
                });
            }
        }

        tracing::info!("input.type: injected {} chars", text.len());
        Ok(())
    }

    /// Inject a key combo (e.g. "ctrl+a", "super+return", "shift+tab").
    pub fn inject_key_combo(&mut self, combo: &str) -> Result<(), String> {
        let keyboard = self.seat.get_keyboard().unwrap();

        let parts: Vec<&str> = combo.split('+').map(|s| s.trim()).collect();
        if parts.is_empty() {
            return Err("empty combo".into());
        }

        // Resolve each part to a keycode
        let mut keycodes = Vec::new();
        for part in &parts {
            let keysym = name_to_keysym(part);
            if keysym.raw() == 0 {
                return Err(format!("unknown key name: '{part}'"));
            }

            let keycode = keyboard.with_xkb_state(self, |ctx| {
                let xkb_guard = ctx.xkb().lock().unwrap();
                let keymap = unsafe { xkb_guard.keymap() };
                find_keycode_for_keysym(keymap, keysym)
            });

            let keycode = keycode.ok_or_else(|| {
                format!("no keycode for '{part}' (keysym {})", xkb::keysym_get_name(keysym))
            })?;
            keycodes.push(keycode);
        }

        let time = self.start_time.elapsed().as_millis() as u32;

        // Press all keys in order
        for &keycode in &keycodes {
            let serial = SERIAL_COUNTER.next_serial();
            keyboard.input::<(), _>(self, keycode, KeyState::Pressed, serial, time, |_, _, _| {
                FilterResult::Forward
            });
        }

        // Release in reverse order
        for &keycode in keycodes.iter().rev() {
            let serial = SERIAL_COUNTER.next_serial();
            keyboard.input::<(), _>(self, keycode, KeyState::Released, serial, time, |_, _, _| {
                FilterResult::Forward
            });
        }

        tracing::info!("input.key: injected combo '{combo}'");
        Ok(())
    }

    /// Inject a mouse click at the given coordinates.
    pub fn inject_click(&mut self, x: f64, y: f64, button: u32) -> Result<(), String> {
        use smithay::backend::input::ButtonState;
        use smithay::input::pointer::{ButtonEvent, MotionEvent};
        use smithay::desktop::WindowSurfaceType;

        let pointer = self.seat.get_pointer().unwrap();
        let keyboard = self.seat.get_keyboard().unwrap();
        let serial = SERIAL_COUNTER.next_serial();
        let time = self.start_time.elapsed().as_millis() as u32;

        // Map button number to evdev button code (BTN_LEFT=0x110, BTN_RIGHT=0x111, BTN_MIDDLE=0x112)
        let button_code = match button {
            1 => 0x110, // left
            2 => 0x112, // middle
            3 => 0x111, // right
            n => return Err(format!("unknown button {n}, use 1=left, 2=middle, 3=right")),
        };

        // Move pointer to position
        let under = self.space.element_under((x, y));
        let focus = under.and_then(|(window, loc)| {
            window
                .surface_under(
                    (x - loc.x as f64, y - loc.y as f64),
                    WindowSurfaceType::ALL,
                )
                .map(|(surface, surface_loc)| {
                    let point = smithay::utils::Point::<f64, smithay::utils::Logical>::from((
                        (loc.x + surface_loc.x) as f64,
                        (loc.y + surface_loc.y) as f64,
                    ));
                    (surface, point)
                })
        });

        // Move pointer
        pointer.motion(
            self,
            focus.clone(),
            &MotionEvent {
                location: smithay::utils::Point::from((x, y)),
                serial,
                time,
            },
        );
        pointer.frame(self);

        // Click-to-focus
        if let Some((window, _)) = self.space.element_under((x, y)) {
            let window = window.clone();
            self.space.raise_element(&window, true);
            if let Some(toplevel) = window.toplevel() {
                let serial = SERIAL_COUNTER.next_serial();
                keyboard.set_focus(self, Some(toplevel.wl_surface().clone()), serial);
            }
        }

        // Press
        let serial = SERIAL_COUNTER.next_serial();
        pointer.button(
            self,
            &ButtonEvent { button: button_code, state: ButtonState::Pressed, serial, time },
        );
        pointer.frame(self);

        // Release
        let serial = SERIAL_COUNTER.next_serial();
        pointer.button(
            self,
            &ButtonEvent { button: button_code, state: ButtonState::Released, serial, time: time + 50 },
        );
        pointer.frame(self);

        tracing::info!("input.click: ({x}, {y}) button={button}");
        Ok(())
    }

    /// Inject a drag operation from (x1,y1) to (x2,y2).
    pub fn inject_drag(&mut self, x1: f64, y1: f64, x2: f64, y2: f64, button: u32) -> Result<(), String> {
        use smithay::backend::input::ButtonState;
        use smithay::input::pointer::{ButtonEvent, MotionEvent};
        use smithay::desktop::WindowSurfaceType;

        let pointer = self.seat.get_pointer().unwrap();
        let time = self.start_time.elapsed().as_millis() as u32;

        let button_code = match button {
            1 => 0x110,
            2 => 0x112,
            3 => 0x111,
            n => return Err(format!("unknown button {n}")),
        };

        // Helper to compute focus at position
        let compute_focus = |space: &smithay::desktop::Space<smithay::desktop::Window>, x: f64, y: f64| {
            space.element_under((x, y)).and_then(|(window, loc)| {
                window
                    .surface_under(
                        (x - loc.x as f64, y - loc.y as f64),
                        WindowSurfaceType::ALL,
                    )
                    .map(|(surface, surface_loc)| {
                        let point = smithay::utils::Point::<f64, smithay::utils::Logical>::from((
                            (loc.x + surface_loc.x) as f64,
                            (loc.y + surface_loc.y) as f64,
                        ));
                        (surface, point)
                    })
            })
        };

        // Move to start position
        let focus = compute_focus(&self.space, x1, y1);
        let serial = SERIAL_COUNTER.next_serial();
        pointer.motion(
            self,
            focus,
            &MotionEvent {
                location: smithay::utils::Point::from((x1, y1)),
                serial,
                time,
            },
        );
        pointer.frame(self);

        // Press
        let serial = SERIAL_COUNTER.next_serial();
        pointer.button(
            self,
            &ButtonEvent { button: button_code, state: ButtonState::Pressed, serial, time },
        );
        pointer.frame(self);

        // Move to end position (interpolate a few steps for smooth drag)
        let steps = 5;
        for i in 1..=steps {
            let t = i as f64 / steps as f64;
            let x = x1 + (x2 - x1) * t;
            let y = y1 + (y2 - y1) * t;
            let focus = compute_focus(&self.space, x, y);
            let serial = SERIAL_COUNTER.next_serial();
            pointer.motion(
                self,
                focus,
                &MotionEvent {
                    location: smithay::utils::Point::from((x, y)),
                    serial,
                    time: time + (i as u32 * 16),
                },
            );
            pointer.frame(self);
        }

        // Release
        let serial = SERIAL_COUNTER.next_serial();
        pointer.button(
            self,
            &ButtonEvent { button: button_code, state: ButtonState::Released, serial, time: time + 100 },
        );
        pointer.frame(self);

        tracing::info!("input.drag: ({x1},{y1}) -> ({x2},{y2}) button={button}");
        Ok(())
    }

    /// Spawn an application inside the compositor.
    pub fn spawn_app(&self, command: &str, args: &[String]) -> Result<u32, String> {
        let child = std::process::Command::new(command)
            .args(args)
            .env("WAYLAND_DISPLAY", &self.socket_name)
            .env("AULINX_COMPOSITOR", "1")
            .env("AULINX_VERSION", env!("CARGO_PKG_VERSION"))
            .env("AULINX_SOCKET", crate::ipc::ipc_socket_path().to_string_lossy().to_string())
            .spawn()
            .map_err(|e| format!("failed to spawn '{}': {}", command, e))?;

        let pid = child.id();
        tracing::info!("window.spawn: {} (pid={pid})", command);
        Ok(pid)
    }

    /// Inject a pointer move to the given coordinates.
    pub fn inject_move(&mut self, x: f64, y: f64) -> Result<(), String> {
        use smithay::input::pointer::MotionEvent;
        use smithay::desktop::WindowSurfaceType;

        let pointer = self.seat.get_pointer().unwrap();
        let serial = SERIAL_COUNTER.next_serial();
        let time = self.start_time.elapsed().as_millis() as u32;

        let under = self.space.element_under((x, y));
        let focus = under.and_then(|(window, loc)| {
            window
                .surface_under(
                    (x - loc.x as f64, y - loc.y as f64),
                    WindowSurfaceType::ALL,
                )
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
                location: smithay::utils::Point::from((x, y)),
                serial,
                time,
            },
        );
        pointer.frame(self);

        tracing::debug!("input.move: ({x}, {y})");
        Ok(())
    }

    /// Inject a scroll event at the given coordinates.
    pub fn inject_scroll(&mut self, x: f64, y: f64, dx: f64, dy: f64) -> Result<(), String> {
        use smithay::backend::input::Axis;
        use smithay::input::pointer::{AxisFrame, MotionEvent};
        use smithay::desktop::WindowSurfaceType;

        let pointer = self.seat.get_pointer().unwrap();
        let serial = SERIAL_COUNTER.next_serial();
        let time = self.start_time.elapsed().as_millis() as u32;

        // Move pointer to position first
        let under = self.space.element_under((x, y));
        let focus = under.and_then(|(window, loc)| {
            window
                .surface_under(
                    (x - loc.x as f64, y - loc.y as f64),
                    WindowSurfaceType::ALL,
                )
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
                location: smithay::utils::Point::from((x, y)),
                serial,
                time,
            },
        );
        pointer.frame(self);

        // Send scroll
        let mut frame = AxisFrame::new(time);
        if dx != 0.0 {
            frame = frame.value(Axis::Horizontal, dx);
        }
        if dy != 0.0 {
            frame = frame.value(Axis::Vertical, dy);
        }
        pointer.axis(self, frame);
        pointer.frame(self);

        tracing::info!("input.scroll: ({x}, {y}) dx={dx} dy={dy}");
        Ok(())
    }
}

/// Map a human-readable key name to a keysym.
fn name_to_keysym(name: &str) -> Keysym {
    // Normalize common aliases
    let xkb_name = match name.to_lowercase().as_str() {
        "ctrl" | "control" => "Control_L",
        "alt" => "Alt_L",
        "shift" => "Shift_L",
        "super" | "win" | "meta" | "logo" => "Super_L",
        "return" | "enter" => "Return",
        "escape" | "esc" => "Escape",
        "tab" => "Tab",
        "backspace" => "BackSpace",
        "delete" | "del" => "Delete",
        "space" => "space",
        "up" => "Up",
        "down" => "Down",
        "left" => "Left",
        "right" => "Right",
        "home" => "Home",
        "end" => "End",
        "pageup" | "page_up" => "Prior",
        "pagedown" | "page_down" => "Next",
        other => {
            // Single character → keysym from char
            if other.len() == 1 {
                let ch = other.chars().next().unwrap();
                return xkb::utf32_to_keysym(ch as u32);
            }
            // Function keys
            if other.starts_with('f') || other.starts_with('F') {
                if other[1..].parse::<u32>().is_ok() {
                    // Pass through as-is (e.g. "F1" → xkb name "F1")
                    return xkb::keysym_from_name(other, xkb::KEYSYM_NO_FLAGS);
                }
            }
            // Try as-is (xkb name)
            return xkb::keysym_from_name(other, xkb::KEYSYM_NO_FLAGS);
        }
    };
    xkb::keysym_from_name(xkb_name, xkb::KEYSYM_NO_FLAGS)
}

/// Scan the keymap for a keysym at any level. Returns (keycode, needs_shift).
/// Level 0 = unshifted, level 1 = shifted.
fn find_keycode_for_keysym_any_level(keymap: &xkb::Keymap, target: Keysym) -> Option<(Keycode, bool)> {
    let min = keymap.min_keycode();
    let max = keymap.max_keycode();

    // First try level 0 (unshifted)
    for raw in min.raw()..=max.raw() {
        let kc = Keycode::new(raw);
        let num_layouts = keymap.num_layouts_for_key(kc);
        for layout in 0..num_layouts {
            let syms = keymap.key_get_syms_by_level(kc, layout, 0);
            if syms.iter().any(|s| *s == target) {
                return Some((kc, false));
            }
        }
    }

    // Then try level 1 (shifted)
    for raw in min.raw()..=max.raw() {
        let kc = Keycode::new(raw);
        let num_layouts = keymap.num_layouts_for_key(kc);
        for layout in 0..num_layouts {
            let num_levels = keymap.num_levels_for_key(kc, layout);
            if num_levels > 1 {
                let syms = keymap.key_get_syms_by_level(kc, layout, 1);
                if syms.iter().any(|s| *s == target) {
                    return Some((kc, true));
                }
            }
        }
    }

    None
}

/// Scan the keymap to find a keycode that produces the given keysym at layout 0, level 0.
fn find_keycode_for_keysym(keymap: &xkb::Keymap, target: Keysym) -> Option<Keycode> {
    let min = keymap.min_keycode();
    let max = keymap.max_keycode();

    for raw in min.raw()..=max.raw() {
        let kc = Keycode::new(raw);
        let num_layouts = keymap.num_layouts_for_key(kc);
        for layout in 0..num_layouts {
            let syms = keymap.key_get_syms_by_level(kc, layout, 0);
            if syms.iter().any(|s| *s == target) {
                return Some(kc);
            }
        }
    }
    None
}
