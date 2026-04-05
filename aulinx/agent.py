"""Core agent — connects LLM to desktop tools."""

import json
import re
import httpx
from rich.console import Console
from rich.panel import Panel

from aulinx.context.desktop import DesktopContext
from aulinx.tools.registry import ToolRegistry

console = Console()

SYSTEM_PROMPT = """\
You are Aulinx, an AI desktop agent running on Linux. You control the user's \
desktop through tools.

RULES:
1. To use a tool, output EXACTLY one JSON block on its own line:
   ```json
   {{"tool": "tool_name", "args": {{"param": "value"}}}}
   ```
2. You may include text before the JSON block to explain what you're doing.
3. Only call ONE tool per response. Wait for the result before calling another.
4. If no tool is needed, respond with plain text.
5. Prefer AT-SPI tools (atspi_*) for UI interaction — they're semantic and reliable.
6. For destructive actions (shell_exec, file operations), explain what you'll do first.

CURRENT DESKTOP STATE:
{context}

AVAILABLE TOOLS:
{tools}
"""

MAX_TOOL_DEPTH = 5  # prevent infinite tool call loops


class Agent:
    def __init__(
        self,
        model: str = "qwen2.5:14b",
        base_url: str = "http://localhost:11434",
        temperature: float = 0.3,
        max_history: int = 20,
    ):
        self.model = model
        self.base_url = base_url
        self.temperature = temperature
        self.max_history = max_history
        self.context = DesktopContext()
        self.tools = ToolRegistry()
        self.history: list[dict] = []

    async def initialize(self):
        """Check Ollama is running and model is available."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self.base_url}/api/tags", timeout=5)
                resp.raise_for_status()
                models = [m["name"] for m in resp.json().get("models", [])]

                if not any(self.model in m for m in models):
                    console.print(
                        f"[yellow]Warning: Model '{self.model}' not found. "
                        f"Available: {', '.join(models) or 'none'}[/yellow]"
                    )
                    console.print(f"[dim]Run: ollama pull {self.model}[/dim]\n")
                else:
                    console.print(f"[dim]  Connected to Ollama ({self.model})[/dim]")

        except (httpx.ConnectError, httpx.TimeoutException):
            console.print(
                "[red]Cannot connect to Ollama at "
                f"{self.base_url}[/red]\n"
                "[dim]  Start it: ollama serve[/dim]"
            )

        await self.context.initialize()
        console.print(f"[dim]  Desktop: {self.context.status()}[/dim]")
        console.print(f"[dim]  Tools: {len(self.tools)} registered[/dim]\n")

    async def handle(self, user_input: str, _depth: int = 0):
        """Process a user message through the LLM and execute any tool calls."""
        if _depth == 0:
            self.history.append({"role": "user", "content": user_input})

        # Build messages
        ctx = await self.context.snapshot()
        system = SYSTEM_PROMPT.format(
            context=ctx,
            tools=self.tools.describe(),
        )

        messages = [
            {"role": "system", "content": system},
            *self.history[-self.max_history:],
        ]

        # Stream response
        response_text = await self._stream_chat(messages)
        console.print()

        self.history.append({"role": "assistant", "content": response_text})

        # Try to extract and execute tool call
        tool_call = _extract_tool_call(response_text)
        if tool_call and _depth < MAX_TOOL_DEPTH:
            tool_name, args = tool_call

            if tool_name not in self.tools:
                console.print(f"[red]Unknown tool: {tool_name}[/red]")
                return

            # Check if action needs confirmation
            if self.tools.needs_confirmation(tool_name):
                console.print(
                    Panel(
                        f"[bold]Tool:[/bold] {tool_name}\n"
                        f"[bold]Args:[/bold] {json.dumps(args, indent=2)}",
                        title="[yellow]Confirm action?[/yellow]",
                        border_style="yellow",
                    )
                )
                try:
                    answer = input("  Allow? [y/N] ").strip().lower()
                    if answer not in ("y", "yes"):
                        self.history.append({
                            "role": "system",
                            "content": "User denied the action.",
                        })
                        console.print("[dim]Action denied.[/dim]")
                        return
                except (EOFError, KeyboardInterrupt):
                    return
            else:
                console.print(
                    f"  [dim]> {tool_name}({_format_args(args)})[/dim]"
                )

            # Execute
            result = await self.tools.execute(tool_name, args)
            result_str = json.dumps(result, indent=2, ensure_ascii=False, default=str)

            # Truncate large results
            if len(result_str) > 3000:
                result_str = result_str[:3000] + "\n... (truncated)"

            console.print(
                Panel(
                    result_str[:1000],
                    title="[green]Result[/green]",
                    border_style="green",
                )
            )

            # Feed result back to LLM
            self.history.append({
                "role": "system",
                "content": f"Tool '{tool_name}' returned:\n{result_str}",
            })

            # Let LLM continue with the result
            await self.handle("", _depth=_depth + 1)

    async def _stream_chat(self, messages: list[dict]) -> str:
        """Stream a chat completion from Ollama."""
        response_text = ""
        async with httpx.AsyncClient() as client:
            try:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": messages,
                        "stream": True,
                        "options": {"temperature": self.temperature},
                    },
                    timeout=90,
                ) as resp:
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                            token = chunk.get("message", {}).get("content", "")
                            response_text += token
                            # Don't print JSON tool calls character by character
                            if "```json" not in response_text:
                                console.print(token, end="", highlight=False)
                            elif response_text.endswith("```\n") or response_text.endswith("```"):
                                # Print the full response once JSON block is complete
                                console.print(response_text, highlight=False, end="")
                        except json.JSONDecodeError:
                            continue
            except httpx.ReadTimeout:
                console.print("\n[yellow]Response timed out.[/yellow]")

        return response_text


def _extract_tool_call(text: str) -> tuple[str, dict] | None:
    """Extract a tool call from the LLM response. Handles multiple formats."""
    # Strategy 1: Look for ```json code block
    json_block = re.search(r"```json\s*\n?(.*?)\n?```", text, re.DOTALL)
    if json_block:
        try:
            call = json.loads(json_block.group(1).strip())
            if "tool" in call:
                return call["tool"], call.get("args", {})
        except json.JSONDecodeError:
            pass

    # Strategy 2: Look for {"tool": ...} anywhere in text
    # Use a greedy approach to handle nested braces
    for match in re.finditer(r'\{[^{}]*"tool"\s*:', text):
        start = match.start()
        # Find matching closing brace
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


def _format_args(args: dict) -> str:
    """Format tool args for display."""
    if not args:
        return ""
    parts = []
    for k, v in args.items():
        val = json.dumps(v) if not isinstance(v, str) else v
        if len(val) > 50:
            val = val[:50] + "..."
        parts.append(f"{k}={val}")
    return ", ".join(parts)
