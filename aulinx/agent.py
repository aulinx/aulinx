"""Core agent — connects LLM to desktop tools via Ollama native tool calling."""

import json
import re
import time

import httpx
from rich.console import Console
from rich.panel import Panel

from aulinx.audit import AuditLog
from aulinx.context.desktop import DesktopContext
from aulinx.history import HistoryManager
from aulinx.tools.registry import ToolRegistry

console = Console()

SYSTEM_PROMPT = """\
You are Aulinx, an AI desktop agent on Linux. You control the desktop through tools.
ALWAYS use a tool when the user asks for information or an action. NEVER guess — call a tool.
You can call tools provided to you. After receiving a tool result, summarize it for the user.
"""

MAX_TOOL_DEPTH = 5
MAX_RETRIES = 2


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
        self.audit = AuditLog()
        self.history_mgr = HistoryManager()
        self.history: list[dict] = []
        self._ollama_ok = False

    async def initialize(self):
        """Check Ollama is running and model is available."""
        self._ollama_ok = await self._check_ollama()
        await self.context.initialize()
        console.print(f"[dim]  Desktop: {self.context.status()}[/dim]")
        console.print(f"[dim]  Tools: {len(self.tools)} registered[/dim]\n")

    async def _check_ollama(self) -> bool:
        """Verify Ollama connectivity and model availability."""
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
                    return False
                console.print(f"[dim]  Connected to Ollama ({self.model})[/dim]")
                return True

        except (httpx.ConnectError, httpx.TimeoutException):
            console.print(
                f"[red]Cannot connect to Ollama at {self.base_url}[/red]\n"
                "[dim]  Start it: ollama serve[/dim]"
            )
            return False

    async def handle(self, user_input: str, _depth: int = 0):
        """Process a user message through the LLM with native tool calling."""
        if _depth == 0:
            if not user_input:
                return
            self.history.append({"role": "user", "content": user_input})

        if not self._ollama_ok:
            self._ollama_ok = await self._check_ollama()
            if not self._ollama_ok:
                console.print("[red]Ollama is not available.[/red]")
                return

        # Build messages with desktop context in system prompt
        ctx = await self.context.snapshot()
        system_msg = SYSTEM_PROMPT + f"\n\nCurrent desktop state:\n{ctx}"

        messages = [
            {"role": "system", "content": system_msg},
            *self.history[-self.max_history:],
        ]

        # Call Ollama with native tool calling
        result = await self._chat_with_tools(messages)
        if result is None:
            return

        response_msg = result.get("message", {})
        role = response_msg.get("role", "assistant")
        content = response_msg.get("content", "")
        tool_calls = response_msg.get("tool_calls")

        # Print text content (if any)
        if content:
            # Strip any leftover JSON tool blocks from content
            cleaned = _strip_json_blocks(content)
            if cleaned:
                console.print(cleaned)

        # Save to history
        history_entry = {"role": role, "content": content or ""}
        if tool_calls:
            history_entry["tool_calls"] = tool_calls
        self.history.append(history_entry)
        self.history_mgr.save(self.history)

        # Handle tool calls
        if tool_calls and _depth < MAX_TOOL_DEPTH:
            for tc in tool_calls:
                fn = tc.get("function", {})
                tool_name = fn.get("name", "")
                args = fn.get("arguments", {})

                if not tool_name:
                    continue

                if tool_name not in self.tools:
                    console.print(f"[red]Unknown tool: {tool_name}[/red]")
                    self.history.append({
                        "role": "tool",
                        "content": json.dumps({"error": f"Unknown tool: {tool_name}"}),
                    })
                    continue

                # Check confirmation
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
                                "role": "tool",
                                "content": json.dumps({"denied": "User denied the action"}),
                            })
                            console.print("[dim]Action denied.[/dim]")
                            continue
                    except (EOFError, KeyboardInterrupt):
                        return
                else:
                    console.print(f"  [dim]> {tool_name}({_format_args(args)})[/dim]")

                # Execute tool
                t0 = time.monotonic()
                tool_result = await self.tools.execute(tool_name, args)
                duration_ms = int((time.monotonic() - t0) * 1000)
                result_str = json.dumps(tool_result, indent=2, ensure_ascii=False, default=str)

                # Audit
                self.audit.log(tool_name, args, result_str, duration_ms)

                # Check for error
                is_error = isinstance(tool_result, dict) and "error" in tool_result

                # Truncate large results
                if len(result_str) > 3000:
                    result_str = result_str[:3000] + "\n... (truncated)"

                # Display
                if is_error:
                    console.print(
                        Panel(result_str[:1000], title="[red]Error[/red]", border_style="red")
                    )
                else:
                    console.print(
                        Panel(
                            result_str[:1000],
                            title=f"[green]Result[/green] [dim]({duration_ms}ms)[/dim]",
                            border_style="green",
                        )
                    )

                # Add tool result to history (Ollama expects "tool" role)
                self.history.append({
                    "role": "tool",
                    "content": result_str,
                })

            # Let LLM process tool results
            await self.handle("", _depth=_depth + 1)

    async def _chat_with_tools(self, messages: list[dict]) -> dict | None:
        """Call Ollama chat API with native tool calling."""
        tools = self.tools.to_ollama_tools()

        for attempt in range(MAX_RETRIES + 1):
            try:
                spinner = console.status("[dim]Thinking...[/dim]", spinner="dots")
                spinner.start()

                try:
                    async with httpx.AsyncClient() as client:
                        resp = await client.post(
                            f"{self.base_url}/api/chat",
                            json={
                                "model": self.model,
                                "messages": messages,
                                "tools": tools,
                                "stream": False,
                                "options": {"temperature": self.temperature},
                            },
                            timeout=httpx.Timeout(connect=10, read=120, write=10, pool=10),
                        )
                        resp.raise_for_status()
                        return resp.json()
                finally:
                    spinner.stop()

            except httpx.ConnectError:
                self._ollama_ok = False
                if attempt < MAX_RETRIES:
                    console.print("[yellow]Connection lost. Retrying...[/yellow]")
                    await _async_sleep(2)
                else:
                    console.print("[red]Cannot reach Ollama.[/red]")
                    return None
            except httpx.ReadTimeout:
                if attempt < MAX_RETRIES:
                    console.print("[yellow]Timed out. Retrying...[/yellow]")
                else:
                    console.print("[yellow]Timed out. Try a simpler query.[/yellow]")
                    return None
            except httpx.HTTPStatusError as e:
                console.print(f"[red]Ollama error: {e.response.status_code}[/red]")
                if e.response.status_code == 400:
                    # Model might not support tools — fall back to text mode
                    console.print("[dim]Falling back to text mode (model may not support tool calling)[/dim]")
                    return await self._chat_text_fallback(messages)
                return None

        return None

    async def _chat_text_fallback(self, messages: list[dict]) -> dict | None:
        """Fallback: stream without native tools, extract JSON manually."""
        response_text = ""
        spinner = console.status("[dim]Thinking...[/dim]", spinner="dots")
        spinner.start()
        first_token = True

        try:
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
                            if not token:
                                continue
                            response_text += token
                            if first_token:
                                spinner.stop()
                                first_token = False
                            if "```json" not in response_text:
                                console.print(token, end="", highlight=False)
                        except json.JSONDecodeError:
                            continue
        finally:
            spinner.stop()

        console.print()

        # Try to extract tool call from text
        tool_call = _extract_tool_call(response_text)
        if tool_call:
            name, args = tool_call
            return {
                "message": {
                    "role": "assistant",
                    "content": response_text,
                    "tool_calls": [{
                        "function": {"name": name, "arguments": args}
                    }],
                }
            }

        return {"message": {"role": "assistant", "content": response_text}}


def _extract_tool_call(text: str) -> tuple[str, dict] | None:
    """Fallback: extract a tool call from free text (for models without native tool calling)."""
    json_block = re.search(r"```json\s*\n?(.*?)\n?```", text, re.DOTALL)
    if json_block:
        try:
            call = json.loads(json_block.group(1).strip())
            if "tool" in call:
                return call["tool"], call.get("args", {})
        except json.JSONDecodeError:
            pass

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


def _strip_json_blocks(text: str) -> str:
    """Remove JSON tool call blocks from text for display."""
    cleaned = text
    cleaned = re.sub(r"```json[\s\S]*?```", "", cleaned)
    cleaned = re.sub(r"```json[\s\S]*", "", cleaned)
    cleaned = re.sub(r"\{\s*\"tool\"\s*:[\s\S]*?\}", "", cleaned)
    return cleaned.strip()


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


async def _async_sleep(seconds: float):
    """Async sleep helper."""
    import asyncio
    await asyncio.sleep(seconds)
