"""Aulinx CLI — interactive AI desktop agent."""

import asyncio
from rich.console import Console
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML

from aulinx.agent import Agent
from aulinx.config import load_config

console = Console()


def print_banner():
    console.print(
        "\n[bold gold1]  Au[/bold gold1][bold white]linx[/bold white]  "
        "[dim]v0.1.0 — The AI-native Linux desktop[/dim]\n"
    )
    console.print("[dim]  Type a command in natural language. Ctrl+C to exit.[/dim]\n")


async def run():
    print_banner()
    config = load_config()
    agent = Agent(
        model=config.llm.model,
        base_url=config.llm.base_url,
        temperature=config.llm.temperature,
        max_history=config.context.max_history,
    )
    await agent.initialize()

    session = PromptSession()

    while True:
        try:
            user_input = await session.prompt_async(
                HTML("<gold>aulinx</gold><white> > </white>")
            )
            if not user_input.strip():
                continue

            await agent.handle(user_input.strip())
            print()

        except KeyboardInterrupt:
            console.print("\n[dim]Goodbye.[/dim]")
            break
        except EOFError:
            break


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
