"""Core agent — connects LLM to desktop tools via streaming Ollama tool calling."""

import json
import time

from rich.console import Console
from rich.panel import Panel

from aulinx.audit import AuditLog
from aulinx.context.desktop import DesktopContext
from aulinx.grounding import ground_element_from_tree
from aulinx.history import HistoryManager
from aulinx.llm import LLMClient, create_client, strip_json_blocks
from aulinx.multi_agent import build_coordination_summary, decompose_task, execute_delegation_plan
from aulinx.outcomes import OutcomeStore, TaskOutcome
from aulinx.planner import ExecutionPlan, build_planning_prompt, inject_plan_into_system, parse_plan
from aulinx.recovery import RecoveryState
from aulinx.summarizer import should_summarize, summarize_history
from aulinx.tool_selector import select_tools
from aulinx.tools.registry import ToolRegistry

console = Console()

SYSTEM_PROMPTS = {
    "core": """\
You are Aulinx, an AI agent for Linux systems. You manage the system through tools.
ALWAYS respond in English. ALWAYS use a tool when the user asks for information or an action.
NEVER guess or make up data — call a tool first. After receiving a tool result, summarize it briefly.

You are running in HEADLESS mode (no GUI). You can manage files, processes, git, network, \
packages, services, docker, logs, and system configuration. You CANNOT control GUI apps or windows.

Multi-step patterns:
- "deploy app" → git_status → shell_exec build → service restart
- "debug server" → journal_logs + port_list + process_list to diagnose
- "check containers" → docker_ps → docker_logs for failing ones
- "security audit" → firewall_status + port_list + cron_list
- "disk issues" → disk_usage + disk_health + journal_logs priority=err
- If a tool fails, try an ALTERNATIVE tool — do NOT retry the same tool with the same args
""",
    "desktop": """\
You are Aulinx, an AI agent for the Linux desktop. You control the desktop through tools.
ALWAYS respond in English. ALWAYS use a tool when the user asks for information or an action.
NEVER guess or make up data — call a tool first. After receiving a tool result, summarize it briefly.

You can see and control GUI apps via AT-SPI (accessibility API). You can click buttons, \
read text, type into fields, manage windows, and control system settings.

Multi-step patterns:
- "write X to file and open it" → call file_write FIRST, then xdg_open AFTER it succeeds
- "type X in app" → first check the app is running (app_list_running), then use atspi_set_text or input_type_text
- "find and click button" → first atspi_find_elements, then atspi_do_action
- If a tool fails, try an ALTERNATIVE tool — do NOT retry the same tool with the same args
""",
    "compositor": """\
You are Aulinx, an AI agent running inside the Aulinx compositor — a custom Wayland compositor \
with a semantic scene graph. You have DIRECT access to the display pipeline.
ALWAYS respond in English. ALWAYS use a tool when the user asks for information or an action.
NEVER guess or make up data — call a tool first. After receiving a tool result, summarize it briefly.

You can use compositor_* tools for precise control: compositor_click at exact coordinates, \
compositor_type text, compositor_screenshot, compositor_spawn apps. These are FASTER and \
MORE RELIABLE than AT-SPI tools because you own the display pipeline.

Start with compositor_summary to get full desktop context in one call (description + ASCII layout + suggestions).
Prefer compositor_* tools over atspi_* tools when both are available.

Multi-step patterns:
- "what's on screen" → compositor_describe (text) or compositor_ascii (layout map) or compositor_screenshot (image)
- "what should I do" → compositor_suggest for AI-suggested next actions
- "open app and type" → compositor_spawn, compositor_wait_for, compositor_type
- "click at position" → compositor_describe + compositor_click
- "do multiple things" → compositor_batch for atomic multi-step actions
- "arrange layout" → compositor_set_ratio, compositor_set_gap, compositor_swap_master
- If a tool fails, try an ALTERNATIVE tool — do NOT retry the same tool with the same args
""",
}

MAX_TOOL_DEPTH = 5


class Agent:
    def __init__(
        self,
        model: str = "qwen2.5:14b",
        base_url: str = "http://localhost:11434",
        temperature: float = 0.3,
        max_history: int = 20,
        mode: str = "desktop",
        provider: str = "ollama",
        api_key: str = "",
    ):
        self.model = model
        self.base_url = base_url
        self.temperature = temperature
        self.max_history = max_history
        self.mode = mode
        self.provider = provider
        self.context = DesktopContext()
        self.tools = ToolRegistry(mode=mode)
        self.audit = AuditLog()
        self.history_mgr = HistoryManager()
        self.history: list[dict] = []
        self.llm: LLMClient = create_client(
            provider=provider,
            model=model,
            base_url=base_url,
            temperature=temperature,
            api_key=api_key,
        )
        self.plan: ExecutionPlan | None = None
        self.use_planner: bool = False  # enable with --plan flag
        self.use_dynamic_tools: bool = False  # enable with --dynamic-tools flag
        self.use_learning: bool = False  # enable with --learn flag
        self.use_multi_agent: bool = False  # enable with --multi-agent flag
        self.recovery = RecoveryState()
        self.outcomes = OutcomeStore()
        self._last_a11y_tree: str = ""  # cached for grounding
        self._task_start: float = 0.0
        self._task_actions: list[str] = []

    async def initialize(self):
        """Check Ollama is running and model is available."""
        ok = await self.llm.check()
        if ok:
            console.print(f"[dim]  Connected to {self.provider} ({self.llm.model})[/dim]")
        else:
            if self.provider == "ollama":
                console.print(
                    f"[yellow]Warning: Model '{self.llm.model}' not found or Ollama not running.[/yellow]\n"
                    f"[dim]  Run: ollama serve && ollama pull {self.llm.model}[/dim]"
                )
            else:
                console.print(
                    f"[yellow]Warning: Could not connect to {self.provider}.[/yellow]\n"
                    f"[dim]  Check your API key and network connection.[/dim]"
                )

        await self.context.initialize()
        console.print(f"[dim]  Desktop: {self.context.status()}[/dim]")
        console.print(f"[dim]  Tools: {len(self.tools)} registered[/dim]\n")

    async def handle(self, user_input: str, _depth: int = 0):
        """Process a user message with streaming tool calling."""
        if _depth == 0:
            if not user_input:
                return
            self.history.append({"role": "user", "content": user_input})
            self.recovery.reset()
            self.plan = None
            self._task_start = time.monotonic()
            self._task_actions = []

        if not self.llm.available:
            ok = await self.llm.check()
            if not ok:
                console.print("[red]Ollama is not available.[/red]")
                return

        # Build messages with desktop context + long-term memory
        ctx = await self.context.snapshot()
        user_query = self.history[-1].get("content", "") if self.history else ""
        memory_ctx = ""
        try:
            from aulinx.long_memory import LongMemory
            memory_ctx = LongMemory().summarize_for_context(user_query)
        except Exception:
            pass
        system_msg = SYSTEM_PROMPTS.get(self.mode, SYSTEM_PROMPTS["desktop"]) + f"\n\nSystem state:\n{ctx}"
        if memory_ctx:
            system_msg += f"\n\n{memory_ctx}"

        # Inject past experience from outcomes (learning)
        if self.use_learning and _depth == 0 and user_query:
            experience = self.outcomes.build_experience_context(user_query)
            if experience:
                system_msg += f"\n\n{experience}"

        # Multi-agent delegation: decompose complex tasks into parallel subtasks
        if self.use_multi_agent and _depth == 0:
            delegated = await self._try_delegate(user_query, system_msg)
            if delegated:
                return

        # Planning: generate a plan on first call, inject into system prompt on subsequent calls
        if self.use_planner and _depth == 0 and self.plan is None:
            await self._generate_plan(user_query, ctx)
        if self.plan and not self.plan.is_complete:
            system_msg = inject_plan_into_system(system_msg, self.plan)

        # Summarize older history to save tokens
        history_slice = self.history[-self.max_history:]
        if should_summarize(history_slice):
            history_slice = summarize_history(history_slice)

        messages = [
            {"role": "system", "content": system_msg},
            *history_slice,
        ]

        # Dynamic tool selection: pick tools relevant to the query
        if self.use_dynamic_tools and user_query:
            selected_names = select_tools(
                user_query,
                mode=self.mode,
                available_tools=set(self.tools._tools.keys()),
            )
            tools = [
                t.to_ollama_schema()
                for t in self.tools._tools.values()
                if t.name in selected_names
            ]
        else:
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

            # Record outcome when the agent gives a final text response (no more tool calls)
            if self.use_learning and _depth > 0 and self._task_actions:
                self._record_outcome(user_query, full_content)

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
                call_sig = json.dumps(args, sort_keys=True)
                if self.recovery.is_repeated_call(tool_name, call_sig):
                    hint = self.recovery.build_recovery_hint(tool_name, "Repeated call detected")
                    console.print(f"[yellow]Repeated call — {hint}[/yellow]")
                    self.history.append({
                        "role": "tool",
                        "content": json.dumps({"error": hint}),
                    })
                    continue
                self.recovery.record_call(tool_name, call_sig)

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

                # Action grounding: if clicking/typing and we have a cached tree,
                # try to resolve element names to exact coordinates
                args = self._try_ground_action(tool_name, args)

                # Execute
                t0 = time.monotonic()
                result = await self.tools.execute(tool_name, args)
                duration_ms = int((time.monotonic() - t0) * 1000)
                result_str = json.dumps(result, indent=2, ensure_ascii=False, default=str)

                self.audit.log(tool_name, args, result_str, duration_ms)
                self._task_actions.append(f"{tool_name}({_format_args(args)})")

                if len(result_str) > 3000:
                    result_str = result_str[:3000] + "\n... (truncated)"

                is_error = isinstance(result, dict) and "error" in result
                if is_error:
                    self.recovery.record_failure(tool_name, call_sig, result_str[:200])
                    hint = self.recovery.build_recovery_hint(tool_name, result_str[:200])
                    console.print(
                        Panel(result_str[:1000], title="[red]Error[/red]", border_style="red")
                    )
                    # Inject recovery hint into tool result
                    result_str = json.dumps({"error": result.get("error", ""), "recovery_hint": hint})
                else:
                    self.recovery.record_success()
                    console.print(
                        Panel(
                            result_str[:1000],
                            title=f"[green]Result[/green] [dim]({duration_ms}ms)[/dim]",
                            border_style="green",
                        )
                    )

                self.history.append({"role": "tool", "content": result_str})

                # Cache a11y tree from observation tools for grounding
                if tool_name in ("atspi_get_tree", "atspi_find_elements", "scene_find"):
                    self._last_a11y_tree = result_str

                # Advance plan if active
                if self.plan and not self.plan.is_complete:
                    if is_error:
                        self.plan.fail_current(result_str[:200])
                    else:
                        self.plan.advance(result_str[:200])

            # Let LLM process tool results
            await self.handle("", _depth=_depth + 1)


    async def _try_delegate(self, goal: str, system_prompt: str) -> bool:
        """Try to delegate the task to multiple worker agents.

        Returns True if delegation happened (caller should return),
        False if the task is too simple for delegation.
        """
        tool_names = list(self.tools._tools.keys())
        plan = await decompose_task(goal, self.llm, tool_names)

        # Only delegate if there are 2+ independent subtasks
        if len(plan.subtasks) < 2:
            return False

        console.print(f"\n[dim]Delegating to {len(plan.subtasks)} worker agents:[/dim]")
        for st in plan.subtasks:
            tools_str = f" [dim]({', '.join(st.tools_hint[:3])})[/dim]" if st.tools_hint else ""
            console.print(f"  [dim]{st.id}. {st.description}{tools_str}[/dim]")
        console.print()

        # Execute all subtasks
        await execute_delegation_plan(plan, self.llm, self.tools, system_prompt)

        # Build and display the combined result
        summary = build_coordination_summary(plan)
        console.print(summary)

        # Add to history so the conversation continues naturally
        self.history.append({"role": "assistant", "content": summary})
        self.history_mgr.save(self.history)

        return True

    def _record_outcome(self, goal: str, final_response: str):
        """Record the outcome of a completed task for future learning."""
        # Heuristic: if the response contains error indicators, mark as failed
        response_lower = final_response.lower()
        failed_indicators = ["error", "failed", "couldn't", "unable", "cannot", "not possible"]
        success = not any(ind in response_lower for ind in failed_indicators)

        plan_steps = []
        if self.plan:
            plan_steps = [f"{s.number}. {s.tool} — {s.description}" for s in self.plan.steps]

        failure_reason = ""
        if not success:
            # Extract first error from history
            for msg in reversed(self.history):
                content = msg.get("content", "")
                if '"error"' in content:
                    failure_reason = content[:200]
                    break

        outcome = TaskOutcome(
            goal=goal,
            plan_steps=plan_steps,
            actions_taken=self._task_actions[:10],
            success=success,
            failure_reason=failure_reason,
            duration_s=round(time.monotonic() - self._task_start, 1),
            model=self.llm.model,
        )
        self.outcomes.record(outcome)

    def _try_ground_action(self, tool_name: str, args: dict) -> dict:
        """Try to ground element references in tool args to exact coordinates.

        If the LLM calls a click/type tool with a target element name,
        look up its coordinates in the cached a11y tree.
        """
        if not self._last_a11y_tree:
            return args

        # Grounding for click tools: if 'element' or 'name' is provided but no coordinates
        click_tools = {"compositor_click", "atspi_do_action", "input_key_combo"}
        if tool_name in click_tools:
            element_name = args.get("element") or args.get("name") or args.get("query", "")
            if element_name and "x" not in args and "y" not in args:
                grounded = ground_element_from_tree(element_name, self._last_a11y_tree)
                if grounded:
                    args = {**args, "x": grounded.center_x, "y": grounded.center_y}
                    console.print(f"  [dim]Grounded '{element_name}' → ({grounded.center_x}, {grounded.center_y})[/dim]")

        return args

    async def _generate_plan(self, goal: str, context: str):
        """Generate an execution plan using the LLM."""
        tool_names = list(self.tools._tools.keys())
        planning_prompt = build_planning_prompt(goal, tool_names, context)

        messages = [
            {"role": "system", "content": planning_prompt},
            {"role": "user", "content": goal},
        ]

        plan_text = ""
        async for event in self.llm.chat_with_tools(messages, []):
            if event.type == "token":
                plan_text += event.data.get("content", "")
            elif event.type == "done":
                plan_text = event.data.get("content", plan_text)

        steps = parse_plan(plan_text)
        if steps:
            self.plan = ExecutionPlan(goal=goal, steps=steps)
            console.print(f"\n[dim]Plan ({len(steps)} steps):[/dim]")
            console.print(f"[dim]{self.plan.format_plan()}[/dim]\n")
        else:
            # Planning failed — fall back to direct execution
            self.plan = None


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
