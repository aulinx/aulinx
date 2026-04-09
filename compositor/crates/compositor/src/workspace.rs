//! Workspace management — Super+1..9 switching.

use crate::layout::{LayoutEngine, WindowId};

/// A workspace containing its own layout engine.
pub struct Workspace {
    pub index: usize,
    pub name: String,
    pub layout: LayoutEngine,
    pub windows: Vec<WindowId>,
}

impl Workspace {
    pub fn new(index: usize) -> Self {
        Self {
            index,
            name: format!("{}", index + 1),
            layout: LayoutEngine::new(),
            windows: Vec::new(),
        }
    }

    pub fn add_window(&mut self, window_id: WindowId, is_dialog: bool) {
        self.windows.push(window_id);
        if is_dialog {
            self.layout.add_floating(
                window_id,
                crate::layout::LayoutRect {
                    x: 0,
                    y: 0,
                    width: 1920,
                    height: 1080,
                },
            );
        } else {
            self.layout.add_tiled(window_id);
        }
    }

    pub fn remove_window(&mut self, window_id: WindowId) {
        self.windows.retain(|&id| id != window_id);
        self.layout.remove(window_id);
    }

    pub fn contains(&self, window_id: WindowId) -> bool {
        self.windows.contains(&window_id)
    }
}

/// Manages multiple workspaces.
pub struct WorkspaceManager {
    pub workspaces: Vec<Workspace>,
    pub active: usize,
}

impl WorkspaceManager {
    pub fn new(count: usize) -> Self {
        let workspaces = (0..count).map(Workspace::new).collect();
        Self {
            workspaces,
            active: 0,
        }
    }

    pub fn active_workspace(&self) -> &Workspace {
        &self.workspaces[self.active]
    }

    pub fn active_workspace_mut(&mut self) -> &mut Workspace {
        &mut self.workspaces[self.active]
    }

    /// Switch to a workspace by index (0-based).
    pub fn switch_to(&mut self, index: usize) -> bool {
        if index < self.workspaces.len() && index != self.active {
            self.active = index;
            true
        } else {
            false
        }
    }

    /// Move a window to a different workspace.
    pub fn move_window_to(&mut self, window_id: WindowId, target: usize) -> bool {
        if target >= self.workspaces.len() {
            return false;
        }

        // Find which workspace has this window
        let source = self
            .workspaces
            .iter()
            .position(|ws| ws.contains(window_id));

        if let Some(source_idx) = source {
            if source_idx == target {
                return false;
            }
            self.workspaces[source_idx].remove_window(window_id);
            self.workspaces[target].add_window(window_id, false);
            true
        } else {
            false
        }
    }

    /// Find which workspace contains a window.
    pub fn find_window(&self, window_id: WindowId) -> Option<usize> {
        self.workspaces
            .iter()
            .position(|ws| ws.contains(window_id))
    }
}
