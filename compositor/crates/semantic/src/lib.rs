//! # aulinx-semantic
//!
//! AI-native semantic desktop understanding.
//!
//! This crate provides the core technology behind Aulinx's AI-native desktop:
//! a **semantic scene graph** that represents everything visible on the desktop
//! with meaning, not just pixels.
//!
//! Instead of screenshotting the desktop and sending it to a vision model
//! (1,200-5,000 tokens per perception), the AI queries the scene graph
//! directly (~50 tokens). Instead of re-perceiving everything from scratch,
//! the AI subscribes to semantic events ("dialog appeared", "text changed").
//!
//! ## Architecture
//!
//! ```text
//! ┌─────────────┐  ┌──────────────────┐  ┌───────────────┐
//! │  AT-SPI      │  │ Compositor IPC   │  │ Direct Source  │
//! │  (any WM)    │  │ (Sway/Hyprland)  │  │ (aulinx-comp) │
//! └──────┬───────┘  └───────┬──────────┘  └───────┬───────┘
//!        │                  │                     │
//!        └──────────────────┼─────────────────────┘
//!                           │
//!                    ┌──────▼──────┐
//!                    │ Scene Graph │
//!                    │  (graph.rs) │
//!                    └──────┬──────┘
//!                           │
//!              ┌────────────┼────────────┐
//!              │            │            │
//!        ┌─────▼─────┐ ┌───▼───┐ ┌──────▼──────┐
//!        │  Queries   │ │ Diffs │ │   Actions   │
//!        │ (query.rs) │ │(.rs)  │ │ (action.rs) │
//!        └────────────┘ └───────┘ └─────────────┘
//! ```
//!
//! ## Usage
//!
//! This crate is used in two ways:
//! - As a library by `aulinx-compositor` (direct integration)
//! - As a library by `aulinx-semanticd` (standalone daemon)

pub mod action;
pub mod diff;
pub mod graph;
pub mod node;
pub mod protocol;
pub mod query;
pub mod sources;

#[cfg(test)]
mod tests;

// Re-export key types for convenience
pub use graph::SceneGraph;
pub use node::{ActionType, ElementRole, ElementState, NodeId, Rect, SemanticNode};
pub use diff::{DiffTracker, EventFilter, SemanticEvent};
pub use action::{ActionRequest, ActionResult};
