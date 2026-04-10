//! DRM/KMS + udev + libinput backend — production mode.
//!
//! Runs on real hardware or a VM with GPU passthrough.
//! Uses libseat for session management (VT switching).

use std::collections::HashMap;
use std::path::Path;

use smithay::backend::allocator::gbm::{GbmAllocator, GbmBufferFlags, GbmDevice};
use smithay::backend::drm::compositor::{DrmCompositor, FrameFlags};
use smithay::backend::drm::output::{DrmOutput, DrmOutputManager};
use smithay::backend::drm::{DrmDevice, DrmDeviceFd, DrmEvent, DrmNode};
use smithay::backend::egl::{EGLDevice, EGLDisplay};
use smithay::backend::libinput::{LibinputInputBackend, LibinputSessionInterface};
use smithay::backend::renderer::gles::GlesRenderer;
use smithay::backend::renderer::multigpu::gbm::GbmGlesBackend;
use smithay::backend::renderer::multigpu::GpuManager;
use smithay::backend::session::libseat::LibSeatSession;
use smithay::backend::session::{Event as SessionEvent, Session};
use smithay::backend::udev::{self as smithay_udev, UdevBackend, UdevEvent};
use smithay::desktop::space::SpaceRenderElements;
use smithay::output::{Mode as WlMode, Output, PhysicalProperties};
use smithay::reexports::calloop::LoopHandle;
use smithay::reexports::drm::control::{connector, crtc, ModeTypeFlags};
use smithay::reexports::input::Libinput;
use smithay::reexports::rustix::fs::OFlags;
use smithay::utils::{DeviceFd, Transform};
use smithay::backend::drm::exporter::gbm::GbmFramebufferExporter;

use smithay_drm_extras::drm_scanner::{DrmScanEvent, DrmScanner};

use super::BackendData;
use crate::state::AulinxState;

/// Supported color formats (prefer higher quality first).
const SUPPORTED_FORMATS: &[smithay::backend::allocator::Fourcc] = &[
    smithay::backend::allocator::Fourcc::Abgr2101010,
    smithay::backend::allocator::Fourcc::Argb2101010,
    smithay::backend::allocator::Fourcc::Abgr8888,
    smithay::backend::allocator::Fourcc::Argb8888,
];

/// Type aliases for DRM generics.
type Alloc = GbmAllocator<DrmDeviceFd>;
type Exporter = GbmFramebufferExporter<DrmDeviceFd>;
type Compositor = DrmCompositor<Alloc, Exporter, (), DrmDeviceFd>;

/// Per-GPU device data.
pub struct DeviceData {
    pub drm_output_manager: DrmOutputManager<Alloc, Exporter, (), DrmDeviceFd>,
    pub drm_scanner: DrmScanner,
    pub render_node: Option<DrmNode>,
    pub surfaces: HashMap<crtc::Handle, SurfaceData>,
}

/// Per-output surface data.
pub struct SurfaceData {
    pub output: Output,
    pub drm_output: DrmOutput<Alloc, Exporter, (), DrmDeviceFd>,
}

/// Udev backend data stored in AulinxState.
pub struct UdevData {
    pub session: LibSeatSession,
    pub primary_gpu: DrmNode,
    pub gpus: GpuManager<GbmGlesBackend<GlesRenderer, DrmDeviceFd>>,
    pub devices: HashMap<DrmNode, DeviceData>,
}

/// Initialize the udev/DRM backend.
pub fn init(loop_handle: &LoopHandle<'static, AulinxState>) -> UdevData {
    // 1. Open a session via libseat
    let (session, session_notifier) = LibSeatSession::new()
        .expect("Failed to create libseat session. Are you in the 'seat' group?");

    tracing::info!("Session opened on seat: {}", session.seat());

    // Insert session event source (handles VT switching)
    loop_handle
        .insert_source(session_notifier, |event, _, _state: &mut AulinxState| {
            match event {
                SessionEvent::PauseSession => {
                    tracing::info!("Session paused (VT switch away)");
                }
                SessionEvent::ActivateSession => {
                    tracing::info!("Session resumed (VT switch back)");
                }
            }
        })
        .expect("Failed to insert session source");

    // 2. Detect primary GPU
    let primary_gpu = smithay_udev::primary_gpu(&session.seat())
        .expect("Failed to detect primary GPU")
        .expect("No GPU found");

    let primary_node = DrmNode::from_path(&primary_gpu)
        .expect("Failed to get DRM node from primary GPU");

    tracing::info!("Primary GPU: {:?} ({:?})", primary_gpu, primary_node);

    // 3. Initialize GPU manager
    let gpus = GpuManager::new(GbmGlesBackend::default())
        .expect("Failed to create GPU manager");

    // 4. Initialize udev for GPU hotplug monitoring
    let udev_backend = UdevBackend::new(&session.seat())
        .expect("Failed to create udev backend");

    let data = UdevData {
        session,
        primary_gpu: primary_node,
        gpus,
        devices: HashMap::new(),
    };

    // Process initially connected devices
    for (device_id, path) in udev_backend.device_list() {
        if let Some(node) = DrmNode::from_dev_id(device_id).ok() {
            tracing::info!("Found GPU: {:?} at {:?}", node, path);
        }
    }

    // Insert udev event source for hotplug
    loop_handle
        .insert_source(udev_backend, |event, _, state: &mut AulinxState| {
            match event {
                UdevEvent::Added { device_id, path } => {
                    if let Some(node) = DrmNode::from_dev_id(device_id).ok() {
                        if let Err(e) = device_added(state, node, &path) {
                            tracing::error!("Failed to add device {:?}: {}", node, e);
                        }
                    }
                }
                UdevEvent::Changed { device_id } => {
                    if let Some(node) = DrmNode::from_dev_id(device_id).ok() {
                        device_changed(state, node);
                    }
                }
                UdevEvent::Removed { device_id } => {
                    if let Some(node) = DrmNode::from_dev_id(device_id).ok() {
                        device_removed(state, node);
                    }
                }
            }
        })
        .expect("Failed to insert udev source");

    // 5. Initialize libinput for input devices
    let mut libinput_context =
        Libinput::new_with_udev(LibinputSessionInterface::from(data.session.clone()));
    libinput_context
        .udev_assign_seat(&data.session.seat())
        .expect("Failed to assign libinput seat");

    let libinput_backend = LibinputInputBackend::new(libinput_context.clone());

    loop_handle
        .insert_source(libinput_backend, |event, _, state: &mut AulinxState| {
            state.process_input_event(event);
        })
        .expect("Failed to insert libinput source");

    tracing::info!("Udev backend initialized");

    data
}

/// Add a newly detected DRM device.
fn device_added(
    state: &mut AulinxState,
    node: DrmNode,
    path: &Path,
) -> Result<(), Box<dyn std::error::Error>> {
    let BackendData::Udev(ref mut udev_data) = state.backend_data else {
        return Err("not udev backend".into());
    };

    // Open the DRM device via session
    let fd = udev_data.session.open(
        path,
        OFlags::RDWR | OFlags::CLOEXEC | OFlags::NOCTTY | OFlags::NONBLOCK,
    )?;
    let fd = DrmDeviceFd::new(DeviceFd::from(fd));

    let (drm, notifier) = DrmDevice::new(fd.clone(), true)?;
    let gbm = GbmDevice::new(fd.clone())?;

    // Insert DRM event source (VBlank + errors)
    let drm_node = node;
    state.loop_handle
        .insert_source(notifier, move |event, _metadata, state: &mut AulinxState| {
            match event {
                DrmEvent::VBlank(crtc) => {
                    frame_finish(state, drm_node, crtc);
                }
                DrmEvent::Error(error) => {
                    tracing::error!("DRM error: {:?}", error);
                }
            }
        })
        .expect("Failed to insert DRM event source");

    // Set up EGL + GPU manager
    let display = unsafe { EGLDisplay::new(gbm.clone())? };
    let egl_device = EGLDevice::device_for_display(&display)?;
    let render_node = egl_device
        .try_get_render_node()
        .ok()
        .flatten()
        .unwrap_or(node);

    udev_data.gpus.as_mut().add_node(render_node, gbm.clone())?;

    let mut renderer = udev_data.gpus.single_renderer(&render_node)?;
    let render_formats = renderer
        .as_mut()
        .egl_context()
        .dmabuf_render_formats()
        .clone();

    let allocator = GbmAllocator::new(
        gbm.clone(),
        GbmBufferFlags::RENDERING | GbmBufferFlags::SCANOUT,
    );
    let framebuffer_exporter = GbmFramebufferExporter::new(gbm.clone(), render_node.into());

    let drm_output_manager = DrmOutputManager::new(
        drm,
        allocator,
        framebuffer_exporter,
        Some(gbm),
        SUPPORTED_FORMATS.iter().copied(),
        render_formats,
    );

    udev_data.devices.insert(
        node,
        DeviceData {
            drm_output_manager,
            drm_scanner: DrmScanner::new(),
            render_node: Some(render_node),
            surfaces: HashMap::new(),
        },
    );

    // Enumerate existing connectors
    device_changed(state, node);

    tracing::info!("DRM device added: {:?}", node);
    Ok(())
}

/// Handle connector hotplug (monitor plugged/unplugged).
fn device_changed(state: &mut AulinxState, node: DrmNode) {
    let BackendData::Udev(ref mut udev_data) = state.backend_data else { return };
    let Some(device) = udev_data.devices.get_mut(&node) else { return };

    // Scan for connector changes
    let scan_result = match device.drm_scanner.scan_connectors(device.drm_output_manager.device()) {
        Ok(r) => r,
        Err(e) => {
            tracing::error!("Failed to scan connectors: {:?}", e);
            return;
        }
    };

    // Collect events first to avoid borrow conflicts
    let events: Vec<DrmScanEvent> = scan_result.into_iter().collect();

    for event in events {
        match event {
            DrmScanEvent::Connected { connector, crtc } => {
                if let Some(crtc) = crtc {
                    connector_connected(state, node, connector, crtc);
                }
            }
            DrmScanEvent::Disconnected { crtc, .. } => {
                if let Some(crtc) = crtc {
                    connector_disconnected(state, node, crtc);
                }
            }
            DrmScanEvent::Changed { .. } => {}
        }
    }
}

/// A new monitor was connected.
fn connector_connected(
    state: &mut AulinxState,
    node: DrmNode,
    connector: connector::Info,
    crtc: crtc::Handle,
) {
    let BackendData::Udev(ref mut udev_data) = state.backend_data else { return };
    let Some(device) = udev_data.devices.get_mut(&node) else { return };

    let render_node = device.render_node.unwrap_or(udev_data.primary_gpu);
    let mut renderer = match udev_data.gpus.single_renderer(&render_node) {
        Ok(r) => r,
        Err(e) => {
            tracing::error!("Failed to get renderer: {:?}", e);
            return;
        }
    };

    let output_name = format!(
        "{}-{}",
        connector.interface().as_str(),
        connector.interface_id()
    );

    tracing::info!("Connector connected: {} on crtc {:?}", output_name, crtc);

    // Select preferred mode
    let mode_idx = connector
        .modes()
        .iter()
        .position(|mode| mode.mode_type().contains(ModeTypeFlags::PREFERRED))
        .unwrap_or(0);

    if connector.modes().is_empty() {
        tracing::warn!("Connector {} has no modes", output_name);
        return;
    }

    let drm_mode = connector.modes()[mode_idx];
    let wl_mode = WlMode::from(drm_mode);

    let make = "Unknown".to_string();
    let model = output_name.clone();
    let serial = "Unknown".to_string();

    let (phys_w, phys_h) = connector.size().unwrap_or((0, 0));

    // Create output
    let output = Output::new(
        output_name.clone(),
        PhysicalProperties {
            size: (phys_w as i32, phys_h as i32).into(),
            subpixel: connector.subpixel().into(),
            make,
            model,
            serial_number: serial,
        },
    );
    output.create_global::<AulinxState>(&state.display_handle);

    // Position output after existing ones
    let x = state.space.outputs().fold(0, |acc, o| {
        acc + state.space.output_geometry(o).unwrap().size.w
    });
    output.set_preferred(wl_mode);
    output.change_current_state(Some(wl_mode), Some(Transform::Normal), None, Some((x, 0).into()));
    state.space.map_output(&output, (x, 0));

    // Get planes for this CRTC
    let planes = match device.drm_output_manager.device().planes(&crtc) {
        Ok(p) => p,
        Err(e) => {
            tracing::error!("Failed to get planes: {:?}", e);
            return;
        }
    };

    // Initialize DRM output compositor
    let drm_output = match device
        .drm_output_manager
        .lock()
        .initialize_output::<_, SpaceRenderElements<GlesRenderer, smithay::backend::renderer::element::surface::WaylandSurfaceRenderElement<GlesRenderer>>>(
            crtc,
            drm_mode,
            &[connector.handle()],
            &output,
            Some(planes),
            renderer.as_mut(),
            &Default::default(),
        ) {
        Ok(o) => o,
        Err(e) => {
            tracing::error!("Failed to initialize DRM output: {:?}", e);
            return;
        }
    };

    device.surfaces.insert(
        crtc,
        SurfaceData {
            output: output.clone(),
            drm_output,
        },
    );

    // Feed semantic bridge
    if let Some(ref mut bridge) = state.semantic_bridge {
        let mode = wl_mode;
        bridge.init(&mut state.scene_graph, mode.size.w, mode.size.h);
    }

    tracing::info!(
        "Output {} ready: {}x{}@{}Hz",
        output_name,
        wl_mode.size.w,
        wl_mode.size.h,
        wl_mode.refresh as f32 / 1000.0,
    );
}

/// A monitor was disconnected.
fn connector_disconnected(state: &mut AulinxState, node: DrmNode, crtc: crtc::Handle) {
    let BackendData::Udev(ref mut udev_data) = state.backend_data else { return };
    let Some(device) = udev_data.devices.get_mut(&node) else { return };

    if let Some(surface) = device.surfaces.remove(&crtc) {
        state.space.unmap_output(&surface.output);
        tracing::info!("Output disconnected: {}", surface.output.name());
    }
}

/// A GPU was removed.
fn device_removed(state: &mut AulinxState, node: DrmNode) {
    let BackendData::Udev(ref mut udev_data) = state.backend_data else { return };

    if let Some(device) = udev_data.devices.remove(&node) {
        for (_, surface) in device.surfaces {
            state.space.unmap_output(&surface.output);
        }
        tracing::info!("DRM device removed: {:?}", node);
    }
}

/// Handle VBlank — frame was displayed, render next one.
fn frame_finish(state: &mut AulinxState, node: DrmNode, crtc: crtc::Handle) {
    let BackendData::Udev(ref mut udev_data) = state.backend_data else { return };
    let Some(device) = udev_data.devices.get_mut(&node) else { return };
    let Some(surface) = device.surfaces.get_mut(&crtc) else { return };

    let render_node = device.render_node.unwrap_or(udev_data.primary_gpu);

    // Mark frame as submitted
    surface.drm_output.with_compositor(|compositor: &mut Compositor| {
        if let Err(e) = compositor.frame_submitted() {
            tracing::error!("Failed to mark frame submitted: {:?}", e);
        }
    });

    // Render next frame
    let mut renderer = match udev_data.gpus.single_renderer(&render_node) {
        Ok(r) => r,
        Err(e) => {
            tracing::error!("Failed to get renderer: {:?}", e);
            return;
        }
    };

    let output = surface.output.clone();
    type RenderElements = SpaceRenderElements<GlesRenderer, smithay::backend::renderer::element::surface::WaylandSurfaceRenderElement<GlesRenderer>>;
    let elements: Vec<RenderElements> = {
        smithay::desktop::space::space_render_elements(
            renderer.as_mut(),
            [&state.space],
            &output,
            1.0,
        )
        .unwrap_or_default()
    };

    surface.drm_output.with_compositor(|compositor: &mut Compositor| {
        match compositor.render_frame::<_, RenderElements>(renderer.as_mut(), &elements, [0.1, 0.1, 0.15, 1.0], FrameFlags::DEFAULT) {
            Ok(render_output) => {
                if !render_output.is_empty {
                    if let Err(e) = compositor.queue_frame(()) {
                        tracing::error!("Failed to queue frame: {:?}", e);
                    }
                }
            }
            Err(e) => {
                tracing::error!("Render error: {:?}", e);
            }
        }
    });

    // Send frame callbacks
    state.space.elements().for_each(|window| {
        window.send_frame(
            &output,
            state.start_time.elapsed(),
            Some(std::time::Duration::ZERO),
            |_, _| Some(output.clone()),
        );
    });

    state.space.refresh();
}

/// Render all outputs (called from main loop for initial frames).
#[allow(dead_code)]
pub fn render_outputs(state: &mut AulinxState) {
    // Collect node+crtc pairs first to avoid borrow conflict
    let pairs: Vec<(DrmNode, crtc::Handle)> = {
        let BackendData::Udev(ref udev_data) = state.backend_data else { return };
        udev_data.devices.iter().flat_map(|(node, device)| {
            device.surfaces.keys().map(move |crtc| (*node, *crtc))
        }).collect()
    };

    for (node, crtc) in pairs {
        frame_finish(state, node, crtc);
    }
}
