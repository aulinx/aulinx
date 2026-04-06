"""Systemd service management tools."""

import subprocess

from aulinx.tools.base import Tier, Tool


def _systemctl(*args: str, user: bool = False, timeout: int = 10) -> dict:
    """Run systemctl and return output."""
    cmd = ["systemctl"]
    if user:
        cmd.append("--user")
    cmd.extend(args)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {
            "stdout": result.stdout.strip(),
            "returncode": result.returncode,
            "stderr": result.stderr.strip(),
        }
    except FileNotFoundError:
        return {"error": "systemctl not found"}
    except subprocess.TimeoutExpired:
        return {"error": "systemctl timed out"}


async def service_list(filter_state: str = "running") -> list[dict]:
    """List systemd services, optionally filtered by state."""
    args = ["list-units", "--type=service", "--no-pager", "--plain", "--no-legend"]
    if filter_state:
        args.extend([f"--state={filter_state}"])

    r = _systemctl(*args)
    if "error" in r:
        return [r]

    services = []
    for line in r["stdout"].splitlines():
        parts = line.split(None, 4)
        if len(parts) >= 4:
            services.append({
                "unit": parts[0],
                "load": parts[1],
                "active": parts[2],
                "sub": parts[3],
                "description": parts[4] if len(parts) > 4 else "",
            })
    return services


async def service_status(name: str) -> dict:
    """Get detailed status of a systemd service."""
    r = _systemctl("status", name, "--no-pager")
    if "error" in r:
        return r

    info = {"name": name, "raw": r["stdout"][:1000]}

    # Parse key fields
    for line in r["stdout"].splitlines():
        line = line.strip()
        if line.startswith("Active:"):
            info["active"] = line.split(":", 1)[1].strip()
        elif line.startswith("Main PID:"):
            info["main_pid"] = line.split(":", 1)[1].strip()
        elif line.startswith("Memory:"):
            info["memory"] = line.split(":", 1)[1].strip()
        elif line.startswith("CPU:"):
            info["cpu"] = line.split(":", 1)[1].strip()

    # Check if enabled
    r2 = _systemctl("is-enabled", name)
    info["enabled"] = r2.get("stdout", "unknown")

    return info


async def service_start(name: str) -> dict:
    """Start a systemd service."""
    r = _systemctl("start", name)
    if r["returncode"] == 0:
        return {"started": True, "service": name}
    return {"error": r["stderr"] or f"Failed to start {name}", "service": name}


async def service_stop(name: str) -> dict:
    """Stop a systemd service."""
    r = _systemctl("stop", name)
    if r["returncode"] == 0:
        return {"stopped": True, "service": name}
    return {"error": r["stderr"] or f"Failed to stop {name}", "service": name}


async def service_restart(name: str) -> dict:
    """Restart a systemd service."""
    r = _systemctl("restart", name)
    if r["returncode"] == 0:
        return {"restarted": True, "service": name}
    return {"error": r["stderr"] or f"Failed to restart {name}", "service": name}


TOOLS = [
    Tool(
        name="service_list",
        description="List systemd services (default: running). filter_state: running, failed, inactive, etc.",
        fn=service_list,
        parameters={"filter_state": "string (default: running)"},
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="service_status",
        description="Get detailed status of a systemd service (active state, PID, memory, CPU)",
        fn=service_status,
        parameters={"name": "string (e.g. nginx, docker, ssh)"},
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="service_start",
        description="Start a systemd service",
        fn=service_start,
        parameters={"name": "string"},
        tier=Tier.DESTRUCTIVE,
    ),
    Tool(
        name="service_stop",
        description="Stop a systemd service",
        fn=service_stop,
        parameters={"name": "string"},
        tier=Tier.DESTRUCTIVE,
    ),
    Tool(
        name="service_restart",
        description="Restart a systemd service",
        fn=service_restart,
        parameters={"name": "string"},
        tier=Tier.DESTRUCTIVE,
    ),
]
