//! Semantic actions — intent-based interaction with UI elements.
//!
//! Instead of "click at pixel (423, 187)", the AI says
//! "activate the Save button". The action system maps semantic
//! intents to concrete operations via the active Source.

use crate::node::{ActionType, NodeId};

/// A request to perform a semantic action on an element.
#[derive(Debug, Clone)]
pub struct ActionRequest {
    pub node_id: NodeId,
    pub action: ActionType,
    pub value: Option<String>,
}

/// Result of executing an action.
#[derive(Debug)]
pub enum ActionResult {
    /// Action completed successfully.
    Success,
    /// The element does not support this action.
    NotSupported,
    /// The element was not found.
    NotFound,
    /// The action failed with a reason.
    Failed(String),
}
