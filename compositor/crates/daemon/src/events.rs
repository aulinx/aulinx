//! Subscription management for semantic event streaming.
//!
//! Clients subscribe with a filter pattern (e.g., "window.*", "element.changed", "*").
//! When semantic events are detected by the diff engine, matching events are
//! pushed to subscribed clients as JSON-RPC notifications.

use std::collections::HashMap;

use aulinx_semantic::diff::{EventFilter, SemanticEvent};

/// A single subscription.
struct Subscription {
    id: u64,
    client_id: u64,
    filter: EventFilter,
}

/// Manages event subscriptions for all connected clients.
pub struct SubscriptionManager {
    subscriptions: HashMap<u64, Subscription>,
    next_id: u64,
}

impl SubscriptionManager {
    pub fn new() -> Self {
        Self {
            subscriptions: HashMap::new(),
            next_id: 1,
        }
    }

    /// Subscribe a client to events matching the given filter pattern.
    /// Returns the subscription ID.
    pub fn subscribe(&mut self, client_id: u64, filter_pattern: &str) -> u64 {
        let id = self.next_id;
        self.next_id += 1;

        self.subscriptions.insert(
            id,
            Subscription {
                id,
                client_id,
                filter: EventFilter::new(filter_pattern),
            },
        );

        tracing::debug!(
            "Client {client_id} subscribed with filter '{filter_pattern}' (sub_id={id})"
        );
        id
    }

    /// Remove a subscription by ID.
    pub fn unsubscribe(&mut self, subscription_id: u64) {
        if self.subscriptions.remove(&subscription_id).is_some() {
            tracing::debug!("Subscription {subscription_id} removed");
        }
    }

    /// Remove all subscriptions for a disconnected client.
    pub fn remove_client(&mut self, client_id: u64) {
        let before = self.subscriptions.len();
        self.subscriptions
            .retain(|_, sub| sub.client_id != client_id);
        let removed = before - self.subscriptions.len();
        if removed > 0 {
            tracing::debug!("Removed {removed} subscriptions for client {client_id}");
        }
    }

    /// Match a list of events against all subscriptions.
    /// Returns (client_id, serialized JSON notification) pairs.
    pub fn match_events(&self, events: &[SemanticEvent]) -> Vec<(u64, String)> {
        let mut notifications = Vec::new();

        for event in events {
            for sub in self.subscriptions.values() {
                if sub.filter.matches(event) {
                    // Format as JSON-RPC notification (no id)
                    let notification = serde_json::json!({
                        "jsonrpc": "2.0",
                        "method": "scene.event",
                        "params": event,
                    });
                    if let Ok(json) = serde_json::to_string(&notification) {
                        notifications.push((sub.client_id, json));
                    }
                }
            }
        }

        notifications
    }

    /// Number of active subscriptions.
    pub fn len(&self) -> usize {
        self.subscriptions.len()
    }

    pub fn is_empty(&self) -> bool {
        self.subscriptions.is_empty()
    }
}
