# Adding New Tools

This guide shows how to create a new tool module for Aulinx.

## Step 1: Create the Tool File

Create `aulinx/tools/my_feature.py`:

```python
"""My feature tools — description of what this module does."""

from aulinx.tools.base import Tier, Tool


async def my_read_tool(path: str = "") -> dict:
    """A read-only tool that returns information."""
    return {"data": "some value", "path": path}


async def my_write_tool(name: str, value: str) -> dict:
    """A tool that modifies something."""
    # Do the mutation
    return {"success": True, "name": name}


TOOLS = [
    Tool(
        name="my_read_tool",
        description="Short description for the LLM (max ~60 chars in compact mode)",
        fn=my_read_tool,
        parameters={"path": "string (optional)"},
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="my_write_tool",
        description="Short description of what this changes",
        fn=my_write_tool,
        parameters={"name": "string", "value": "string"},
        tier=Tier.MUTATE,
    ),
]
```

## Step 2: Register the Module

In `aulinx/tools/registry.py`, add your module to both the import and the loop:

```python
from aulinx.tools import (
    ...
    my_feature,  # add here
)

for module in [
    ...
    my_feature,  # and here
]:
```

## Step 3: Choose the Right Tier

| Tier | Use when |
|------|----------|
| `Tier.OBSERVE` | Read-only, no side effects (listing, reading, searching) |
| `Tier.LOW_RISK` | Minor side effects (set clipboard, adjust volume, send notification) |
| `Tier.MUTATE` | Creates or modifies data (write files, launch apps). Confirms first time per session. |
| `Tier.DESTRUCTIVE` | Hard to reverse (kill process, trash files, disconnect wifi). Always confirms. |
| `Tier.IRREVERSIBLE` | Cannot be undone (permanent delete, shutdown). Always confirms with extra warning. |

## Step 4: Write Tests

Create `tests/test_my_feature.py`:

```python
import pytest
from aulinx.tools.my_feature import my_read_tool, my_write_tool


class TestMyFeature:
    @pytest.mark.asyncio
    async def test_read_tool(self):
        result = await my_read_tool("/tmp")
        assert "data" in result

    @pytest.mark.asyncio
    async def test_write_tool(self):
        result = await my_write_tool("test", "value")
        assert result["success"] is True
```

## Step 5: Verify

```bash
make test   # all tests pass
make lint   # no lint errors
```

## Guidelines

- All tool functions must be `async`
- Return dicts or lists (JSON-serializable)
- Return `{"error": "message"}` on failure — don't raise exceptions
- Handle `FileNotFoundError`, `PermissionError`, `subprocess.TimeoutExpired` gracefully
- Keep descriptions under 60 characters (they're shown to the LLM in compact mode)
- Parameters dict values are type hints for the LLM, not enforced
