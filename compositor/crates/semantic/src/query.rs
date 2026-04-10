//! Query engine — structured access to the scene graph.
//!
//! The query module provides the JSON-RPC-facing query interface.
//! Each method maps to an IPC command (scene.graph, scene.find, etc.).

use serde_json::Value;

use crate::graph::SceneGraph;
use crate::node::ElementRole;

/// Execute a query against the scene graph and return a JSON result.
pub fn execute_query(graph: &SceneGraph, method: &str, params: &Value) -> Result<Value, String> {
    match method {
        "scene.graph" => Ok(graph.to_json()),

        "scene.windows" => {
            let windows: Vec<Value> = graph
                .windows()
                .iter()
                .map(|w| serde_json::to_value(w).unwrap_or(Value::Null))
                .collect();
            Ok(Value::Array(windows))
        }

        "scene.window" => {
            let window_id = params
                .get("window_id")
                .and_then(|v| v.as_u64())
                .ok_or("missing window_id parameter")?;
            graph
                .window_to_json(window_id)
                .ok_or_else(|| format!("window {} not found", window_id))
        }

        "scene.find" => {
            let query = params
                .get("query")
                .and_then(|v| v.as_str())
                .ok_or("missing query parameter")?;
            let results: Vec<Value> = graph
                .find(query)
                .iter()
                .map(|(id, node)| {
                    let mut val = serde_json::to_value(node).unwrap_or(Value::Null);
                    if let Value::Object(ref mut map) = val {
                        map.insert("node_id".to_string(), serde_json::to_value(id).unwrap());
                    }
                    val
                })
                .collect();
            Ok(Value::Array(results))
        }

        "scene.find_by_role" => {
            let role_str = params
                .get("role")
                .and_then(|v| v.as_str())
                .ok_or("missing role parameter")?;
            let role: ElementRole =
                serde_json::from_value(Value::String(role_str.to_string()))
                    .map_err(|e| format!("invalid role: {}", e))?;
            let results: Vec<Value> = graph
                .find_by_role(&role)
                .iter()
                .map(|(id, node)| {
                    let mut val = serde_json::to_value(node).unwrap_or(Value::Null);
                    if let Value::Object(ref mut map) = val {
                        map.insert("node_id".to_string(), serde_json::to_value(id).unwrap());
                    }
                    val
                })
                .collect();
            Ok(Value::Array(results))
        }

        "scene.focused" => {
            let (window_id, element_id) = graph.focused();
            let window_data = window_id.and_then(|id| graph.window_to_json(id));
            Ok(serde_json::json!({
                "window_id": window_id,
                "element_id": element_id,
                "window": window_data,
            }))
        }

        "scene.window_count" => {
            Ok(serde_json::json!({"count": graph.windows().len()}))
        }

        "scene.find_window" => {
            let title = params.get("title").and_then(|v| v.as_str()).unwrap_or("");
            let app_id = params.get("app_id").and_then(|v| v.as_str()).unwrap_or("");
            let matches: Vec<Value> = graph
                .windows()
                .iter()
                .filter_map(|w| {
                    let val = serde_json::to_value(w).ok()?;
                    let w_title = val.get("title").and_then(|v| v.as_str()).unwrap_or("");
                    let w_app = val.get("app_id").and_then(|v| v.as_str()).unwrap_or("");
                    let title_match = title.is_empty() || w_title.to_lowercase().contains(&title.to_lowercase());
                    let app_match = app_id.is_empty() || w_app.to_lowercase().contains(&app_id.to_lowercase());
                    if title_match && app_match { Some(val) } else { None }
                })
                .collect();
            Ok(Value::Array(matches))
        }

        _ => Err(format!("unknown query method: {}", method)),
    }
}
