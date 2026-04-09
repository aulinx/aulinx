//! Screen capture — window.screenshot and screen.capture.
//!
//! Reads pixels from the renderer's framebuffer, encodes as PNG,
//! and returns as base64 string in the JSON-RPC response.

use smithay::backend::renderer::glow::GlowRenderer;

use crate::backend::BackendData;
use crate::state::AulinxState;

impl AulinxState {
    /// Capture the full screen as a base64 PNG.
    pub fn capture_screen(&mut self) -> Result<String, String> {
        let BackendData::Winit(ref mut winit_data) = self.backend_data else {
            return Err("screen capture only supported on winit backend for now".into());
        };

        let size = winit_data.backend.window_size();
        let renderer = winit_data.backend.renderer();

        // Read pixels from the current framebuffer
        let pixels = renderer
            .read_pixels(
                smithay::utils::Rectangle::from_loc_and_size(
                    (0, 0),
                    (size.physical_size.w, size.physical_size.h),
                ),
            )
            .map_err(|e| format!("read_pixels failed: {e:?}"))?;

        // Encode as PNG
        encode_png(
            &pixels,
            size.physical_size.w as u32,
            size.physical_size.h as u32,
        )
    }

    /// Capture a specific window as a base64 PNG.
    pub fn capture_window(&mut self, window_id: u64) -> Result<String, String> {
        // Find the window's location and size in the space
        let window = self
            .window_ids
            .iter()
            .find(|(_, &id)| id == window_id)
            .map(|(w, _)| w.clone())
            .ok_or_else(|| format!("window {window_id} not found"))?;

        let geo = self
            .space
            .element_geometry(&window)
            .ok_or("window has no geometry")?;

        let BackendData::Winit(ref mut winit_data) = self.backend_data else {
            return Err("capture only supported on winit backend".into());
        };

        let renderer = winit_data.backend.renderer();

        // Read pixels from the window's region
        let pixels = renderer
            .read_pixels(smithay::utils::Rectangle::from_loc_and_size(
                (geo.loc.x, geo.loc.y),
                (geo.size.w, geo.size.h),
            ))
            .map_err(|e| format!("read_pixels failed: {e:?}"))?;

        encode_png(&pixels, geo.size.w as u32, geo.size.h as u32)
    }
}

/// Encode RGBA pixel data as a base64-encoded PNG string.
fn encode_png(pixels: &[u8], width: u32, height: u32) -> Result<String, String> {
    use image::{ImageBuffer, RgbaImage};

    let img: RgbaImage = ImageBuffer::from_raw(width, height, pixels.to_vec())
        .ok_or("failed to create image buffer")?;

    let mut png_bytes = Vec::new();
    let mut cursor = std::io::Cursor::new(&mut png_bytes);

    img.write_to(&mut cursor, image::ImageFormat::Png)
        .map_err(|e| format!("PNG encode error: {e}"))?;

    Ok(base64::Engine::encode(
        &base64::engine::general_purpose::STANDARD,
        &png_bytes,
    ))
}
