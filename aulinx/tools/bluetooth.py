"""Bluetooth tools — scan, pair, connect via bluetoothctl."""

import subprocess
from aulinx.tools.registry import Tool, Tier


def _bluetoothctl(*args: str, timeout: int = 10) -> dict:
    """Run bluetoothctl command."""
    try:
        result = subprocess.run(
            ["bluetoothctl", *args],
            capture_output=True, text=True, timeout=timeout,
        )
        return {"stdout": result.stdout.strip(), "returncode": result.returncode, "stderr": result.stderr.strip()}
    except FileNotFoundError:
        return {"error": "bluetoothctl not found (install bluez-utils)"}
    except subprocess.TimeoutExpired:
        return {"error": "bluetoothctl timed out"}


async def bluetooth_status() -> dict:
    """Get Bluetooth adapter status and paired devices."""
    info = {}

    # Adapter info
    r = _bluetoothctl("show")
    if "error" in r:
        return r
    for line in r["stdout"].splitlines():
        line = line.strip()
        if line.startswith("Powered:"):
            info["powered"] = "yes" in line.lower()
        elif line.startswith("Discoverable:"):
            info["discoverable"] = "yes" in line.lower()
        elif line.startswith("Name:"):
            info["adapter_name"] = line.split(":", 1)[1].strip()

    # Paired devices
    r = _bluetoothctl("devices", "Paired")
    devices = []
    for line in r.get("stdout", "").splitlines():
        # "Device AA:BB:CC:DD:EE:FF Device Name"
        parts = line.strip().split(None, 2)
        if len(parts) >= 3 and parts[0] == "Device":
            devices.append({"address": parts[1], "name": parts[2]})
    info["paired_devices"] = devices

    # Connected devices
    r = _bluetoothctl("devices", "Connected")
    connected = []
    for line in r.get("stdout", "").splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) >= 3 and parts[0] == "Device":
            connected.append({"address": parts[1], "name": parts[2]})
    info["connected_devices"] = connected

    return info


async def bluetooth_scan(timeout: int = 10) -> list[dict]:
    """Scan for nearby Bluetooth devices."""
    # Start scan
    _bluetoothctl("--timeout", str(timeout), "scan", "on", timeout=timeout + 5)

    # List found devices
    r = _bluetoothctl("devices")
    if "error" in r:
        return [r]

    devices = []
    for line in r.get("stdout", "").splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) >= 3 and parts[0] == "Device":
            devices.append({"address": parts[1], "name": parts[2]})

    return devices


async def bluetooth_connect(address: str) -> dict:
    """Connect to a Bluetooth device by MAC address."""
    r = _bluetoothctl("connect", address, timeout=15)
    if "error" in r:
        return r
    if "Connection successful" in r.get("stdout", ""):
        return {"connected": True, "address": address}
    return {"connected": False, "output": r.get("stdout", "")[:200]}


async def bluetooth_disconnect(address: str) -> dict:
    """Disconnect a Bluetooth device."""
    r = _bluetoothctl("disconnect", address)
    if "error" in r:
        return r
    if "Successful" in r.get("stdout", ""):
        return {"disconnected": True, "address": address}
    return {"disconnected": False, "output": r.get("stdout", "")[:200]}


async def bluetooth_toggle(on: bool = True) -> dict:
    """Turn Bluetooth on or off."""
    action = "power" + (" on" if on else " off")
    r = _bluetoothctl("power", "on" if on else "off")
    if "error" in r:
        return r
    success = "succeeded" in r.get("stdout", "").lower() or "yes" in r.get("stdout", "").lower()
    return {"bluetooth": "on" if on else "off", "success": success}


TOOLS = [
    Tool(
        name="bluetooth_status",
        description="Get Bluetooth status — adapter power, paired devices, connected devices",
        fn=bluetooth_status,
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="bluetooth_scan",
        description="Scan for nearby Bluetooth devices (takes ~10 seconds)",
        fn=bluetooth_scan,
        parameters={"timeout": "int seconds (default 10)"},
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="bluetooth_connect",
        description="Connect to a Bluetooth device by MAC address. Use bluetooth_status to see paired devices.",
        fn=bluetooth_connect,
        parameters={"address": "string (MAC address, e.g. AA:BB:CC:DD:EE:FF)"},
        tier=Tier.MUTATE,
    ),
    Tool(
        name="bluetooth_disconnect",
        description="Disconnect a Bluetooth device",
        fn=bluetooth_disconnect,
        parameters={"address": "string (MAC address)"},
        tier=Tier.MUTATE,
    ),
    Tool(
        name="bluetooth_toggle",
        description="Turn Bluetooth on or off",
        fn=bluetooth_toggle,
        parameters={"on": "bool (true=on, false=off)"},
        tier=Tier.MUTATE,
    ),
]
