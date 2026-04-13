"""Aulinx SDK — programmatic Python API for the Aulinx agent.

Usage::

    from aulinx.sdk import AulinxClient

    async def main():
        client = AulinxClient(provider="ollama", model="qwen2.5:14b")

        # Execute a single tool directly
        result = await client.execute_tool("date_now")
        print(result)

        # List available tools
        tools = await client.list_tools()

        # Run a natural-language instruction through the agent
        run = await client.run("What time is it?")
        print(run.response)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from aulinx.llm import LLMClient, create_client, strip_json_blocks
from aulinx.tools.registry import ToolRegistry


@dataclass
class RunResult:
    """Result of an agent run."""

    response: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    tool_results: list[dict] = field(default_factory=list)
    success: bool = True
    duration_s: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0


class AulinxClient:
    """High-level SDK client for programmatic access to Aulinx.

    Wraps the tool registry and LLM client to provide a clean API
    without the interactive REPL or Rich console output.
    """

    def __init__(
        self,
        provider: str = "ollama",
        model: str = "",
        base_url: str = "",
        api_key: str = "",
        mode: str = "desktop",
    ):
        self._provider = provider
        self._model = model
        self._base_url = base_url
        self._api_key = api_key
        self._mode = mode
        self._tools = ToolRegistry(mode=mode)
        self._llm: LLMClient = create_client(
            provider=provider,
            model=model,
            base_url=base_url,
            api_key=api_key,
        )
        self._stats = {
            "runs": 0,
            "tool_calls": 0,
            "total_tokens_in": 0,
            "total_tokens_out": 0,
            "total_duration_s": 0.0,
        }

    # -- Public API -----------------------------------------------------------

    async def run(self, instruction: str) -> RunResult:
        """Execute a natural language instruction and return the result.

        Sends the instruction to the LLM with the full tool set,
        executes any tool calls the model requests, and returns the
        aggregated result.
        """
        return await self.run_with_tools(instruction, tools=None)

    async def run_with_tools(
        self,
        instruction: str,
        tools: list[str] | None = None,
    ) -> RunResult:
        """Execute an instruction with a specific subset of tools enabled.

        Args:
            instruction: Natural language instruction for the agent.
            tools: Optional list of tool names to make available. If None,
                   all tools for the current mode are available.

        Returns:
            RunResult with the LLM response and any tool call details.
        """
        t0 = time.monotonic()
        result = RunResult()

        # Build tool schemas
        if tools is not None:
            schemas = [
                t.to_ollama_schema()
                for t in self._tools._tools.values()
                if t.name in tools
            ]
        else:
            schemas = self._tools.to_ollama_tools()

        from aulinx.agent import SYSTEM_PROMPTS

        messages = [
            {"role": "system", "content": SYSTEM_PROMPTS.get(self._mode, SYSTEM_PROMPTS["desktop"])},
            {"role": "user", "content": instruction},
        ]

        # Stream LLM response
        full_content = ""
        tool_calls_raw: list[dict] | None = None

        try:
            async for event in self._llm.chat_with_tools(messages, schemas):
                if event.type == "token":
                    full_content = event.data.get("content", "")
                elif event.type == "tool_calls":
                    tool_calls_raw = event.data.get("calls")
                elif event.type == "done":
                    full_content = event.data.get("content", "")
                    tool_calls_raw = event.data.get("tool_calls") or tool_calls_raw
                    result.tokens_in = event.data.get("tokens_in", 0)
                    result.tokens_out = event.data.get("tokens_out", 0)
                elif event.type == "error":
                    result.success = False
                    result.response = event.data.get("message", "Unknown error")
                    break
        except Exception as exc:
            result.success = False
            result.response = str(exc)
            result.duration_s = time.monotonic() - t0
            self._update_stats(result)
            return result

        # Execute tool calls
        if tool_calls_raw:
            for tc in tool_calls_raw:
                fn = tc.get("function", {})
                tool_name = fn.get("name", "")
                args = fn.get("arguments", {})

                result.tool_calls.append({"name": tool_name, "arguments": args})

                if tool_name in self._tools:
                    tool_result = await self._tools.execute(tool_name, args)
                    result.tool_results.append(
                        {"name": tool_name, "result": tool_result}
                    )
                else:
                    result.tool_results.append(
                        {"name": tool_name, "result": {"error": f"Unknown tool: {tool_name}"}}
                    )

        result.response = strip_json_blocks(full_content) if full_content else ""
        result.duration_s = time.monotonic() - t0
        self._update_stats(result)
        return result

    async def list_tools(self, mode: str | None = None) -> list[dict]:
        """List available tools.

        Args:
            mode: Override mode filter ("core", "desktop", "compositor").
                  If None, uses the client's configured mode.

        Returns:
            List of dicts with tool name, description, tier, and parameters.
        """
        registry = self._tools
        if mode is not None and mode != self._mode:
            registry = ToolRegistry(mode=mode)

        return [
            {
                "name": tool.name,
                "description": tool.description,
                "tier": tool.tier.name,
                "parameters": tool.parameters or {},
            }
            for tool in sorted(registry._tools.values(), key=lambda t: t.name)
        ]

    async def execute_tool(self, name: str, **kwargs) -> dict:
        """Execute a single tool directly by name.

        Args:
            name: Tool name (e.g. "date_now", "who_am_i").
            **kwargs: Arguments to pass to the tool function.

        Returns:
            Tool result dict, or ``{"error": "..."}`` on failure.
        """
        result = await self._tools.execute(name, kwargs)
        self._stats["tool_calls"] += 1
        return result

    def get_stats(self) -> dict:
        """Get cumulative usage statistics for this client.

        Returns:
            Dict with runs, tool_calls, total_tokens_in,
            total_tokens_out, total_duration_s.
        """
        return dict(self._stats)

    # -- Helpers --------------------------------------------------------------

    def _update_stats(self, result: RunResult) -> None:
        self._stats["runs"] += 1
        self._stats["tool_calls"] += len(result.tool_calls)
        self._stats["total_tokens_in"] += result.tokens_in
        self._stats["total_tokens_out"] += result.tokens_out
        self._stats["total_duration_s"] += result.duration_s
