"""Ollama LLM client — shared by agent and WebSocket server."""

import asyncio
import json
import re
from typing import AsyncIterator

import httpx

MAX_RETRIES = 2


class LLMEvent:
    """Event emitted during LLM streaming."""

    def __init__(self, type: str, **kwargs):
        self.type = type  # "token", "tool_calls", "done", "error"
        self.data = kwargs


class OllamaClient:
    """Handles all communication with Ollama, including streaming and tool calling."""

    def __init__(self, model: str, base_url: str, temperature: float = 0.3):
        self.model = model
        self.base_url = base_url
        self.temperature = temperature
        self._available = False

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

    @property
    def available(self) -> bool:
        return self._available

    def available_models(self) -> list[str]:
        """Synchronously unavailable — use check() first."""
        return []

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
    ) -> AsyncIterator[LLMEvent]:
        """Stream a chat completion with native tool calling.

        Yields LLMEvent objects:
        - LLMEvent("token", content="...") for each text token
        - LLMEvent("tool_calls", calls=[...]) when tool calls are detected
        - LLMEvent("done", content="full text", tool_calls=[...] or None)
        - LLMEvent("error", message="...")
        """
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
                    # Model doesn't support tools — fall back to text streaming
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
                        # Final chunk — may contain tool_calls
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
                            # Don't stream JSON blocks character by character
                            if "```json" not in full_content:
                                yield LLMEvent("token", content=token)
                    except json.JSONDecodeError:
                        continue

        # Try extracting tool call from text
        tool_call = extract_tool_call(full_content)
        if tool_call:
            name, args = tool_call
            tool_calls = [{"function": {"name": name, "arguments": args}}]
            yield LLMEvent("tool_calls", calls=tool_calls)
            yield LLMEvent("done", content=full_content, tool_calls=tool_calls)
        else:
            yield LLMEvent("done", content=full_content, tool_calls=None)


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
