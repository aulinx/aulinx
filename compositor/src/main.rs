//! Aulinx Compositor — AI-native Wayland compositor
//!
//! This is the Phase 2 compositor that provides:
//! - Wayland window management
//! - AI IPC via Unix socket (JSON-RPC)
//! - Native input injection (type text, send keys)
//! - Per-window screen capture
//! - Layer-shell support for the AI command palette overlay
//!
//! Architecture:
//! ```
//! Python Agent <-> Unix Socket (JSON-RPC) <-> Rust Compositor
//!                  /run/aulinx/ai.sock
//! ```

fn main() {
    // Initialize logging
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info")),
        )
        .init();

    tracing::info!("Aulinx Compositor v{}", env!("CARGO_PKG_VERSION"));
    tracing::info!("Phase 2 compositor — not yet functional");
    tracing::info!("Run the Python agent for now: aulinx");

    // TODO Phase 2 implementation:
    // 1. Initialize Smithay backend (DRM/KMS or Winit for development)
    // 2. Create Wayland display and event loop
    // 3. Set up XDG Shell for window management
    // 4. Set up Layer Shell for AI palette overlay
    // 5. Start AI IPC socket server
    // 6. Implement IPC commands:
    //    - windows.list / windows.focus / windows.close
    //    - input.type / input.key / input.mouse
    //    - screen.capture
    // 7. Run the event loop

    eprintln!("\nThe Aulinx compositor is under development.");
    eprintln!("Use the Python agent for now: aulinx -m qwen2.5:14b\n");
}
