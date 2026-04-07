"""Core agent — connects LLM to desktop tools via streaming Ollama tool calling."""

import json
import time

from rich.console import Console
from rich.panel import Panel

from aulinx.audit import AuditLog
from aulinx.context.desktop import DesktopContext
from aulinx.history import HistoryManager
from aulinx.llm import OllamaClient, strip_json_blocks
from aulinx.tools.registry import ToolRegistry

console = Console()

SYSTEM_PROMPT = """\
You are Aulinx, an AI desktop agent on Linux. You control the desktop through tools.
ALWAYS respond in English. ALWAYS use a tool when the user asks for information or an action.
NEVER guess or make up data — call a tool first. After receiving a tool result, summarize it briefly.

Multi-step patterns:
- "write X to file and open it" → call file_write FIRST, then xdg_open AFTER it succeeds
- "type X in app" → first check the app is running (app_list_running), then use atspi_set_text or input_type_text
- "find and click button" → first atspi_find_elements, then atspi_do_action
- If a tool fails, try an ALTERNATIVE tool — do NOT retry the same tool with the same args
"""

MAX_TOOL_DEPTH = 5


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
        self.llm = OllamaClient(model, base_url, temperature)

    async def initialize(self):
        """Check Ollama is running and model is available."""
        ok = await self.llm.check()
        if ok:
            console.print(f"[dim]  Connected to Ollama ({self.model})[/dim]")
        else:
            console.print(
                f"[yellow]Warning: Model '{self.model}' not found or Ollama not running.[/yellow]\n"
                f"[dim]  Run: ollama serve && ollama pull {self.model}[/dim]"
            )

        await self.context.initialize()
        console.print(f"[dim]  Desktop: {self.context.status()}[/dim]")
        console.print(f"[dim]  Tools: {len(self.tools)} registered[/dim]\n")

    async def handle(self, user_input: str, _depth: int = 0, _last_tool_call: str = ""):
        """Process a user message with streaming tool calling."""
        if _depth == 0:
            if not user_input:
                return
            self.history.append({"role": "user", "content": user_input})

        if not self.llm.available:
            ok = await self.llm.check()
            if not ok:
                console.print("[red]Ollama is not available.[/red]")
                return

        # Build messages
        ctx = await self.context.snapshot()
        system_msg = SYSTEM_PROMPT + f"\n\nDesktop state:\n{ctx}"

        messages = [
            {"role": "system", "content": system_msg},
            *self.history[-self.max_history:],
        ]

        tools = self.tools.to_ollama_tools()

        # Stream response
        full_content = ""
        tool_calls = None
        first_token = True
        spinner = console.status("[dim]Thinking...[/dim]", spinner="dots")
        spinner.start()

        async for event in self.llm.chat_with_tools(messages, tools):
            if event.type == "token":
                if first_token:
                    spinner.stop()
                    first_token = False
                # Only print text if no tool calls coming (we'll know at "done")
                full_content = event.data.get("content", "")

            elif event.type == "tool_calls":
                spinner.stop()
                tool_calls = event.data.get("calls")

            elif event.type == "done":
                spinner.stop()
                full_content = event.data.get("content", "")
                tool_calls = event.data.get("tool_calls")

            elif event.type == "error":
                spinner.stop()
                console.print(f"[red]{event.data.get('message', 'Unknown error')}[/red]")
                return

        # Print text content (only if no tool calls — tool calls mean the text is noise)
        if full_content and not tool_calls:
            cleaned = strip_json_blocks(full_content)
            if cleaned:
                console.print(cleaned)

        # Save to history
        history_entry = {"role": "assistant", "content": full_content or ""}
        if tool_calls:
            history_entry["tool_calls"] = tool_calls
        self.history.append(history_entry)
        self.history_mgr.save(self.history)

        # Execute tool calls
        if tool_calls and _depth < MAX_TOOL_DEPTH:
            for tc in tool_calls:
                fn = tc.get("function", {})
                tool_name = fn.get("name", "")
                args = fn.get("arguments", {})

                # Prevent infinite retry of same failing tool
                call_sig = f"{tool_name}:{json.dumps(args, sort_keys=True)}"
                if call_sig == _last_tool_call:
                    console.print("[yellow]Same tool call repeated — stopping to avoid loop.[/yellow]")
                    self.history.append({
                        "role": "tool",
                        "content": json.dumps({"error": "Repeated call detected. Try a different approach."}),
                    })
                    continue

                if not tool_name or tool_name not in self.tools:
                    if tool_name:
                        console.print(f"[red]Unknown tool: {tool_name}[/red]")
                    self.history.append({
                        "role": "tool",
                        "content": json.dumps({"error": f"Unknown tool: {tool_name}"}),
                    })
                    continue

                # Permission check
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
                                "content": json.dumps({"denied": "User denied"}),
                            })
                            console.print("[dim]Action denied.[/dim]")
                            continue
                    except (EOFError, KeyboardInterrupt):
                        return
                else:
                    console.print(f"  [dim]> {tool_name}({_format_args(args)})[/dim]")

                # Execute
                t0 = time.monotonic()
                result = await self.tools.execute(tool_name, args)
                duration_ms = int((time.monotonic() - t0) * 1000)
                result_str = json.dumps(result, indent=2, ensure_ascii=False, default=str)

                self.audit.log(tool_name, args, result_str, duration_ms)

                if len(result_str) > 3000:
                    result_str = result_str[:3000] + "\n... (truncated)"

                is_error = isinstance(result, dict) and "error" in result
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

                self.history.append({"role": "tool", "content": result_str})

            # Let LLM process tool results (pass last call sig for duplicate detection)
            await self.handle("", _depth=_depth + 1, _last_tool_call=call_sig)


def _format_args(args: dict) -> str:
    if not args:
        return ""
    parts = []
    for k, v in args.items():
        val = json.dumps(v) if not isinstance(v, str) else v
        if len(val) > 50:
            val = val[:50] + "..."
        parts.append(f"{k}={val}")
    return ", ".join(parts)
