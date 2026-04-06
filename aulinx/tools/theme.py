"""Theme and appearance tools — dark/light mode, wallpaper, GTK/Qt theme."""

import os
import subprocess
from pathlib import Path

from aulinx.tools.base import Tier, Tool


def _gsettings(schema: str, key: str, value: str | None = None) -> dict:
    """Get or set a gsettings value."""
    try:
        if value is None:
            result = subprocess.run(
                ["gsettings", "get", schema, key],
                capture_output=True, text=True, timeout=5,
            )
        else:
            result = subprocess.run(
                ["gsettings", "set", schema, key, value],
                capture_output=True, text=True, timeout=5,
            )
        if result.returncode == 0:
            return {"value": result.stdout.strip().strip("'")} if value is None else {"set": True}
        return {"error": result.stderr.strip()}
    except FileNotFoundError:
        return {"error": "gsettings not found"}
    except subprocess.TimeoutExpired:
        return {"error": "timed out"}


async def theme_get() -> dict:
    """Get current theme settings — color scheme, GTK theme, icon theme, wallpaper."""
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    info = {"desktop": desktop}

    if "gnome" in desktop or "unity" in desktop or "budgie" in desktop:
        r = _gsettings("org.gnome.desktop.interface", "color-scheme")
        info["color_scheme"] = r.get("value", "unknown")  # prefer-dark, prefer-light, default

        r = _gsettings("org.gnome.desktop.interface", "gtk-theme")
        info["gtk_theme"] = r.get("value", "unknown")

        r = _gsettings("org.gnome.desktop.interface", "icon-theme")
        info["icon_theme"] = r.get("value", "unknown")

        r = _gsettings("org.gnome.desktop.interface", "font-name")
        info["font"] = r.get("value", "unknown")

        r = _gsettings("org.gnome.desktop.background", "picture-uri")
        info["wallpaper"] = r.get("value", "unknown")

        r = _gsettings("org.gnome.desktop.interface", "cursor-theme")
        info["cursor_theme"] = r.get("value", "unknown")

    elif "kde" in desktop or "plasma" in desktop:
        # KDE uses different config
        try:
            result = subprocess.run(
                ["kreadconfig5", "--group", "General", "--key", "ColorScheme"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                info["color_scheme"] = result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    return info


async def theme_set_dark(dark: bool = True) -> dict:
    """Switch between dark and light mode."""
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()

    if "gnome" in desktop or "unity" in desktop or "budgie" in desktop:
        scheme = "prefer-dark" if dark else "prefer-light"
        r = _gsettings("org.gnome.desktop.interface", "color-scheme", scheme)
        if "error" in r:
            return r
        return {"dark_mode": dark, "color_scheme": scheme}

    elif "kde" in desktop or "plasma" in desktop:
        scheme = "BreezeDark" if dark else "BreezeLight"
        try:
            result = subprocess.run(
                ["plasma-apply-colorscheme", scheme],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return {"dark_mode": dark, "color_scheme": scheme}
            return {"error": result.stderr.strip()}
        except FileNotFoundError:
            return {"error": "plasma-apply-colorscheme not found"}

    return {"error": f"Unsupported desktop: {desktop}"}


async def wallpaper_set(path: str) -> dict:
    """Set the desktop wallpaper."""
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        return {"error": f"File not found: {path}"}

    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    uri = f"file://{p}"

    if "gnome" in desktop or "unity" in desktop or "budgie" in desktop:
        r1 = _gsettings("org.gnome.desktop.background", "picture-uri", uri)
        _gsettings("org.gnome.desktop.background", "picture-uri-dark", uri)
        if "error" in r1:
            return r1
        return {"wallpaper": str(p), "set": True}

    elif "kde" in desktop or "plasma" in desktop:
        # KDE requires a DBus call or script
        script = f'''
var allDesktops = desktops();
for (i = 0; i < allDesktops.length; i++) {{
    d = allDesktops[i];
    d.wallpaperPlugin = "org.kde.image";
    d.currentConfigGroup = Array("Wallpaper", "org.kde.image", "General");
    d.writeConfig("Image", "file://{p}");
}}
'''
        try:
            result = subprocess.run(
                ["qdbus", "org.kde.plasmashell", "/PlasmaShell",
                 "org.kde.PlasmaShell.evaluateScript", script],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return {"wallpaper": str(p), "set": True}
            return {"error": result.stderr.strip()}
        except FileNotFoundError:
            return {"error": "qdbus not found"}

    return {"error": f"Unsupported desktop: {desktop}"}


TOOLS = [
    Tool(
        name="theme_get",
        description="Get current theme — color scheme (dark/light), GTK theme, icon theme, font, wallpaper",
        fn=theme_get,
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="theme_set_dark",
        description="Switch to dark mode (true) or light mode (false)",
        fn=theme_set_dark,
        parameters={"dark": "bool (true=dark, false=light)"},
        tier=Tier.LOW_RISK,
    ),
    Tool(
        name="wallpaper_set",
        description="Set the desktop wallpaper from a file path",
        fn=wallpaper_set,
        parameters={"path": "string (path to image file)"},
        tier=Tier.LOW_RISK,
    ),
]
