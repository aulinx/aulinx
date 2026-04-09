//! Backend abstraction.

pub mod winit;

pub enum BackendData {
    Winit(winit::WinitData),
    None,
}

impl BackendData {
    pub fn seat_name(&self) -> String {
        match self {
            BackendData::Winit(_) => "winit".to_string(),
            BackendData::None => "seat0".to_string(),
        }
    }
}
