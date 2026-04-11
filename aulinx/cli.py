"""Aulinx CLI — AI-native Linux agent."""

import argparse
import asyncio
import os

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from rich.console import Console

from aulinx import __version__
from aulinx.agent import Agent
from aulinx.completer import AulinxCompleter
from aulinx.config import load_config


def detect_mode() -> str:
    """Auto-detect the operating mode based on environment.

    Returns:
        'compositor' — running inside Aulinx compositor (AULINX_COMPOSITOR=1 or IPC socket exists)
        'desktop'    — running on a Linux desktop (WAYLAND_DISPLAY or DISPLAY set)
        'core'       — headless / server / SSH (no display)
    """
    # Fast path: AULINX_COMPOSITOR env var set by compositor for child processes
    if os.environ.get("AULINX_COMPOSITOR") == "1":
        return "compositor"

    # Check for compositor IPC socket
    xdg = os.environ.get("XDG_RUNTIME_DIR", "")
    compositor_socket = os.environ.get("AULINX_SOCKET", "")
    if not compositor_socket and xdg:
        compositor_socket = os.path.join(xdg, "aulinx", "semantic.sock")
    if compositor_socket and os.path.exists(compositor_socket):
        return "compositor"

    # Check for display server
    if os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY"):
        return "desktop"

    return "core"

console = Console()


def print_banner(mode: str = "desktop"):
    mode_label = {"core": "Core", "desktop": "Desktop", "compositor": "Compositor"}[mode]
    console.print(
        f"\n[bold gold1]  Au[/bold gold1][bold white]linx[/bold white]  "
        f"[dim]v{__version__} — AI-native Linux ({mode_label} mode)[/dim]\n"
    )
    console.print("[dim]  Type a command in natural language. Ctrl+C to exit.[/dim]")
    console.print("[dim]  /history — show past sessions  /audit — show recent tool calls[/dim]\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="aulinx",
        description="Aulinx — The AI-native Linux desktop",
    )
    parser.add_argument(
        "-c", "--command",
        help="Run a single command and exit (non-interactive)",
    )
    parser.add_argument(
        "-m", "--model",
        help="Override the LLM model (e.g., qwen2.5:7b, llama3.1:8b)",
    )
    parser.add_argument(
        "--base-url",
        help="Override the Ollama API URL",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume the last conversation session",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Start WebSocket server for the UI command palette (ws://localhost:8765)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="WebSocket server port (default: 8765)",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run as background daemon with global hotkey (Super+Space) and ambient context",
    )
    parser.add_argument(
        "--mcp",
        action="store_true",
        help="Run as MCP server (stdio transport) for Claude Desktop or other AI clients",
    )
    parser.add_argument(
        "--voice",
        action="store_true",
        help="Enable voice input (requires faster-whisper, sounddevice, numpy)",
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "core", "desktop", "compositor"],
        default="auto",
        help="Operating mode: core (headless), desktop (GUI), compositor (Aulinx WM). Default: auto-detect",
    )
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="List all available tools for the detected mode",
    )
    parser.add_argument(
        "--info",
        action="store_true",
        help="Show system capabilities and tool counts per mode",
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="Run diagnostic check on system dependencies",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"aulinx {__version__}",
    )
    return parser.parse_args()


def _build_agent(args: argparse.Namespace, mode: str = "desktop") -> Agent:
    config = load_config()
    return Agent(
        model=args.model or config.llm.model,
        base_url=args.base_url or config.llm.base_url,
        temperature=config.llm.temperature,
        max_history=config.context.max_history,
        mode=mode,
    )


async def run_interactive(agent: Agent, resume: bool = False, voice: bool = False, mode: str = "desktop"):
    """Run the interactive REPL."""
    print_banner(mode)
    await agent.initialize()

    # Initialize voice if requested
    voice_input = None
    if voice:
        from aulinx.voice import VoiceInput
        voice_input = VoiceInput()
        await voice_input.initialize()

    if resume:
        prev = agent.history_mgr.load_latest()
        if prev:
            agent.history = prev
            console.print(f"[dim]  Resumed session with {len(prev)} messages.[/dim]\n")

    completer = AulinxCompleter(list(agent.tools._tools.keys()))
    session = PromptSession(completer=completer)

    while True:
        try:
            user_input = await session.prompt_async(
                HTML("<gold>aulinx</gold><white> > </white>")
            )
            text = user_input.strip()
            if not text:
                continue

            # Built-in commands
            if text.startswith("/"):
                await _handle_slash_command(text, agent, voice_input)
                continue

            await agent.handle(text)
            print()

        except KeyboardInterrupt:
            console.print("\n[dim]Goodbye.[/dim]")
            break
        except EOFError:
            break


async def run_command(agent: Agent, command: str):
    """Run a single command and exit."""
    await agent.initialize()
    await agent.handle(command)
    print()


async def _handle_slash_command(text: str, agent: Agent, voice_input=None):
    """Handle built-in slash commands."""
    cmd = text.lower().split()[0]

    if cmd == "/history":
        sessions = agent.history_mgr.list_sessions()
        if not sessions:
            console.print("[dim]No past sessions.[/dim]")
            return
        console.print("\n[bold]Recent sessions:[/bold]")
        for s in sessions:
            console.print(
                f"  [dim]{s['session_id']}[/dim] — "
                f"{s['messages']} msgs — "
                f"[italic]{s['preview']}[/italic]"
            )
        console.print()

    elif cmd == "/audit":
        entries = agent.audit.recent(15)
        if not entries:
            console.print("[dim]No audit entries.[/dim]")
            return
        console.print("\n[bold]Recent tool calls:[/bold]")
        for e in entries:
            console.print(
                f"  [dim]{e['ts']}[/dim] "
                f"[yellow]{e['tool']}[/yellow] "
                f"[dim]({e['duration_ms']}ms)[/dim] "
                f"{e['result_preview'][:60]}"
            )
        console.print()

    elif cmd == "/clear":
        agent.history.clear()
        console.print("[dim]Conversation cleared.[/dim]\n")

    elif cmd == "/tools":
        mode_label = {"core": "Core", "desktop": "Desktop", "compositor": "Compositor"}.get(agent.mode, "?")
        console.print(f"\n[bold]{len(agent.tools)} tools available ({mode_label} mode):[/bold]\n")
        console.print(agent.tools.describe())
        console.print()

    elif cmd == "/context":
        ctx = await agent.context.snapshot()
        console.print(f"\n[bold]Desktop context:[/bold]\n{ctx}\n")

    elif cmd == "/doctor":
        from aulinx.doctor import run_doctor
        await run_doctor(agent.base_url)

    elif cmd == "/voice":
        if voice_input and voice_input.available:
            text = await voice_input.listen(duration=5.0)
            if text:
                await agent.handle(text)
                print()
        else:
            console.print("[yellow]Voice not available. Start with: aulinx --voice[/yellow]\n")
            console.print("[dim]Install: pip install faster-whisper sounddevice numpy[/dim]\n")

    elif cmd == "/info":
        _show_info()

    elif cmd == "/help":
        console.print("""
[bold]Commands:[/bold]
  /tools    — List all available tools
  /context  — Show current desktop context
  /info     — Show system capabilities and mode
  /history  — Show past conversation sessions
  /audit    — Show recent tool calls
  /doctor   — Check system dependencies
  /voice    — Speak a command (requires --voice flag)
  /clear    — Clear conversation history
  /help     — Show this help
""")
    else:
        console.print(f"[dim]Unknown command: {cmd}. Type /help for options.[/dim]\n")


def _show_info():
    """Show a beautiful summary of Aulinx capabilities."""
    from aulinx.tools.registry import ToolRegistry

    mode = detect_mode()
    mode_names = {"core": "Core (headless)", "desktop": "Desktop", "compositor": "Compositor"}

    console.print(f"\n[bold gold1]  Au[/bold gold1][bold white]linx[/bold white]  [dim]v{__version__}[/dim]\n")
    console.print("  [bold]AI-native Linux. Desktop to server.[/bold]")
    console.print("  Other AI agents look at your screen. Aulinx IS the screen.\n")

    # Mode detection
    colors = {"core": "cyan", "desktop": "green", "compositor": "gold1"}
    console.print(f"  [{colors[mode]}]Detected mode: {mode_names[mode]}[/{colors[mode]}]\n")

    # Tool counts per tier
    from rich.table import Table
    table = Table(show_header=True, header_style="bold", padding=(0, 2))
    table.add_column("Tier", width=15)
    table.add_column("Tools", width=8, justify="right")
    table.add_column("Native", width=8, justify="right")
    table.add_column("Capabilities", width=50)

    for m, desc in [
        ("core", "Files, git, process, network, docker, packages, services, system"),
        ("desktop", "+ AT-SPI GUI control, screenshots, audio, display, input sim"),
        ("compositor", "+ Wayland compositor IPC, input injection, scene graph, events"),
    ]:
        r = ToolRegistry(mode=m)
        native = len(r.to_ollama_tools(core_only=True))
        marker = " [bold]<-- you are here[/bold]" if m == mode else ""
        table.add_row(
            f"[{colors[m]}]{m.capitalize()}[/{colors[m]}]",
            str(len(r)),
            str(native),
            desc + marker,
        )

    console.print(table)

    # Compositor IPC
    console.print("\n  [bold]Compositor IPC:[/bold] 34 commands over Unix socket")
    console.print("  [bold]Keyboard shortcuts:[/bold] 12 (Super+Return/Esc/J/K/H/L/Q/Space/F/1-9)")
    console.print("  [bold]Wayland protocols:[/bold] 11")
    console.print("\n  [dim]Run 'aulinx --doctor' for detailed dependency check[/dim]")
    console.print("  [dim]Run 'aulinx --mode core' to force headless mode[/dim]\n")


def main():
    args = parse_args()

    if args.list_tools:
        mode = args.mode if args.mode != "auto" else detect_mode()
        from aulinx.tools.registry import ToolRegistry
        registry = ToolRegistry(mode=mode)
        mode_label = {"core": "Core", "desktop": "Desktop", "compositor": "Compositor"}[mode]
        console.print(f"\n[bold]{len(registry)} tools ({mode_label} mode):[/bold]\n")
        console.print(registry.describe())
        console.print()
        return

    if args.info:
        _show_info()
        return

    if args.doctor:
        from aulinx.doctor import run_doctor
        config = load_config()
        asyncio.run(run_doctor(args.base_url or config.llm.base_url))
        return

    if args.mcp:
        from aulinx.mcp_server import run_mcp_server
        asyncio.run(run_mcp_server())
        return

    if args.daemon:
        from aulinx.daemon import run_daemon
        asyncio.run(run_daemon(port=args.port))
        return

    if args.serve:
        from aulinx.server import run_server
        asyncio.run(run_server(
            port=args.port,
            model=args.model or "",
            base_url=args.base_url or "",
        ))
        return

    mode = args.mode if args.mode != "auto" else detect_mode()
    agent = _build_agent(args, mode=mode)

    if args.command:
        asyncio.run(run_command(agent, args.command))
    else:
        asyncio.run(run_interactive(agent, resume=args.resume, voice=args.voice, mode=mode))


if __name__ == "__main__":
    main()
