//! AI virtual input injection — stubbed until borrow pattern resolved.

use crate::state::AulinxState;

impl AulinxState {
    pub fn inject_text(&mut self, text: &str) -> Result<(), String> {
        tracing::info!("input.type: '{text}' (injection not yet wired)");
        Err("input injection requires keyboard borrow refactor — coming soon".into())
    }

    pub fn inject_key_combo(&mut self, combo: &str) -> Result<(), String> {
        tracing::info!("input.key: '{combo}' (injection not yet wired)");
        Err("input injection requires keyboard borrow refactor — coming soon".into())
    }
}
