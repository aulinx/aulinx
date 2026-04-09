//! Semantic node types — the vocabulary of the scene graph.

use serde::{Deserialize, Serialize};

/// Unique identifier for a node in the scene graph.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct NodeId(pub u64);

/// Axis-aligned rectangle in logical coordinates.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct Rect {
    pub x: i32,
    pub y: i32,
    pub width: i32,
    pub height: i32,
}

impl Rect {
    pub fn new(x: i32, y: i32, width: i32, height: i32) -> Self {
        Self { x, y, width, height }
    }

    pub fn contains(&self, px: i32, py: i32) -> bool {
        px >= self.x && px < self.x + self.width && py >= self.y && py < self.y + self.height
    }
}

/// A node in the semantic scene graph.
///
/// The graph is a tree: Desktop → Screen → Window → Element → Element...
/// Every visible thing on the desktop maps to a node with semantic meaning.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum SemanticNode {
    Desktop {
        screens: Vec<NodeId>,
    },
    Screen {
        name: String,
        geometry: Rect,
        windows: Vec<NodeId>,
    },
    Window {
        id: u64,
        pid: u32,
        app_id: String,
        title: String,
        geometry: Rect,
        focused: bool,
        workspace: usize,
        floating: bool,
        elements: Vec<NodeId>,
    },
    Element {
        role: ElementRole,
        label: String,
        #[serde(skip_serializing_if = "Option::is_none")]
        value: Option<String>,
        state: ElementState,
        bounds: Rect,
        actions: Vec<ActionType>,
        children: Vec<NodeId>,
    },
}

/// The role of a UI element — what kind of control it is.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ElementRole {
    Button,
    TextField,
    Label,
    CheckBox,
    RadioButton,
    Menu,
    MenuItem,
    Tab,
    TabPanel,
    ScrollBar,
    List,
    ListItem,
    Tree,
    TreeItem,
    Table,
    TableCell,
    Dialog,
    Alert,
    Toolbar,
    StatusBar,
    ProgressBar,
    Image,
    Link,
    Heading,
    Paragraph,
    Separator,
    Slider,
    SpinButton,
    ComboBox,
    Panel,
    Unknown(String),
}

/// State flags for a UI element.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ElementState {
    pub enabled: bool,
    pub visible: bool,
    pub focused: bool,
    pub checked: Option<bool>,
    pub expanded: Option<bool>,
    pub selected: bool,
    pub editable: bool,
}

impl Default for ElementState {
    fn default() -> Self {
        Self {
            enabled: true,
            visible: true,
            focused: false,
            checked: None,
            expanded: None,
            selected: false,
            editable: false,
        }
    }
}

/// Actions that can be performed on an element.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ActionType {
    /// Click / press / activate the element.
    Activate,
    /// Set the text value of an input field.
    SetValue,
    /// Scroll the element.
    Scroll,
    /// Expand a tree node or collapsible.
    Expand,
    /// Collapse a tree node or collapsible.
    Collapse,
    /// Select this item.
    Select,
    /// Focus this element.
    Focus,
}
