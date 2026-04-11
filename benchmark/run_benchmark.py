#!/usr/bin/env python3
"""Run OSWorld benchmark with the Aulinx agent.

This script wraps OSWorld's evaluation harness, injecting the Aulinx
agent adapter. It handles setup, execution, and result collection.

Usage:
    # Run full benchmark (requires OSWorld + VM)
    python -m benchmark.run_benchmark --osworld-path ../OSWorld

    # Run specific domain
    python -m benchmark.run_benchmark --osworld-path ../OSWorld --domain libreoffice_calc

    # Run with Claude instead of Ollama
    python -m benchmark.run_benchmark --osworld-path ../OSWorld \
        --api-type anthropic --model claude-sonnet-4-20250514

    # Dry run — test adapter without VM
    python -m benchmark.run_benchmark --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("aulinx.benchmark")


def parse_args():
    p = argparse.ArgumentParser(description="Run OSWorld benchmark with Aulinx agent")

    # OSWorld config
    p.add_argument("--osworld-path", type=str, default="../OSWorld",
                   help="Path to cloned OSWorld repository")
    p.add_argument("--provider", type=str, default="vmware",
                   choices=["vmware", "virtualbox", "docker", "aws"],
                   help="VM provider for OSWorld")
    p.add_argument("--domain", type=str, default=None,
                   help="Specific domain to test (e.g. libreoffice_calc)")

    # Agent config
    p.add_argument("--model", type=str, default="qwen2.5:14b",
                   help="LLM model name")
    p.add_argument("--base-url", type=str, default="http://localhost:11434",
                   help="LLM API base URL")
    p.add_argument("--api-type", type=str, default="ollama",
                   choices=["ollama", "openai", "anthropic"],
                   help="LLM API type")
    p.add_argument("--temperature", type=float, default=0.3)
    p.add_argument("--max-tokens", type=int, default=1024)

    # Execution config
    p.add_argument("--max-steps", type=int, default=20,
                   help="Maximum steps per task")
    p.add_argument("--sleep-after-execution", type=float, default=2.0,
                   help="Seconds to wait after each action")
    p.add_argument("--result-dir", type=str, default="benchmark/results",
                   help="Directory to store results")

    # Modes
    p.add_argument("--dry-run", action="store_true",
                   help="Test adapter without VM — parse sample tasks only")
    p.add_argument("--resume", action="store_true",
                   help="Resume from previous run (skip completed tasks)")

    return p.parse_args()


def dry_run():
    """Test the adapter without a VM — verify prompt building and action parsing."""
    from .action_mapper import parse_response
    from .osworld_adapter import AulinxAgent
    from .prompt_builder import build_prompt, parse_a11y_tree

    logger.info("=== Dry Run: Testing Aulinx OSWorld Adapter ===\n")

    # Test 1: a11y tree parsing
    sample_tree = """<?xml version="1.0"?>
<desktop>
  <application name="Files" description="File manager">
    <frame name="Home" showing="true" visible="true"
           screencoord="(0, 0)" size="(1920, 1080)">
      <button name="New Folder" showing="true" visible="true"
              screencoord="(100, 50)" size="(120, 30)" enabled="true"/>
      <textbox name="Location" showing="true" visible="true"
               screencoord="(300, 50)" size="(400, 30)" value="/home/user"
               enabled="true" focused="true"/>
      <list name="File List" showing="true" visible="true"
            screencoord="(0, 100)" size="(1920, 980)">
        <list_item name="Documents" showing="true" visible="true"
                   screencoord="(20, 120)" size="(200, 30)"/>
        <list_item name="Downloads" showing="true" visible="true"
                   screencoord="(20, 160)" size="(200, 30)"/>
        <list_item name="Pictures" showing="true" visible="true"
                   screencoord="(20, 200)" size="(200, 30)"/>
      </list>
    </frame>
  </application>
</desktop>"""

    parsed = parse_a11y_tree(sample_tree)
    logger.info("Test 1 — A11y tree parsing:")
    for line in parsed.split("\n"):
        logger.info("  %s", line)
    logger.info("")

    # Test 2: prompt building
    messages = build_prompt("Open the Documents folder", sample_tree)
    logger.info("Test 2 — Prompt building:")
    logger.info("  System prompt: %d chars", len(messages[0]["content"]))
    logger.info("  User prompt: %d chars", len(messages[1]["content"]))
    total_tokens_est = sum(len(m["content"]) // 4 for m in messages)
    logger.info("  Estimated tokens: ~%d", total_tokens_est)
    logger.info("")

    # Test 3: action parsing
    test_responses = [
        "thought: I need to click on Documents\naction: click(x=120, y=135)",
        "thought: typing the path\naction: type(text=\"/home/user/Documents\")",
        "thought: pressing enter to confirm\naction: press(key=\"enter\")",
        "thought: using keyboard shortcut\naction: hotkey(keys=[\"ctrl\", \"l\"])",
        "thought: scrolling down to find file\naction: scroll(x=960, y=540, direction=\"down\", amount=3)",
        "thought: task is done\naction: done()",
    ]

    logger.info("Test 3 — Action parsing:")
    for resp in test_responses:
        thought, action = parse_response(resp)
        logger.info("  Input:  %s", resp.split("\n")[-1])
        logger.info("  Output: %s", action)
        logger.info("")

    # Test 4: agent instantiation
    agent = AulinxAgent(model="test", api_type="ollama")
    agent.reset()
    logger.info("Test 4 — Agent instantiation: OK")
    logger.info("  Model: %s", agent.model)
    logger.info("  API: %s", agent.api_type)
    logger.info("  Action space: %s", agent.action_space)
    logger.info("")

    logger.info("=== All dry-run tests passed ===")


def run_benchmark(args):
    """Run the full OSWorld benchmark."""
    osworld_path = Path(args.osworld_path).resolve()

    if not osworld_path.exists():
        logger.error("OSWorld not found at %s", osworld_path)
        logger.error("Clone it: git clone https://github.com/xlang-ai/OSWorld.git %s", osworld_path)
        sys.exit(1)

    # Add OSWorld to path
    sys.path.insert(0, str(osworld_path))

    # Import OSWorld components
    try:
        from desktop_env.desktop_env import DesktopEnv
    except ImportError:
        logger.error("Cannot import OSWorld. Install it: cd %s && pip install -e .", osworld_path)
        sys.exit(1)

    from .osworld_adapter import AulinxAgent

    # Initialize agent
    agent = AulinxAgent(
        model=args.model,
        base_url=args.base_url,
        api_type=args.api_type,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
    )

    # Load task examples
    examples_dir = osworld_path / "evaluation_examples"
    if not examples_dir.exists():
        logger.error("evaluation_examples not found in %s", osworld_path)
        sys.exit(1)

    # Collect tasks
    tasks = _load_tasks(examples_dir, args.domain)
    logger.info("Loaded %d tasks", len(tasks))

    # Setup result directory
    result_dir = Path(args.result_dir)
    result_dir.mkdir(parents=True, exist_ok=True)

    # Track results
    results = []
    start_time = time.time()

    # Initialize environment
    env = DesktopEnv(
        provider_name=args.provider,
        action_space=agent.action_space,
        require_a11y_tree=True,
        require_terminal=False,
    )

    for i, (task_id, task) in enumerate(tasks.items()):
        task_result_dir = result_dir / task.get("domain", "unknown") / task_id
        task_result_dir.mkdir(parents=True, exist_ok=True)

        # Skip if already completed (resume mode)
        if args.resume and (task_result_dir / "result.txt").exists():
            logger.info("[%d/%d] Skipping %s (already completed)", i + 1, len(tasks), task_id)
            continue

        logger.info("[%d/%d] Running task: %s", i + 1, len(tasks), task_id)
        instruction = task.get("instruction", "")

        try:
            # Reset environment and agent
            env.reset(task_config=task)
            agent.reset()
            time.sleep(5)

            obs = env._get_obs()
            done = False
            step_idx = 0
            task_start = time.time()

            while not done and step_idx < args.max_steps:
                response, actions = agent.predict(instruction, obs)

                for action in actions:
                    logger.info("  Step %d: %s", step_idx + 1, action)
                    obs, reward, done, info = env.step(action, args.sleep_after_execution)

                    # Save trajectory
                    with open(task_result_dir / "traj.jsonl", "a") as f:
                        f.write(json.dumps({
                            "step": step_idx + 1,
                            "action": action if isinstance(action, str) else action,
                            "response": response,
                            "reward": reward,
                            "done": done,
                        }, default=str) + "\n")

                    if done:
                        break
                step_idx += 1

            # Evaluate
            time.sleep(5)
            score = env.evaluate()
            task_time = time.time() - task_start
            token_stats = agent.get_token_stats()

            result = {
                "task_id": task_id,
                "domain": task.get("domain", "unknown"),
                "score": score,
                "steps": step_idx,
                "time_s": round(task_time, 1),
                "tokens_in": token_stats["total_input_tokens"],
                "tokens_out": token_stats["total_output_tokens"],
                "llm_calls": token_stats["total_calls"],
            }
            results.append(result)

            with open(task_result_dir / "result.txt", "w") as f:
                f.write(f"{score}\n")

            logger.info("  Score: %.2f | Steps: %d | Time: %.1fs | Tokens: %d in + %d out",
                        score, step_idx, task_time,
                        token_stats["total_input_tokens"],
                        token_stats["total_output_tokens"])

        except Exception as e:
            logger.error("  Task %s failed: %s", task_id, e)
            results.append({"task_id": task_id, "score": 0.0, "error": str(e)})

    # Save aggregate results
    total_time = time.time() - start_time
    summary = _compute_summary(results, total_time)

    with open(result_dir / "results.json", "w") as f:
        json.dump({"summary": summary, "tasks": results}, f, indent=2)

    _print_summary(summary)


def _load_tasks(examples_dir: Path, domain: str | None) -> dict:
    """Load task examples from OSWorld's evaluation_examples directory."""
    tasks = {}
    for domain_dir in sorted(examples_dir.iterdir()):
        if not domain_dir.is_dir():
            continue
        if domain and domain_dir.name != domain:
            continue
        for task_file in sorted(domain_dir.glob("*.json")):
            with open(task_file) as f:
                task = json.load(f)
            task["domain"] = domain_dir.name
            tasks[task_file.stem] = task
    return tasks


def _compute_summary(results: list[dict], total_time: float) -> dict:
    """Compute aggregate metrics from task results."""
    scored = [r for r in results if "error" not in r]
    passed = [r for r in scored if r["score"] > 0]

    total_tokens = sum(r.get("tokens_in", 0) + r.get("tokens_out", 0) for r in scored)
    total_calls = sum(r.get("llm_calls", 0) for r in scored)

    return {
        "total_tasks": len(results),
        "completed": len(scored),
        "passed": len(passed),
        "failed": len(scored) - len(passed),
        "errors": len(results) - len(scored),
        "success_rate": round(len(passed) / max(1, len(scored)) * 100, 1),
        "total_tokens": total_tokens,
        "avg_tokens_per_task": round(total_tokens / max(1, len(scored))),
        "total_llm_calls": total_calls,
        "avg_calls_per_task": round(total_calls / max(1, len(scored)), 1),
        "total_time_s": round(total_time, 1),
        "avg_time_per_task_s": round(total_time / max(1, len(scored)), 1),
    }


def _print_summary(summary: dict):
    """Print a formatted results summary."""
    print("\n" + "=" * 60)
    print("  AULINX OSWORLD BENCHMARK RESULTS")
    print("=" * 60)
    print(f"  Tasks:        {summary['completed']} completed, {summary['errors']} errors")
    print(f"  Success rate: {summary['success_rate']}% ({summary['passed']}/{summary['completed']})")
    print(f"  Avg tokens:   {summary['avg_tokens_per_task']} per task")
    print(f"  Avg LLM calls: {summary['avg_calls_per_task']} per task")
    print(f"  Total time:   {summary['total_time_s']}s ({summary['avg_time_per_task_s']}s avg)")
    print("=" * 60)

    # Comparison context
    print("\n  Comparison:")
    print("  Agent S3:     62.6% (100 steps)")
    print("  Claude CUA:   ~22%  (15 steps)")
    print("  Human:        72.4%")
    print("=" * 60 + "\n")


def main():
    args = parse_args()
    if args.dry_run:
        dry_run()
    else:
        run_benchmark(args)


if __name__ == "__main__":
    main()
