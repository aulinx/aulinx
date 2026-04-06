"""Package manager tools — auto-detects apt, dnf, or pacman."""

import shutil
import subprocess

from aulinx.tools.base import Tier, Tool


def _detect_pm() -> str | None:
    """Detect which package manager is available."""
    for pm in ["apt", "dnf", "pacman"]:
        if shutil.which(pm):
            return pm
    return None


async def package_search(query: str) -> list[dict]:
    """Search for packages by name."""
    pm = _detect_pm()
    if not pm:
        return [{"error": "No supported package manager found (apt, dnf, pacman)"}]

    try:
        if pm == "apt":
            result = subprocess.run(
                ["apt", "search", query],
                capture_output=True, text=True, timeout=30,
                env={**__import__("os").environ, "DEBIAN_FRONTEND": "noninteractive"},
            )
        elif pm == "dnf":
            result = subprocess.run(
                ["dnf", "search", query],
                capture_output=True, text=True, timeout=30,
            )
        elif pm == "pacman":
            result = subprocess.run(
                ["pacman", "-Ss", query],
                capture_output=True, text=True, timeout=30,
            )
        else:
            return [{"error": f"Unsupported: {pm}"}]

        if result.returncode != 0 and not result.stdout:
            return [{"error": result.stderr.strip() or "Search failed", "pm": pm}]

        # Parse results (keep it simple — return raw lines)
        lines = result.stdout.strip().splitlines()
        packages = []
        for line in lines[:30]:  # limit to 30 results
            line = line.strip()
            if line and not line.startswith("=") and not line.startswith("Sorting"):
                packages.append(line)
        return [{"pm": pm, "results": packages}]

    except subprocess.TimeoutExpired:
        return [{"error": f"{pm} search timed out"}]


async def package_install(name: str) -> dict:
    """Install a package. Requires sudo."""
    pm = _detect_pm()
    if not pm:
        return {"error": "No supported package manager found"}

    cmds = {
        "apt": ["sudo", "apt", "install", "-y", name],
        "dnf": ["sudo", "dnf", "install", "-y", name],
        "pacman": ["sudo", "pacman", "-S", "--noconfirm", name],
    }
    cmd = cmds.get(pm)
    if not cmd:
        return {"error": f"Unsupported: {pm}"}

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            return {"installed": True, "package": name, "pm": pm}
        return {"error": result.stderr.strip()[:500] or "Install failed", "pm": pm}
    except subprocess.TimeoutExpired:
        return {"error": "Install timed out (120s)"}


async def package_list_installed(query: str = "") -> list[str]:
    """List installed packages, optionally filtered by name."""
    pm = _detect_pm()
    if not pm:
        return ["No supported package manager found"]

    try:
        if pm == "apt":
            cmd = ["dpkg", "--get-selections"]
        elif pm == "dnf":
            cmd = ["dnf", "list", "installed"]
        elif pm == "pacman":
            cmd = ["pacman", "-Q"]
        else:
            return [f"Unsupported: {pm}"]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        lines = result.stdout.strip().splitlines()

        if query:
            lines = [line for line in lines if query.lower() in line.lower()]

        return lines[:50]

    except subprocess.TimeoutExpired:
        return ["Timed out listing packages"]


TOOLS = [
    Tool(
        name="package_search",
        description="Search for packages by name (auto-detects apt/dnf/pacman)",
        fn=package_search,
        parameters={"query": "string"},
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="package_install",
        description="Install a package via apt/dnf/pacman (requires sudo). Confirm with user first.",
        fn=package_install,
        parameters={"name": "string (package name)"},
        tier=Tier.DESTRUCTIVE,
    ),
    Tool(
        name="package_list_installed",
        description="List installed packages, optionally filtered by name",
        fn=package_list_installed,
        parameters={"query": "string (optional filter)"},
        tier=Tier.OBSERVE,
    ),
]
