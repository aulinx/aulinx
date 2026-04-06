"""Aulinx CLI — interactive AI desktop agent."""

import argparse
import asyncio

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from rich.console import Console

from aulinx import __version__
from aulinx.agent import Agent
from aulinx.completer import AulinxCompleter
from aulinx.config import load_config

console = Console()


def print_banner():
    console.print(
        f"\n[bold gold1]  Au[/bold gold1][bold white]linx[/bold white]  "
        f"[dim]v{__version__} — The AI-native Linux desktop[/dim]\n"
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


def _build_agent(args: argparse.Namespace) -> Agent:
    config = load_config()
    return Agent(
        model=args.model or config.llm.model,
        base_url=args.base_url or config.llm.base_url,
        temperature=config.llm.temperature,
        max_history=config.context.max_history,
    )


async def run_interactive(agent: Agent, resume: bool = False):
    """Run the interactive REPL."""
    print_banner()
    await agent.initialize()

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
                await _handle_slash_command(text, agent)
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


async def _handle_slash_command(text: str, agent: Agent):
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
        console.print(f"\n[bold]{len(agent.tools)} tools available:[/bold]\n")
        console.print(agent.tools.describe())
        console.print()

    elif cmd == "/context":
        ctx = await agent.context.snapshot()
        console.print(f"\n[bold]Desktop context:[/bold]\n{ctx}\n")

    elif cmd == "/doctor":
        from aulinx.doctor import run_doctor
        await run_doctor(agent.base_url)

    elif cmd == "/help":
        console.print("""
[bold]Commands:[/bold]
  /tools    — List all available tools
  /context  — Show current desktop context
  /history  — Show past conversation sessions
  /audit    — Show recent tool calls
  /doctor   — Check system dependencies
  /clear    — Clear conversation history
  /help     — Show this help
""")
    else:
        console.print(f"[dim]Unknown command: {cmd}. Type /help for options.[/dim]\n")


def main():
    args = parse_args()

    if args.doctor:
        from aulinx.doctor import run_doctor
        config = load_config()
        asyncio.run(run_doctor(args.base_url or config.llm.base_url))
        return

    if args.serve:
        from aulinx.server import run_server
        asyncio.run(run_server(
            port=args.port,
            model=args.model or "",
            base_url=args.base_url or "",
        ))
        return

    agent = _build_agent(args)

    if args.command:
        asyncio.run(run_command(agent, args.command))
    else:
        asyncio.run(run_interactive(agent, resume=args.resume))


if __name__ == "__main__":
    main()
