//! Floating layout — manual window positioning with z-order stack.

use super::{LayoutRect, WindowId};

/// A floating window with its stored position.
#[derive(Debug, Clone)]
struct FloatingWindow {
    window_id: WindowId,
    rect: LayoutRect,
}

/// Floating layout manages manually positioned windows.
pub struct FloatingLayout {
    /// Windows in z-order (last = topmost).
    windows: Vec<FloatingWindow>,
}

impl FloatingLayout {
    pub fn new() -> Self {
        Self {
            windows: Vec::new(),
        }
    }

    /// Add a window with a default centered position.
    pub fn add_window(&mut self, window_id: WindowId, area: LayoutRect) {
        // Default: centered, 80% of available area
        let w = (area.width as f32 * 0.8) as i32;
        let h = (area.height as f32 * 0.8) as i32;
        let x = area.x + (area.width - w) / 2;
        let y = area.y + (area.height - h) / 2;

        self.windows.push(FloatingWindow {
            window_id,
            rect: LayoutRect {
                x,
                y,
                width: w,
                height: h,
            },
        });
    }

    /// Remove a window.
    pub fn remove_window(&mut self, window_id: WindowId) {
        self.windows.retain(|w| w.window_id != window_id);
    }

    /// Move/resize a window.
    pub fn set_geometry(&mut self, window_id: WindowId, rect: LayoutRect) {
        if let Some(w) = self.windows.iter_mut().find(|w| w.window_id == window_id) {
            w.rect = rect;
        }
    }

    /// Raise a window to the top of the z-stack.
    pub fn raise(&mut self, window_id: WindowId) {
        if let Some(idx) = self.windows.iter().position(|w| w.window_id == window_id) {
            let w = self.windows.remove(idx);
            self.windows.push(w);
        }
    }

    /// Get all window positions in z-order.
    pub fn calculate_layout(&self) -> Vec<(WindowId, LayoutRect)> {
        self.windows
            .iter()
            .map(|w| (w.window_id, w.rect))
            .collect()
    }

    pub fn contains(&self, window_id: WindowId) -> bool {
        self.windows.iter().any(|w| w.window_id == window_id)
    }

    pub fn is_empty(&self) -> bool {
        self.windows.is_empty()
    }
}

impl Default for FloatingLayout {
    fn default() -> Self {
        Self::new()
    }
}
