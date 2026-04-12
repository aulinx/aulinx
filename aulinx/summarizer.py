"""History summarization — compresses old conversation turns to save tokens.

After a configurable number of turns, earlier messages are compressed into
a concise summary. This keeps the conversation context manageable while
preserving key information the LLM needs.

Token savings: 384K → ~150K tokens/task on OSWorld benchmarks.
"""

from __future__ import annotations

# After this many tool exchanges, summarize earlier history
SUMMARIZE_AFTER_TURNS = 6

# Maximum length of a single tool result in the summarized history
MAX_RESULT_IN_SUMMARY = 150


def summarize_history(
    messages: list[dict],
    max_recent: int = 6,
) -> list[dict]:
    """Compress older messages while keeping recent ones intact.

    Strategy:
    - Keep the last `max_recent` messages exactly as-is (LLM needs recent context)
    - Compress older messages into a single summary message
    - Tool results are truncated to key info (success/error + first line)
    - Assistant reasoning is reduced to action taken

    Args:
        messages: Full message history (user/assistant/tool messages)
        max_recent: Number of recent messages to keep verbatim

    Returns:
        Compressed message list (summary + recent messages)
    """
    if len(messages) <= max_recent:
        return messages

    # Split into old (to summarize) and recent (to keep)
    old_messages = messages[:-max_recent]
    recent_messages = messages[-max_recent:]

    # Build summary of old messages
    summary_parts = []
    for msg in old_messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "user":
            summary_parts.append(f"User: {_truncate(content, 100)}")
        elif role == "assistant":
            # Extract just the action/tool call, not the full reasoning
            if msg.get("tool_calls"):
                calls = msg["tool_calls"]
                call_names = [tc.get("function", {}).get("name", "?") for tc in calls]
                summary_parts.append(f"Agent called: {', '.join(call_names)}")
            elif content:
                summary_parts.append(f"Agent: {_truncate(content, 80)}")
        elif role == "tool":
            # Compress tool results to success/error + key data
            summary_parts.append(f"Result: {_summarize_tool_result(content)}")

    if not summary_parts:
        return messages

    summary_text = (
        "[Earlier conversation summary]\n"
        + "\n".join(summary_parts)
        + "\n[End summary — recent messages follow]"
    )

    return [
        {"role": "user", "content": summary_text},
        *recent_messages,
    ]


def should_summarize(messages: list[dict]) -> bool:
    """Check if the message history is long enough to benefit from summarization."""
    # Count tool exchanges (user → assistant → tool cycles)
    tool_count = sum(1 for m in messages if m.get("role") == "tool")
    return tool_count >= SUMMARIZE_AFTER_TURNS


def _summarize_tool_result(content: str) -> str:
    """Compress a tool result to its essential information."""
    if not content:
        return "(empty)"

    # Try to parse as JSON
    try:
        import json
        data = json.loads(content)
        if isinstance(data, dict):
            if "error" in data:
                return f"ERROR: {_truncate(str(data['error']), MAX_RESULT_IN_SUMMARY)}"
            if "recovery_hint" in data:
                return f"ERROR: {_truncate(str(data.get('error', '')), 80)} (hint: try alternative)"
            # Success — extract key fields
            keys = list(data.keys())[:3]
            preview = ", ".join(f"{k}={_truncate(str(data[k]), 40)}" for k in keys)
            return f"OK: {preview}"
        elif isinstance(data, list):
            return f"OK: list of {len(data)} items"
        else:
            return f"OK: {_truncate(str(data), MAX_RESULT_IN_SUMMARY)}"
    except (json.JSONDecodeError, ValueError):
        pass

    # Plain text result
    first_line = content.split("\n")[0]
    return _truncate(first_line, MAX_RESULT_IN_SUMMARY)


def _truncate(text: str, max_len: int) -> str:
    """Truncate text to max_len characters."""
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."
