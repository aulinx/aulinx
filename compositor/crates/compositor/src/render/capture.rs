//! Screen capture — stubbed until Smithay renderer API is verified.

use crate::state::AulinxState;

impl AulinxState {
    pub fn capture_screen(&mut self) -> Result<String, String> {
        Err("screen capture not yet implemented — needs Smithay renderer API verification".into())
    }

    pub fn capture_window(&mut self, _window_id: u64) -> Result<String, String> {
        Err("window capture not yet implemented — needs Smithay renderer API verification".into())
    }
}
