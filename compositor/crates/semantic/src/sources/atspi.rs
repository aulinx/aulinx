//! AT-SPI source — reads the accessibility tree via D-Bus.
//!
//! This source connects to the AT-SPI accessibility bus and maps
//! accessible nodes to SemanticNodes. Works on any Linux desktop
//! with AT-SPI support (GNOME, KDE, Sway, etc.).
//!
//! AT-SPI uses D-Bus with a dedicated accessibility bus. The registry
//! at `org.a11y.atspi.Registry` lists all accessible applications.
//! Each application exposes a tree of `org.a11y.atspi.Accessible` objects
//! with roles (Button, TextField, etc.), names, states, and actions.
//!
//! Architecture:
//! ```text
//! AT-SPI D-Bus Bus
//!   └── Registry (org.a11y.atspi.Registry)
//!         ├── Application "firefox" (pid 1234)
//!         │     └── Accessible tree: Frame → Panel → Button, TextField, ...
//!         └── Application "foot" (pid 5678)
//!               └── Accessible tree: Frame → Terminal
//! ```

#[cfg(feature = "atspi")]
mod imp {
    use std::collections::HashMap;
    use std::collections::hash_map::DefaultHasher;
    use std::hash::{Hash, Hasher};

    use zbus::blocking::Connection;
    use zbus::zvariant::{OwnedObjectPath, OwnedValue, Value};

    use crate::action::{ActionRequest, ActionResult};
    use crate::graph::SceneGraph;
    use crate::node::*;
    use crate::sources::Source;

    /// AT-SPI accessible role constants (from AT-SPI spec).
    /// These map to the Role enum in org.a11y.atspi.Accessible.
    mod roles {
        pub const ROLE_FRAME: u32 = 22;
        pub const ROLE_DIALOG: u32 = 16;
        pub const ROLE_PUSH_BUTTON: u32 = 42;
        pub const ROLE_TOGGLE_BUTTON: u32 = 73;
        pub const ROLE_TEXT: u32 = 60;
        pub const ROLE_PASSWORD_TEXT: u32 = 39;
        pub const ROLE_LABEL: u32 = 29;
        pub const ROLE_CHECK_BOX: u32 = 7;
        pub const ROLE_RADIO_BUTTON: u32 = 43;
        pub const ROLE_COMBO_BOX: u32 = 11;
        pub const ROLE_MENU: u32 = 32;
        pub const ROLE_MENU_ITEM: u32 = 34;
        pub const ROLE_MENU_BAR: u32 = 33;
        pub const ROLE_PAGE_TAB: u32 = 37;
        pub const ROLE_PAGE_TAB_LIST: u32 = 38;
        pub const ROLE_SCROLL_BAR: u32 = 47;
        pub const ROLE_LIST: u32 = 30;
        pub const ROLE_LIST_ITEM: u32 = 31;
        pub const ROLE_TREE: u32 = 74;
        pub const ROLE_TREE_ITEM: u32 = 87;
        pub const ROLE_TABLE: u32 = 55;
        pub const ROLE_TABLE_CELL: u32 = 56;
        pub const ROLE_TOOL_BAR: u32 = 72;
        pub const ROLE_STATUS_BAR: u32 = 53;
        pub const ROLE_PROGRESS_BAR: u32 = 41;
        pub const ROLE_IMAGE: u32 = 26;
        pub const ROLE_LINK: u32 = 80;
        pub const ROLE_HEADING: u32 = 81;
        pub const ROLE_PARAGRAPH: u32 = 82;
        pub const ROLE_SEPARATOR: u32 = 48;
        pub const ROLE_SLIDER: u32 = 50;
        pub const ROLE_SPIN_BUTTON: u32 = 52;
        pub const ROLE_PANEL: u32 = 73;
        pub const ROLE_FILLER: u32 = 21;
        pub const ROLE_ALERT: u32 = 1;
        pub const ROLE_SCROLL_PANE: u32 = 49;
        pub const ROLE_APPLICATION: u32 = 75;
    }

    /// AT-SPI state bit indices.
    mod states {
        pub const STATE_ENABLED: u32 = 17;
        pub const STATE_VISIBLE: u32 = 29;
        pub const STATE_SHOWING: u32 = 23;
        pub const STATE_FOCUSED: u32 = 12;
        pub const STATE_CHECKED: u32 = 5;
        pub const STATE_EXPANDED: u32 = 9;
        pub const STATE_SELECTED: u32 = 22;
        pub const STATE_EDITABLE: u32 = 8;
    }

    /// An AT-SPI accessible reference (bus name + object path).
    #[derive(Debug, Clone)]
    struct AccessibleRef {
        bus_name: String,
        path: OwnedObjectPath,
    }

    pub struct AtSpiSource {
        connection: Option<Connection>,
        screen_node: Option<NodeId>,
        /// Maps AT-SPI accessible paths to our NodeIds for update tracking.
        path_to_node: HashMap<String, NodeId>,
        /// Max depth when walking the accessibility tree.
        max_depth: usize,
    }

    impl AtSpiSource {
        pub fn new() -> Self {
            Self {
                connection: None,
                screen_node: None,
                path_to_node: HashMap::new(),
                max_depth: 8,
            }
        }

        /// Connect to the AT-SPI accessibility bus.
        fn connect(&mut self) -> Result<(), Box<dyn std::error::Error>> {
            // AT-SPI uses a dedicated bus. Try the accessibility bus first,
            // fall back to the session bus.
            let conn = match Self::connect_a11y_bus() {
                Ok(c) => c,
                Err(e) => {
                    tracing::warn!("AT-SPI bus not available ({e}), trying session bus");
                    Connection::session()?
                }
            };
            self.connection = Some(conn);
            Ok(())
        }

        /// Try to connect to the dedicated AT-SPI bus.
        fn connect_a11y_bus() -> Result<Connection, Box<dyn std::error::Error>> {
            // The AT-SPI bus address is published on the session bus
            // by org.a11y.Bus at /org/a11y/bus, interface org.a11y.Bus, method GetAddress
            let session = Connection::session()?;
            let reply = session.call_method(
                Some("org.a11y.Bus"),
                "/org/a11y/bus",
                Some("org.a11y.Bus"),
                "GetAddress",
                &(),
            )?;
            let address: String = reply.body().deserialize()?;
            let conn = zbus::blocking::connection::Builder::address(address.as_str())?
                .build()?;
            Ok(conn)
        }

        /// Get all accessible applications from the AT-SPI registry.
        fn get_applications(&self) -> Vec<AccessibleRef> {
            let Some(conn) = &self.connection else {
                return Vec::new();
            };

            let reply = match conn.call_method(
                Some("org.a11y.atspi.Registry"),
                "/org/a11y/atspi/accessible/root",
                Some("org.a11y.atspi.Accessible"),
                "GetChildren",
                &(),
            ) {
                Ok(r) => r,
                Err(e) => {
                    tracing::debug!("Failed to get AT-SPI applications: {e}");
                    return Vec::new();
                }
            };

            // Returns array of (bus_name, object_path) tuples
            let children: Vec<(String, OwnedObjectPath)> = match reply.body().deserialize() {
                Ok(c) => c,
                Err(_) => return Vec::new(),
            };

            children
                .into_iter()
                .map(|(bus_name, path)| AccessibleRef { bus_name, path })
                .collect()
        }

        /// Get the role of an accessible object.
        fn get_role(&self, acc: &AccessibleRef) -> Option<u32> {
            let conn = self.connection.as_ref()?;
            let reply = conn
                .call_method(
                    Some(acc.bus_name.as_str()),
                    acc.path.as_str(),
                    Some("org.a11y.atspi.Accessible"),
                    "GetRole",
                    &(),
                )
                .ok()?;
            reply.body().deserialize().ok()
        }

        /// Get the name of an accessible object.
        fn get_name(&self, acc: &AccessibleRef) -> String {
            let Some(conn) = &self.connection else {
                return String::new();
            };
            // Name is a property
            match conn.call_method(
                Some(acc.bus_name.as_str()),
                acc.path.as_str(),
                Some("org.freedesktop.DBus.Properties"),
                "Get",
                &("org.a11y.atspi.Accessible", "Name"),
            ) {
                Ok(reply) => {
                    let val: OwnedValue = match reply.body().deserialize() {
                        Ok(v) => v,
                        Err(_) => return String::new(),
                    };
                    match val.downcast_ref::<Value>() {
                        Ok(Value::Str(s)) => s.to_string(),
                        _ => val.to_string(),
                    }
                }
                Err(_) => String::new(),
            }
        }

        /// Get the PID of an accessible application.
        fn get_pid(&self, acc: &AccessibleRef) -> u32 {
            let Some(conn) = &self.connection else {
                return 0;
            };
            let reply = match conn.call_method(
                Some(acc.bus_name.as_str()),
                acc.path.as_str(),
                Some("org.a11y.atspi.Application"),
                "GetPid",
                &(),
            ) {
                Ok(r) => r,
                Err(_) => return 0,
            };
            reply.body().deserialize::<i32>().unwrap_or(0) as u32
        }

        /// Get children of an accessible object.
        fn get_children(&self, acc: &AccessibleRef) -> Vec<AccessibleRef> {
            let Some(conn) = &self.connection else {
                return Vec::new();
            };
            let reply = match conn.call_method(
                Some(acc.bus_name.as_str()),
                acc.path.as_str(),
                Some("org.a11y.atspi.Accessible"),
                "GetChildren",
                &(),
            ) {
                Ok(r) => r,
                Err(_) => return Vec::new(),
            };
            let children: Vec<(String, OwnedObjectPath)> =
                match reply.body().deserialize() {
                    Ok(c) => c,
                    Err(_) => return Vec::new(),
                };
            children
                .into_iter()
                .map(|(bus_name, path)| AccessibleRef { bus_name, path })
                .collect()
        }

        /// Get the state set of an accessible object as a pair of u32 bitfields.
        fn get_state(&self, acc: &AccessibleRef) -> ElementState {
            let Some(conn) = &self.connection else {
                return ElementState::default();
            };
            let reply = match conn.call_method(
                Some(acc.bus_name.as_str()),
                acc.path.as_str(),
                Some("org.a11y.atspi.Accessible"),
                "GetState",
                &(),
            ) {
                Ok(r) => r,
                Err(_) => return ElementState::default(),
            };
            let bits: Vec<u32> = match reply.body().deserialize() {
                Ok(b) => b,
                Err(_) => return ElementState::default(),
            };

            let state_bits = if bits.len() >= 2 {
                (bits[0] as u64) | ((bits[1] as u64) << 32)
            } else if bits.len() == 1 {
                bits[0] as u64
            } else {
                return ElementState::default();
            };

            let has_state = |bit: u32| -> bool { (state_bits & (1u64 << bit)) != 0 };

            ElementState {
                enabled: has_state(states::STATE_ENABLED),
                visible: has_state(states::STATE_VISIBLE) || has_state(states::STATE_SHOWING),
                focused: has_state(states::STATE_FOCUSED),
                checked: if has_state(states::STATE_CHECKED) {
                    Some(true)
                } else {
                    None
                },
                expanded: if has_state(states::STATE_EXPANDED) {
                    Some(true)
                } else {
                    None
                },
                selected: has_state(states::STATE_SELECTED),
                editable: has_state(states::STATE_EDITABLE),
            }
        }

        /// Get available actions for an accessible.
        fn get_actions(&self, acc: &AccessibleRef) -> Vec<ActionType> {
            let Some(conn) = &self.connection else {
                return Vec::new();
            };
            // Get number of actions
            let reply = match conn.call_method(
                Some(acc.bus_name.as_str()),
                acc.path.as_str(),
                Some("org.a11y.atspi.Action"),
                "GetNActions",
                &(),
            ) {
                Ok(r) => r,
                Err(_) => return Vec::new(),
            };
            let n_actions: i32 = match reply.body().deserialize() {
                Ok(n) => n,
                Err(_) => return Vec::new(),
            };

            let mut actions = Vec::new();
            for i in 0..n_actions {
                if let Ok(reply) = conn.call_method(
                    Some(acc.bus_name.as_str()),
                    acc.path.as_str(),
                    Some("org.a11y.atspi.Action"),
                    "GetName",
                    &(i,),
                ) {
                    if let Ok(name) = reply.body().deserialize::<String>() {
                        match name.as_str() {
                            "click" | "press" | "activate" => actions.push(ActionType::Activate),
                            "expand" => actions.push(ActionType::Expand),
                            "collapse" => actions.push(ActionType::Collapse),
                            "select" => actions.push(ActionType::Select),
                            "focus" => actions.push(ActionType::Focus),
                            _ => {}
                        }
                    }
                }
            }

            // Infer actions from role if none found
            if actions.is_empty() {
                // Will be handled at the call site based on role
            }

            actions
        }

        /// Convert an AT-SPI role to our ElementRole.
        fn map_role(atspi_role: u32) -> ElementRole {
            match atspi_role {
                roles::ROLE_PUSH_BUTTON | roles::ROLE_TOGGLE_BUTTON => ElementRole::Button,
                roles::ROLE_TEXT | roles::ROLE_PASSWORD_TEXT => ElementRole::TextField,
                roles::ROLE_LABEL => ElementRole::Label,
                roles::ROLE_CHECK_BOX => ElementRole::CheckBox,
                roles::ROLE_RADIO_BUTTON => ElementRole::RadioButton,
                roles::ROLE_COMBO_BOX => ElementRole::ComboBox,
                roles::ROLE_MENU | roles::ROLE_MENU_BAR => ElementRole::Menu,
                roles::ROLE_MENU_ITEM => ElementRole::MenuItem,
                roles::ROLE_PAGE_TAB => ElementRole::Tab,
                roles::ROLE_PAGE_TAB_LIST => ElementRole::TabPanel,
                roles::ROLE_SCROLL_BAR => ElementRole::ScrollBar,
                roles::ROLE_LIST => ElementRole::List,
                roles::ROLE_LIST_ITEM => ElementRole::ListItem,
                roles::ROLE_TREE => ElementRole::Tree,
                roles::ROLE_TREE_ITEM => ElementRole::TreeItem,
                roles::ROLE_TABLE => ElementRole::Table,
                roles::ROLE_TABLE_CELL => ElementRole::TableCell,
                roles::ROLE_TOOL_BAR => ElementRole::Toolbar,
                roles::ROLE_STATUS_BAR => ElementRole::StatusBar,
                roles::ROLE_PROGRESS_BAR => ElementRole::ProgressBar,
                roles::ROLE_IMAGE => ElementRole::Image,
                roles::ROLE_LINK => ElementRole::Link,
                roles::ROLE_HEADING => ElementRole::Heading,
                roles::ROLE_PARAGRAPH => ElementRole::Paragraph,
                roles::ROLE_SEPARATOR => ElementRole::Separator,
                roles::ROLE_SLIDER => ElementRole::Slider,
                roles::ROLE_SPIN_BUTTON => ElementRole::SpinButton,
                roles::ROLE_DIALOG => ElementRole::Dialog,
                roles::ROLE_ALERT => ElementRole::Alert,
                roles::ROLE_PANEL | roles::ROLE_FILLER | roles::ROLE_SCROLL_PANE => {
                    ElementRole::Panel
                }
                other => ElementRole::Unknown(format!("atspi_role_{other}")),
            }
        }

        /// Infer default actions from role.
        fn default_actions(role: &ElementRole) -> Vec<ActionType> {
            match role {
                ElementRole::Button => vec![ActionType::Activate],
                ElementRole::TextField => vec![ActionType::SetValue, ActionType::Focus],
                ElementRole::CheckBox | ElementRole::RadioButton => vec![ActionType::Activate],
                ElementRole::ComboBox => vec![ActionType::Expand, ActionType::Focus],
                ElementRole::MenuItem => vec![ActionType::Activate],
                ElementRole::Tab => vec![ActionType::Activate],
                ElementRole::Link => vec![ActionType::Activate],
                ElementRole::ListItem | ElementRole::TreeItem => {
                    vec![ActionType::Select, ActionType::Activate]
                }
                ElementRole::Slider | ElementRole::SpinButton => vec![ActionType::SetValue],
                _ => vec![],
            }
        }

        /// Recursively walk an accessible tree and add elements to the graph.
        fn walk_tree(
            &mut self,
            graph: &mut SceneGraph,
            parent_node: NodeId,
            acc: &AccessibleRef,
            depth: usize,
            is_window_level: bool,
        ) {
            if depth > self.max_depth {
                return;
            }

            let atspi_role = match self.get_role(acc) {
                Some(r) => r,
                None => return,
            };

            // Skip the application-level node and container nodes that add no value
            if atspi_role == roles::ROLE_APPLICATION {
                // Walk children directly, attaching to parent
                for child in self.get_children(acc) {
                    self.walk_tree(graph, parent_node, &child, depth + 1, true);
                }
                return;
            }

            let name = self.get_name(acc);
            let role = Self::map_role(atspi_role);

            // Skip unnamed panels/fillers to reduce noise
            if name.is_empty()
                && matches!(
                    role,
                    ElementRole::Panel | ElementRole::Unknown(_)
                )
            {
                // Still walk children, but attach to parent
                for child in self.get_children(acc) {
                    self.walk_tree(graph, parent_node, &child, depth + 1, false);
                }
                return;
            }

            let state = self.get_state(acc);
            let mut actions = self.get_actions(acc);
            if actions.is_empty() {
                actions = Self::default_actions(&role);
            }

            let path_key = format!("{}:{}", acc.bus_name, acc.path.as_str());

            // Create the element node
            let node_id = graph.alloc_id();
            graph.insert(
                node_id,
                SemanticNode::Element {
                    role,
                    label: name,
                    value: None,
                    state,
                    bounds: Rect::new(0, 0, 0, 0), // AT-SPI extents would need Component interface
                    actions,
                    children: Vec::new(),
                },
            );

            // Attach to parent
            if is_window_level {
                if let Some(SemanticNode::Window { elements, .. }) = graph.get_mut(parent_node) {
                    elements.push(node_id);
                }
            } else {
                if let Some(SemanticNode::Element { children, .. }) = graph.get_mut(parent_node) {
                    children.push(node_id);
                }
            }

            self.path_to_node.insert(path_key, node_id);

            // Recurse into children
            for child in self.get_children(acc) {
                self.walk_tree(graph, node_id, &child, depth + 1, false);
            }
        }

        /// Execute an AT-SPI action by node ID.
        fn do_atspi_action(&self, acc_path: &str, action_index: i32) -> ActionResult {
            let Some(conn) = &self.connection else {
                return ActionResult::Failed("not connected".into());
            };

            // Parse bus_name:path
            let parts: Vec<&str> = acc_path.splitn(2, ':').collect();
            if parts.len() != 2 {
                return ActionResult::Failed("invalid path".into());
            }

            match conn.call_method(
                Some(parts[0]),
                parts[1],
                Some("org.a11y.atspi.Action"),
                "DoAction",
                &(action_index,),
            ) {
                Ok(_) => ActionResult::Success,
                Err(e) => ActionResult::Failed(format!("DoAction failed: {e}")),
            }
        }
    }

    impl Source for AtSpiSource {
        fn name(&self) -> &str {
            "atspi"
        }

        fn start(&mut self, graph: &mut SceneGraph) -> Result<(), Box<dyn std::error::Error>> {
            self.connect()?;
            tracing::info!("AT-SPI source: connected to accessibility bus");

            // Create a default screen if none exists
            if graph.is_empty() {
                self.screen_node = Some(graph.add_screen("default", Rect::new(0, 0, 1920, 1080)));
            }

            // Do initial tree walk
            self.poll(graph)?;
            Ok(())
        }

        fn poll(&mut self, graph: &mut SceneGraph) -> Result<(), Box<dyn std::error::Error>> {
            let apps = self.get_applications();
            tracing::debug!("AT-SPI: found {} applications", apps.len());

            let screen_id = match self.screen_node {
                Some(id) => id,
                None => return Ok(()),
            };

            // For each application, find top-level windows and build element trees
            for app in &apps {
                let pid = self.get_pid(app);
                let app_name = self.get_name(app);

                // Get the application's children (top-level frames/windows)
                let children = self.get_children(app);
                for child in &children {
                    let role = self.get_role(child).unwrap_or(0);

                    // Only process top-level windows (frames/dialogs)
                    if role != roles::ROLE_FRAME && role != roles::ROLE_DIALOG {
                        continue;
                    }

                    let title = self.get_name(child);
                    let path_key = format!("{}:{}", child.bus_name, child.path.as_str());

                    // Check if we already track this window
                    if self.path_to_node.contains_key(&path_key) {
                        // TODO: update existing window (title changes, element tree refresh)
                        continue;
                    }

                    // Use a hash of the path as window ID
                    let window_id = {
                        let mut hasher = std::collections::hash_map::DefaultHasher::new();
                        std::hash::Hash::hash(&path_key, &mut hasher);
                        std::hash::Hasher::finish(&hasher)
                    };

                    let win_node = graph.add_window(
                        screen_id,
                        window_id,
                        pid,
                        &app_name,
                        &title,
                        Rect::new(0, 0, 0, 0),
                    );
                    self.path_to_node.insert(path_key, win_node);

                    // Walk the accessibility tree under this window
                    let frame_children = self.get_children(child);
                    for frame_child in &frame_children {
                        self.walk_tree(graph, win_node, frame_child, 0, true);
                    }
                }
            }

            Ok(())
        }

        fn execute_action(&self, request: &ActionRequest) -> ActionResult {
            // Find the AT-SPI path for this node
            let path = self.path_to_node.iter().find_map(|(path, &nid)| {
                if nid == request.node_id {
                    Some(path.clone())
                } else {
                    None
                }
            });

            let Some(path) = path else {
                return ActionResult::NotFound;
            };

            match request.action {
                ActionType::Activate => self.do_atspi_action(&path, 0),
                ActionType::Expand => self.do_atspi_action(&path, 0),
                ActionType::Collapse => self.do_atspi_action(&path, 0),
                ActionType::Select => self.do_atspi_action(&path, 0),
                _ => ActionResult::NotSupported,
            }
        }
    }
}

// When the atspi feature is not enabled, provide a stub implementation
#[cfg(not(feature = "atspi"))]
mod imp {
    use crate::action::{ActionRequest, ActionResult};
    use crate::graph::SceneGraph;
    use crate::sources::Source;

    pub struct AtSpiSource;

    impl AtSpiSource {
        pub fn new() -> Self {
            Self
        }
    }

    impl Source for AtSpiSource {
        fn name(&self) -> &str {
            "atspi"
        }

        fn start(&mut self, _graph: &mut SceneGraph) -> Result<(), Box<dyn std::error::Error>> {
            tracing::warn!("AT-SPI source: not available (compile with 'atspi' feature)");
            Ok(())
        }

        fn poll(&mut self, _graph: &mut SceneGraph) -> Result<(), Box<dyn std::error::Error>> {
            Ok(())
        }

        fn execute_action(&self, _request: &ActionRequest) -> ActionResult {
            ActionResult::NotSupported
        }
    }
}

pub use imp::AtSpiSource;
