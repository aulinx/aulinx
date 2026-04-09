//! aulinx-compositor — AI-native Wayland compositor.
//!
//! Usage:
//!   AULINX_BACKEND=winit cargo run -p aulinx-compositor
//!
//! Then connect clients:
//!   WAYLAND_DISPLAY=<socket> foot

mod backend;
mod input;
mod ipc;
mod layout;
mod render;
mod semantic_bridge;
mod shell;
mod state;
mod workspace;
mod xwayland;

use std::path::PathBuf;

fn ipc_socket_path() -> PathBuf {
    if let Ok(path) = std::env::var("AULINX_SOCKET") {
        return PathBuf::from(path);
    }
    if let Ok(runtime_dir) = std::env::var("XDG_RUNTIME_DIR") {
        return PathBuf::from(runtime_dir)
            .join("aulinx")
            .join("semantic.sock");
    }
    PathBuf::from("/tmp/aulinx-semantic.sock")
}

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

    // Create calloop event loop
    let mut event_loop: EventLoop<'static, AulinxState> =
        EventLoop::try_new().expect("Failed to create event loop");
    let loop_handle = event_loop.handle();
    let loop_signal = event_loop.get_signal();

    // Create Wayland display
    let display: Display<AulinxState> = Display::new().expect("Failed to create Wayland display");

    // Initialize backend
    let backend_name = std::env::var("AULINX_BACKEND").unwrap_or_else(|_| "winit".to_string());
    let backend_data = match backend_name.as_str() {
        "winit" => {
            let winit_data = backend::winit::init(&loop_handle);
            BackendData::Winit(winit_data)
        }
        "udev" | "drm" => {
            let udev_data = backend::udev::init(&loop_handle);
            BackendData::Udev(udev_data)
        }
        other => {
            tracing::error!("Unknown backend: {other}. Use 'winit' or 'udev'.");
            std::process::exit(1);
        }
    };

    // Create compositor state
    let mut state = AulinxState::new(display, loop_handle, loop_signal, backend_data);

    // Initialize semantic bridge + IPC
    state.init_semantic();

    // Start XWayland for X11 app compatibility
    if std::env::var("AULINX_NO_XWAYLAND").is_err() {
        state.start_xwayland();
    }

    tracing::info!("Compositor running. Connect clients with:");
    tracing::info!("  WAYLAND_DISPLAY={} <client>", state.socket_name);
    tracing::info!("  e.g.: WAYLAND_DISPLAY={} foot", state.socket_name);
    tracing::info!("AI agents connect to: {}", ipc_socket_path().display());

    // Run the event loop
    event_loop
        .run(None, &mut state, |state| {
            // Poll IPC server each iteration
            state.poll_ipc();
        })
        .expect("Event loop failed");
}
