"""Server/headless tools — system administration for Linux servers.

These tools work without a GUI and are useful for server management,
Docker containers, SSH sessions, and WSL.
"""

import subprocess

from aulinx.tools.base import Tier, Tool


async def journal_logs(unit: str = "", lines: int = 50, priority: str = "") -> str:
    """Query systemd journal logs.

    Args:
        unit: Service unit name (e.g. 'nginx', 'sshd'). Empty for all.
        lines: Number of recent lines to show.
        priority: Filter by priority (emerg, alert, crit, err, warning, notice, info, debug).
    """
    cmd = ["journalctl", "--no-pager", "-n", str(lines)]
    if unit:
        cmd += ["-u", unit]
    if priority:
        cmd += ["-p", priority]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return result.stdout or result.stderr or "No logs found"
    except FileNotFoundError:
        return "journalctl not found (not a systemd system)"
    except subprocess.TimeoutExpired:
        return "Timed out reading logs"


async def docker_ps() -> str:
    """List running Docker containers."""
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "table {{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout or result.stderr or "No containers running"
    except FileNotFoundError:
        return "Docker not installed"


async def docker_logs(container: str, lines: int = 50) -> str:
    """Get logs from a Docker container.

    Args:
        container: Container name or ID.
        lines: Number of recent lines.
    """
    try:
        result = subprocess.run(
            ["docker", "logs", "--tail", str(lines), container],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout + result.stderr or "No logs"
    except FileNotFoundError:
        return "Docker not installed"


async def port_list() -> str:
    """List listening network ports."""
    try:
        result = subprocess.run(
            ["ss", "-tlnp"],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout or "No listening ports"
    except FileNotFoundError:
        try:
            result = subprocess.run(
                ["netstat", "-tlnp"],
                capture_output=True, text=True, timeout=10,
            )
            return result.stdout or "No listening ports"
        except FileNotFoundError:
            return "Neither ss nor netstat found"


async def firewall_status() -> str:
    """Check firewall status (ufw, firewalld, or iptables)."""
    # Try ufw first
    try:
        result = subprocess.run(["ufw", "status", "verbose"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return f"[ufw]\n{result.stdout}"
    except FileNotFoundError:
        pass

    # Try firewalld
    try:
        result = subprocess.run(["firewall-cmd", "--state"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            zones = subprocess.run(["firewall-cmd", "--list-all"], capture_output=True, text=True, timeout=5)
            return f"[firewalld] {result.stdout.strip()}\n{zones.stdout}"
    except FileNotFoundError:
        pass

    # Fall back to iptables
    try:
        result = subprocess.run(["iptables", "-L", "-n", "--line-numbers"], capture_output=True, text=True, timeout=5)
        return f"[iptables]\n{result.stdout or result.stderr}"
    except FileNotFoundError:
        return "No firewall found (ufw, firewalld, iptables)"


async def cron_list() -> str:
    """List cron jobs for the current user."""
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout or "No cron jobs"
        return "No crontab for current user"
    except FileNotFoundError:
        return "crontab not found"


async def disk_health() -> str:
    """Check disk SMART health status."""
    try:
        # List block devices first
        lsblk = subprocess.run(
            ["lsblk", "-d", "-o", "NAME,SIZE,TYPE,MODEL"],
            capture_output=True, text=True, timeout=5,
        )
        output = f"[Devices]\n{lsblk.stdout}\n"

        # Try smartctl on first disk
        result = subprocess.run(
            ["smartctl", "-H", "/dev/sda"],
            capture_output=True, text=True, timeout=10,
        )
        output += f"[SMART /dev/sda]\n{result.stdout or result.stderr}"
        return output
    except FileNotFoundError:
        return "smartctl not installed (apt install smartmontools)"


async def system_logs_summary() -> str:
    """Get a summary of recent system errors and warnings."""
    try:
        result = subprocess.run(
            ["journalctl", "--no-pager", "-p", "err", "-n", "20", "--since", "1 hour ago"],
            capture_output=True, text=True, timeout=10,
        )
        errors = result.stdout.strip()
        if not errors:
            return "No errors in the last hour"
        return f"Recent errors (last hour):\n{errors}"
    except FileNotFoundError:
        return "journalctl not available"


TOOLS = [
    Tool("journal_logs", "Query systemd journal logs",
         journal_logs,
         parameters={"unit": "string — service name (e.g. nginx)", "lines": "int — number of lines (default 50)", "priority": "string — log priority filter"},
         tier=Tier.OBSERVE),
    Tool("docker_ps", "List running Docker containers",
         docker_ps, tier=Tier.OBSERVE),
    Tool("docker_logs", "Get Docker container logs",
         docker_logs,
         parameters={"container": "string — container name or ID", "lines": "int — number of lines"},
         tier=Tier.OBSERVE),
    Tool("port_list", "List listening network ports",
         port_list, tier=Tier.OBSERVE),
    Tool("firewall_status", "Check firewall status and rules",
         firewall_status, tier=Tier.OBSERVE),
    Tool("cron_list", "List cron jobs for current user",
         cron_list, tier=Tier.OBSERVE),
    Tool("disk_health", "Check disk SMART health status",
         disk_health, tier=Tier.OBSERVE),
    Tool("system_logs_summary", "Recent system errors and warnings",
         system_logs_summary, tier=Tier.OBSERVE),
]
