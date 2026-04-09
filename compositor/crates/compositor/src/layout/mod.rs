//! Hybrid tiling/floating layout engine.
//!
//! Each window is either tiled (managed by the n-ary tree) or floating
//! (manually positioned). Dialogs auto-float. Users can toggle with Super+F.

pub mod floating;
pub mod tiling;

use floating::FloatingLayout;
use tiling::TilingLayout;

/// A compositor window ID (matches the Smithay Space element order).
pub type WindowId = u64;

/// A layout rectangle.
#[derive(Debug, Clone, Copy)]
pub struct LayoutRect {
    pub x: i32,
    pub y: i32,
    pub width: i32,
    pub height: i32,
}

/// The hybrid layout engine.
pub struct LayoutEngine {
    pub tiling: TilingLayout,
    pub floating: FloatingLayout,
    pub focused_window: Option<WindowId>,
}

impl LayoutEngine {
    pub fn new() -> Self {
        Self {
            tiling: TilingLayout::new(),
            floating: FloatingLayout::new(),
            focused_window: None,
        }
    }

    /// Add a window to the tiling layout.
    pub fn add_tiled(&mut self, window_id: WindowId) {
        self.tiling.add_window(window_id, self.focused_window);
    }

    /// Add a window to the floating layout.
    pub fn add_floating(&mut self, window_id: WindowId, area: LayoutRect) {
        self.floating.add_window(window_id, area);
    }

    /// Remove a window from whichever layout contains it.
    pub fn remove(&mut self, window_id: WindowId) {
        if self.floating.contains(window_id) {
            self.floating.remove_window(window_id);
        } else {
            self.tiling.remove_window(window_id);
        }
        if self.focused_window == Some(window_id) {
            self.focused_window = None;
        }
    }

    /// Toggle a window between tiling and floating.
    pub fn toggle_floating(&mut self, window_id: WindowId, area: LayoutRect) {
        if self.floating.contains(window_id) {
            // Move to tiling
            self.floating.remove_window(window_id);
            self.tiling.add_window(window_id, self.focused_window);
        } else {
            // Move to floating
            self.tiling.remove_window(window_id);
            self.floating.add_window(window_id, area);
        }
    }

    /// Is this window floating?
    pub fn is_floating(&self, window_id: WindowId) -> bool {
        self.floating.contains(window_id)
    }

    /// Set the focused window (affects where new tiled windows split).
    pub fn set_focused(&mut self, window_id: Option<WindowId>) {
        self.focused_window = window_id;
    }

    /// Calculate all window positions for the given output area.
    /// Returns tiled windows first, then floating on top.
    pub fn calculate_layout(&self, area: LayoutRect) -> Vec<(WindowId, LayoutRect)> {
        let mut result = self.tiling.calculate_layout(area);
        result.extend(self.floating.calculate_layout());
        result
    }

    /// Raise a floating window to the top.
    pub fn raise_floating(&mut self, window_id: WindowId) {
        self.floating.raise(window_id);
    }

    /// Set geometry for a floating window.
    pub fn set_floating_geometry(&mut self, window_id: WindowId, rect: LayoutRect) {
        self.floating.set_geometry(window_id, rect);
    }
}

impl Default for LayoutEngine {
    fn default() -> Self {
        Self::new()
    }
}
