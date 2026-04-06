# Contributing to Aulinx

Thank you for your interest in contributing to Aulinx! This guide will help you get started.

## Development Setup

```bash
git clone https://github.com/aulinx/aulinx.git
cd aulinx
pip install -e ".[dev]"
```

For the UI:
```bash
cd ui
npm install
npm run dev
```

## Running Tests

```bash
make test     # run all tests
make lint     # check code style
```

## Code Style

- **Python**: We use [ruff](https://docs.astral.sh/ruff/) for linting and formatting. Line length: 100 chars.
- **TypeScript**: ESLint is configured in `ui/`.
- All tool functions must be `async` and return JSON-serializable data.
- Use type hints for all function signatures.

## Adding a New Tool

1. Create a new file in `aulinx/tools/` (e.g., `aulinx/tools/my_tool.py`)
2. Import the base types:
   ```python
   from aulinx.tools.base import Tier, Tool
   ```
3. Write your async tool functions
4. Define a `TOOLS` list at the bottom of the file:
   ```python
   TOOLS = [
       Tool(
           name="my_tool_name",
           description="What the tool does (shown to the LLM)",
           fn=my_tool_function,
           parameters={"param1": "string", "param2": "int (default 10)"},
           tier=Tier.OBSERVE,  # or LOW_RISK, MUTATE, DESTRUCTIVE, IRREVERSIBLE
       ),
   ]
   ```
5. Register the module in `aulinx/tools/registry.py` — add it to the import list and the `for module in [...]` loop
6. Add tests in `tests/`

See `docs/adding-tools.md` for a complete guide.

## Permission Tiers

| Tier | When to use |
|------|-------------|
| `OBSERVE` | Read-only, no side effects |
| `LOW_RISK` | Minor mutations (set clipboard, adjust volume) |
| `MUTATE` | Creates/modifies data (write files, launch apps) |
| `DESTRUCTIVE` | Hard to reverse (kill process, trash files) |
| `IRREVERSIBLE` | Cannot be undone (permanent delete, shutdown) |

## Pull Request Process

1. Fork the repo and create a branch from `main`
2. Make your changes
3. Run `make test` and `make lint` — both must pass
4. Write a clear commit message describing what and why
5. Open a PR with a description of your changes

## Reporting Bugs

Use the [bug report template](https://github.com/aulinx/aulinx/issues/new?template=bug_report.md) on GitHub Issues.

## Feature Requests

Use the [feature request template](https://github.com/aulinx/aulinx/issues/new?template=feature_request.md) on GitHub Issues.
