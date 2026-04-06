"""Network tools — status, wifi, connections via nmcli (NetworkManager)."""

import subprocess

from aulinx.tools.base import Tier, Tool


def _nmcli(*args: str, timeout: int = 10) -> dict:
    """Run nmcli and return parsed output."""
    try:
        result = subprocess.run(
            ["nmcli", *args],
            capture_output=True, text=True, timeout=timeout,
        )
        return {"stdout": result.stdout.strip(), "returncode": result.returncode, "stderr": result.stderr.strip()}
    except FileNotFoundError:
        return {"error": "nmcli not found (install NetworkManager)"}
    except subprocess.TimeoutExpired:
        return {"error": "nmcli timed out"}


async def network_status() -> dict:
    """Get current network status — connectivity, active connections, IP addresses."""
    info = {}

    # Overall connectivity
    r = _nmcli("general", "status", "-t")
    if "error" in r:
        return r
    for line in r["stdout"].splitlines():
        parts = line.split(":")
        if len(parts) >= 4:
            info["state"] = parts[0]
            info["connectivity"] = parts[1]
            info["wifi_hw"] = parts[2]
            info["wifi"] = parts[3]

    # Active connections
    r = _nmcli("connection", "show", "--active", "-t", "-f", "NAME,TYPE,DEVICE")
    connections = []
    for line in r.get("stdout", "").splitlines():
        parts = line.split(":")
        if len(parts) >= 3:
            connections.append({"name": parts[0], "type": parts[1], "device": parts[2]})
    info["active_connections"] = connections

    # IP addresses
    r = _nmcli("device", "show", "-t", "-f", "DEVICE,IP4.ADDRESS,IP6.ADDRESS")
    ips = {}
    for line in r.get("stdout", "").splitlines():
        parts = line.split(":", 1)
        if len(parts) == 2 and parts[1]:
            key, val = parts
            device = key.split(".")[0] if "." in key else key
            if device not in ips:
                ips[device] = {}
            if "IP4" in key:
                ips[device]["ipv4"] = val
            elif "IP6" in key:
                ips[device]["ipv6"] = val
    info["devices"] = ips

    return info


async def wifi_list() -> list[dict]:
    """Scan for available WiFi networks."""
    # Trigger a rescan first
    _nmcli("device", "wifi", "rescan", timeout=15)

    r = _nmcli("device", "wifi", "list", "-t", "-f", "SSID,SIGNAL,SECURITY,IN-USE")
    if "error" in r:
        return [r]

    networks = []
    seen = set()
    for line in r.get("stdout", "").splitlines():
        parts = line.split(":")
        if len(parts) >= 3:
            ssid = parts[0]
            if not ssid or ssid in seen:
                continue
            seen.add(ssid)
            networks.append({
                "ssid": ssid,
                "signal": int(parts[1]) if parts[1].isdigit() else 0,
                "security": parts[2] if len(parts) > 2 else "",
                "connected": parts[3] == "*" if len(parts) > 3 else False,
            })

    return sorted(networks, key=lambda n: n["signal"], reverse=True)


async def wifi_connect(ssid: str, password: str = "") -> dict:
    """Connect to a WiFi network."""
    args = ["device", "wifi", "connect", ssid]
    if password:
        args.extend(["password", password])

    r = _nmcli(*args, timeout=30)
    if "error" in r:
        return r
    if r["returncode"] == 0:
        return {"connected": True, "ssid": ssid}
    return {"connected": False, "error": r["stderr"] or r["stdout"]}


async def wifi_disconnect() -> dict:
    """Disconnect from the current WiFi network."""
    r = _nmcli("device", "disconnect", "wlan0")
    if "error" in r:
        # Try common interface names
        for iface in ("wlp0s20f3", "wlp2s0", "wifi0"):
            r = _nmcli("device", "disconnect", iface)
            if r.get("returncode") == 0:
                return {"disconnected": True, "interface": iface}
    if r.get("returncode") == 0:
        return {"disconnected": True}
    return {"error": r.get("stderr") or r.get("stdout") or "Failed to disconnect"}


TOOLS = [
    Tool(
        name="network_status",
        description="Get current network status — connectivity, active connections, IP addresses",
        fn=network_status,
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="wifi_list",
        description="Scan and list available WiFi networks with signal strength",
        fn=wifi_list,
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="wifi_connect",
        description="Connect to a WiFi network by SSID (password optional for open networks)",
        fn=wifi_connect,
        parameters={"ssid": "string", "password": "string (optional)"},
        tier=Tier.MUTATE,
    ),
    Tool(
        name="wifi_disconnect",
        description="Disconnect from the current WiFi network",
        fn=wifi_disconnect,
        tier=Tier.DESTRUCTIVE,
    ),
]
