"""Core agent — connects LLM to desktop tools."""

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
You are Aulinx, an AI desktop agent on Linux. You ALWAYS use tools to answer questions. NEVER guess or make up answers — call a tool first.

To use a tool, output a JSON block:
```json
{{"tool": "tool_name", "args": {{"key": "value"}}}}
```
Rules:
- ALWAYS call a tool when the user asks for information or an action
- ONE tool per response. Wait for the result.
- Brief explanation before the JSON is OK.

IMPORTANT — match user requests to the RIGHT tool:
- time/date/clock → date_now
- timer/reminder/alarm → set_timer
- search in files/code → text_grep (NOT git_log)
- system memory/RAM → system_info
- volume/sound → audio_get_volume or audio_set_volume
- dark mode/theme → theme_set_dark or theme_get
- open a file/URL → xdg_open
- wifi → wifi_list or network_status
- bluetooth → bluetooth_status
- brightness → display_brightness
- battery/power → power_status
- git history → git_log
- git changes → git_status or git_diff
- list windows → window_list
- click button → atspi_do_action
- read UI text → atspi_read_text
- calendar → calendar_show
- who am i → who_am_i
- disk space → disk_usage
- files/directories → file_list, file_read, file_search
- processes/CPU → process_list
- kill process → process_kill
- services → service_list or service_status
- install package → package_install
- environment vars → env_get

Desktop: {context}

Tools:
{tools}
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
        """Process a user message through the LLM and execute any tool calls."""
        if _depth == 0:
            # Skip empty inputs from tool result continuations
            if not user_input:
                return
            self.history.append({"role": "user", "content": user_input})

        # Check Ollama is still available
        if not self._ollama_ok:
            self._ollama_ok = await self._check_ollama()
            if not self._ollama_ok:
                console.print("[red]Ollama is not available. Please start it and try again.[/red]")
                return

        # Build messages
        ctx = await self.context.snapshot()
        system = SYSTEM_PROMPT.format(
            context=ctx,
            tools=self.tools.describe(compact=True),
        )

        messages = [
            {"role": "system", "content": system},
            *self.history[-self.max_history:],
        ]

        # Stream response with retry
        response_text = await self._stream_with_retry(messages)
        if response_text is None:
            return  # all retries failed

        console.print()

        self.history.append({"role": "assistant", "content": response_text})
        self.history_mgr.save(self.history)

        # Try to extract and execute tool call
        tool_call = _extract_tool_call(response_text)
        if tool_call and _depth < MAX_TOOL_DEPTH:
            await self._execute_tool_call(tool_call, _depth)

    async def _stream_with_retry(self, messages: list[dict]) -> str | None:
        """Stream chat with retry on transient failures."""
        for attempt in range(MAX_RETRIES + 1):
            try:
                return await self._stream_chat(messages)
            except httpx.ConnectError:
                self._ollama_ok = False
                if attempt < MAX_RETRIES:
                    console.print(
                        f"[yellow]Connection lost. Retrying ({attempt + 1}/{MAX_RETRIES})...[/yellow]"
                    )
                    await _async_sleep(2)
                else:
                    console.print("[red]Cannot reach Ollama after retries. Is it still running?[/red]")
                    return None
            except httpx.ReadTimeout:
                if attempt < MAX_RETRIES:
                    console.print(
                        f"[yellow]Response timed out. Retrying ({attempt + 1}/{MAX_RETRIES})...[/yellow]"
                    )
                else:
                    console.print("[yellow]Response timed out. Try a simpler query or a smaller model.[/yellow]")
                    return None
            except httpx.HTTPStatusError as e:
                console.print(f"[red]Ollama error: {e.response.status_code}[/red]")
                if e.response.status_code == 404:
                    console.print(f"[dim]Model '{self.model}' not found. Run: ollama pull {self.model}[/dim]")
                return None
        return None

    async def _execute_tool_call(self, tool_call: tuple[str, dict], _depth: int):
        """Execute a tool call with confirmation and error handling."""
        tool_name, args = tool_call

        if tool_name not in self.tools:
            error_msg = f"Unknown tool: {tool_name}"
            console.print(f"[red]{error_msg}[/red]")
            self.history.append({"role": "system", "content": error_msg})
            # Let the LLM try again with a different tool
            await self.handle("", _depth=_depth + 1)
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
                        "content": "User denied the action. Suggest an alternative or ask what they'd prefer.",
                    })
                    console.print("[dim]Action denied.[/dim]")
                    await self.handle("", _depth=_depth + 1)
                    return
            except (EOFError, KeyboardInterrupt):
                return
        else:
            console.print(f"  [dim]> {tool_name}({_format_args(args)})[/dim]")

        # Execute with timing
        t0 = time.monotonic()
        result = await self.tools.execute(tool_name, args)
        duration_ms = int((time.monotonic() - t0) * 1000)
        result_str = json.dumps(result, indent=2, ensure_ascii=False, default=str)

        # Audit log
        self.audit.log(tool_name, args, result_str, duration_ms)

        # Check for tool errors
        is_error = isinstance(result, dict) and "error" in result

        # Truncate large results
        if len(result_str) > 3000:
            result_str = result_str[:3000] + "\n... (truncated)"

        # Display result
        if is_error:
            console.print(
                Panel(
                    result_str[:1000],
                    title="[red]Error[/red]",
                    border_style="red",
                )
            )
            self.history.append({
                "role": "system",
                "content": f"Tool '{tool_name}' FAILED:\n{result_str}\n"
                "Explain the error to the user and suggest an alternative approach.",
            })
        else:
            console.print(
                Panel(
                    result_str[:1000],
                    title=f"[green]Result[/green] [dim]({duration_ms}ms)[/dim]",
                    border_style="green",
                )
            )
            self.history.append({
                "role": "system",
                "content": f"Tool '{tool_name}' returned:\n{result_str}",
            })

        # Let LLM continue with the result
        await self.handle("", _depth=_depth + 1)

    async def _stream_chat(self, messages: list[dict]) -> str:
        """Stream a chat completion from Ollama with spinner on first token."""
        response_text = ""
        first_token = True
        spinner = console.status("[dim]Thinking...[/dim]", spinner="dots")
        spinner.start()

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

                            # Stop spinner on first real token
                            if first_token:
                                spinner.stop()
                                first_token = False

                            # Don't print JSON tool calls character by character
                            if "```json" not in response_text:
                                console.print(token, end="", highlight=False)
                            elif response_text.endswith("```\n") or response_text.endswith("```"):
                                console.print(response_text, highlight=False, end="")
                        except json.JSONDecodeError:
                            continue
        finally:
            spinner.stop()

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
