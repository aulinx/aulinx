"""Core agent — connects LLM to desktop tools."""

import json
import httpx
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from aulinx.context.desktop import DesktopContext
from aulinx.tools.registry import ToolRegistry

console = Console()

SYSTEM_PROMPT = """\
You are Aulinx, an AI desktop agent running on Linux. You can see and control \
the user's desktop through tools.

Available tools are provided below. Use them to help the user accomplish tasks \
on their desktop. Always prefer semantic actions (AT-SPI) over coordinate-based \
input.

When you need to perform an action, respond with a tool call in this JSON format:
{"tool": "tool_name", "args": {"param": "value"}}

When you want to respond to the user with text, just write normally.

Current desktop context:
{context}
"""


class Agent:
    def __init__(self, model: str = "qwen2.5:14b", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url
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
                        f"[yellow]Warning: Model '{self.model}' not found in Ollama. "
                        f"Available: {', '.join(models) or 'none'}[/yellow]"
                    )
                    console.print(f"[dim]Run: ollama pull {self.model}[/dim]\n")
                else:
                    console.print(f"[dim]  Connected to Ollama ({self.model})[/dim]")

        except (httpx.ConnectError, httpx.TimeoutException):
            console.print(
                "[red]Error: Cannot connect to Ollama at "
                f"{self.base_url}[/red]\n"
                "[dim]  Make sure Ollama is running: ollama serve[/dim]"
            )

        # Initialize desktop context (AT-SPI, etc.)
        await self.context.initialize()
        console.print(f"[dim]  Desktop context: {self.context.status()}[/dim]\n")

    async def handle(self, user_input: str):
        """Process a user message through the LLM and execute any tool calls."""
        self.history.append({"role": "user", "content": user_input})

        # Build system prompt with current desktop context
        ctx = await self.context.snapshot()
        system = SYSTEM_PROMPT.format(context=ctx)
        tool_descriptions = self.tools.describe()

        messages = [
            {"role": "system", "content": system + "\n\nTools:\n" + tool_descriptions},
            *self.history,
        ]

        # Stream response from Ollama
        response_text = ""
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/chat",
                json={"model": self.model, "messages": messages, "stream": True},
                timeout=60,
            ) as resp:
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                        token = chunk.get("message", {}).get("content", "")
                        response_text += token
                        console.print(token, end="", highlight=False)
                    except json.JSONDecodeError:
                        continue

        console.print()  # newline after stream

        # Check if response contains a tool call
        tool_result = await self._try_execute_tool(response_text)
        if tool_result:
            self.history.append({"role": "assistant", "content": response_text})
            self.history.append({"role": "system", "content": f"Tool result: {tool_result}"})
            # Let LLM process the tool result
            await self.handle(f"[Tool executed. Result: {tool_result}]")
        else:
            self.history.append({"role": "assistant", "content": response_text})

    async def _try_execute_tool(self, text: str) -> str | None:
        """Try to parse and execute a tool call from the LLM response."""
        # Look for JSON tool call pattern in the response
        try:
            # Find JSON in the response
            start = text.find('{"tool"')
            if start == -1:
                return None
            end = text.find("}", start) + 1
            if end <= start:
                return None

            call = json.loads(text[start:end])
            tool_name = call.get("tool")
            args = call.get("args", {})

            if not tool_name or tool_name not in self.tools:
                return None

            console.print(
                Panel(
                    f"[bold]Tool:[/bold] {tool_name}\n[bold]Args:[/bold] {json.dumps(args, indent=2)}",
                    title="[yellow]Executing tool[/yellow]",
                    border_style="yellow",
                )
            )

            result = await self.tools.execute(tool_name, args)
            console.print(
                Panel(str(result)[:500], title="[green]Result[/green]", border_style="green")
            )
            return str(result)

        except (json.JSONDecodeError, KeyError, TypeError):
            return None
