//! Backend abstraction.

pub mod udev;
pub mod winit;

use smithay::backend::session::Session;

pub enum BackendData {
    Winit(winit::WinitData),
    Udev(udev::UdevData),
}

impl BackendData {
    pub fn seat_name(&self) -> String {
        match self {
            BackendData::Winit(_) => "winit".to_string(),
            BackendData::Udev(data) => data.session.seat(),
        }
    }
}
