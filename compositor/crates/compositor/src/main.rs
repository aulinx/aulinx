//! aulinx-compositor — AI-native Wayland compositor.
//!
//! Usage:
//!   AULINX_BACKEND=winit cargo run -p aulinx-compositor

mod backend;
mod state;

use smithay::reexports::calloop::EventLoop;
use smithay::reexports::wayland_server::Display;

use crate::backend::BackendData;
use crate::state::AulinxState;

fn main() {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info")),
        )
        .init();

    tracing::info!("aulinx-compositor v{}", env!("CARGO_PKG_VERSION"));

    let mut event_loop: EventLoop<'static, AulinxState> =
        EventLoop::try_new().expect("Failed to create event loop");
    let loop_handle = event_loop.handle();
    let loop_signal = event_loop.get_signal();

    let display: Display<AulinxState> = Display::new().expect("Failed to create display");

    let backend_name = std::env::var("AULINX_BACKEND").unwrap_or_else(|_| "winit".to_string());
    let backend_data = match backend_name.as_str() {
        "winit" => {
            let winit_data = backend::winit::init(&loop_handle);
            BackendData::Winit(winit_data)
        }
        other => {
            tracing::error!("Unknown backend: {other}. Use 'winit'.");
            std::process::exit(1);
        }
    };

    let mut state = AulinxState::new(display, loop_handle, loop_signal, backend_data);

    tracing::info!("Compositor running. Connect clients with:");
    tracing::info!("  WAYLAND_DISPLAY={} <client>", state.socket_name);

    event_loop
        .run(None, &mut state, |_state| {})
        .expect("Event loop failed");
}
