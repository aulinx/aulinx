"""Configuration — loads from ~/.config/aulinx/config.toml."""

from dataclasses import dataclass, field
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "aulinx"
CONFIG_FILE = CONFIG_DIR / "config.toml"

DEFAULT_CONFIG = """\
# Aulinx configuration

[llm]
# Model to use with Ollama
model = "qwen2.5:14b"
# Ollama API base URL
base_url = "http://localhost:11434"
# Temperature (lower = more deterministic tool calls)
temperature = 0.3

[permissions]
# Override permission tiers for specific tools
# Format: tool_name = "tier"
# Tiers: observe, low_risk, mutate, destructive, irreversible
# Example: uncomment to auto-allow shell_exec (not recommended)
# shell_exec = "mutate"

[context]
# Max messages to keep in conversation history
max_history = 20
# Include clipboard content in context
include_clipboard = true
# Include running apps in context
include_running_apps = true
"""


@dataclass
class LLMConfig:
    model: str = "qwen2.5:14b"
    base_url: str = "http://localhost:11434"
    temperature: float = 0.3
    router_model: str = ""  # small fast model for intent routing (e.g. qwen2.5:3b)
    use_router: bool = False  # enable multi-model routing


@dataclass
class ContextConfig:
    max_history: int = 20
    include_clipboard: bool = True
    include_running_apps: bool = True


@dataclass
class Config:
    llm: LLMConfig = field(default_factory=LLMConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    permission_overrides: dict[str, str] = field(default_factory=dict)


def load_config() -> Config:
    """Load config from ~/.config/aulinx/config.toml, creating defaults if needed."""
    config = Config()

    if not CONFIG_FILE.exists():
        _create_default_config()
        return config

    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore
        except ImportError:
            return config

    try:
        with open(CONFIG_FILE, "rb") as f:
            data = tomllib.load(f)

        # LLM settings
        if "llm" in data:
            llm = data["llm"]
            config.llm.model = llm.get("model", config.llm.model)
            config.llm.base_url = llm.get("base_url", config.llm.base_url)
            config.llm.temperature = llm.get("temperature", config.llm.temperature)

        # Context settings
        if "context" in data:
            ctx = data["context"]
            config.context.max_history = ctx.get("max_history", config.context.max_history)
            config.context.include_clipboard = ctx.get("include_clipboard", config.context.include_clipboard)
            config.context.include_running_apps = ctx.get("include_running_apps", config.context.include_running_apps)

        # Permission overrides
        if "permissions" in data:
            config.permission_overrides = {
                k: v for k, v in data["permissions"].items() if isinstance(v, str)
            }

    except Exception:
        pass

    return config


def _create_default_config():
    """Create default config file."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(DEFAULT_CONFIG)
    except OSError:
        pass
