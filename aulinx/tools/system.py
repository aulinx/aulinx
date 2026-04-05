"""System information and shell tools."""

import subprocess
import os
from aulinx.tools.registry import Tool, Tier


async def system_info() -> dict:
    """Get system information."""
    info = {}

    # OS
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    info["os"] = line.split("=", 1)[1].strip().strip('"')
                    break
    except FileNotFoundError:
        info["os"] = "unknown"

    # Kernel
    try:
        info["kernel"] = subprocess.check_output(["uname", "-r"], text=True).strip()
    except Exception:
        pass

    # Memory
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith(("MemTotal:", "MemAvailable:")):
                    key, val = line.split(":")
                    info[key.strip()] = val.strip()
    except FileNotFoundError:
        pass

    # CPU load
    try:
        with open("/proc/loadavg") as f:
            info["load_avg"] = f.read().split()[:3]
    except FileNotFoundError:
        pass

    # Desktop
    info["desktop"] = os.environ.get("XDG_CURRENT_DESKTOP", "unknown")
    info["session_type"] = os.environ.get("XDG_SESSION_TYPE", "unknown")

    return info


async def shell_exec(command: str) -> dict:
    """Execute a shell command and return output."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=os.path.expanduser("~"),
        )
        return {
            "stdout": result.stdout[:2000],
            "stderr": result.stderr[:500],
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": "Command timed out (30s)", "exit_code": -1}
    except Exception as e:
        return {"error": str(e), "exit_code": -1}


TOOLS = [
    Tool(
        name="system_info",
        description="Get system information (OS, kernel, memory, CPU load, desktop environment)",
        fn=system_info,
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="shell_exec",
        description="Execute a shell command and return stdout/stderr. Use with caution.",
        fn=shell_exec,
        parameters={"command": "string"},
        tier=Tier.DESTRUCTIVE,
    ),
]
