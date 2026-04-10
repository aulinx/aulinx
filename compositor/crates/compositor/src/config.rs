//! Compositor configuration — loaded from TOML file.
//!
//! Default path: `~/.config/aulinx/compositor.toml`
//! Override: `AULINX_COMPOSITOR_CONFIG=/path/to/config.toml`

use serde::Deserialize;
use std::path::PathBuf;

/// Top-level compositor configuration.
#[derive(Debug, Clone, Deserialize)]
#[serde(default)]
pub struct Config {
    /// Layout settings.
    pub layout: LayoutConfig,
    /// Appearance settings.
    pub appearance: AppearanceConfig,
    /// Terminal to launch with Super+Return.
    pub terminal: String,
}

/// Layout configuration.
#[derive(Debug, Clone, Deserialize)]
#[serde(default)]
pub struct LayoutConfig {
    /// Gap between windows in pixels.
    pub gap: i32,
    /// Outer gap (screen edge padding) in pixels.
    pub outer_gap: i32,
    /// Master window width ratio (0.0-1.0).
    pub master_ratio: f32,
}

/// Appearance configuration.
#[derive(Debug, Clone, Deserialize)]
#[serde(default)]
pub struct AppearanceConfig {
    /// Background color as [r, g, b, a] floats (0.0-1.0).
    pub background: [f32; 4],
}

impl Default for Config {
    fn default() -> Self {
        Self {
            layout: LayoutConfig::default(),
            appearance: AppearanceConfig::default(),
            terminal: "foot".to_string(),
        }
    }
}

impl Default for LayoutConfig {
    fn default() -> Self {
        Self {
            gap: 4,
            outer_gap: 4,
            master_ratio: 0.6,
        }
    }
}

impl Default for AppearanceConfig {
    fn default() -> Self {
        Self {
            background: [0.08, 0.08, 0.12, 1.0],
        }
    }
}

impl Config {
    /// Load config from the default or environment-specified path.
    pub fn load() -> Self {
        let path = Self::config_path();
        if path.exists() {
            match std::fs::read_to_string(&path) {
                Ok(contents) => match toml::from_str(&contents) {
                    Ok(config) => {
                        tracing::info!("Loaded config from {}", path.display());
                        return config;
                    }
                    Err(e) => {
                        tracing::warn!("Failed to parse config {}: {}", path.display(), e);
                    }
                },
                Err(e) => {
                    tracing::warn!("Failed to read config {}: {}", path.display(), e);
                }
            }
        }
        tracing::info!("Using default config");
        Self::default()
    }

    fn config_path() -> PathBuf {
        if let Ok(path) = std::env::var("AULINX_COMPOSITOR_CONFIG") {
            return PathBuf::from(path);
        }
        dirs_or_default("aulinx", "compositor.toml")
    }
}

fn dirs_or_default(app: &str, file: &str) -> PathBuf {
    if let Ok(config_dir) = std::env::var("XDG_CONFIG_HOME") {
        return PathBuf::from(config_dir).join(app).join(file);
    }
    if let Ok(home) = std::env::var("HOME") {
        return PathBuf::from(home).join(".config").join(app).join(file);
    }
    PathBuf::from(file)
}
