//! aulinx-compositor — AI-native Wayland compositor.

mod backend;
mod config;
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

    let backend_name = std::env::var("AULINX_BACKEND").unwrap_or_else(|_| "auto".to_string());
    let backend_data = match backend_name.as_str() {
        "auto" => {
            // Auto-detect: use winit if WAYLAND_DISPLAY/DISPLAY is set, udev otherwise
            if std::env::var("WAYLAND_DISPLAY").is_ok() || std::env::var("DISPLAY").is_ok() {
                tracing::info!("Auto-detected winit backend (running inside existing desktop)");
                let winit_data = backend::winit::init(&loop_handle);
                BackendData::Winit(winit_data)
            } else {
                tracing::info!("Auto-detected udev backend (bare metal / TTY)");
                let udev_data = backend::udev::init(&loop_handle);
                BackendData::Udev(udev_data)
            }
        }
        "winit" => {
            let winit_data = backend::winit::init(&loop_handle);
            BackendData::Winit(winit_data)
        }
        "udev" | "drm" => {
            let udev_data = backend::udev::init(&loop_handle);
            BackendData::Udev(udev_data)
        }
        other => {
            tracing::error!("Unknown backend: {other}. Use 'auto', 'winit', or 'udev'.");
            std::process::exit(1);
        }
    };

    let mut state = AulinxState::new(display, loop_handle, loop_signal, backend_data);

    // Initialize semantic bridge
    let mut bridge = semantic_bridge::SemanticBridge::new();
    let size = match state.backend_data {
        BackendData::Winit(ref w) => {
            let s = w.backend.window_size();
            (s.w as i32, s.h as i32)
        }
        BackendData::Udev(_) => {
            // Udev: outputs are added dynamically, bridge re-inits on connector connect
            (1920, 1080)
        }
    };
    bridge.init(&mut state.scene_graph, size.0, size.1);
    state.semantic_bridge = Some(bridge);

    // Start IPC server
    let socket_path = ipc::ipc_socket_path();
    let mut ipc_server = ipc::CompositorIpc::new(&socket_path).ok();

    tracing::info!("Compositor running (v{}, {} backend, {} IPC commands)",
        env!("CARGO_PKG_VERSION"),
        match &state.backend_data { BackendData::Winit(_) => "winit", BackendData::Udev(_) => "udev" },
        34,  // IPC command count (scene:22 + input:7 + window:3 + layout:2)
    );
    tracing::info!("Keys: Super+Return=terminal, J/K=focus, H/L=resize, Space=swap, Shift+Q=close, Esc=quit");
    tracing::info!("Connect clients with:");
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
            // Push semantic events to IPC subscribers
            if let Some(ref mut ipc) = ipc_server {
                if let Some(ref mut bridge) = state.semantic_bridge {
                    let events = bridge.drain_events();
                    if !events.is_empty() {
                        ipc.push_events(&events);
                    }
                }
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
                        ipc::CompositorCmd::InputScroll { client_id, req_id, x, y, dx, dy } => {
                            let result = state.inject_scroll(x, y, dx, dy);
                            let resp = match result {
                                Ok(()) => aulinx_semantic::protocol::JsonRpcResponse::success(req_id, serde_json::json!({"ok": true})),
                                Err(e) => aulinx_semantic::protocol::JsonRpcResponse::error(req_id, -32603, e),
                            };
                            ipc.respond(client_id, &serde_json::to_string(&resp).unwrap());
                        }
                        ipc::CompositorCmd::InputMove { client_id, req_id, x, y } => {
                            let result = state.inject_move(x, y);
                            let resp = match result {
                                Ok(()) => aulinx_semantic::protocol::JsonRpcResponse::success(req_id, serde_json::json!({"ok": true})),
                                Err(e) => aulinx_semantic::protocol::JsonRpcResponse::error(req_id, -32603, e),
                            };
                            ipc.respond(client_id, &serde_json::to_string(&resp).unwrap());
                        }
                        ipc::CompositorCmd::InputBatch { client_id, req_id, actions } => {
                            let mut results = Vec::new();
                            for action in &actions {
                                let method = action.get("method").and_then(|v| v.as_str()).unwrap_or("");
                                let params = action.get("params").cloned().unwrap_or(serde_json::json!({}));
                                let r = match method {
                                    "input.type" => {
                                        let text = params.get("text").and_then(|v| v.as_str()).unwrap_or("");
                                        state.inject_text(text).map(|_| "ok".to_string())
                                    }
                                    "input.key" => {
                                        let combo = params.get("combo").and_then(|v| v.as_str()).unwrap_or("");
                                        state.inject_key_combo(combo).map(|_| "ok".to_string())
                                    }
                                    "input.click" => {
                                        let x = params.get("x").and_then(|v| v.as_f64()).unwrap_or(0.0);
                                        let y = params.get("y").and_then(|v| v.as_f64()).unwrap_or(0.0);
                                        let btn = params.get("button").and_then(|v| v.as_u64()).unwrap_or(1) as u32;
                                        state.inject_click(x, y, btn).map(|_| "ok".to_string())
                                    }
                                    "input.move" => {
                                        let x = params.get("x").and_then(|v| v.as_f64()).unwrap_or(0.0);
                                        let y = params.get("y").and_then(|v| v.as_f64()).unwrap_or(0.0);
                                        state.inject_move(x, y).map(|_| "ok".to_string())
                                    }
                                    "sleep" => {
                                        let ms = params.get("ms").and_then(|v| v.as_u64()).unwrap_or(100);
                                        std::thread::sleep(std::time::Duration::from_millis(ms));
                                        Ok("ok".to_string())
                                    }
                                    _ => Err(format!("unknown batch action: {method}")),
                                };
                                results.push(serde_json::json!({
                                    "method": method,
                                    "result": match &r { Ok(s) => s.as_str(), Err(e) => e.as_str() },
                                    "ok": r.is_ok(),
                                }));
                                if r.is_err() { break; }
                            }
                            let resp = aulinx_semantic::protocol::JsonRpcResponse::success(
                                req_id,
                                serde_json::json!({"executed": results.len(), "results": results}),
                            );
                            ipc.respond(client_id, &serde_json::to_string(&resp).unwrap());
                        }
                        ipc::CompositorCmd::InputDrag { client_id, req_id, x1, y1, x2, y2, button } => {
                            let result = state.inject_drag(x1, y1, x2, y2, button);
                            let resp = match result {
                                Ok(()) => aulinx_semantic::protocol::JsonRpcResponse::success(req_id, serde_json::json!({"ok": true})),
                                Err(e) => aulinx_semantic::protocol::JsonRpcResponse::error(req_id, -32603, e),
                            };
                            ipc.respond(client_id, &serde_json::to_string(&resp).unwrap());
                        }
                        ipc::CompositorCmd::WindowSpawn { client_id, req_id, command, args } => {
                            let result = state.spawn_app(&command, &args);
                            let resp = match result {
                                Ok(pid) => aulinx_semantic::protocol::JsonRpcResponse::success(req_id, serde_json::json!({"ok": true, "pid": pid})),
                                Err(e) => aulinx_semantic::protocol::JsonRpcResponse::error(req_id, -32603, e),
                            };
                            ipc.respond(client_id, &serde_json::to_string(&resp).unwrap());
                        }
                        ipc::CompositorCmd::InputClick { client_id, req_id, x, y, button } => {
                            let result = state.inject_click(x, y, button);
                            let resp = match result {
                                Ok(()) => aulinx_semantic::protocol::JsonRpcResponse::success(req_id, serde_json::json!({"ok": true})),
                                Err(e) => aulinx_semantic::protocol::JsonRpcResponse::error(req_id, -32603, e),
                            };
                            ipc.respond(client_id, &serde_json::to_string(&resp).unwrap());
                        }
                        ipc::CompositorCmd::WindowClose { client_id, req_id, window_id } => {
                            let result = state.close_window(window_id);
                            let resp = match result {
                                Ok(()) => aulinx_semantic::protocol::JsonRpcResponse::success(req_id, serde_json::json!({"ok": true})),
                                Err(e) => aulinx_semantic::protocol::JsonRpcResponse::error(req_id, -32603, e),
                            };
                            ipc.respond(client_id, &serde_json::to_string(&resp).unwrap());
                        }
                        ipc::CompositorCmd::WindowFocus { client_id, req_id, window_id } => {
                            let result = state.focus_window(window_id);
                            let resp = match result {
                                Ok(()) => aulinx_semantic::protocol::JsonRpcResponse::success(req_id, serde_json::json!({"ok": true})),
                                Err(e) => aulinx_semantic::protocol::JsonRpcResponse::error(req_id, -32603, e),
                            };
                            ipc.respond(client_id, &serde_json::to_string(&resp).unwrap());
                        }
                        ipc::CompositorCmd::WindowSwapMaster { client_id, req_id, window_id } => {
                            let result = state.swap_window_to_master(window_id);
                            let resp = match result {
                                Ok(()) => aulinx_semantic::protocol::JsonRpcResponse::success(req_id, serde_json::json!({"ok": true})),
                                Err(e) => aulinx_semantic::protocol::JsonRpcResponse::error(req_id, -32603, e),
                            };
                            ipc.respond(client_id, &serde_json::to_string(&resp).unwrap());
                        }
                        ipc::CompositorCmd::GetConfig { client_id, req_id } => {
                            let config = serde_json::json!({
                                "layout": {
                                    "gap": state.config.layout.gap,
                                    "outer_gap": state.config.layout.outer_gap,
                                    "master_ratio": state.config.layout.master_ratio,
                                },
                                "appearance": {
                                    "background": state.config.appearance.background,
                                },
                                "terminal": state.config.terminal,
                            });
                            let resp = aulinx_semantic::protocol::JsonRpcResponse::success(req_id, config);
                            ipc.respond(client_id, &serde_json::to_string(&resp).unwrap());
                        }
                        ipc::CompositorCmd::Suggest { client_id, req_id } => {
                            let suggestions = state.suggest_actions();
                            let resp = aulinx_semantic::protocol::JsonRpcResponse::success(req_id, serde_json::json!({"suggestions": suggestions}));
                            ipc.respond(client_id, &serde_json::to_string(&resp).unwrap());
                        }
                        ipc::CompositorCmd::Summary { client_id, req_id } => {
                            let resp = aulinx_semantic::protocol::JsonRpcResponse::success(req_id, serde_json::json!({
                                "version": env!("CARGO_PKG_VERSION"),
                                "description": state.describe_desktop(),
                                "ascii": state.ascii_layout(),
                                "suggestions": state.suggest_actions(),
                                "status": state.get_status(),
                            }));
                            ipc.respond(client_id, &serde_json::to_string(&resp).unwrap());
                        }
                        ipc::CompositorCmd::AsciiLayout { client_id, req_id } => {
                            let ascii = state.ascii_layout();
                            let resp = aulinx_semantic::protocol::JsonRpcResponse::success(req_id, serde_json::json!({"ascii": ascii}));
                            ipc.respond(client_id, &serde_json::to_string(&resp).unwrap());
                        }
                        ipc::CompositorCmd::Describe { client_id, req_id } => {
                            let description = state.describe_desktop();
                            let resp = aulinx_semantic::protocol::JsonRpcResponse::success(req_id, serde_json::json!({"description": description}));
                            ipc.respond(client_id, &serde_json::to_string(&resp).unwrap());
                        }
                        ipc::CompositorCmd::Status { client_id, req_id } => {
                            let status = state.get_status();
                            let resp = aulinx_semantic::protocol::JsonRpcResponse::success(req_id, status);
                            ipc.respond(client_id, &serde_json::to_string(&resp).unwrap());
                        }
                        ipc::CompositorCmd::SceneWaitFor { client_id, req_id, title, app_id, count } => {
                            let matched = state.check_wait_condition(title.as_deref(), app_id.as_deref(), count);
                            let resp = aulinx_semantic::protocol::JsonRpcResponse::success(
                                req_id,
                                serde_json::json!({"matched": matched}),
                            );
                            ipc.respond(client_id, &serde_json::to_string(&resp).unwrap());
                        }
                        ipc::CompositorCmd::SceneDiff { client_id, req_id } => {
                            let events = state.get_recent_events();
                            let resp = aulinx_semantic::protocol::JsonRpcResponse::success(
                                req_id,
                                serde_json::json!({"events": events}),
                            );
                            ipc.respond(client_id, &serde_json::to_string(&resp).unwrap());
                        }
                        ipc::CompositorCmd::ElementAt { client_id, req_id, x, y } => {
                            let result = state.element_at(x, y);
                            let resp = aulinx_semantic::protocol::JsonRpcResponse::success(req_id, result);
                            ipc.respond(client_id, &serde_json::to_string(&resp).unwrap());
                        }
                        ipc::CompositorCmd::WindowMinimize { client_id, req_id, window_id } => {
                            // In tiling WM, "minimize" means unmap from layout
                            let result = match state.find_window_by_semantic_id(window_id) {
                                Ok(window) => {
                                    state.space.unmap_elem(&window);
                                    state.relayout();
                                    Ok(())
                                }
                                Err(e) => Err(e),
                            };
                            let resp = match result {
                                Ok(()) => aulinx_semantic::protocol::JsonRpcResponse::success(req_id, serde_json::json!({"ok": true})),
                                Err(e) => aulinx_semantic::protocol::JsonRpcResponse::error(req_id, -32603, e),
                            };
                            ipc.respond(client_id, &serde_json::to_string(&resp).unwrap());
                        }
                        ipc::CompositorCmd::LayoutSetRatio { client_id, req_id, ratio } => {
                            state.config.layout.master_ratio = ratio.clamp(0.2, 0.8);
                            state.relayout();
                            let resp = aulinx_semantic::protocol::JsonRpcResponse::success(req_id, serde_json::json!({"ok": true, "ratio": state.config.layout.master_ratio}));
                            ipc.respond(client_id, &serde_json::to_string(&resp).unwrap());
                        }
                        ipc::CompositorCmd::LayoutSetGap { client_id, req_id, gap } => {
                            state.config.layout.gap = gap.clamp(0, 32);
                            state.config.layout.outer_gap = gap.clamp(0, 32);
                            state.relayout();
                            let resp = aulinx_semantic::protocol::JsonRpcResponse::success(req_id, serde_json::json!({"ok": true, "gap": state.config.layout.gap}));
                            ipc.respond(client_id, &serde_json::to_string(&resp).unwrap());
                        }
                        ipc::CompositorCmd::AnnotatedScreenshot { client_id, req_id } => {
                            let result = state.take_annotated_screenshot();
                            let resp = match result {
                                Ok(b64) => aulinx_semantic::protocol::JsonRpcResponse::success(req_id, serde_json::json!({"format": "png", "data": b64, "annotated": true})),
                                Err(e) => aulinx_semantic::protocol::JsonRpcResponse::error(req_id, -32603, e),
                            };
                            ipc.respond(client_id, &serde_json::to_string(&resp).unwrap());
                        }
                        ipc::CompositorCmd::Screenshot { client_id, req_id } => {
                            let result = state.take_screenshot();
                            let resp = match result {
                                Ok(b64) => aulinx_semantic::protocol::JsonRpcResponse::success(req_id, serde_json::json!({"format": "png", "data": b64})),
                                Err(e) => aulinx_semantic::protocol::JsonRpcResponse::error(req_id, -32603, e),
                            };
                            ipc.respond(client_id, &serde_json::to_string(&resp).unwrap());
                        }
                    }
                }
            }
        })
        .expect("Event loop failed");
}
