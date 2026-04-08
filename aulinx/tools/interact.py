"""User interaction tools — ask questions, show messages, confirm actions."""

from aulinx.tools.base import Tier, Tool


async def user_ask(question: str, options: str = "") -> dict:
    """Ask the user a question and wait for their response.

    Use for multi-step workflows that need user input.
    If options are provided, they are shown as choices.
    """
    try:
        if options:
            print(f"\n  [Aulinx asks] {question}")
            print(f"  Options: {options}")
            response = input("  Your answer: ").strip()
        else:
            print(f"\n  [Aulinx asks] {question}")
            response = input("  Your answer: ").strip()

        return {"question": question, "answer": response}
    except (EOFError, KeyboardInterrupt):
        return {"question": question, "answer": "", "cancelled": True}


async def user_confirm(message: str) -> dict:
    """Ask the user for yes/no confirmation."""
    try:
        print(f"\n  [Aulinx] {message}")
        response = input("  Confirm? [y/N] ").strip().lower()
        confirmed = response in ("y", "yes")
        return {"message": message, "confirmed": confirmed}
    except (EOFError, KeyboardInterrupt):
        return {"message": message, "confirmed": False, "cancelled": True}


async def user_notify(title: str, message: str) -> dict:
    """Show an informational message to the user (not a desktop notification — inline in chat)."""
    print(f"\n  [{title}] {message}")
    return {"shown": True, "title": title}


TOOLS = [
    Tool(
        name="user_ask",
        description="Ask the user a question and wait for their response. Use for multi-step tasks needing input.",
        fn=user_ask,
        parameters={
            "question": "string (the question to ask)",
            "options": "string (optional: comma-separated choices, e.g. 'yes,no,skip')",
        },
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="user_confirm",
        description="Ask the user for yes/no confirmation before proceeding.",
        fn=user_confirm,
        parameters={"message": "string (what to confirm)"},
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="user_notify",
        description="Show an inline message to the user (not a desktop notification).",
        fn=user_notify,
        parameters={"title": "string", "message": "string"},
        tier=Tier.OBSERVE,
    ),
]
