"""Tests for multi-provider LLM client abstraction."""

from aulinx.llm import (
    AnthropicClient,
    GeminiClient,
    LLMClient,
    OllamaClient,
    OpenAIClient,
    create_client,
    _ollama_tools_to_anthropic,
    _ollama_tools_to_openai,
    _clean_messages_for_openai,
    _ensure_alternating,
)


class TestCreateClient:
    def test_ollama_default(self):
        client = create_client("ollama")
        assert isinstance(client, OllamaClient)
        assert client.model == "qwen2.5:14b"
        assert "11434" in client.base_url

    def test_openai(self):
        client = create_client("openai", api_key="test-key")
        assert isinstance(client, OpenAIClient)
        assert client.model == "gpt-4o"
        assert client.api_key == "test-key"

    def test_anthropic(self):
        client = create_client("anthropic", api_key="test-key")
        assert isinstance(client, AnthropicClient)
        assert "claude" in client.model
        assert client.api_key == "test-key"

    def test_gemini(self):
        client = create_client("gemini", api_key="test-key")
        assert isinstance(client, GeminiClient)
        assert "gemini" in client.model

    def test_custom_model(self):
        client = create_client("openai", model="gpt-4-turbo", api_key="k")
        assert client.model == "gpt-4-turbo"

    def test_custom_base_url(self):
        client = create_client("openai", base_url="http://localhost:8080/v1", api_key="k")
        assert client.base_url == "http://localhost:8080/v1"

    def test_unknown_provider(self):
        try:
            create_client("unknown")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "unknown" in str(e).lower()

    def test_all_are_llm_client(self):
        for provider in ["ollama", "openai", "anthropic", "gemini"]:
            client = create_client(provider, api_key="test")
            assert isinstance(client, LLMClient)


class TestToolFormatConversion:
    SAMPLE_TOOLS = [
        {
            "type": "function",
            "function": {
                "name": "file_read",
                "description": "Read a file",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path"},
                    },
                    "required": ["path"],
                },
            },
        }
    ]

    def test_to_openai_passthrough(self):
        result = _ollama_tools_to_openai(self.SAMPLE_TOOLS)
        assert len(result) == 1
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "file_read"

    def test_to_anthropic(self):
        result = _ollama_tools_to_anthropic(self.SAMPLE_TOOLS)
        assert len(result) == 1
        assert result[0]["name"] == "file_read"
        assert "input_schema" in result[0]
        assert result[0]["input_schema"]["type"] == "object"


class TestCleanMessages:
    def test_regular_messages(self):
        msgs = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
        ]
        result = _clean_messages_for_openai(msgs)
        assert len(result) == 2
        assert result[0]["role"] == "system"

    def test_tool_messages(self):
        msgs = [
            {"role": "tool", "content": '{"result": "ok"}'},
        ]
        result = _clean_messages_for_openai(msgs)
        assert result[0]["role"] == "tool"
        assert "tool_call_id" in result[0]


class TestEnsureAlternating:
    def test_already_alternating(self):
        msgs = [
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
        ]
        assert _ensure_alternating(msgs) == msgs

    def test_merges_consecutive_user(self):
        msgs = [
            {"role": "user", "content": "hello"},
            {"role": "user", "content": "world"},
        ]
        result = _ensure_alternating(msgs)
        assert len(result) == 1
        assert "hello" in result[0]["content"]
        assert "world" in result[0]["content"]

    def test_empty(self):
        assert _ensure_alternating([]) == []

    def test_single_message(self):
        msgs = [{"role": "user", "content": "hi"}]
        assert _ensure_alternating(msgs) == msgs
