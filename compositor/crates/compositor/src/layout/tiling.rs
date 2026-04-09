//! N-ary tree tiling layout (COSMIC pattern).
//!
//! The tree has two node types:
//! - `Group`: internal node with a split direction and sized children
//! - `Leaf`: a window reference
//!
//! When a window is added, the focused leaf splits. When removed,
//! the empty slot merges with its sibling.

use id_tree::{InsertBehavior, Node, NodeId, Tree, TreeBuilder};

use super::{LayoutRect, WindowId};

/// Split direction for a group node.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum SplitDirection {
    Horizontal,
    Vertical,
}

impl SplitDirection {
    pub fn toggle(self) -> Self {
        match self {
            SplitDirection::Horizontal => SplitDirection::Vertical,
            SplitDirection::Vertical => SplitDirection::Horizontal,
        }
    }
}

/// Data stored in each tree node.
#[derive(Debug, Clone)]
pub enum TilingNode {
    Group {
        direction: SplitDirection,
        /// Relative sizes of children (sum to 1.0).
        ratios: Vec<f32>,
    },
    Leaf {
        window_id: WindowId,
    },
}

/// The tiling layout tree.
pub struct TilingLayout {
    tree: Tree<TilingNode>,
    root_id: Option<NodeId>,
    /// Alternating split direction for new insertions.
    next_direction: SplitDirection,
}

impl TilingLayout {
    pub fn new() -> Self {
        Self {
            tree: TreeBuilder::new().build(),
            root_id: None,
            next_direction: SplitDirection::Horizontal,
        }
    }

    /// Add a window to the layout. Splits at the focused position.
    pub fn add_window(&mut self, window_id: WindowId, focused: Option<WindowId>) {
        let new_leaf = TilingNode::Leaf { window_id };

        if self.root_id.is_none() {
            // First window becomes root
            let id = self
                .tree
                .insert(Node::new(new_leaf), InsertBehavior::AsRoot)
                .unwrap();
            self.root_id = Some(id);
            return;
        }

        // Find the focused leaf to split next to
        let split_at = focused
            .and_then(|wid| self.find_leaf(wid))
            .or_else(|| {
                // Default: split at the last leaf
                self.last_leaf()
            });

        let Some(split_node_id) = split_at else {
            return;
        };

        // Replace the focused leaf with a group containing [old_leaf, new_leaf]
        let old_data = self.tree.get(&split_node_id).unwrap().data().clone();
        let direction = self.next_direction;
        self.next_direction = direction.toggle();

        // Change the split node to a group
        *self.tree.get_mut(&split_node_id).unwrap().data_mut() = TilingNode::Group {
            direction,
            ratios: vec![0.5, 0.5],
        };

        // Add the old leaf and new leaf as children
        self.tree
            .insert(
                Node::new(old_data),
                InsertBehavior::UnderNode(&split_node_id),
            )
            .unwrap();
        self.tree
            .insert(
                Node::new(new_leaf),
                InsertBehavior::UnderNode(&split_node_id),
            )
            .unwrap();
    }

    /// Remove a window from the layout.
    pub fn remove_window(&mut self, window_id: WindowId) {
        let Some(leaf_id) = self.find_leaf(window_id) else {
            return;
        };

        let parent_id = self
            .tree
            .get(&leaf_id)
            .ok()
            .and_then(|n| n.parent())
            .cloned();

        // Remove the leaf
        self.tree.remove_node(leaf_id, id_tree::RemoveBehavior::DropChildren).ok();

        // If parent is a group with one child, collapse it
        if let Some(parent_id) = parent_id {
            let children: Vec<NodeId> = self
                .tree
                .children_ids(&parent_id)
                .ok()
                .map(|iter| iter.cloned().collect())
                .unwrap_or_default();

            if children.len() == 1 {
                // Replace parent with its sole remaining child
                let child_id = children[0].clone();
                let child_data = self.tree.get(&child_id).unwrap().data().clone();
                *self.tree.get_mut(&parent_id).unwrap().data_mut() = child_data;

                // Move grandchildren to parent
                let grandchildren: Vec<NodeId> = self
                    .tree
                    .children_ids(&child_id)
                    .ok()
                    .map(|iter| iter.cloned().collect())
                    .unwrap_or_default();

                self.tree
                    .remove_node(child_id, id_tree::RemoveBehavior::LiftChildren)
                    .ok();
            } else if children.is_empty() {
                // Parent is now empty — remove it too if it's not root
                if Some(&parent_id) != self.root_id.as_ref() {
                    self.tree
                        .remove_node(parent_id, id_tree::RemoveBehavior::DropChildren)
                        .ok();
                } else {
                    self.root_id = None;
                    self.tree = TreeBuilder::new().build();
                }
            } else {
                // Update ratios to redistribute space
                if let TilingNode::Group { ratios, .. } =
                    self.tree.get_mut(&parent_id).unwrap().data_mut()
                {
                    let n = children.len();
                    *ratios = vec![1.0 / n as f32; n];
                }
            }
        } else {
            // Removed root
            self.root_id = None;
        }
    }

    /// Calculate rectangles for all windows given the available area.
    pub fn calculate_layout(&self, area: LayoutRect) -> Vec<(WindowId, LayoutRect)> {
        let mut result = Vec::new();
        if let Some(ref root_id) = self.root_id {
            self.layout_node(root_id, area, &mut result);
        }
        result
    }

    fn layout_node(
        &self,
        node_id: &NodeId,
        area: LayoutRect,
        result: &mut Vec<(WindowId, LayoutRect)>,
    ) {
        let node = match self.tree.get(node_id) {
            Ok(n) => n,
            Err(_) => return,
        };

        match node.data() {
            TilingNode::Leaf { window_id } => {
                result.push((*window_id, area));
            }
            TilingNode::Group { direction, ratios } => {
                let children: Vec<NodeId> = self
                    .tree
                    .children_ids(node_id)
                    .ok()
                    .map(|iter| iter.cloned().collect())
                    .unwrap_or_default();

                let mut offset = 0;
                for (i, child_id) in children.iter().enumerate() {
                    let ratio = ratios.get(i).copied().unwrap_or(1.0 / children.len() as f32);
                    let child_area = match direction {
                        SplitDirection::Horizontal => {
                            let w = (area.width as f32 * ratio) as i32;
                            let r = LayoutRect {
                                x: area.x + offset,
                                y: area.y,
                                width: w,
                                height: area.height,
                            };
                            offset += w;
                            r
                        }
                        SplitDirection::Vertical => {
                            let h = (area.height as f32 * ratio) as i32;
                            let r = LayoutRect {
                                x: area.x,
                                y: area.y + offset,
                                width: area.width,
                                height: h,
                            };
                            offset += h;
                            r
                        }
                    };
                    self.layout_node(child_id, child_area, result);
                }
            }
        }
    }

    /// Find the tree node containing a given window.
    fn find_leaf(&self, window_id: WindowId) -> Option<NodeId> {
        self.tree
            .traverse_pre_order_ids(self.root_id.as_ref()?)
            .ok()?
            .find(|id| {
                matches!(
                    self.tree.get(id).map(|n| n.data()),
                    Ok(TilingNode::Leaf { window_id: wid }) if *wid == window_id
                )
            })
            .cloned()
    }

    /// Find the last (rightmost/bottommost) leaf.
    fn last_leaf(&self) -> Option<NodeId> {
        self.tree
            .traverse_post_order_ids(self.root_id.as_ref()?)
            .ok()?
            .find(|id| {
                matches!(
                    self.tree.get(id).map(|n| n.data()),
                    Ok(TilingNode::Leaf { .. })
                )
            })
            .cloned()
    }

    /// Get the number of windows in the layout.
    pub fn window_count(&self) -> usize {
        let Some(ref root_id) = self.root_id else {
            return 0;
        };
        self.tree
            .traverse_pre_order_ids(root_id)
            .ok()
            .map(|iter| {
                iter.filter(|id| {
                    matches!(
                        self.tree.get(id).map(|n| n.data()),
                        Ok(TilingNode::Leaf { .. })
                    )
                })
                .count()
            })
            .unwrap_or(0)
    }

    pub fn is_empty(&self) -> bool {
        self.root_id.is_none()
    }
}

impl Default for TilingLayout {
    fn default() -> Self {
        Self::new()
    }
}
