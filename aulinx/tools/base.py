"""Base types for tools — Tool and Tier. Separate module to avoid circular imports."""

from __future__ import annotations

from enum import IntEnum
from typing import Any, Awaitable, Callable


class Tier(IntEnum):
    """Permission tiers for tool actions."""
    OBSERVE = 0      # Never confirm (read-only)
    LOW_RISK = 1     # Auto-allow with audit log
    MUTATE = 2       # Confirm first time per session
    DESTRUCTIVE = 3  # Always confirm
    IRREVERSIBLE = 4 # Always confirm + extra warning


# Map our simple param type strings to JSON Schema types
_TYPE_MAP = {
    "string": "string",
    "str": "string",
    "int": "integer",
    "float": "number",
    "bool": "boolean",
    "boolean": "boolean",
}


def _parse_param_type(desc: str) -> str:
    """Extract JSON Schema type from our parameter description string."""
    lower = desc.lower().strip()
    for key, val in _TYPE_MAP.items():
        if lower.startswith(key):
            return val
    return "string"


class Tool:
    """A single tool the agent can call."""

    def __init__(
        self,
        name: str,
        description: str,
        fn: Callable[..., Awaitable[Any]],
        parameters: dict | None = None,
        tier: Tier = Tier.OBSERVE,
    ):
        self.name = name
        self.description = description
        self.fn = fn
        self.parameters = parameters or {}
        self.tier = tier

    def to_ollama_schema(self) -> dict:
        """Convert to Ollama/OpenAI function calling schema."""
        properties = {}
        required = []

        for param_name, param_desc in self.parameters.items():
            desc = str(param_desc)
            param_type = _parse_param_type(desc)

            prop: dict[str, Any] = {
                "type": param_type,
                "description": desc,
            }

            # Parse enum values from descriptions like "cpu|memory|pid"
            if "|" in desc:
                parts = desc.split("(")[0].strip() if "(" in desc else desc
                enum_vals = [v.strip() for v in parts.split("|") if v.strip() and " " not in v.strip()]
                if enum_vals and all(len(v) < 30 for v in enum_vals):
                    prop["enum"] = enum_vals

            properties[param_name] = prop

            # If "optional" or "default" is in the description, it's not required
            lower = desc.lower()
            if "optional" not in lower and "default" not in lower:
                required.append(param_name)

        schema = {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                },
            },
        }

        if required:
            schema["function"]["parameters"]["required"] = required

        return schema
