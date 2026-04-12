"""LLM clients — multi-provider abstraction for Ollama, OpenAI, Anthropic, Gemini."""

import asyncio
import json
import os
import re
from abc import ABC, abstractmethod
from typing import AsyncIterator

import httpx

MAX_RETRIES = 2


class LLMEvent:
    """Event emitted during LLM streaming."""

    def __init__(self, type: str, **kwargs):
        self.type = type  # "token", "tool_calls", "done", "error"
        self.data = kwargs


class LLMClient(ABC):
    """Base class for all LLM providers."""

    def __init__(
        self,
        model: str,
        base_url: str,
        temperature: float = 0.3,
        api_key: str = "",
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.api_key = api_key
        self._available = False

    @property
    def available(self) -> bool:
        return self._available

    @abstractmethod
    async def check(self) -> bool:
        """Check if the provider is reachable and model exists."""
        ...

    @abstractmethod
    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
    ) -> AsyncIterator[LLMEvent]:
        """Stream a chat completion with tool calling.

        Yields LLMEvent objects:
        - LLMEvent("token", content="...") for each text token
        - LLMEvent("tool_calls", calls=[...]) when tool calls are detected
        - LLMEvent("done", content="full text", tool_calls=[...] or None)
        - LLMEvent("error", message="...")
        """
        ...
        # Make this an async generator for type checking
        if False:
            yield  # pragma: no cover


class OllamaClient(LLMClient):
    """Handles all communication with Ollama, including streaming and tool calling."""

    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:11434",
        temperature: float = 0.3,
        router_model: str = "",
        **kwargs,
    ):
        super().__init__(model, base_url, temperature)
        self.router_model = router_model

    async def check(self) -> bool:
        """Check if Ollama is reachable and model exists."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self.base_url}/api/tags", timeout=5)
                resp.raise_for_status()
                models = [m["name"] for m in resp.json().get("models", [])]
                self._available = any(self.model in m for m in models)
                return self._available
        except (httpx.ConnectError, httpx.TimeoutException):
            self._available = False
            return False

    async def route_intent(self, user_message: str, tool_names: list[str]) -> str | None:
        """Use a small fast model to classify which tool to call."""
        if not self.router_model:
            return None

        prompt = (
            f"Pick the single best tool for this user request. Reply with ONLY the tool name, nothing else.\n\n"
            f"Tools: {', '.join(tool_names)}\n\n"
            f"User: {user_message}\n\n"
            f"Tool:"
        )

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": self.router_model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {"temperature": 0.0, "num_predict": 20},
                    },
                    timeout=httpx.Timeout(connect=5, read=15, write=5, pool=5),
                )
                resp.raise_for_status()
                response = resp.json().get("response", "").strip().split("\n")[0].strip()
                response = response.strip("\"' `").split("(")[0].strip()
                if response in tool_names:
                    return response
        except Exception:
            pass

        return None

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
    ) -> AsyncIterator[LLMEvent]:
        for attempt in range(MAX_RETRIES + 1):
            try:
                async for event in self._stream_with_tools(messages, tools):
                    yield event
                return
            except httpx.ConnectError:
                self._available = False
                if attempt < MAX_RETRIES:
                    yield LLMEvent("error", message=f"Connection lost. Retrying ({attempt + 1})...")
                    await asyncio.sleep(2)
                else:
                    yield LLMEvent("error", message="Cannot reach Ollama.")
                    return
            except httpx.ReadTimeout:
                if attempt < MAX_RETRIES:
                    yield LLMEvent("error", message=f"Timed out. Retrying ({attempt + 1})...")
                else:
                    yield LLMEvent("error", message="Timed out. Try a simpler query.")
                    return
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 400:
                    async for event in self._stream_text_fallback(messages):
                        yield event
                    return
                yield LLMEvent("error", message=f"Ollama error: {e.response.status_code}")
                return

    async def _stream_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
    ) -> AsyncIterator[LLMEvent]:
        """Stream from Ollama with native tool calling."""
        full_content = ""
        tool_calls = None

        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "tools": tools,
                    "stream": True,
                    "options": {"temperature": self.temperature},
                },
                timeout=httpx.Timeout(connect=10, read=120, write=10, pool=10),
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    msg = chunk.get("message", {})
                    token = msg.get("content", "")
                    chunk_tools = msg.get("tool_calls")

                    if token:
                        full_content += token
                        yield LLMEvent("token", content=token)

                    if chunk_tools:
                        tool_calls = chunk_tools

                    if chunk.get("done"):
                        if chunk_tools:
                            tool_calls = chunk_tools
                        break

        if tool_calls:
            yield LLMEvent("tool_calls", calls=tool_calls)

        yield LLMEvent("done", content=full_content, tool_calls=tool_calls)

    async def _stream_text_fallback(
        self,
        messages: list[dict],
    ) -> AsyncIterator[LLMEvent]:
        """Fallback: stream without tools, extract JSON tool calls from text."""
        full_content = ""

        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": True,
                    "options": {"temperature": self.temperature},
                },
                timeout=httpx.Timeout(connect=10, read=90, write=10, pool=10),
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            full_content += token
                            if "```json" not in full_content:
                                yield LLMEvent("token", content=token)
                    except json.JSONDecodeError:
                        continue

        tool_call = extract_tool_call(full_content)
        if tool_call:
            name, args = tool_call
            tool_calls = [{"function": {"name": name, "arguments": args}}]
            yield LLMEvent("tool_calls", calls=tool_calls)
            yield LLMEvent("done", content=full_content, tool_calls=tool_calls)
        else:
            yield LLMEvent("done", content=full_content, tool_calls=None)


class OpenAIClient(LLMClient):
    """OpenAI-compatible API client with streaming and tool calling."""

    def __init__(
        self,
        model: str = "gpt-4o",
        base_url: str = "https://api.openai.com/v1",
        temperature: float = 0.3,
        api_key: str = "",
        **kwargs,
    ):
        super().__init__(model, base_url, temperature, api_key)
        if not self.api_key:
            self.api_key = os.environ.get("OPENAI_API_KEY", "")

    async def check(self) -> bool:
        """Check if the API is reachable."""
        if not self.api_key:
            self._available = False
            return False
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=10,
                )
                resp.raise_for_status()
                self._available = True
                return True
        except Exception:
            self._available = False
            return False

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
    ) -> AsyncIterator[LLMEvent]:
        if not self.api_key:
            yield LLMEvent("error", message="OPENAI_API_KEY not set.")
            return

        # Convert Ollama tool format to OpenAI format
        openai_tools = _ollama_tools_to_openai(tools)

        for attempt in range(MAX_RETRIES + 1):
            try:
                async for event in self._stream(messages, openai_tools):
                    yield event
                return
            except (httpx.ConnectError, httpx.ReadTimeout) as e:
                if attempt < MAX_RETRIES:
                    yield LLMEvent("error", message=f"Connection issue. Retrying ({attempt + 1})...")
                    await asyncio.sleep(2)
                else:
                    yield LLMEvent("error", message=f"Cannot reach OpenAI API: {e}")
                    return
            except httpx.HTTPStatusError as e:
                yield LLMEvent("error", message=f"OpenAI API error {e.response.status_code}: {e.response.text[:200]}")
                return

    async def _stream(
        self,
        messages: list[dict],
        tools: list[dict],
    ) -> AsyncIterator[LLMEvent]:
        full_content = ""
        tool_calls_accum: dict[int, dict] = {}  # index -> {id, name, arguments_str}

        body: dict = {
            "model": self.model,
            "messages": _clean_messages_for_openai(messages),
            "temperature": self.temperature,
            "stream": True,
        }
        if tools:
            body["tools"] = tools

        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=httpx.Timeout(connect=10, read=120, write=10, pool=10),
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    delta = chunk.get("choices", [{}])[0].get("delta", {})

                    # Text content
                    token = delta.get("content", "")
                    if token:
                        full_content += token
                        yield LLMEvent("token", content=token)

                    # Tool calls (streamed incrementally)
                    for tc in delta.get("tool_calls", []):
                        idx = tc.get("index", 0)
                        if idx not in tool_calls_accum:
                            tool_calls_accum[idx] = {
                                "id": tc.get("id", ""),
                                "name": tc.get("function", {}).get("name", ""),
                                "arguments": "",
                            }
                        if tc.get("id"):
                            tool_calls_accum[idx]["id"] = tc["id"]
                        fn = tc.get("function", {})
                        if fn.get("name"):
                            tool_calls_accum[idx]["name"] = fn["name"]
                        if fn.get("arguments"):
                            tool_calls_accum[idx]["arguments"] += fn["arguments"]

        # Convert accumulated tool calls to Ollama-compatible format
        if tool_calls_accum:
            tool_calls = []
            for idx in sorted(tool_calls_accum):
                tc = tool_calls_accum[idx]
                try:
                    args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append({
                    "function": {"name": tc["name"], "arguments": args}
                })
            yield LLMEvent("tool_calls", calls=tool_calls)
            yield LLMEvent("done", content=full_content, tool_calls=tool_calls)
        else:
            yield LLMEvent("done", content=full_content, tool_calls=None)


class AnthropicClient(LLMClient):
    """Anthropic Messages API client with streaming and tool calling."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        base_url: str = "https://api.anthropic.com",
        temperature: float = 0.3,
        api_key: str = "",
        **kwargs,
    ):
        super().__init__(model, base_url, temperature, api_key)
        if not self.api_key:
            self.api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    async def check(self) -> bool:
        if not self.api_key:
            self._available = False
            return False
        # Anthropic has no /models endpoint — just mark as available if key exists
        self._available = True
        return True

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
    ) -> AsyncIterator[LLMEvent]:
        if not self.api_key:
            yield LLMEvent("error", message="ANTHROPIC_API_KEY not set.")
            return

        anthropic_tools = _ollama_tools_to_anthropic(tools)

        for attempt in range(MAX_RETRIES + 1):
            try:
                async for event in self._stream(messages, anthropic_tools):
                    yield event
                return
            except (httpx.ConnectError, httpx.ReadTimeout) as e:
                if attempt < MAX_RETRIES:
                    yield LLMEvent("error", message=f"Connection issue. Retrying ({attempt + 1})...")
                    await asyncio.sleep(2)
                else:
                    yield LLMEvent("error", message=f"Cannot reach Anthropic API: {e}")
                    return
            except httpx.HTTPStatusError as e:
                yield LLMEvent("error", message=f"Anthropic API error {e.response.status_code}: {e.response.text[:200]}")
                return

    async def _stream(
        self,
        messages: list[dict],
        tools: list[dict],
    ) -> AsyncIterator[LLMEvent]:
        # Separate system message
        system = ""
        chat_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            elif msg["role"] == "tool":
                # Anthropic expects tool results as user messages with tool_result content
                chat_messages.append({
                    "role": "user",
                    "content": [{"type": "tool_result", "tool_use_id": msg.get("tool_use_id", "tool"), "content": msg["content"]}],
                })
            else:
                chat_messages.append(msg)

        # Ensure messages alternate user/assistant
        chat_messages = _ensure_alternating(chat_messages)

        body: dict = {
            "model": self.model,
            "messages": chat_messages,
            "max_tokens": 4096,
            "temperature": self.temperature,
            "stream": True,
        }
        if system:
            body["system"] = system
        if tools:
            body["tools"] = tools

        full_content = ""
        tool_calls = []
        current_tool_input = ""
        current_tool_name = ""
        current_tool_id = ""

        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=body,
                timeout=httpx.Timeout(connect=10, read=120, write=10, pool=10),
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    try:
                        event = json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue

                    event_type = event.get("type", "")

                    if event_type == "content_block_start":
                        block = event.get("content_block", {})
                        if block.get("type") == "tool_use":
                            current_tool_name = block.get("name", "")
                            current_tool_id = block.get("id", "")
                            current_tool_input = ""

                    elif event_type == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            token = delta.get("text", "")
                            if token:
                                full_content += token
                                yield LLMEvent("token", content=token)
                        elif delta.get("type") == "input_json_delta":
                            current_tool_input += delta.get("partial_json", "")

                    elif event_type == "content_block_stop":
                        if current_tool_name:
                            try:
                                args = json.loads(current_tool_input) if current_tool_input else {}
                            except json.JSONDecodeError:
                                args = {}
                            tool_calls.append({
                                "function": {"name": current_tool_name, "arguments": args},
                                "id": current_tool_id,
                            })
                            current_tool_name = ""
                            current_tool_input = ""

        if tool_calls:
            yield LLMEvent("tool_calls", calls=tool_calls)
            yield LLMEvent("done", content=full_content, tool_calls=tool_calls)
        else:
            yield LLMEvent("done", content=full_content, tool_calls=None)


class GeminiClient(LLMClient):
    """Google Gemini API client via OpenAI-compatible endpoint."""

    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai",
        temperature: float = 0.3,
        api_key: str = "",
        **kwargs,
    ):
        super().__init__(model, base_url, temperature, api_key)
        if not self.api_key:
            self.api_key = os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")

    async def check(self) -> bool:
        if not self.api_key:
            self._available = False
            return False
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=10,
                )
                resp.raise_for_status()
                self._available = True
                return True
        except Exception:
            self._available = False
            return False

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
    ) -> AsyncIterator[LLMEvent]:
        if not self.api_key:
            yield LLMEvent("error", message="GEMINI_API_KEY not set.")
            return

        # Gemini uses OpenAI-compatible format
        openai_tools = _ollama_tools_to_openai(tools)

        for attempt in range(MAX_RETRIES + 1):
            try:
                async for event in self._stream(messages, openai_tools):
                    yield event
                return
            except (httpx.ConnectError, httpx.ReadTimeout) as e:
                if attempt < MAX_RETRIES:
                    yield LLMEvent("error", message=f"Connection issue. Retrying ({attempt + 1})...")
                    await asyncio.sleep(2)
                else:
                    yield LLMEvent("error", message=f"Cannot reach Gemini API: {e}")
                    return
            except httpx.HTTPStatusError as e:
                yield LLMEvent("error", message=f"Gemini API error {e.response.status_code}: {e.response.text[:200]}")
                return

    async def _stream(
        self,
        messages: list[dict],
        tools: list[dict],
    ) -> AsyncIterator[LLMEvent]:
        """Stream using Gemini's OpenAI-compatible endpoint."""
        full_content = ""
        tool_calls_accum: dict[int, dict] = {}

        body: dict = {
            "model": self.model,
            "messages": _clean_messages_for_openai(messages),
            "temperature": self.temperature,
            "stream": True,
        }
        if tools:
            body["tools"] = tools

        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=httpx.Timeout(connect=10, read=120, write=10, pool=10),
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    token = delta.get("content", "")
                    if token:
                        full_content += token
                        yield LLMEvent("token", content=token)

                    for tc in delta.get("tool_calls", []):
                        idx = tc.get("index", 0)
                        if idx not in tool_calls_accum:
                            tool_calls_accum[idx] = {"id": "", "name": "", "arguments": ""}
                        if tc.get("id"):
                            tool_calls_accum[idx]["id"] = tc["id"]
                        fn = tc.get("function", {})
                        if fn.get("name"):
                            tool_calls_accum[idx]["name"] = fn["name"]
                        if fn.get("arguments"):
                            tool_calls_accum[idx]["arguments"] += fn["arguments"]

        if tool_calls_accum:
            tool_calls = []
            for idx in sorted(tool_calls_accum):
                tc = tool_calls_accum[idx]
                try:
                    args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append({"function": {"name": tc["name"], "arguments": args}})
            yield LLMEvent("tool_calls", calls=tool_calls)
            yield LLMEvent("done", content=full_content, tool_calls=tool_calls)
        else:
            yield LLMEvent("done", content=full_content, tool_calls=None)


# --- Provider factory ---

PROVIDERS = {
    "ollama": OllamaClient,
    "openai": OpenAIClient,
    "anthropic": AnthropicClient,
    "gemini": GeminiClient,
}


def create_client(
    provider: str = "ollama",
    model: str = "",
    base_url: str = "",
    temperature: float = 0.3,
    api_key: str = "",
    **kwargs,
) -> LLMClient:
    """Create an LLM client for the given provider.

    Args:
        provider: One of "ollama", "openai", "anthropic", "gemini"
        model: Model name (defaults per provider if empty)
        base_url: API base URL (defaults per provider if empty)
        temperature: Sampling temperature
        api_key: API key (falls back to env vars)
    """
    cls = PROVIDERS.get(provider)
    if cls is None:
        raise ValueError(f"Unknown provider: {provider!r}. Choose from: {', '.join(PROVIDERS)}")

    # Apply per-provider defaults
    if provider == "ollama":
        model = model or "qwen2.5:14b"
        base_url = base_url or "http://localhost:11434"
    elif provider == "openai":
        model = model or "gpt-4o"
        base_url = base_url or "https://api.openai.com/v1"
    elif provider == "anthropic":
        model = model or "claude-sonnet-4-20250514"
        base_url = base_url or "https://api.anthropic.com"
    elif provider == "gemini":
        model = model or "gemini-2.5-flash"
        base_url = base_url or "https://generativelanguage.googleapis.com/v1beta/openai"

    return cls(model=model, base_url=base_url, temperature=temperature, api_key=api_key, **kwargs)


# --- Format conversion helpers ---

def _ollama_tools_to_openai(tools: list[dict]) -> list[dict]:
    """Convert Ollama tool format to OpenAI tool format.

    Ollama and OpenAI use the same format (OpenAI function calling schema),
    so this is mostly a pass-through with validation.
    """
    result = []
    for tool in tools:
        # Already in OpenAI format
        if tool.get("type") == "function" and "function" in tool:
            result.append(tool)
        else:
            # Wrap if needed
            result.append({"type": "function", "function": tool.get("function", tool)})
    return result


def _ollama_tools_to_anthropic(tools: list[dict]) -> list[dict]:
    """Convert Ollama/OpenAI tool format to Anthropic tool format.

    Anthropic uses: {name, description, input_schema} instead of
    {type: "function", function: {name, description, parameters}}
    """
    result = []
    for tool in tools:
        fn = tool.get("function", tool)
        result.append({
            "name": fn.get("name", ""),
            "description": fn.get("description", ""),
            "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
        })
    return result


def _clean_messages_for_openai(messages: list[dict]) -> list[dict]:
    """Clean messages for OpenAI/Gemini format.

    Removes tool_calls from message dicts (they're in a different format)
    and ensures tool results use the right role.
    """
    cleaned = []
    for msg in messages:
        role = msg.get("role", "user")
        if role == "tool":
            # OpenAI expects tool results with tool_call_id
            cleaned.append({
                "role": "tool",
                "content": msg.get("content", ""),
                "tool_call_id": msg.get("tool_call_id", "tool"),
            })
        else:
            entry = {"role": role, "content": msg.get("content", "")}
            cleaned.append(entry)
    return cleaned


def _ensure_alternating(messages: list[dict]) -> list[dict]:
    """Ensure messages alternate between user and assistant roles.

    Anthropic requires strict alternation. Merge consecutive same-role messages.
    """
    if not messages:
        return messages

    result = [messages[0]]
    for msg in messages[1:]:
        if msg["role"] == result[-1]["role"]:
            # Merge content
            prev_content = result[-1].get("content", "")
            new_content = msg.get("content", "")
            if isinstance(prev_content, str) and isinstance(new_content, str):
                result[-1]["content"] = prev_content + "\n" + new_content
            elif isinstance(prev_content, list) and isinstance(new_content, list):
                result[-1]["content"] = prev_content + new_content
            elif isinstance(prev_content, str) and isinstance(new_content, list):
                result[-1]["content"] = [{"type": "text", "text": prev_content}] + new_content
            elif isinstance(prev_content, list) and isinstance(new_content, str):
                result[-1]["content"] = prev_content + [{"type": "text", "text": new_content}]
        else:
            result.append(msg)
    return result


# --- Text extraction utilities ---

def extract_tool_call(text: str) -> tuple[str, dict] | None:
    """Extract a tool call from free text (fallback for models without native tool calling)."""
    # Strategy 1: ```json code block
    json_block = re.search(r"```json\s*\n?(.*?)\n?```", text, re.DOTALL)
    if json_block:
        try:
            call = json.loads(json_block.group(1).strip())
            if "tool" in call:
                return call["tool"], call.get("args", {})
        except json.JSONDecodeError:
            pass

    # Strategy 2: {"tool": ...} in text
    for match in re.finditer(r'\{[^{}]*"tool"\s*:', text):
        start = match.start()
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        call = json.loads(text[start : i + 1])
                        if "tool" in call:
                            return call["tool"], call.get("args", {})
                    except json.JSONDecodeError:
                        break
                    break

    return None


def strip_json_blocks(text: str) -> str:
    """Remove JSON tool call blocks from text for display."""
    cleaned = re.sub(r"```json[\s\S]*?```", "", text)
    cleaned = re.sub(r"```json[\s\S]*", "", cleaned)
    cleaned = re.sub(r"\{\s*\"tool\"\s*:[\s\S]*?\}", "", cleaned)
    return cleaned.strip()
