//! aulinx-compositor — AI-native Wayland compositor.

mod backend;
mod input;
mod ipc;
mod semantic_bridge;
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

    // Initialize semantic bridge
    let mut bridge = semantic_bridge::SemanticBridge::new();
    let size = if let BackendData::Winit(ref w) = state.backend_data {
        let s = w.backend.window_size();
        (s.w as i32, s.h as i32)
    } else {
        (1920, 1080)
    };
    bridge.init(&mut state.scene_graph, size.0, size.1);
    state.semantic_bridge = Some(bridge);

    // Start IPC server
    let socket_path = ipc::ipc_socket_path();
    let mut ipc_server = ipc::CompositorIpc::new(&socket_path).ok();

    tracing::info!("Compositor running. Connect clients with:");
    tracing::info!("  WAYLAND_DISPLAY={} <client>", state.socket_name);
    tracing::info!("AI agents connect to: {}", socket_path.display());

    event_loop
        .run(None, &mut state, |state| {
            // Dispatch Wayland clients
            if let Some(mut display) = state.display.take() {
                display.dispatch_clients(state).ok();
                display.flush_clients().ok();
                state.display = Some(display);
            }
            // Poll IPC server and handle compositor commands
            if let Some(ref mut ipc) = ipc_server {
                let commands = ipc.poll(&state.scene_graph);
                for cmd in commands {
                    match cmd {
                        ipc::CompositorCmd::InputType { client_id, req_id, text } => {
                            let result = state.inject_text(&text);
                            let resp = match result {
                                Ok(()) => aulinx_semantic::protocol::JsonRpcResponse::success(req_id, serde_json::json!({"ok": true})),
                                Err(e) => aulinx_semantic::protocol::JsonRpcResponse::error(req_id, -32603, e),
                            };
                            ipc.respond(client_id, &serde_json::to_string(&resp).unwrap());
                        }
                        ipc::CompositorCmd::InputKey { client_id, req_id, combo } => {
                            let result = state.inject_key_combo(&combo);
                            let resp = match result {
                                Ok(()) => aulinx_semantic::protocol::JsonRpcResponse::success(req_id, serde_json::json!({"ok": true})),
                                Err(e) => aulinx_semantic::protocol::JsonRpcResponse::error(req_id, -32603, e),
                            };
                            ipc.respond(client_id, &serde_json::to_string(&resp).unwrap());
                        }
                        ipc::CompositorCmd::WindowClose { client_id, req_id } => {
                            let resp = aulinx_semantic::protocol::JsonRpcResponse::error(req_id, -32601, "not yet implemented".into());
                            ipc.respond(client_id, &serde_json::to_string(&resp).unwrap());
                        }
                    }
                }
            }
        })
        .expect("Event loop failed");
}
