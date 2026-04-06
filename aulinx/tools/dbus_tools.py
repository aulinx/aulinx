"""D-Bus tools — introspect services and call methods."""

import subprocess
import xml.etree.ElementTree as ET

from aulinx.tools.base import Tier, Tool


async def dbus_list_services(bus: str = "session") -> list[str]:
    """List all available D-Bus services on the session or system bus."""
    flag = "--session" if bus == "session" else "--system"
    try:
        result = subprocess.run(
            ["dbus-send", flag, "--dest=org.freedesktop.DBus",
             "--type=method_call", "--print-reply",
             "/org/freedesktop/DBus", "org.freedesktop.DBus.ListNames"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return [f"Error: {result.stderr.strip()}"]

        # Parse the output — dbus-send prints array of strings
        names = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith('string "'):
                name = line[8:-1]  # strip 'string "' and '"'
                if not name.startswith(":"):  # skip unique connection names
                    names.append(name)
        return sorted(names)

    except FileNotFoundError:
        return ["Error: dbus-send not found"]
    except subprocess.TimeoutExpired:
        return ["Error: dbus-send timed out"]


async def dbus_introspect(
    destination: str, path: str = "/", bus: str = "session"
) -> dict:
    """Introspect a D-Bus object — list its interfaces, methods, and signals."""
    flag = "--session" if bus == "session" else "--system"
    try:
        result = subprocess.run(
            ["dbus-send", flag, f"--dest={destination}",
             "--type=method_call", "--print-reply",
             path, "org.freedesktop.DBus.Introspectable.Introspect"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return {"error": result.stderr.strip()}

        # Extract XML from dbus-send output
        xml_start = result.stdout.find("<?xml")
        if xml_start == -1:
            xml_start = result.stdout.find("<node")
        if xml_start == -1:
            return {"error": "No XML in response", "raw": result.stdout[:500]}

        xml_text = result.stdout[xml_start:]
        # dbus-send wraps it in quotes, clean up
        xml_text = xml_text.strip().strip('"').replace('\\"', '"')

        root = ET.fromstring(xml_text)
        info = {"path": path, "interfaces": [], "child_nodes": []}

        for iface in root.findall("interface"):
            iface_info = {"name": iface.get("name"), "methods": [], "signals": [], "properties": []}

            for method in iface.findall("method"):
                args = []
                for arg in method.findall("arg"):
                    args.append({
                        "name": arg.get("name", ""),
                        "type": arg.get("type", ""),
                        "direction": arg.get("direction", ""),
                    })
                iface_info["methods"].append({"name": method.get("name"), "args": args})

            for signal in iface.findall("signal"):
                iface_info["signals"].append(signal.get("name"))

            for prop in iface.findall("property"):
                iface_info["properties"].append({
                    "name": prop.get("name"),
                    "type": prop.get("type"),
                    "access": prop.get("access"),
                })

            info["interfaces"].append(iface_info)

        for child in root.findall("node"):
            info["child_nodes"].append(child.get("name"))

        return info

    except FileNotFoundError:
        return {"error": "dbus-send not found"}
    except subprocess.TimeoutExpired:
        return {"error": "dbus-send timed out"}
    except ET.ParseError as e:
        return {"error": f"XML parse error: {e}"}


async def dbus_call(
    destination: str,
    path: str,
    method: str,
    args: str = "",
    bus: str = "session",
) -> dict:
    """Call a D-Bus method. Args should be dbus-send formatted (e.g. 'string:hello int32:42')."""
    flag = "--session" if bus == "session" else "--system"
    cmd = [
        "dbus-send", flag, f"--dest={destination}",
        "--type=method_call", "--print-reply",
        path, method,
    ]
    if args:
        cmd.extend(args.split())

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return {
            "stdout": result.stdout[:2000],
            "stderr": result.stderr[:500] if result.stderr else None,
            "exit_code": result.returncode,
        }
    except FileNotFoundError:
        return {"error": "dbus-send not found"}
    except subprocess.TimeoutExpired:
        return {"error": "dbus-send timed out"}


TOOLS = [
    Tool(
        name="dbus_list_services",
        description="List available D-Bus services on session or system bus",
        fn=dbus_list_services,
        parameters={"bus": "session|system (default: session)"},
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="dbus_introspect",
        description="Introspect a D-Bus object — show its interfaces, methods, signals, properties",
        fn=dbus_introspect,
        parameters={"destination": "string (e.g. org.freedesktop.Notifications)", "path": "string (default: /)", "bus": "session|system"},
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="dbus_call",
        description="Call a D-Bus method. Use dbus_introspect first to find available methods.",
        fn=dbus_call,
        parameters={"destination": "string", "path": "string", "method": "string", "args": "string (dbus-send format)", "bus": "session|system"},
        tier=Tier.DESTRUCTIVE,
    ),
]
