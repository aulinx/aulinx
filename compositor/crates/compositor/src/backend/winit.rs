//! Winit backend — runs the compositor as a window inside an existing WM.

use std::time::Duration;

use smithay::backend::renderer::damage::OutputDamageTracker;
use smithay::backend::renderer::element::RenderElementStates;
use smithay::backend::renderer::glow::GlowRenderer;
use smithay::backend::winit::{self as winit_backend, WinitEvent, WinitGraphicsBackend};
use smithay::desktop::space::SpaceRenderElements;
use smithay::output::{Mode, Output, PhysicalProperties, Subpixel};
use smithay::reexports::calloop::timer::{TimeoutAction, Timer};
use smithay::reexports::calloop::LoopHandle;
use smithay::utils::Transform;

use super::BackendData;
use crate::state::AulinxState;

pub struct WinitData {
    pub backend: WinitGraphicsBackend<GlowRenderer>,
    pub damage_tracker: OutputDamageTracker,
    pub output: Output,
}

pub fn init(loop_handle: &LoopHandle<'static, AulinxState>) -> WinitData {
    let (backend, winit_event_loop) =
        winit_backend::init::<GlowRenderer>().expect("Failed to initialize winit backend");

    let size = backend.window_size();

    let output = Output::new(
        "winit".to_string(),
        PhysicalProperties {
            size: (0, 0).into(),
            subpixel: Subpixel::Unknown,
            make: "Aulinx".to_string(),
            model: "Winit".to_string(),
            serial_number: "0".to_string(),
        },
    );

    let mode = Mode {
        size: (size.w as i32, size.h as i32).into(),
        refresh: 60_000,
    };
    output.change_current_state(Some(mode), Some(Transform::Flipped180), None, Some((0, 0).into()));
    output.set_preferred(mode);

    // CRITICAL: advertise the output to clients so they know display dimensions
    // Without this, clients like foot won't create surfaces
    // Note: create_global needs the display handle, which we don't have here.
    // We'll do it in AulinxState::new instead.

    let damage_tracker = OutputDamageTracker::from_output(&output);

    loop_handle
        .insert_source(winit_event_loop, |event, _, state: &mut AulinxState| {
            match event {
                WinitEvent::Resized { size, .. } => {
                    if let BackendData::Winit(ref winit_data) = state.backend_data {
                        let mode = Mode { size, refresh: 60_000 };
                        winit_data.output.change_current_state(Some(mode), None, None, None);
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

    loop_handle
        .insert_source(
            Timer::from_duration(Duration::from_millis(16)),
            |_, _, state: &mut AulinxState| {
                render_frame(state);
                TimeoutAction::ToDuration(Duration::from_millis(16))
            },
        )
        .expect("Failed to insert redraw timer");

    tracing::info!("Winit backend initialized ({}x{})", size.w, size.h);

    WinitData { backend, damage_tracker, output }
}

fn render_frame(state: &mut AulinxState) {
    let BackendData::Winit(ref mut winit_data) = state.backend_data else {
        return;
    };

    let output = winit_data.output.clone();

    if state.space.outputs().next().is_none() {
        state.space.map_output(&output, (0, 0));
    }

    let window_count = state.space.elements().count();

    // Collect render elements from the space (window surfaces)
    let elements: Vec<SpaceRenderElements<GlowRenderer, smithay::backend::renderer::element::surface::WaylandSurfaceRenderElement<GlowRenderer>>> = {
        let renderer = winit_data.backend.renderer();
        smithay::desktop::space::space_render_elements(renderer, [&state.space], &output, 1.0)
            .unwrap_or_default()
    };

    static LOGGED: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);
    if window_count > 0 && !LOGGED.swap(true, std::sync::atomic::Ordering::Relaxed) {
        tracing::info!("Rendering {} windows, {} elements", window_count, elements.len());
    }

    // Render
    {
        let Ok((renderer, mut target)) = winit_data.backend.bind() else {
            return;
        };
        let _ = winit_data.damage_tracker.render_output(
            renderer,
            &mut target,
            0,
            &elements,
            [0.1, 0.1, 0.15, 1.0],
        );
    }
    winit_data.backend.submit(None).ok();

    // Send frame callbacks to clients
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
