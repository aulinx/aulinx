//! aulinx-semanticd — Standalone semantic desktop daemon.
//!
//! Runs on any Wayland compositor (Sway, Hyprland, GNOME, niri, etc.)
//! and provides AI-native semantic understanding via a Unix socket API.
//!
//! Usage:
//!   aulinx-semanticd              # Run with default socket path
//!   aulinx-semanticd --dump       # Dump scene graph JSON and exit
//!   AULINX_SOCKET=/tmp/test.sock aulinx-semanticd  # Custom socket path

mod events;
mod ipc;

use std::path::PathBuf;
use std::time::Duration;

use aulinx_semantic::sources::atspi::AtSpiSource;
use aulinx_semantic::sources::compositor_ipc::CompositorIpcSource;
use aulinx_semantic::sources::Source;
use aulinx_semantic::{DiffTracker, SceneGraph};

fn socket_path() -> PathBuf {
    // Check env override
    if let Ok(path) = std::env::var("AULINX_SOCKET") {
        return PathBuf::from(path);
    }
    // Default: $XDG_RUNTIME_DIR/aulinx/semantic.sock
    if let Ok(runtime_dir) = std::env::var("XDG_RUNTIME_DIR") {
        return PathBuf::from(runtime_dir)
            .join("aulinx")
            .join("semantic.sock");
    }
    // Fallback
    PathBuf::from("/tmp/aulinx-semantic.sock")
}

fn main() {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info")),
        )
        .init();

    tracing::info!("aulinx-semanticd v{}", env!("CARGO_PKG_VERSION"));

    let dump_mode = std::env::args().any(|a| a == "--dump");

    // Initialize scene graph
    let mut graph = SceneGraph::new();
    let mut tracker = DiffTracker::new();

    // Initialize sources
    let mut sources: Vec<Box<dyn Source>> = Vec::new();

    // AT-SPI source
    let mut atspi = AtSpiSource::new();
    match atspi.start(&mut graph) {
        Ok(()) => {
            tracing::info!("AT-SPI source started");
            sources.push(Box::new(atspi));
        }
        Err(e) => tracing::warn!("AT-SPI source failed to start: {e}"),
    }

    // Compositor IPC source (Sway/Hyprland/niri)
    let mut compositor_ipc = CompositorIpcSource::new();
    match compositor_ipc.start(&mut graph) {
        Ok(()) => {
            tracing::info!("Compositor IPC source started");
            sources.push(Box::new(compositor_ipc));
        }
        Err(e) => tracing::warn!("Compositor IPC source not available: {e}"),
    }

    tracing::info!("Scene graph: {} nodes", graph.len());

    // Print discovered windows
    let windows = graph.windows();
    tracing::info!("Found {} windows:", windows.len());
    for win in &windows {
        if let aulinx_semantic::SemanticNode::Window {
            title, app_id, pid, ..
        } = win
        {
            tracing::info!("  [{pid}] {app_id}: {title}");
        }
    }

    // Dump mode: print JSON and exit
    if dump_mode {
        let json = graph.to_json();
        let pretty = serde_json::to_string_pretty(&json).unwrap_or_default();
        println!("{pretty}");
        return;
    }

    // Take initial snapshot for diff tracking
    graph.snapshot(&mut tracker);

    // Run the IPC server
    let sock = socket_path();
    tracing::info!("Starting IPC server on {}", sock.display());

    if let Err(e) = ipc::run_sync_server(
        &sock,
        &mut graph,
        &mut sources,
        &mut tracker,
        Duration::from_secs(2), // Poll AT-SPI every 2 seconds
    ) {
        tracing::error!("IPC server error: {e}");
        std::process::exit(1);
    }
}
