"""Process management tools — list, inspect, kill processes."""

import subprocess
from aulinx.tools.registry import Tool, Tier


async def process_list(sort_by: str = "cpu", limit: int = 20) -> list[dict]:
    """List running processes sorted by CPU or memory usage."""
    sort_key = {
        "cpu": "-pcpu",
        "memory": "-pmem",
        "mem": "-pmem",
        "pid": "pid",
        "name": "comm",
    }.get(sort_by, "-pcpu")

    try:
        result = subprocess.run(
            ["ps", "ax", f"--sort={sort_key}",
             "-o", "pid,user,%cpu,%mem,rss,comm,args",
             "--no-headers"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return [{"error": result.stderr.strip()}]

        processes = []
        for line in result.stdout.strip().splitlines():
            parts = line.split(None, 6)
            if len(parts) < 6:
                continue
            processes.append({
                "pid": int(parts[0]),
                "user": parts[1],
                "cpu": float(parts[2]),
                "mem": float(parts[3]),
                "rss_mb": round(int(parts[4]) / 1024, 1),
                "name": parts[5],
                "command": parts[6][:100] if len(parts) > 6 else parts[5],
            })

        # ps --sort is ascending; reverse for descending cpu/mem
        if sort_by in ("cpu", "memory", "mem"):
            processes.reverse()

        return processes[:limit]

    except FileNotFoundError:
        return [{"error": "ps command not found"}]
    except subprocess.TimeoutExpired:
        return [{"error": "ps timed out"}]


async def process_kill(pid: int, signal: str = "TERM") -> dict:
    """Send a signal to a process."""
    sig = signal.upper()
    if sig not in ("TERM", "KILL", "HUP", "INT", "STOP", "CONT"):
        return {"error": f"Invalid signal: {signal}. Use TERM, KILL, HUP, INT, STOP, CONT."}

    try:
        # Get process info first
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "pid,user,comm", "--no-headers"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return {"error": f"Process {pid} not found"}

        parts = result.stdout.strip().split(None, 2)
        proc_name = parts[2] if len(parts) > 2 else "unknown"

        # Send signal
        kill_result = subprocess.run(
            ["kill", f"-{sig}", str(pid)],
            capture_output=True, text=True, timeout=5,
        )
        if kill_result.returncode == 0:
            return {"killed": True, "pid": pid, "name": proc_name, "signal": sig}
        return {"error": kill_result.stderr.strip(), "pid": pid}

    except FileNotFoundError:
        return {"error": "kill command not found"}
    except subprocess.TimeoutExpired:
        return {"error": "timed out"}


TOOLS = [
    Tool(
        name="process_list",
        description="List running processes sorted by CPU or memory usage",
        fn=process_list,
        parameters={"sort_by": "cpu|memory|pid|name (default: cpu)", "limit": "int (default 20)"},
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="process_kill",
        description="Kill a process by PID. Use process_list first to find the PID.",
        fn=process_kill,
        parameters={"pid": "int", "signal": "TERM|KILL|HUP|INT (default: TERM)"},
        tier=Tier.DESTRUCTIVE,
    ),
]
