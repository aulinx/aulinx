//! AI virtual input injection — input.type, input.key, input.mouse.
//!
//! The compositor synthesizes keyboard and pointer events directly
//! into the focused client. No ydotool, no AT-SPI — the compositor
//! has full authority to inject input.

use smithay::backend::input::{ButtonState, KeyState};
use smithay::input::pointer::{ButtonEvent, MotionEvent};
use smithay::utils::SERIAL_COUNTER;

use crate::state::AulinxState;

/// Key combo parsed from a string like "ctrl+shift+t".
struct KeyCombo {
    modifiers: Vec<u32>, // keycodes for modifier keys
    key: u32,            // keycode for the main key
}

impl AulinxState {
    /// Type text into the focused client by sending key press/release events.
    ///
    /// For each character, finds the corresponding keycode via xkb and
    /// sends press + release. This works for ASCII text. For Unicode,
    /// a virtual keyboard protocol would be better (future improvement).
    pub fn inject_text(&mut self, text: &str) -> Result<(), String> {
        let seat = self.seat.clone();
        let keyboard = seat.get_keyboard().ok_or("no keyboard")?;

        // Check there's a focused surface
        if keyboard.current_focus().is_none() {
            return Err("no focused window".into());
        }

        for ch in text.chars() {
            let keycode = char_to_keycode(ch);
            if keycode == 0 {
                tracing::debug!("No keycode for char '{ch}', skipping");
                continue;
            }

            let serial = SERIAL_COUNTER.next_serial();
            let time = self.start_time.elapsed().as_millis() as u32;

            // Check if shift is needed
            let needs_shift = ch.is_ascii_uppercase() || "!@#$%^&*()_+{}|:\"<>?~".contains(ch);

            if needs_shift {
                // Press shift (keycode 42 = left shift)
                keyboard.input::<(), _>(self, 42, KeyState::Pressed, serial, time, |_, _, _| {
                    smithay::input::keyboard::FilterResult::Forward
                });
            }

            // Press key
            let serial = SERIAL_COUNTER.next_serial();
            keyboard.input::<(), _>(self, keycode, KeyState::Pressed, serial, time, |_, _, _| {
                smithay::input::keyboard::FilterResult::Forward
            });

            // Release key
            let serial = SERIAL_COUNTER.next_serial();
            let time = time + 10;
            keyboard.input::<(), _>(self, keycode, KeyState::Released, serial, time, |_, _, _| {
                smithay::input::keyboard::FilterResult::Forward
            });

            if needs_shift {
                let serial = SERIAL_COUNTER.next_serial();
                keyboard.input::<(), _>(self, 42, KeyState::Released, serial, time, |_, _, _| {
                    smithay::input::keyboard::FilterResult::Forward
                });
            }
        }

        Ok(())
    }

    /// Send a keyboard shortcut like "ctrl+shift+t".
    pub fn inject_key_combo(&mut self, combo: &str) -> Result<(), String> {
        let seat = self.seat.clone();
        let keyboard = seat.get_keyboard().ok_or("no keyboard")?;

        let parsed = parse_key_combo(combo)?;
        let time = self.start_time.elapsed().as_millis() as u32;

        // Press modifiers
        for &modifier in &parsed.modifiers {
            let serial = SERIAL_COUNTER.next_serial();
            keyboard.input::<(), _>(self, modifier, KeyState::Pressed, serial, time, |_, _, _| {
                smithay::input::keyboard::FilterResult::Forward
            });
        }

        // Press main key
        let serial = SERIAL_COUNTER.next_serial();
        keyboard.input::<(), _>(self, parsed.key, KeyState::Pressed, serial, time, |_, _, _| {
            smithay::input::keyboard::FilterResult::Forward
        });

        // Release main key
        let serial = SERIAL_COUNTER.next_serial();
        let time = time + 10;
        keyboard.input::<(), _>(self, parsed.key, KeyState::Released, serial, time, |_, _, _| {
            smithay::input::keyboard::FilterResult::Forward
        });

        // Release modifiers (reverse order)
        for &modifier in parsed.modifiers.iter().rev() {
            let serial = SERIAL_COUNTER.next_serial();
            keyboard.input::<(), _>(self, modifier, KeyState::Released, serial, time, |_, _, _| {
                smithay::input::keyboard::FilterResult::Forward
            });
        }

        Ok(())
    }

    /// Move the pointer to (x, y) and optionally click.
    pub fn inject_mouse(
        &mut self,
        x: f64,
        y: f64,
        button: Option<u32>,
        action: Option<&str>,
    ) -> Result<(), String> {
        let seat = self.seat.clone();
        let pointer = seat.get_pointer().ok_or("no pointer")?;

        let serial = SERIAL_COUNTER.next_serial();
        let time = self.start_time.elapsed().as_millis() as u32;

        // Find surface under target position
        let under = self.space.element_under((x, y));
        let focus = under.and_then(|(window, loc)| {
            window
                .surface_under(
                    (x - loc.x as f64, y - loc.y as f64),
                    smithay::desktop::WindowSurfaceType::ALL,
                )
                .map(|(surface, surface_loc)| {
                    (surface, smithay::utils::Point::from((
                        (loc.x + surface_loc.x) as f64,
                        (loc.y + surface_loc.y) as f64,
                    )))
                })
        });

        // Move pointer
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

        // Click if requested
        if let Some(btn) = button {
            let btn_code = match btn {
                1 => 0x110, // BTN_LEFT
                2 => 0x112, // BTN_MIDDLE
                3 => 0x111, // BTN_RIGHT
                n => n,
            };

            match action.unwrap_or("click") {
                "click" => {
                    // Press
                    let serial = SERIAL_COUNTER.next_serial();
                    pointer.button(
                        self,
                        &ButtonEvent {
                            button: btn_code,
                            state: ButtonState::Pressed,
                            serial,
                            time,
                        },
                    );
                    pointer.frame(self);

                    // Release
                    let serial = SERIAL_COUNTER.next_serial();
                    pointer.button(
                        self,
                        &ButtonEvent {
                            button: btn_code,
                            state: ButtonState::Released,
                            serial,
                            time: time + 50,
                        },
                    );
                    pointer.frame(self);
                }
                "press" => {
                    let serial = SERIAL_COUNTER.next_serial();
                    pointer.button(
                        self,
                        &ButtonEvent {
                            button: btn_code,
                            state: ButtonState::Pressed,
                            serial,
                            time,
                        },
                    );
                    pointer.frame(self);
                }
                "release" => {
                    let serial = SERIAL_COUNTER.next_serial();
                    pointer.button(
                        self,
                        &ButtonEvent {
                            button: btn_code,
                            state: ButtonState::Released,
                            serial,
                            time,
                        },
                    );
                    pointer.frame(self);
                }
                other => return Err(format!("unknown action: {other}")),
            }
        }

        Ok(())
    }
}

/// Map a character to a Linux evdev keycode.
fn char_to_keycode(ch: char) -> u32 {
    match ch.to_ascii_lowercase() {
        'a' => 30, 'b' => 48, 'c' => 46, 'd' => 32, 'e' => 18,
        'f' => 33, 'g' => 34, 'h' => 35, 'i' => 23, 'j' => 36,
        'k' => 37, 'l' => 38, 'm' => 50, 'n' => 49, 'o' => 24,
        'p' => 25, 'q' => 16, 'r' => 19, 's' => 31, 't' => 20,
        'u' => 22, 'v' => 47, 'w' => 17, 'x' => 45, 'y' => 21,
        'z' => 44,
        '1' | '!' => 2,  '2' | '@' => 3,  '3' | '#' => 4,
        '4' | '$' => 5,  '5' | '%' => 6,  '6' | '^' => 7,
        '7' | '&' => 8,  '8' | '*' => 9,  '9' | '(' => 10,
        '0' | ')' => 11,
        ' ' => 57,        // space
        '\n' => 28,        // enter
        '\t' => 15,        // tab
        '-' | '_' => 12,
        '=' | '+' => 13,
        '[' | '{' => 26,
        ']' | '}' => 27,
        '\\' | '|' => 43,
        ';' | ':' => 39,
        '\'' | '"' => 40,
        '`' | '~' => 41,
        ',' | '<' => 51,
        '.' | '>' => 52,
        '/' | '?' => 53,
        _ => 0, // unmapped
    }
}

/// Parse a key combo string like "ctrl+shift+t" into keycodes.
fn parse_key_combo(combo: &str) -> Result<KeyCombo, String> {
    let parts: Vec<&str> = combo.split('+').collect();
    if parts.is_empty() {
        return Err("empty combo".into());
    }

    let mut modifiers = Vec::new();
    let key_str = parts.last().unwrap();

    for &part in &parts[..parts.len() - 1] {
        let modifier_keycode = match part.to_lowercase().as_str() {
            "ctrl" | "control" => 29,   // KEY_LEFTCTRL
            "shift" => 42,              // KEY_LEFTSHIFT
            "alt" => 56,                // KEY_LEFTALT
            "super" | "logo" | "mod4" => 125, // KEY_LEFTMETA
            other => return Err(format!("unknown modifier: {other}")),
        };
        modifiers.push(modifier_keycode);
    }

    // Parse the main key
    let key = if key_str.len() == 1 {
        let ch = key_str.chars().next().unwrap();
        let k = char_to_keycode(ch);
        if k == 0 {
            return Err(format!("unknown key: {key_str}"));
        }
        k
    } else {
        match key_str.to_lowercase().as_str() {
            "return" | "enter" => 28,
            "escape" | "esc" => 1,
            "tab" => 15,
            "backspace" => 14,
            "delete" | "del" => 111,
            "home" => 102,
            "end" => 107,
            "pageup" | "pgup" => 104,
            "pagedown" | "pgdn" => 109,
            "up" => 103,
            "down" => 108,
            "left" => 105,
            "right" => 106,
            "insert" | "ins" => 110,
            "space" => 57,
            "f1" => 59, "f2" => 60, "f3" => 61, "f4" => 62,
            "f5" => 63, "f6" => 64, "f7" => 65, "f8" => 66,
            "f9" => 67, "f10" => 68, "f11" => 87, "f12" => 88,
            other => return Err(format!("unknown key: {other}")),
        }
    };

    Ok(KeyCombo { modifiers, key })
}
