"""Configuration — loads from ~/.config/aulinx/config.toml."""

from dataclasses import dataclass, field
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "aulinx"
CONFIG_FILE = CONFIG_DIR / "config.toml"

DEFAULT_CONFIG = """\
# Aulinx configuration

[llm]
# LLM provider: "ollama", "openai", "anthropic", "gemini"
provider = "ollama"
# Model name (provider-specific, leave empty for default)
model = "qwen2.5:14b"
# API base URL (leave empty for provider default)
base_url = "http://localhost:11434"
# API key (only needed for cloud providers; can also use env vars:
#   OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY)
# api_key = ""
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
    provider: str = "ollama"  # "ollama", "openai", "anthropic", "gemini"
    model: str = "qwen2.5:14b"
    base_url: str = "http://localhost:11434"
    temperature: float = 0.3
    api_key: str = ""  # falls back to env vars per provider
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
            config.llm.provider = llm.get("provider", config.llm.provider)
            config.llm.model = llm.get("model", config.llm.model)
            config.llm.base_url = llm.get("base_url", config.llm.base_url)
            config.llm.temperature = llm.get("temperature", config.llm.temperature)
            config.llm.api_key = llm.get("api_key", config.llm.api_key)

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

    # Validate
    _validate_config(config)

    return config


def _validate_config(config: Config):
    """Validate config values and warn about issues."""
    warnings = []

    if config.llm.temperature < 0 or config.llm.temperature > 2:
        config.llm.temperature = max(0, min(2, config.llm.temperature))
        warnings.append(f"Temperature clamped to {config.llm.temperature} (valid: 0-2)")

    if config.context.max_history < 1:
        config.context.max_history = 20
        warnings.append("max_history must be >= 1, reset to 20")

    valid_providers = {"ollama", "openai", "anthropic", "gemini", "qwen-cloud"}
    if config.llm.provider not in valid_providers:
        warnings.append(f"Unknown provider '{config.llm.provider}'. Valid: {valid_providers}")
        config.llm.provider = "ollama"

    if not config.llm.base_url.startswith(("http://", "https://")):
        warnings.append(f"base_url '{config.llm.base_url}' should start with http:// or https://")

    valid_tiers = {"observe", "low_risk", "mutate", "destructive", "irreversible"}
    for tool, tier in config.permission_overrides.items():
        if tier not in valid_tiers:
            warnings.append(f"Invalid permission tier '{tier}' for '{tool}'. Valid: {valid_tiers}")

    if warnings:
        import sys
        for w in warnings:
            print(f"[config] Warning: {w}", file=sys.stderr)


def _create_default_config():
    """Create default config file."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(DEFAULT_CONFIG)
    except OSError:
        pass
