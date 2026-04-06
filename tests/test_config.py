"""Tests for configuration system."""

from aulinx.config import Config, ContextConfig, LLMConfig, load_config


class TestConfigDefaults:
    def test_default_model(self):
        config = Config()
        assert config.llm.model == "qwen2.5:14b"

    def test_default_temperature(self):
        config = Config()
        assert config.llm.temperature == 0.3

    def test_default_base_url(self):
        config = Config()
        assert "11434" in config.llm.base_url

    def test_default_max_history(self):
        config = Config()
        assert config.context.max_history == 20

    def test_default_permission_overrides_empty(self):
        config = Config()
        assert config.permission_overrides == {}


class TestLoadConfig:
    def test_load_returns_config(self):
        config = load_config()
        assert isinstance(config, Config)
        assert isinstance(config.llm, LLMConfig)
        assert isinstance(config.context, ContextConfig)
