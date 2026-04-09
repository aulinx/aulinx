//! Winit backend — runs the compositor as a window inside an existing WM.
//!
//! Used for development: `AULINX_BACKEND=winit cargo run -p aulinx-compositor`

use std::time::Duration;

use smithay::backend::renderer::damage::OutputDamageTracker;
use smithay::backend::renderer::glow::GlowRenderer;
use smithay::backend::winit::{self as winit_backend, WinitEvent, WinitGraphicsBackend};
use smithay::output::{Mode, Output, PhysicalProperties, Subpixel};
use smithay::reexports::calloop::timer::{TimeoutAction, Timer};
use smithay::reexports::calloop::LoopHandle;
use smithay::utils::Transform;

use super::BackendData;
use crate::state::AulinxState;

/// Winit-specific backend data.
pub struct WinitData {
    pub backend: WinitGraphicsBackend<GlowRenderer>,
    pub damage_tracker: OutputDamageTracker,
    pub output: Output,
}

/// Initialize the Winit backend and wire it into the event loop.
pub fn init(loop_handle: &LoopHandle<'static, AulinxState>) -> WinitData {
    let (backend, winit_event_loop) =
        winit_backend::init::<GlowRenderer>().expect("Failed to initialize winit backend");

    let size = backend.window_size();

    // Create output representing the winit window
    let output = Output::new(
        "winit".to_string(),
        PhysicalProperties {
            size: (0, 0).into(),
            subpixel: Subpixel::Unknown,
            make: "Aulinx".to_string(),
            model: "Winit".to_string(),
        },
    );

    let mode = Mode {
        size: size.physical_size,
        refresh: 60_000,
    };
    output.change_current_state(
        Some(mode),
        Some(Transform::Flipped180),
        None,
        Some((0, 0).into()),
    );
    output.set_preferred(mode);

    let damage_tracker = OutputDamageTracker::from_output(&output);

    // Insert winit event source
    loop_handle
        .insert_source(winit_event_loop, |event, _, state: &mut AulinxState| {
            match event {
                WinitEvent::Resized { size, .. } => {
                    if let BackendData::Winit(ref winit_data) = state.backend_data {
                        let mode = Mode {
                            size,
                            refresh: 60_000,
                        };
                        winit_data
                            .output
                            .change_current_state(Some(mode), None, None, None);
                    }
                }
                WinitEvent::Input(event) => {
                    state.process_input_event(event);
                }
                WinitEvent::Focus(_) => {}
                WinitEvent::Redraw => {
                    render_frame(state);
                }
                WinitEvent::CloseRequested => {
                    state.loop_signal.stop();
                }
            }
        })
        .expect("Failed to insert winit event source");

    // Redraw timer at ~60fps
    loop_handle
        .insert_source(
            Timer::from_duration(Duration::from_millis(16)),
            |_, _, state: &mut AulinxState| {
                render_frame(state);
                TimeoutAction::ToDuration(Duration::from_millis(16))
            },
        )
        .expect("Failed to insert redraw timer");

    tracing::info!(
        "Winit backend initialized ({}x{})",
        size.physical_size.w,
        size.physical_size.h
    );

    WinitData {
        backend,
        damage_tracker,
        output,
    }
}

/// Render a frame to the winit window.
fn render_frame(state: &mut AulinxState) {
    let BackendData::Winit(ref mut winit_data) = state.backend_data else {
        return;
    };

    let output = winit_data.output.clone();

    // Map output into space if not already
    if state.space.outputs().next().is_none() {
        state.space.map_output(&output, (0, 0));
    }

    // Render
    let renderer = winit_data.backend.renderer();
    let age = winit_data.backend.buffer_age().unwrap_or(0);

    // Use damage tracker to render
    let render_result = smithay::desktop::space::render_output::<
        _,
        smithay::backend::renderer::element::surface::WaylandSurfaceRenderElement<GlowRenderer>,
        _,
        _,
    >(
        &output,
        renderer,
        age as usize,
        [&state.space],
        &[],
        &mut winit_data.damage_tracker,
        [0.1, 0.1, 0.15, 1.0], // Dark blue-grey background
    );

    match render_result {
        Ok(render_output_result) => {
            winit_data
                .backend
                .submit(Some(&render_output_result.states))
                .ok();
        }
        Err(err) => {
            tracing::warn!("Render error: {err:?}");
            winit_data.backend.submit(None).ok();
        }
    }

    // Send frame callbacks
    state.space.elements().for_each(|window| {
        window.send_frame(
            &output,
            state.start_time.elapsed(),
            Some(Duration::ZERO),
            |_, _| Some(output.clone()),
        );
    });

    state.space.refresh();
}
