"""System administration tools — firewall, users, SSH, kernel, startup apps."""

import os
import subprocess

from aulinx.tools.base import Tier, Tool


async def firewall_status() -> dict:
    """Get firewall status and rules (ufw)."""
    try:
        result = subprocess.run(
            ["sudo", "ufw", "status", "verbose"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return {"status": result.stdout.strip()}
        # Try without sudo
        result = subprocess.run(
            ["ufw", "status"], capture_output=True, text=True, timeout=5,
        )
        return {"status": result.stdout.strip() or result.stderr.strip()}
    except FileNotFoundError:
        return {"error": "ufw not found. Install: sudo apt install ufw"}


async def firewall_allow(port: str) -> dict:
    """Allow a port through the firewall."""
    try:
        result = subprocess.run(
            ["sudo", "ufw", "allow", port],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return {"allowed": True, "port": port, "output": result.stdout.strip()}
        return {"error": result.stderr.strip()}
    except FileNotFoundError:
        return {"error": "ufw not found"}


async def user_list() -> list[dict]:
    """List system users (human users with UID >= 1000)."""
    users = []
    try:
        with open("/etc/passwd") as f:
            for line in f:
                parts = line.strip().split(":")
                if len(parts) >= 7:
                    uid = int(parts[2])
                    if uid >= 1000 or parts[0] == "root":
                        users.append({
                            "username": parts[0],
                            "uid": uid,
                            "gid": int(parts[3]),
                            "home": parts[5],
                            "shell": parts[6],
                        })
    except FileNotFoundError:
        return [{"error": "/etc/passwd not found"}]
    return users


async def ssh_status() -> dict:
    """Check SSH service status and authorized keys."""
    info = {}

    # Service status
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "sshd"],
            capture_output=True, text=True, timeout=5,
        )
        info["service"] = result.stdout.strip()
    except FileNotFoundError:
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "ssh"],
                capture_output=True, text=True, timeout=5,
            )
            info["service"] = result.stdout.strip()
        except FileNotFoundError:
            info["service"] = "systemctl not found"

    # Authorized keys count
    auth_keys = os.path.expanduser("~/.ssh/authorized_keys")
    if os.path.exists(auth_keys):
        with open(auth_keys) as f:
            keys = [line for line in f.readlines() if line.strip() and not line.startswith("#")]
        info["authorized_keys"] = len(keys)
    else:
        info["authorized_keys"] = 0

    return info


async def kernel_info() -> dict:
    """Get kernel version and system information."""
    info = {}
    try:
        result = subprocess.run(["uname", "-a"], capture_output=True, text=True, timeout=5)
        info["uname"] = result.stdout.strip()
    except FileNotFoundError:
        pass

    try:
        result = subprocess.run(["uname", "-r"], capture_output=True, text=True, timeout=5)
        info["kernel"] = result.stdout.strip()
    except FileNotFoundError:
        pass

    # CPU info
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    info["cpu"] = line.split(":")[1].strip()
                    break
    except FileNotFoundError:
        pass

    # Total RAM
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal"):
                    kb = int(line.split()[1])
                    info["ram_gb"] = round(kb / 1024 / 1024, 1)
                    break
    except FileNotFoundError:
        pass

    return info


async def startup_apps_list() -> list[dict]:
    """List autostart applications."""
    apps = []
    autostart_dirs = [
        os.path.expanduser("~/.config/autostart"),
        "/etc/xdg/autostart",
    ]
    for d in autostart_dirs:
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.endswith(".desktop"):
                    path = os.path.join(d, f)
                    name = f.replace(".desktop", "")
                    hidden = False
                    try:
                        with open(path) as fh:
                            for line in fh:
                                if line.startswith("Name="):
                                    name = line.split("=", 1)[1].strip()
                                elif line.strip() == "Hidden=true":
                                    hidden = True
                    except OSError:
                        pass
                    apps.append({"name": name, "file": f, "dir": d, "hidden": hidden})
    return apps


TOOLS = [
    Tool(
        name="firewall_status",
        description="Get firewall (ufw) status and rules",
        fn=firewall_status,
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="firewall_allow",
        description="Allow a port through the firewall (ufw)",
        fn=firewall_allow,
        parameters={"port": "string (e.g. '22', '80/tcp', '443')"},
        tier=Tier.DESTRUCTIVE,
    ),
    Tool(
        name="user_list",
        description="List system users (human accounts with UID >= 1000)",
        fn=user_list,
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="ssh_status",
        description="Check SSH service status and count of authorized keys",
        fn=ssh_status,
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="kernel_info",
        description="Get kernel version, CPU model, and RAM size",
        fn=kernel_info,
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="startup_apps_list",
        description="List applications that start automatically on login",
        fn=startup_apps_list,
        tier=Tier.OBSERVE,
    ),
]
