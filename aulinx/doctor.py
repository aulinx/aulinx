"""Diagnostic check — verifies all dependencies and capabilities."""

import os
import shutil

from rich.console import Console
from rich.table import Table

console = Console()


async def run_doctor(base_url: str = "http://localhost:11434"):
    """Run a full diagnostic check and print results."""
    console.print("\n[bold]Aulinx Doctor[/bold] — checking your system\n")

    table = Table(show_header=True, header_style="bold")
    table.add_column("Component", width=25)
    table.add_column("Status", width=10)
    table.add_column("Details", width=50)

    # Core
    _check_ollama(table, base_url)
    _check_python_dep(table, "pyatspi", "AT-SPI (GUI control)", "apt install python3-pyatspi")

    # Clipboard
    _check_binary(table, "wl-paste", "Clipboard (Wayland)", "apt install wl-clipboard")
    _check_binary(table, "xclip", "Clipboard (X11)", "apt install xclip")

    # Notifications
    _check_binary(table, "notify-send", "Notifications", "apt install libnotify-bin")

    # Network
    _check_binary(table, "nmcli", "NetworkManager", "apt install network-manager")

    # Bluetooth
    _check_binary(table, "bluetoothctl", "Bluetooth", "apt install bluez-utils")

    # Audio
    _check_binary(table, "wpctl", "PipeWire audio", "apt install wireplumber")
    _check_binary(table, "pactl", "PulseAudio", "apt install pulseaudio-utils")

    # Display
    _check_binary(table, "wlr-randr", "Display (Wayland)", "apt install wlr-randr")
    _check_binary(table, "xrandr", "Display (X11)", "apt install x11-xserver-utils")
    _check_binary(table, "brightnessctl", "Brightness", "apt install brightnessctl")

    # Screenshot
    _check_binary(table, "grim", "Screenshot (Wayland)", "apt install grim")
    _check_binary(table, "scrot", "Screenshot (X11)", "apt install scrot")

    # Input simulation
    _check_binary(table, "wtype", "Input (Wayland)", "apt install wtype")
    _check_binary(table, "xdotool", "Input (X11)", "apt install xdotool")

    # Power
    _check_binary(table, "powerprofilesctl", "Power profiles", "apt install power-profiles-daemon")

    # Services
    _check_binary(table, "systemctl", "Systemd", "built-in")

    # Package manager
    pm = None
    for name in ["apt", "dnf", "pacman"]:
        if shutil.which(name):
            pm = name
            break
    if pm:
        table.add_row("Package manager", "[green]OK[/green]", pm)
    else:
        table.add_row("Package manager", "[red]MISS[/red]", "No apt, dnf, or pacman found")

    # XDG
    _check_binary(table, "xdg-open", "XDG open", "apt install xdg-utils")
    _check_binary(table, "xdg-mime", "XDG MIME", "apt install xdg-utils")

    # Session info
    _check_env(table, "XDG_CURRENT_DESKTOP", "Desktop environment")
    _check_env(table, "XDG_SESSION_TYPE", "Session type (wayland/x11)")
    _check_env(table, "WAYLAND_DISPLAY", "Wayland display")
    _check_env(table, "DISPLAY", "X11 display")

    console.print(table)
    console.print()


def _check_ollama(table: Table, base_url: str):
    """Check Ollama connectivity."""
    import httpx

    try:
        resp = httpx.get(f"{base_url}/api/tags", timeout=5)
        models = [m["name"] for m in resp.json().get("models", [])]
        if models:
            table.add_row("Ollama", "[green]OK[/green]", f"{len(models)} models: {', '.join(models[:5])}")
        else:
            table.add_row("Ollama", "[yellow]WARN[/yellow]", "Running but no models. Run: ollama pull qwen2.5:14b")
    except Exception:
        table.add_row("Ollama", "[red]MISS[/red]", f"Not running at {base_url}. Run: ollama serve")


def _check_python_dep(table: Table, module: str, label: str, install_hint: str):
    """Check if a Python module is importable."""
    try:
        __import__(module)
        table.add_row(label, "[green]OK[/green]", f"python module '{module}' found")
    except ImportError:
        table.add_row(label, "[red]MISS[/red]", f"Install: {install_hint}")


def _check_binary(table: Table, name: str, label: str, install_hint: str):
    """Check if a binary is in PATH."""
    path = shutil.which(name)
    if path:
        table.add_row(label, "[green]OK[/green]", path)
    else:
        table.add_row(label, "[dim]MISS[/dim]", f"Install: {install_hint}")


def _check_env(table: Table, var: str, label: str):
    """Check an environment variable."""
    val = os.environ.get(var)
    if val:
        table.add_row(label, "[green]OK[/green]", f"{var}={val}")
    else:
        table.add_row(label, "[dim]—[/dim]", f"{var} not set")
