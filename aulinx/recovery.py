"""Error recovery module — replaces simple anti-loop detection with strategy-based fallback.

When a tool call fails or repeats, this module suggests alternative approaches
rather than just stopping. It tracks failure patterns and switches strategies
after consecutive failures.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Tool equivalence groups — if one fails, try another from the same group
TOOL_ALTERNATIVES: dict[str, list[str]] = {
    # GUI interaction alternatives
    "atspi_do_action": ["input_key_combo", "compositor_click"],
    "atspi_set_text": ["input_type_text", "compositor_type"],
    "atspi_find_elements": ["atspi_get_tree", "compositor_find_window"],
    "input_type_text": ["atspi_set_text", "compositor_type"],
    "input_key_combo": ["atspi_do_action", "compositor_key"],
    # Screenshot alternatives
    "screenshot": ["window_screenshot", "compositor_screenshot", "screenshot_ocr"],
    "window_screenshot": ["screenshot", "compositor_screenshot"],
    "compositor_screenshot": ["screenshot", "window_screenshot"],
    # Window management alternatives
    "window_focus": ["compositor_focus", "app_launch"],
    "window_close": ["compositor_close", "input_key_combo"],
    "compositor_focus": ["window_focus"],
    "compositor_close": ["window_close"],
    # File alternatives
    "file_read": ["shell_exec"],
    "file_write": ["shell_exec"],
    # Compositor vs AT-SPI
    "compositor_click": ["atspi_do_action", "input_key_combo"],
    "compositor_type": ["input_type_text", "atspi_set_text"],
    "compositor_key": ["input_key_combo"],
}

MAX_CONSECUTIVE_FAILURES = 3


@dataclass
class FailureRecord:
    """Tracks a single tool failure."""
    tool_name: str
    args_signature: str
    error: str


@dataclass
class RecoveryState:
    """Tracks failure history and provides recovery strategies."""
    failures: list[FailureRecord] = field(default_factory=list)
    _call_history: list[str] = field(default_factory=list)  # call signatures
    _consecutive_failures: int = 0

    def record_call(self, tool_name: str, args_signature: str):
        """Record a tool call (before execution)."""
        self._call_history.append(f"{tool_name}:{args_signature}")

    def record_success(self):
        """Record a successful tool execution."""
        self._consecutive_failures = 0

    def record_failure(self, tool_name: str, args_signature: str, error: str):
        """Record a failed tool execution."""
        self.failures.append(FailureRecord(tool_name, args_signature, error))
        self._consecutive_failures += 1

    def is_repeated_call(self, tool_name: str, args_signature: str) -> bool:
        """Check if this exact call was already made."""
        sig = f"{tool_name}:{args_signature}"
        return sig in self._call_history[-3:]  # check last 3 calls

    def should_switch_strategy(self) -> bool:
        """Check if we've hit too many consecutive failures."""
        return self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES

    def get_alternatives(self, tool_name: str) -> list[str]:
        """Get alternative tools for a failed tool."""
        return TOOL_ALTERNATIVES.get(tool_name, [])

    def build_recovery_hint(self, tool_name: str, error: str) -> str:
        """Build a recovery hint to inject into the LLM prompt."""
        alternatives = self.get_alternatives(tool_name)
        failed_tools = {f.tool_name for f in self.failures[-5:]}

        # Filter out alternatives that also failed recently
        viable = [t for t in alternatives if t not in failed_tools]

        parts = [f"The tool '{tool_name}' failed: {error[:200]}"]

        if viable:
            parts.append(f"Try one of these alternatives instead: {', '.join(viable)}")
        elif self.should_switch_strategy():
            parts.append(
                "Multiple tools have failed consecutively. Consider a different approach entirely: "
                "use shell_exec for direct command-line operations, or break the task into simpler sub-steps."
            )
        else:
            parts.append("Try a different approach or different arguments.")

        return " ".join(parts)

    def reset(self):
        """Reset state for a new task."""
        self.failures.clear()
        self._call_history.clear()
        self._consecutive_failures = 0
