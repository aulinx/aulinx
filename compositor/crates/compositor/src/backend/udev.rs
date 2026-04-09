//! DRM/KMS + udev + libinput backend — production mode.
//!
//! Runs on real hardware or a VM with GPU passthrough.
//! Uses libseat for session management (VT switching).
//!
//! Architecture:
//! - UdevBackend detects GPUs via udev, monitors hotplug
//! - LibSeatSession manages seat access (DRM master, input devices)
//! - DRM device provides display outputs (CRTCs + connectors)
//! - GBM allocates GPU buffers for rendering
//! - Libinput handles keyboard, mouse, touchpad from /dev/input
//! - GlowRenderer does OpenGL rendering to DRM framebuffers

use std::collections::HashMap;
use std::path::Path;

use smithay::backend::drm::{DrmDevice, DrmDeviceFd, DrmNode};
use smithay::backend::egl::EGLDevice;
use smithay::backend::libinput::{LibinputInputBackend, LibinputSessionInterface};
use smithay::backend::renderer::glow::GlowRenderer;
use smithay::backend::renderer::multigpu::gbm::GbmGlesBackend;
use smithay::backend::renderer::multigpu::GpuManager;
use smithay::backend::session::libseat::LibSeatSession;
use smithay::backend::session::{Event as SessionEvent, Session};
use smithay::backend::udev::{UdevBackend, UdevEvent};
use smithay::output::{Mode, Output, PhysicalProperties, Subpixel};
use smithay::reexports::calloop::LoopHandle;
use smithay::reexports::input::Libinput;
use smithay::utils::Transform;

use crate::state::AulinxState;

/// Per-GPU device data.
pub struct DeviceData {
    pub drm: DrmDevice,
    pub drm_node: DrmNode,
    pub outputs: HashMap<smithay::backend::drm::connector::Handle, Output>,
}

/// Udev backend data stored in AulinxState.
pub struct UdevData {
    pub session: LibSeatSession,
    pub primary_gpu: DrmNode,
    pub devices: HashMap<DrmNode, DeviceData>,
}

/// Initialize the udev/DRM backend.
///
/// This is a scaffold — the exact Smithay 0.7 API calls need verification
/// on a real Linux system with DRM access. The structure follows Anvil's
/// udev backend pattern.
pub fn init(loop_handle: &LoopHandle<'static, AulinxState>) -> UdevData {
    // 1. Open a session via libseat
    let (session, session_notifier) = LibSeatSession::new()
        .expect("Failed to create libseat session. Are you in the 'seat' group?");

    tracing::info!("Session opened on seat: {}", session.seat());

    // Insert session event source (handles VT switching)
    loop_handle
        .insert_source(session_notifier, |event, _, state: &mut AulinxState| {
            match event {
                SessionEvent::PauseSession => {
                    tracing::info!("Session paused (VT switch away)");
                    // TODO: pause rendering, release DRM master
                }
                SessionEvent::ActivateSession => {
                    tracing::info!("Session resumed (VT switch back)");
                    // TODO: resume rendering, reclaim DRM master
                }
            }
        })
        .expect("Failed to insert session source");

    // 2. Detect primary GPU
    let primary_gpu = smithay::backend::udev::primary_gpu(&session.seat())
        .expect("Failed to detect primary GPU")
        .expect("No GPU found");

    tracing::info!("Primary GPU: {:?}", primary_gpu);

    // 3. Initialize udev for GPU hotplug monitoring
    let udev_backend = UdevBackend::new(&session.seat())
        .expect("Failed to create udev backend");

    // Process initially connected devices
    for (device_id, path) in udev_backend.device_list() {
        tracing::info!("Found GPU: {:?} at {:?}", device_id, path);
        // TODO: open DRM device, enumerate connectors, create outputs
    }

    // Insert udev event source for hotplug
    loop_handle
        .insert_source(udev_backend, |event, _, state: &mut AulinxState| {
            match event {
                UdevEvent::Added { device_id, path } => {
                    tracing::info!("GPU added: {:?} at {:?}", device_id, path);
                    // TODO: open device, set up outputs
                }
                UdevEvent::Changed { device_id } => {
                    tracing::info!("GPU changed: {:?}", device_id);
                    // TODO: re-enumerate connectors (monitor plug/unplug)
                }
                UdevEvent::Removed { device_id } => {
                    tracing::info!("GPU removed: {:?}", device_id);
                    // TODO: clean up device, remove outputs
                }
            }
        })
        .expect("Failed to insert udev source");

    // 4. Initialize libinput for input devices
    let mut libinput_context =
        Libinput::new_with_udev(LibinputSessionInterface::from(session.clone()));
    libinput_context
        .udev_assign_seat(&session.seat())
        .expect("Failed to assign libinput seat");

    let libinput_backend = LibinputInputBackend::new(libinput_context.clone());

    loop_handle
        .insert_source(libinput_backend, |event, _, state: &mut AulinxState| {
            state.process_input_event(event);
        })
        .expect("Failed to insert libinput source");

    tracing::info!("Udev backend initialized");
    tracing::info!("DRM rendering and output enumeration need to be completed on target hardware");

    UdevData {
        session,
        primary_gpu,
        devices: HashMap::new(),
    }
}
