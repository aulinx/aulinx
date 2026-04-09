#[cfg(test)]
mod tests {
    use crate::diff::{DiffTracker, EventFilter, SemanticEvent};
    use crate::graph::SceneGraph;
    use crate::node::*;
    use crate::query;

    // ---- SceneGraph basics ----

    #[test]
    fn new_graph_has_root() {
        let g = SceneGraph::new();
        assert_eq!(g.len(), 1); // root Desktop node
        assert!(g.is_empty()); // "empty" means only root
        assert!(matches!(g.root(), SemanticNode::Desktop { .. }));
    }

    #[test]
    fn add_screen_and_window() {
        let mut g = SceneGraph::new();
        let screen = g.add_screen("HDMI-1", Rect::new(0, 0, 1920, 1080));
        let win = g.add_window(screen, 1, 1000, "foot", "Terminal", Rect::new(0, 0, 960, 1080));

        assert_eq!(g.len(), 3); // root + screen + window
        assert!(!g.is_empty());

        // Window lookup by compositor ID
        let w = g.window(1).unwrap();
        match w {
            SemanticNode::Window { title, app_id, .. } => {
                assert_eq!(title, "Terminal");
                assert_eq!(app_id, "foot");
            }
            _ => panic!("expected Window node"),
        }

        // Node ID lookup
        assert_eq!(g.window_node_id(1), Some(win));
        assert_eq!(g.window_node_id(999), None);
    }

    #[test]
    fn add_elements_to_window() {
        let mut g = SceneGraph::new();
        let screen = g.add_screen("default", Rect::new(0, 0, 1920, 1080));
        let win = g.add_window(screen, 1, 100, "firefox", "GitHub", Rect::new(0, 0, 1200, 800));

        let toolbar = g.add_element(win, ElementRole::Toolbar, "Navigation", vec![]);
        let _btn = g.add_child_element(toolbar, ElementRole::Button, "Back", vec![ActionType::Activate]);
        let _btn2 = g.add_child_element(toolbar, ElementRole::Button, "Forward", vec![ActionType::Activate]);
        let _field = g.add_element(win, ElementRole::TextField, "URL", vec![ActionType::SetValue, ActionType::Focus]);

        // root + screen + window + toolbar + 2 buttons + text field = 7
        assert_eq!(g.len(), 7);
    }

    #[test]
    fn remove_window_cleans_up_elements() {
        let mut g = SceneGraph::new();
        let screen = g.add_screen("default", Rect::new(0, 0, 1920, 1080));
        let win = g.add_window(screen, 1, 100, "app", "Window", Rect::new(0, 0, 800, 600));
        let toolbar = g.add_element(win, ElementRole::Toolbar, "Toolbar", vec![]);
        let _btn = g.add_child_element(toolbar, ElementRole::Button, "OK", vec![ActionType::Activate]);

        assert_eq!(g.len(), 5); // root + screen + window + toolbar + button
        g.remove_window(1);
        assert_eq!(g.len(), 2); // root + screen
        assert!(g.window(1).is_none());
    }

    #[test]
    fn multiple_windows() {
        let mut g = SceneGraph::new();
        let screen = g.add_screen("default", Rect::new(0, 0, 1920, 1080));
        g.add_window(screen, 1, 100, "foot", "Terminal", Rect::new(0, 0, 960, 1080));
        g.add_window(screen, 2, 200, "firefox", "Browser", Rect::new(960, 0, 960, 1080));

        let wins = g.windows();
        assert_eq!(wins.len(), 2);
    }

    // ---- Focus ----

    #[test]
    fn focus_tracking() {
        let mut g = SceneGraph::new();
        let screen = g.add_screen("default", Rect::new(0, 0, 1920, 1080));
        g.add_window(screen, 1, 100, "foot", "Terminal", Rect::new(0, 0, 960, 1080));
        g.add_window(screen, 2, 200, "firefox", "Browser", Rect::new(960, 0, 960, 1080));

        assert_eq!(g.focused(), (None, None));

        g.set_focused_window(Some(1));
        assert_eq!(g.focused().0, Some(1));

        // Verify the window node's focused flag is set
        match g.window(1).unwrap() {
            SemanticNode::Window { focused, .. } => assert!(*focused),
            _ => panic!(),
        }
        match g.window(2).unwrap() {
            SemanticNode::Window { focused, .. } => assert!(!*focused),
            _ => panic!(),
        }

        // Switch focus
        g.set_focused_window(Some(2));
        match g.window(1).unwrap() {
            SemanticNode::Window { focused, .. } => assert!(!*focused),
            _ => panic!(),
        }
        match g.window(2).unwrap() {
            SemanticNode::Window { focused, .. } => assert!(*focused),
            _ => panic!(),
        }
    }

    // ---- Find / Query ----

    #[test]
    fn find_by_text() {
        let mut g = SceneGraph::new();
        let screen = g.add_screen("default", Rect::new(0, 0, 1920, 1080));
        let win = g.add_window(screen, 1, 100, "app", "My App", Rect::new(0, 0, 800, 600));
        g.add_element(win, ElementRole::Button, "Save", vec![ActionType::Activate]);
        g.add_element(win, ElementRole::Button, "Cancel", vec![ActionType::Activate]);
        g.add_element(win, ElementRole::Button, "Save As", vec![ActionType::Activate]);

        let results = g.find("save");
        assert_eq!(results.len(), 2); // "Save" and "Save As"

        let results = g.find("cancel");
        assert_eq!(results.len(), 1);

        let results = g.find("nonexistent");
        assert_eq!(results.len(), 0);

        // Window title search
        let results = g.find("My App");
        assert_eq!(results.len(), 1);
    }

    #[test]
    fn find_by_role() {
        let mut g = SceneGraph::new();
        let screen = g.add_screen("default", Rect::new(0, 0, 1920, 1080));
        let win = g.add_window(screen, 1, 100, "app", "App", Rect::new(0, 0, 800, 600));
        g.add_element(win, ElementRole::Button, "OK", vec![ActionType::Activate]);
        g.add_element(win, ElementRole::Button, "Cancel", vec![ActionType::Activate]);
        g.add_element(win, ElementRole::TextField, "Name", vec![ActionType::SetValue]);

        let buttons = g.find_by_role(&ElementRole::Button);
        assert_eq!(buttons.len(), 2);

        let fields = g.find_by_role(&ElementRole::TextField);
        assert_eq!(fields.len(), 1);

        let menus = g.find_by_role(&ElementRole::Menu);
        assert_eq!(menus.len(), 0);
    }

    // ---- JSON serialization ----

    #[test]
    fn to_json_includes_children() {
        let mut g = SceneGraph::new();
        let screen = g.add_screen("default", Rect::new(0, 0, 1920, 1080));
        let win = g.add_window(screen, 1, 100, "foot", "Terminal", Rect::new(0, 0, 800, 600));
        g.add_element(win, ElementRole::Button, "Close", vec![ActionType::Activate]);

        let json = g.to_json();
        let screens = json["screens"].as_array().unwrap();
        assert_eq!(screens.len(), 1);

        let windows = screens[0]["windows"].as_array().unwrap();
        assert_eq!(windows.len(), 1);
        assert_eq!(windows[0]["title"], "Terminal");

        let elements = windows[0]["elements"].as_array().unwrap();
        assert_eq!(elements.len(), 1);
        assert_eq!(elements[0]["label"], "Close");
    }

    #[test]
    fn window_to_json() {
        let mut g = SceneGraph::new();
        let screen = g.add_screen("default", Rect::new(0, 0, 1920, 1080));
        g.add_window(screen, 1, 100, "foot", "Terminal", Rect::new(0, 0, 800, 600));
        g.add_window(screen, 2, 200, "firefox", "Browser", Rect::new(800, 0, 800, 600));

        let json = g.window_to_json(1).unwrap();
        assert_eq!(json["app_id"], "foot");

        let json = g.window_to_json(2).unwrap();
        assert_eq!(json["app_id"], "firefox");

        assert!(g.window_to_json(999).is_none());
    }

    // ---- Query engine (JSON-RPC dispatch) ----

    #[test]
    fn query_scene_graph() {
        let mut g = SceneGraph::new();
        let screen = g.add_screen("default", Rect::new(0, 0, 1920, 1080));
        g.add_window(screen, 1, 100, "foot", "Terminal", Rect::new(0, 0, 800, 600));

        let result = query::execute_query(&g, "scene.graph", &serde_json::json!({})).unwrap();
        assert!(result["screens"].is_array());
    }

    #[test]
    fn query_scene_find() {
        let mut g = SceneGraph::new();
        let screen = g.add_screen("default", Rect::new(0, 0, 1920, 1080));
        let win = g.add_window(screen, 1, 100, "app", "App", Rect::new(0, 0, 800, 600));
        g.add_element(win, ElementRole::Button, "Save", vec![ActionType::Activate]);

        let result = query::execute_query(
            &g,
            "scene.find",
            &serde_json::json!({"query": "Save"}),
        )
        .unwrap();
        let arr = result.as_array().unwrap();
        assert_eq!(arr.len(), 1);
        assert_eq!(arr[0]["label"], "Save");
        assert!(arr[0]["node_id"].is_object() || arr[0]["node_id"].is_number());
    }

    #[test]
    fn query_scene_focused() {
        let mut g = SceneGraph::new();
        let screen = g.add_screen("default", Rect::new(0, 0, 1920, 1080));
        g.add_window(screen, 1, 100, "foot", "Terminal", Rect::new(0, 0, 800, 600));
        g.set_focused_window(Some(1));

        let result = query::execute_query(&g, "scene.focused", &serde_json::json!({})).unwrap();
        assert_eq!(result["window_id"], 1);
    }

    #[test]
    fn query_unknown_method() {
        let g = SceneGraph::new();
        let result = query::execute_query(&g, "bogus.method", &serde_json::json!({}));
        assert!(result.is_err());
    }

    // ---- Diff engine ----

    #[test]
    fn diff_detects_window_opened() {
        let mut g = SceneGraph::new();
        let screen = g.add_screen("default", Rect::new(0, 0, 1920, 1080));

        let mut tracker = DiffTracker::new();
        g.snapshot(&mut tracker);

        // Add a window
        g.add_window(screen, 1, 100, "foot", "Terminal", Rect::new(0, 0, 800, 600));

        let events = g.diff(&tracker);
        assert!(events.iter().any(|e| matches!(
            e,
            SemanticEvent::WindowOpened { window_id: 1, .. }
        )));
    }

    #[test]
    fn diff_detects_window_closed() {
        let mut g = SceneGraph::new();
        let screen = g.add_screen("default", Rect::new(0, 0, 1920, 1080));
        g.add_window(screen, 1, 100, "foot", "Terminal", Rect::new(0, 0, 800, 600));

        let mut tracker = DiffTracker::new();
        g.snapshot(&mut tracker);

        g.remove_window(1);

        let events = g.diff(&tracker);
        assert!(events.iter().any(|e| matches!(
            e,
            SemanticEvent::WindowClosed { window_id: 1 }
        )));
    }

    #[test]
    fn diff_detects_title_change() {
        let mut g = SceneGraph::new();
        let screen = g.add_screen("default", Rect::new(0, 0, 1920, 1080));
        g.add_window(screen, 1, 100, "foot", "Terminal", Rect::new(0, 0, 800, 600));

        let mut tracker = DiffTracker::new();
        g.snapshot(&mut tracker);

        // Change title
        let node_id = g.window_node_id(1).unwrap();
        if let Some(SemanticNode::Window { title, .. }) = g.get_mut(node_id) {
            *title = "Terminal — vim".to_string();
        }

        let events = g.diff(&tracker);
        assert!(events.iter().any(|e| matches!(
            e,
            SemanticEvent::WindowTitleChanged {
                window_id: 1,
                ref old,
                ref new,
            } if old == "Terminal" && new == "Terminal — vim"
        )));
    }

    #[test]
    fn diff_detects_focus_change() {
        let mut g = SceneGraph::new();
        let screen = g.add_screen("default", Rect::new(0, 0, 1920, 1080));
        g.add_window(screen, 1, 100, "foot", "Terminal", Rect::new(0, 0, 960, 1080));
        g.add_window(screen, 2, 200, "firefox", "Browser", Rect::new(960, 0, 960, 1080));

        let mut tracker = DiffTracker::new();
        g.snapshot(&mut tracker);

        g.set_focused_window(Some(1));

        let events = g.diff(&tracker);
        assert!(events.iter().any(|e| matches!(
            e,
            SemanticEvent::WindowFocused { window_id: 1 }
        )));
    }

    #[test]
    fn diff_detects_window_move() {
        let mut g = SceneGraph::new();
        let screen = g.add_screen("default", Rect::new(0, 0, 1920, 1080));
        g.add_window(screen, 1, 100, "foot", "Terminal", Rect::new(0, 0, 800, 600));

        let mut tracker = DiffTracker::new();
        g.snapshot(&mut tracker);

        let node_id = g.window_node_id(1).unwrap();
        if let Some(SemanticNode::Window { geometry, .. }) = g.get_mut(node_id) {
            *geometry = Rect::new(100, 100, 800, 600);
        }

        let events = g.diff(&tracker);
        assert!(events.iter().any(|e| matches!(
            e,
            SemanticEvent::WindowMoved { window_id: 1, .. }
        )));
    }

    #[test]
    fn diff_detects_element_appeared() {
        let mut g = SceneGraph::new();
        let screen = g.add_screen("default", Rect::new(0, 0, 1920, 1080));
        let win = g.add_window(screen, 1, 100, "app", "App", Rect::new(0, 0, 800, 600));

        let mut tracker = DiffTracker::new();
        g.snapshot(&mut tracker);

        g.add_element(win, ElementRole::Button, "Save", vec![ActionType::Activate]);

        let events = g.diff(&tracker);
        assert!(events.iter().any(|e| matches!(
            e,
            SemanticEvent::ElementAppeared {
                window_id: 1,
                ref label,
                ..
            } if label == "Save"
        )));
    }

    #[test]
    fn diff_no_changes_produces_no_events() {
        let mut g = SceneGraph::new();
        let screen = g.add_screen("default", Rect::new(0, 0, 1920, 1080));
        g.add_window(screen, 1, 100, "foot", "Terminal", Rect::new(0, 0, 800, 600));

        let mut tracker = DiffTracker::new();
        g.snapshot(&mut tracker);

        // No changes
        let events = g.diff(&tracker);
        assert!(events.is_empty());
    }

    // ---- EventFilter ----

    #[test]
    fn filter_wildcard_matches_all() {
        let f = EventFilter::new("*");
        let event = SemanticEvent::WindowOpened {
            window_id: 1,
            app_id: "test".into(),
            title: "Test".into(),
        };
        assert!(f.matches(&event));
    }

    #[test]
    fn filter_exact_match() {
        let f = EventFilter::new("window.opened");
        assert!(f.matches(&SemanticEvent::WindowOpened {
            window_id: 1,
            app_id: "test".into(),
            title: "Test".into(),
        }));
        assert!(!f.matches(&SemanticEvent::WindowClosed { window_id: 1 }));
    }

    #[test]
    fn filter_prefix_match() {
        let f = EventFilter::new("window.*");
        assert!(f.matches(&SemanticEvent::WindowOpened {
            window_id: 1,
            app_id: "test".into(),
            title: "Test".into(),
        }));
        assert!(f.matches(&SemanticEvent::WindowClosed { window_id: 1 }));
        assert!(f.matches(&SemanticEvent::WindowFocused { window_id: 1 }));
        assert!(!f.matches(&SemanticEvent::ElementAppeared {
            window_id: 1,
            node_id: NodeId(5),
            role: ElementRole::Button,
            label: "OK".into(),
        }));
    }

    #[test]
    fn filter_element_prefix() {
        let f = EventFilter::new("element.*");
        assert!(f.matches(&SemanticEvent::ElementAppeared {
            window_id: 1,
            node_id: NodeId(5),
            role: ElementRole::Button,
            label: "OK".into(),
        }));
        assert!(f.matches(&SemanticEvent::ElementChanged {
            window_id: 1,
            node_id: NodeId(5),
            property: "label".into(),
            old: serde_json::Value::String("old".into()),
            new: serde_json::Value::String("new".into()),
        }));
        assert!(!f.matches(&SemanticEvent::WindowOpened {
            window_id: 1,
            app_id: "test".into(),
            title: "Test".into(),
        }));
    }

    // ---- Rect ----

    #[test]
    fn rect_contains() {
        let r = Rect::new(10, 20, 100, 50);
        assert!(r.contains(10, 20));  // top-left corner
        assert!(r.contains(50, 40));  // middle
        assert!(r.contains(109, 69)); // just inside bottom-right
        assert!(!r.contains(110, 70)); // just outside
        assert!(!r.contains(9, 20));   // just left
        assert!(!r.contains(10, 19));  // just above
    }

    // ---- ElementState ----

    #[test]
    fn element_state_default() {
        let s = ElementState::default();
        assert!(s.enabled);
        assert!(s.visible);
        assert!(!s.focused);
        assert!(!s.selected);
        assert!(!s.editable);
        assert_eq!(s.checked, None);
        assert_eq!(s.expanded, None);
    }

    // ---- Serde roundtrip ----

    #[test]
    fn semantic_node_serde_roundtrip() {
        let node = SemanticNode::Element {
            role: ElementRole::Button,
            label: "Save".to_string(),
            value: None,
            state: ElementState::default(),
            bounds: Rect::new(10, 20, 80, 30),
            actions: vec![ActionType::Activate],
            children: vec![],
        };

        let json = serde_json::to_string(&node).unwrap();
        let parsed: SemanticNode = serde_json::from_str(&json).unwrap();

        match parsed {
            SemanticNode::Element { label, role, .. } => {
                assert_eq!(label, "Save");
                assert_eq!(role, ElementRole::Button);
            }
            _ => panic!("expected Element"),
        }
    }

    #[test]
    fn semantic_event_serde_roundtrip() {
        let event = SemanticEvent::WindowOpened {
            window_id: 42,
            app_id: "firefox".to_string(),
            title: "GitHub".to_string(),
        };

        let json = serde_json::to_string(&event).unwrap();
        assert!(json.contains("\"event\":\"window_opened\""));

        let parsed: SemanticEvent = serde_json::from_str(&json).unwrap();
        match parsed {
            SemanticEvent::WindowOpened {
                window_id,
                app_id,
                title,
            } => {
                assert_eq!(window_id, 42);
                assert_eq!(app_id, "firefox");
                assert_eq!(title, "GitHub");
            }
            _ => panic!("expected WindowOpened"),
        }
    }
}
