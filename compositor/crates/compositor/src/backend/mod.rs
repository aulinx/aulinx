//! Backend abstraction — Winit for development, DRM/udev for production.

pub mod udev;
pub mod winit;

/// Backend-specific data stored in AulinxState.
pub enum BackendData {
    /// Winit backend — runs as a window inside an existing compositor.
    Winit(winit::WinitData),
    /// DRM/udev backend — runs on real hardware.
    Udev(udev::UdevData),
    /// Placeholder for early initialization.
    None,
}

impl BackendData {
    pub fn seat_name(&self) -> String {
        match self {
            BackendData::Winit(_) => "winit".to_string(),
            BackendData::Udev(data) => data.session.seat(),
            BackendData::None => "seat0".to_string(),
        }
    }
}
