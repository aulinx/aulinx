# Configuration

Aulinx uses a TOML config file at `~/.config/aulinx/config.toml`. It's auto-created on first run.

## Default Config

```toml
[llm]
model = "qwen2.5:14b"
base_url = "http://localhost:11434"
temperature = 0.3

[permissions]
# Override permission tiers for specific tools
# shell_exec = "mutate"

[context]
max_history = 20
include_clipboard = true
include_running_apps = true
```

## LLM Settings

| Key | Default | Description |
|-----|---------|-------------|
| `model` | `qwen2.5:14b` | Ollama model name |
| `base_url` | `http://localhost:11434` | Ollama API URL |
| `temperature` | `0.3` | Lower = more deterministic tool calls |

## Permission Overrides

Override the default tier for any tool:

```toml
[permissions]
shell_exec = "mutate"        # normally "destructive" — downgrade to confirm-once
app_launch = "observe"        # normally "mutate" — make it auto-allow
file_trash = "irreversible"   # normally "destructive" — upgrade to extra warning
```

Valid tiers: `observe`, `low_risk`, `mutate`, `destructive`, `irreversible`

## Context Settings

| Key | Default | Description |
|-----|---------|-------------|
| `max_history` | `20` | Max messages kept in LLM context |
| `include_clipboard` | `true` | Include clipboard preview in context |
| `include_running_apps` | `true` | List running GUI apps in context |

## CLI Overrides

CLI flags override the config file:

```bash
aulinx -m gemma3:12b                    # override model
aulinx --base-url http://192.168.1.5:11434  # override Ollama URL
```

## Data Directories

| Path | Purpose |
|------|---------|
| `~/.config/aulinx/config.toml` | Configuration |
| `~/.local/share/aulinx/audit.jsonl` | Tool call audit log |
| `~/.local/share/aulinx/history/` | Conversation sessions |
| `~/.local/share/aulinx/memory.json` | Persistent workflow memory |
