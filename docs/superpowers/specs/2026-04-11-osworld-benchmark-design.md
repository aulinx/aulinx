# OSWorld Benchmark Integration — Design Spec

## Context

Aulinx claims semantic desktop understanding beats screenshot-based agents. OSWorld (NeurIPS 2024) is the standard benchmark for desktop AI agents — 369 tasks across Ubuntu apps (LibreOffice, Chrome, VS Code, GIMP, etc.). Agent S3 holds 62.6% (69.9% with best-of-N). We need quantified proof that Aulinx's a11y-first approach is more accurate AND more token-efficient.

## Approach

Write a thin adapter (`AulinxAgent`) that implements OSWorld's `predict(instruction, obs)` interface. Aulinx runs inside OSWorld's VM, reads the a11y tree semantically, and outputs `computer_13` structured actions. No modifications to OSWorld itself.

## Architecture

```
OSWorld Harness
  ├── env.reset(task)                → VM setup, first observation
  ├── AulinxAgent.predict(instr, obs) → (response, actions)
  ├── env.step(action)               → execute, new observation
  └── env.evaluate()                 → score 0.0-1.0
```

## Files

All under `benchmark/`:

| File | Purpose |
|------|---------|
| `osworld_adapter.py` | `AulinxAgent` class — implements `predict()` |
| `action_mapper.py` | LLM response → computer_13 action dicts |
| `prompt_builder.py` | a11y tree + instruction → LLM prompt |
| `run_benchmark.py` | CLI wrapper to run OSWorld with our agent |
| `analyze_results.py` | Parse results, compute metrics, generate report |

## Key Decisions

- **Observation**: `a11y_tree` primary (Aulinx's strength), screenshot as optional fallback
- **Action space**: `computer_13` (structured JSON — CLICK, TYPING, PRESS, HOTKEY, SCROLL, DRAG_TO)
- **LLM**: Ollama (qwen2.5:14b) default, Claude/OpenAI optional via `--model`/`--base-url`
- **No OSWorld modifications**: pure adapter, symlinked into `mm_agents/`

## Action Mapping

| LLM output | computer_13 |
|---|---|
| click(x, y) | `{action_type: CLICK, coordinate: [x,y]}` |
| type(text) | `{action_type: TYPING, text: "..."}` |
| press(key) | `{action_type: PRESS, key: "..."}` |
| hotkey(keys) | `{action_type: HOTKEY, key: [...]}` |
| scroll(x, y, dir) | `{action_type: SCROLL, coordinate: [x,y], direction: "..."}` |
| drag(x1,y1,x2,y2) | `{action_type: DRAG_TO, startCoordinate: [...], endCoordinate: [...]}` |
| wait | `WAIT` |
| done | `DONE` |
| fail | `FAIL` |

## Metrics

- Success rate (% tasks passed)
- Tokens per task (input + output)
- LLM calls per task
- Latency per task
- Cost estimate per task

## Verification

1. `python run_benchmark.py --dry-run` parses 5 sample tasks without VM
2. Single task end-to-end in VMware: `python run.py --agent aulinx --examples 1`
3. Full suite: all 369 tasks, results in `docs/benchmark.md`
4. Comparison table vs Agent S3 / Claude Computer Use baselines
