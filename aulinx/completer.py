"""Tab completion for the Aulinx REPL."""

from prompt_toolkit.completion import Completer, Completion

SLASH_COMMANDS = {
    "/tools": "List all available tools",
    "/context": "Show current desktop context",
    "/history": "Browse past conversation sessions",
    "/audit": "Show recent tool calls",
    "/doctor": "Check system dependencies",
    "/clear": "Clear conversation history",
    "/help": "Show help",
}


class AulinxCompleter(Completer):
    """Completes slash commands and @tool references."""

    def __init__(self, tool_names: list[str]):
        self._tool_names = sorted(tool_names)

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor

        # Slash commands
        if text.startswith("/"):
            prefix = text.lower()
            for cmd, desc in SLASH_COMMANDS.items():
                if cmd.startswith(prefix):
                    yield Completion(
                        cmd,
                        start_position=-len(text),
                        display_meta=desc,
                    )
            return

        # @tool references anywhere in text
        # Find the last @ in the text
        at_pos = text.rfind("@")
        if at_pos >= 0:
            prefix = text[at_pos + 1:].lower()
            for name in self._tool_names:
                if name.startswith(prefix):
                    yield Completion(
                        name,
                        start_position=-len(prefix),
                        display_meta="tool",
                    )
