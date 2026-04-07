"""AI suggestion engine — monitors context and sends smart notifications."""

import asyncio
import os
import subprocess
import time

from rich.console import Console

console = Console()


class SuggestionEngine:
    """Monitors desktop context and generates proactive suggestions via notifications."""

    def __init__(self, llm_client=None, check_interval: int = 30):
        self.llm = llm_client
        self.check_interval = check_interval
        self._running = False
        self._last_suggestions: dict[str, float] = {}  # suggestion -> timestamp (cooldown)
        self._cooldown = 300  # 5 minutes between same suggestion

    async def start(self):
        """Start the suggestion monitoring loop."""
        self._running = True
        console.print("[dim]  Suggestion engine started[/dim]")

        while self._running:
            try:
                await self._check_and_suggest()
            except Exception as e:
                console.print(f"[dim]  Suggestion error: {e}[/dim]")
            await asyncio.sleep(self.check_interval)

    async def stop(self):
        self._running = False

    async def _check_and_suggest(self):
        """Check context for suggestion opportunities."""
        suggestions = []

        # Check for uncommitted git changes in common directories
        for project_dir in _find_git_repos():
            suggestion = await _check_git_status(project_dir)
            if suggestion:
                suggestions.append(suggestion)

        # Check high CPU usage
        suggestion = await _check_high_cpu()
        if suggestion:
            suggestions.append(suggestion)

        # Check low disk space
        suggestion = await _check_disk_space()
        if suggestion:
            suggestions.append(suggestion)

        # Check low battery
        suggestion = await _check_battery()
        if suggestion:
            suggestions.append(suggestion)

        # Send notifications for new suggestions (with cooldown)
        now = time.time()
        for s in suggestions:
            key = s["title"] + s["body"]
            last_sent = self._last_suggestions.get(key, 0)
            if now - last_sent > self._cooldown:
                _send_notification(s["title"], s["body"], s.get("urgency", "low"))
                self._last_suggestions[key] = now


def _find_git_repos() -> list[str]:
    """Find git repos in common locations."""
    home = os.path.expanduser("~")
    candidates = [
        os.path.join(home, d)
        for d in os.listdir(home)
        if os.path.isdir(os.path.join(home, d, ".git"))
    ]
    # Also check ~/Documents, ~/Projects, ~/Github
    for parent in ["Documents", "Projects", "Github", "repos", "code", "dev"]:
        parent_path = os.path.join(home, parent)
        if os.path.isdir(parent_path):
            for d in os.listdir(parent_path):
                full = os.path.join(parent_path, d)
                if os.path.isdir(os.path.join(full, ".git")):
                    candidates.append(full)
    return candidates[:10]  # limit to 10 repos


async def _check_git_status(repo_path: str) -> dict | None:
    """Check if a git repo has uncommitted changes."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, timeout=5, cwd=repo_path,
        )
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().splitlines()
            repo_name = os.path.basename(repo_path)
            return {
                "title": f"Uncommitted changes in {repo_name}",
                "body": f"{len(lines)} modified files. Consider committing.",
                "urgency": "low",
            }
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None


async def _check_high_cpu() -> dict | None:
    """Check if any process is using excessive CPU."""
    try:
        result = subprocess.run(
            ["ps", "ax", "--sort=-pcpu", "-o", "pid,%cpu,comm", "--no-headers"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines()[:3]:
                parts = line.split()
                if len(parts) >= 3:
                    cpu = float(parts[1])
                    name = parts[2]
                    if cpu > 80:
                        return {
                            "title": f"High CPU: {name}",
                            "body": f"{name} is using {cpu:.0f}% CPU.",
                            "urgency": "normal",
                        }
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


async def _check_disk_space() -> dict | None:
    """Check if disk space is running low."""
    try:
        result = subprocess.run(
            ["df", "-h", "--output=pcent,target", "/"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines()[1:]:
                parts = line.strip().split()
                if parts:
                    pct = int(parts[0].rstrip("%"))
                    if pct > 90:
                        return {
                            "title": "Low disk space",
                            "body": f"Root filesystem is {pct}% full.",
                            "urgency": "critical",
                        }
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass
    return None


async def _check_battery() -> dict | None:
    """Check if battery is low."""
    try:
        bat_path = "/sys/class/power_supply/BAT0/capacity"
        status_path = "/sys/class/power_supply/BAT0/status"
        if os.path.exists(bat_path):
            capacity = int(open(bat_path).read().strip())
            status = open(status_path).read().strip() if os.path.exists(status_path) else ""
            if capacity < 15 and status == "Discharging":
                return {
                    "title": "Battery low",
                    "body": f"Battery at {capacity}%. Connect charger.",
                    "urgency": "critical",
                }
    except (ValueError, OSError):
        pass
    return None


def _send_notification(title: str, body: str, urgency: str = "low"):
    """Send a desktop notification."""
    try:
        cmd = ["notify-send", "--urgency", urgency, "--icon", "dialog-information"]
        cmd.extend(["--app-name", "Aulinx"])
        cmd.extend([title, body])
        subprocess.run(cmd, capture_output=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
