"""System information and shell tools."""

import os
import subprocess

from aulinx.sandbox import SandboxConfig, sandbox_command
from aulinx.tools.base import Tier, Tool


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
    """Execute a shell command and return output.

    If sandbox is configured (via config.toml [security] section),
    the command runs inside a bubblewrap or firejail sandbox.
    """
    # Load sandbox config if available
    try:
        from aulinx.config import load_config
        config = load_config()
        sandbox_cfg = SandboxConfig(
            enabled=config.security.sandbox_enabled,
            backend=config.security.sandbox_backend,
            allow_network=config.security.sandbox_allow_network,
            allow_home_write=config.security.sandbox_allow_home_write,
            timeout_s=config.security.sandbox_timeout_s,
        )
    except Exception:
        sandbox_cfg = SandboxConfig()

    timeout = sandbox_cfg.timeout_s if sandbox_cfg.enabled else 30

    try:
        cmd_argv = sandbox_command(command, sandbox_cfg)
        result = subprocess.run(
            cmd_argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.path.expanduser("~"),
        )
        return {
            "stdout": result.stdout[:2000],
            "stderr": result.stderr[:500],
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": f"Command timed out ({timeout}s)", "exit_code": -1}
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
