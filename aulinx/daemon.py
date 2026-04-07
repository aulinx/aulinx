"""Aulinx daemon — background service with global hotkey and ambient context.

Runs as a systemd user service or standalone process.
Listens for global hotkey (Super+Space) to invoke the AI palette.
Monitors desktop context continuously for ambient suggestions.
"""

import asyncio
import os
import signal
import subprocess

from rich.console import Console

console = Console()

# Default hotkey: Super+Space
DEFAULT_HOTKEY = "super+space"


class AulinxDaemon:
    """Background daemon that provides hotkey activation and ambient context."""

    def __init__(self, hotkey: str = DEFAULT_HOTKEY, port: int = 8765):
        self.hotkey = hotkey
        self.port = port
        self._running = False
        self._context_task = None

    async def start(self):
        """Start the daemon with hotkey listener and context engine."""
        self._running = True
        console.print("[bold gold1]Aulinx Daemon[/bold gold1] starting...")
        console.print(f"[dim]  Hotkey: {self.hotkey}[/dim]")
        console.print(f"[dim]  Server port: {self.port}[/dim]")

        # Start the WebSocket server in background
        server_task = asyncio.create_task(self._run_server())

        # Start the hotkey listener
        hotkey_task = asyncio.create_task(self._listen_hotkey())

        # Start the ambient context engine
        self._context_task = asyncio.create_task(self._run_context_engine())

        console.print("[bold green]Daemon ready.[/bold green] Press hotkey to invoke palette.")

        # Handle signals
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))
            except NotImplementedError:
                pass  # Windows

        await asyncio.gather(server_task, hotkey_task, self._context_task, return_exceptions=True)

    async def stop(self):
        """Stop the daemon."""
        self._running = False
        console.print("\n[dim]Daemon stopping...[/dim]")

    async def _run_server(self):
        """Run the WebSocket server for the UI palette."""
        from aulinx.server import run_server
        try:
            await run_server(port=self.port)
        except Exception as e:
            console.print(f"[red]Server error: {e}[/red]")

    async def _listen_hotkey(self):
        """Listen for the global hotkey using evdev or dbus."""
        # Try different hotkey backends
        backend = _detect_hotkey_backend()

        if backend == "dbus-gnome":
            await self._hotkey_gnome_dbus()
        elif backend == "evdev":
            await self._hotkey_evdev()
        else:
            console.print("[yellow]No hotkey backend available. Use 'aulinx --serve' manually.[/yellow]")
            # Keep running without hotkey
            while self._running:
                await asyncio.sleep(1)

    async def _hotkey_gnome_dbus(self):
        """Register a global hotkey via GNOME's D-Bus settings."""
        # Set a custom keybinding in GNOME that launches the palette
        try:
            # Register custom keybinding
            _register_gnome_hotkey(self.hotkey, self.port)
            console.print(f"[dim]  Hotkey registered via GNOME settings ({self.hotkey})[/dim]")
            while self._running:
                await asyncio.sleep(1)
        except Exception as e:
            console.print(f"[yellow]GNOME hotkey registration failed: {e}[/yellow]")

    async def _hotkey_evdev(self):
        """Listen for hotkey via evdev (requires root or input group)."""
        try:
            import evdev
            devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
            keyboards = [d for d in devices if "keyboard" in d.name.lower() or evdev.ecodes.EV_KEY in d.capabilities()]

            if not keyboards:
                console.print("[yellow]No keyboard devices found for hotkey.[/yellow]")
                return

            console.print(f"[dim]  Listening on {keyboards[0].name}[/dim]")

            dev = keyboards[0]
            super_held = False

            async for event in dev.async_read_loop():
                if not self._running:
                    break
                if event.type == evdev.ecodes.EV_KEY:
                    key_event = evdev.categorize(event)
                    if key_event.keycode in ("KEY_LEFTMETA", "KEY_RIGHTMETA"):
                        super_held = key_event.keystate in (1, 2)  # pressed or held
                    elif key_event.keycode == "KEY_SPACE" and key_event.keystate == 1 and super_held:
                        await self._invoke_palette()

        except ImportError:
            console.print("[yellow]evdev not installed. Run: pip install evdev[/yellow]")
        except PermissionError:
            console.print("[yellow]Need root or input group for evdev hotkey. Add user to input group: sudo usermod -a -G input $USER[/yellow]")

    async def _invoke_palette(self):
        """Called when hotkey is pressed — open the palette UI."""
        console.print("[gold1]Hotkey pressed — opening palette[/gold1]")
        # Open the web UI in the default browser
        try:
            subprocess.Popen(
                ["xdg-open", f"http://localhost:{self.port + 1}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            pass

    async def _run_context_engine(self):
        """Ambient context engine — monitors desktop state continuously."""
        from aulinx.context.desktop import DesktopContext

        ctx = DesktopContext()
        await ctx.initialize()
        context_file = os.path.expanduser("~/.local/share/aulinx/context.json")
        os.makedirs(os.path.dirname(context_file), exist_ok=True)

        while self._running:
            try:
                snapshot = await ctx.snapshot()
                # Save context to file for other processes to read
                with open(context_file, "w") as f:
                    f.write(snapshot)
            except Exception:
                pass
            await asyncio.sleep(5)  # Update every 5 seconds


def _detect_hotkey_backend() -> str:
    """Detect the best hotkey backend for the current desktop."""
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    if "gnome" in desktop:
        return "dbus-gnome"
    try:
        import evdev  # noqa: F401
        return "evdev"
    except ImportError:
        pass
    return "none"


def _register_gnome_hotkey(hotkey: str, port: int):
    """Register a custom keybinding in GNOME settings."""
    # GNOME uses gsettings for custom keybindings
    import subprocess

    schema = "org.gnome.settings-daemon.plugins.media-keys"
    custom_schema = "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding"
    path = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/aulinx/"

    # Set the custom keybinding
    subprocess.run([
        "gsettings", "set", schema, "custom-keybindings",
        f"['{path}']"
    ], capture_output=True)

    subprocess.run([
        "gsettings", "set", f"{custom_schema}:{path}", "name", "Aulinx Palette"
    ], capture_output=True)

    subprocess.run([
        "gsettings", "set", f"{custom_schema}:{path}", "command",
        f"xdg-open http://localhost:{port + 1}"
    ], capture_output=True)

    # Map hotkey format: "super+space" → "<Super>space"
    gnome_key = hotkey.replace("super+", "<Super>").replace("ctrl+", "<Ctrl>").replace("alt+", "<Alt>").replace("shift+", "<Shift>")
    subprocess.run([
        "gsettings", "set", f"{custom_schema}:{path}", "binding", gnome_key
    ], capture_output=True)


async def run_daemon(hotkey: str = DEFAULT_HOTKEY, port: int = 8765):
    daemon = AulinxDaemon(hotkey=hotkey, port=port)
    await daemon.start()
