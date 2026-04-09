//! Cursor theme loading via xcursor.

use smithay::input::pointer::CursorImageStatus;

/// Cursor state tracked by the compositor.
pub struct CursorState {
    pub status: CursorImageStatus,
    pub theme: String,
    pub size: u32,
}

impl Default for CursorState {
    fn default() -> Self {
        Self {
            status: CursorImageStatus::default_named(),
            theme: std::env::var("XCURSOR_THEME").unwrap_or_else(|_| "default".into()),
            size: std::env::var("XCURSOR_SIZE")
                .ok()
                .and_then(|s| s.parse().ok())
                .unwrap_or(24),
        }
    }
}
