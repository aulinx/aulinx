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
    p.add_argument("--vmware-path", type=str, default=None,
                   help="Path to VMware Workstation directory (for vmrun)")

    # Agent config
    p.add_argument("--model", type=str, default="qwen2.5:14b",
                   help="LLM model name")
    p.add_argument("--base-url", type=str, default="http://localhost:11434",
                   help="LLM API base URL")
    p.add_argument("--api-type", type=str, default="ollama",
                   choices=["ollama", "openai", "anthropic", "gemini"],
                   help="LLM API type")
    p.add_argument("--temperature", type=float, default=0.3)
    p.add_argument("--max-tokens", type=int, default=1024)

    # Execution config
    p.add_argument("--max-steps", type=int, default=30,
                   help="Maximum steps per task (default: 30)")
    p.add_argument("--sleep-after-execution", type=float, default=2.0,
                   help="Seconds to wait after each action")
    p.add_argument("--result-dir", type=str, default="benchmark/results",
                   help="Directory to store results")

    # Model profiles (shortcuts for common configurations)
    p.add_argument("--profile", type=str, default=None,
                   choices=["local", "cloud", "best", "qwen-cloud"],
                   help="Model profile: local (Qwen/Ollama), qwen-cloud (Qwen Max/Dashscope), cloud (Claude Sonnet), best (Claude Opus)")

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
    """Run the full OSWorld benchmark.

    Uses direct HTTP communication with the OSWorld VM server instead of
    the heavy DesktopEnv class, avoiding PyTorch/transformers dependencies.
    For snapshot management, uses vmrun directly.
    """

    osworld_path = Path(args.osworld_path).resolve()

    if not osworld_path.exists():
        logger.error("OSWorld not found at %s", osworld_path)
        logger.error("Clone it: git clone https://github.com/xlang-ai/OSWorld.git %s", osworld_path)
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

    # Discover VM
    vmx_path = _find_vmx(osworld_path)
    logger.info("VM at %s", vmx_path)

    # Start VM if not running
    _ensure_vm_running(vmx_path)
    vm_ip = _get_vm_ip(vmx_path)
    logger.info("VM IP: %s", vm_ip)

    # Wait for VM HTTP server
    _wait_for_vm(vm_ip)

    # Load task examples
    examples_dir = osworld_path / "evaluation_examples" / "examples"
    if not examples_dir.exists():
        # Fallback to flat structure
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
            # Revert VM to clean snapshot
            _revert_vm(vmx_path)
            vm_ip = _get_vm_ip(vmx_path)
            _wait_for_vm(vm_ip)
            agent.reset()
            time.sleep(3)

            done = False
            step_idx = 0
            task_start = time.time()

            while not done and step_idx < args.max_steps:
                # Get observation
                obs = _get_obs(vm_ip)

                response, actions = agent.predict(instruction, obs)
                action = actions[0]

                logger.info("  Step %d: %s", step_idx + 1, action)

                # Check terminal actions
                if isinstance(action, str):
                    if action == "DONE":
                        done = True
                    elif action == "FAIL":
                        done = True
                    elif action == "WAIT":
                        time.sleep(2)
                    # Save and continue
                    with open(task_result_dir / "traj.jsonl", "a") as f:
                        f.write(json.dumps({
                            "step": step_idx + 1,
                            "action": action,
                            "response": response,
                        }, default=str) + "\n")
                    step_idx += 1
                    continue

                # Execute action on VM
                _execute_action(vm_ip, action)
                time.sleep(args.sleep_after_execution)

                # Save trajectory
                with open(task_result_dir / "traj.jsonl", "a") as f:
                    f.write(json.dumps({
                        "step": step_idx + 1,
                        "action": action,
                        "response": response,
                    }, default=str) + "\n")

                step_idx += 1

            task_time = time.time() - task_start
            token_stats = agent.get_token_stats()

            result = {
                "task_id": task_id,
                "domain": task.get("domain", "unknown"),
                "steps": step_idx,
                "time_s": round(task_time, 1),
                "tokens_in": token_stats["total_input_tokens"],
                "tokens_out": token_stats["total_output_tokens"],
                "llm_calls": token_stats["total_calls"],
                "completed": done,
            }
            results.append(result)

            logger.info("  Steps: %d | Time: %.1fs | Tokens: %d in + %d out",
                        step_idx, task_time,
                        token_stats["total_input_tokens"],
                        token_stats["total_output_tokens"])

        except Exception as e:
            logger.error("  Task %s failed: %s", task_id, e)
            results.append({
                "task_id": task_id,
                "domain": task.get("domain", "unknown"),
                "score": 0.0,
                "error": str(e),
            })

    # Save aggregate results
    total_time = time.time() - start_time
    summary = _compute_summary(results, total_time)

    with open(result_dir / "results.json", "w") as f:
        json.dump({"summary": summary, "tasks": results}, f, indent=2)

    _print_summary(summary)


def _vmrun() -> str:
    """Get the vmrun executable path."""
    import shutil
    vmrun = shutil.which("vmrun")
    if vmrun:
        return vmrun
    # Check common Windows locations
    for d in [
        r"D:\Tools\VMware\VMware Workstation",
        r"C:\Program Files (x86)\VMware\VMware Workstation",
        r"C:\Program Files\VMware\VMware Workstation",
    ]:
        candidate = Path(d) / "vmrun.exe"
        if candidate.exists():
            return str(candidate)
    raise FileNotFoundError("vmrun not found. Install VMware Workstation or add it to PATH.")


def _find_vmx(osworld_path: Path) -> str:
    """Find the OSWorld VM's .vmx file."""
    vm_data = osworld_path / "vmware_vm_data"
    if not vm_data.exists():
        raise FileNotFoundError(f"No vmware_vm_data directory in {osworld_path}")
    for vmx in vm_data.rglob("*.vmx"):
        return str(vmx)
    raise FileNotFoundError(f"No .vmx file found in {vm_data}")


def _ensure_vm_running(vmx_path: str):
    """Start the VM if it's not already running."""
    import subprocess
    result = subprocess.run(
        [_vmrun(), "list"],
        capture_output=True, text=True, timeout=15,
    )
    if vmx_path.replace("/", "\\") in result.stdout or vmx_path in result.stdout:
        logger.info("VM already running")
        return

    logger.info("Starting VM...")
    subprocess.run(
        [_vmrun(), "-T", "ws", "start", vmx_path, "nogui"],
        capture_output=True, timeout=120,
    )
    time.sleep(15)  # Wait for boot


def _get_vm_ip(vmx_path: str) -> str:
    """Get the VM's IP address via vmrun."""
    import subprocess

    # Retry a few times — VM may still be booting
    for attempt in range(5):
        result = subprocess.run(
            [_vmrun(), "-T", "ws", "getGuestIPAddress", vmx_path, "-wait"],
            capture_output=True, text=True, timeout=60,
        )
        ip = result.stdout.strip()
        if ip and result.returncode == 0:
            return ip
        logger.info("Waiting for VM IP (attempt %d/5)...", attempt + 1)
        time.sleep(10)

    raise RuntimeError(f"Could not get VM IP after 5 attempts: {result.stderr}")


def _revert_vm(vmx_path: str):
    """Revert VM to init_state snapshot and restart."""
    import subprocess
    logger.info("Reverting VM to init_state...")
    subprocess.run(
        [_vmrun(), "-T", "ws", "revertToSnapshot", vmx_path, "init_state"],
        capture_output=True, timeout=60,
    )
    time.sleep(2)
    subprocess.run(
        [_vmrun(), "-T", "ws", "start", vmx_path, "nogui"],
        capture_output=True, timeout=60,
    )
    time.sleep(10)


def _wait_for_vm(vm_ip: str, timeout: int = 120):
    """Wait for the VM's HTTP server to become available."""
    import httpx
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(f"http://{vm_ip}:5000/screenshot", timeout=5)
            if r.status_code == 200:
                logger.info("VM HTTP server ready at %s", vm_ip)
                return
        except Exception:
            pass
        time.sleep(3)
    raise TimeoutError(f"VM at {vm_ip} did not become ready within {timeout}s")


def _get_obs(vm_ip: str) -> dict:
    """Get observation from the VM via HTTP."""
    import httpx
    screenshot = httpx.get(f"http://{vm_ip}:5000/screenshot", timeout=15).content
    try:
        tree_resp = httpx.get(f"http://{vm_ip}:5000/accessibility", timeout=15)
        a11y_tree = tree_resp.json().get("AT", "")
    except Exception:
        a11y_tree = ""
    return {
        "screenshot": screenshot,
        "accessibility_tree": a11y_tree,
        "terminal": None,
    }


def _execute_action(vm_ip: str, action: dict):
    """Execute a computer_13 action on the VM via pyautogui."""
    import httpx
    action_type = action.get("action_type", "")

    cmd = ""
    if action_type == "CLICK":
        x, y = action["coordinate"]
        cmd = f"import pyautogui; pyautogui.click({x}, {y})"
    elif action_type == "DOUBLE_CLICK":
        x, y = action["coordinate"]
        cmd = f"import pyautogui; pyautogui.doubleClick({x}, {y})"
    elif action_type == "RIGHT_CLICK":
        x, y = action["coordinate"]
        cmd = f"import pyautogui; pyautogui.rightClick({x}, {y})"
    elif action_type == "TYPING":
        text = action["text"].replace("\\", "\\\\").replace("'", "\\'")
        cmd = f"import pyautogui; pyautogui.typewrite('{text}', interval=0.02)"
    elif action_type == "PRESS":
        cmd = f"import pyautogui; pyautogui.press('{action['key']}')"
    elif action_type == "HOTKEY":
        keys = ", ".join(f"'{k}'" for k in action["key"])
        cmd = f"import pyautogui; pyautogui.hotkey({keys})"
    elif action_type == "SCROLL":
        x, y = action.get("coordinate", [960, 540])
        dy = action.get("dy", -3)
        cmd = f"import pyautogui; pyautogui.scroll({dy}, {x}, {y})"
    elif action_type == "DRAG_TO":
        sx, sy = action["startCoordinate"]
        ex, ey = action["endCoordinate"]
        cmd = f"import pyautogui; pyautogui.moveTo({sx},{sy}); pyautogui.drag({ex-sx},{ey-sy}, duration=0.5)"
    else:
        logger.warning("Unknown action type: %s", action_type)
        return

    try:
        httpx.post(
            f"http://{vm_ip}:5000/execute",
            json={"command": ["python3", "-c", cmd]},
            timeout=15,
        )
    except Exception as e:
        logger.warning("Action execution error: %s", e)


def _load_tasks(examples_dir: Path, domain: str | None) -> dict:
    """Load task examples from OSWorld's evaluation_examples directory."""
    tasks = {}
    for domain_dir in sorted(examples_dir.iterdir()):
        if not domain_dir.is_dir():
            continue
        if domain and domain_dir.name != domain:
            continue
        for task_file in sorted(domain_dir.glob("*.json")):
            with open(task_file, encoding="utf-8") as f:
                task = json.load(f)
            task["domain"] = domain_dir.name
            tasks[task_file.stem] = task
    return tasks


def _compute_summary(results: list[dict], total_time: float) -> dict:
    """Compute aggregate metrics from task results.

    success_rate is passed / total_tasks. A task that errored out (harness
    crash, VM failure, agent exception) did not solve the task and counts as
    a failure — this matches OSWorld's standard scoring. passed + failed +
    errors == total_tasks.
    """
    total = len(results)
    scored = [r for r in results if "error" not in r]
    passed = [r for r in scored if r.get("completed")]

    total_tokens = sum(r.get("tokens_in", 0) + r.get("tokens_out", 0) for r in scored)
    total_calls = sum(r.get("llm_calls", 0) for r in scored)

    return {
        "total_tasks": total,
        "completed": len(scored),
        "passed": len(passed),
        "failed": len(scored) - len(passed),
        "errors": total - len(scored),
        "success_rate": round(len(passed) / max(1, total) * 100, 1),
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
    print(f"  Success rate: {summary['success_rate']}% ({summary['passed']}/{summary['total_tasks']})")
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


MODEL_PROFILES = {
    "local": {
        "model": "qwen2.5:14b",
        "base_url": "http://localhost:11434",
        "api_type": "ollama",
        "max_tokens": 1024,
    },
    "qwen-cloud": {
        "model": "qwen-max",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_type": "openai",
        "max_tokens": 2048,
    },
    "cloud": {
        "model": "claude-sonnet-4-20250514",
        "base_url": "https://api.anthropic.com",
        "api_type": "anthropic",
        "max_tokens": 2048,
    },
    "best": {
        "model": "claude-opus-4-20250514",
        "base_url": "https://api.anthropic.com",
        "api_type": "anthropic",
        "max_tokens": 4096,
    },
}


def _apply_profile(args):
    """Apply model profile defaults — explicit CLI flags take priority."""
    if not args.profile:
        return
    profile = MODEL_PROFILES[args.profile]
    parser_defaults = parse_args.__wrapped_defaults__ if hasattr(parse_args, '__wrapped_defaults__') else {
        "model": "qwen2.5:14b",
        "base_url": "http://localhost:11434",
        "api_type": "ollama",
        "max_tokens": 1024,
    }
    # Only override if the user didn't explicitly set the flag
    if args.model == parser_defaults.get("model", "qwen2.5:14b"):
        args.model = profile["model"]
    if args.base_url == parser_defaults.get("base_url", "http://localhost:11434"):
        args.base_url = profile["base_url"]
    if args.api_type == parser_defaults.get("api_type", "ollama"):
        args.api_type = profile["api_type"]
    if args.max_tokens == parser_defaults.get("max_tokens", 1024):
        args.max_tokens = profile["max_tokens"]
    logger.info("Using profile '%s': model=%s, api=%s", args.profile, args.model, args.api_type)


def main():
    import os

    # Load .env file if it exists
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

    args = parse_args()

    # Apply model profile defaults (CLI flags take priority)
    _apply_profile(args)

    # Add vmrun to PATH if needed
    vmware_dirs = [
        args.vmware_path,
        r"D:\Tools\VMware\VMware Workstation",
        r"C:\Program Files (x86)\VMware\VMware Workstation",
        r"C:\Program Files\VMware\VMware Workstation",
    ]
    for d in vmware_dirs:
        if d and os.path.exists(d):
            os.environ["PATH"] += os.pathsep + d
            break

    if args.dry_run:
        dry_run()
    else:
        run_benchmark(args)


if __name__ == "__main__":
    main()
