"""Disk and USB tools — list drives, mount, unmount, eject."""

import subprocess

from aulinx.tools.base import Tier, Tool


async def disk_list_drives() -> list[dict]:
    """List all block devices (drives, USB sticks, partitions)."""
    try:
        result = subprocess.run(
            ["lsblk", "-J", "-o", "NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE,MODEL,TRAN"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            import json
            data = json.loads(result.stdout)
            devices = []
            for dev in data.get("blockdevices", []):
                devices.append({
                    "name": f"/dev/{dev['name']}",
                    "size": dev.get("size", ""),
                    "type": dev.get("type", ""),
                    "mount": dev.get("mountpoint", ""),
                    "filesystem": dev.get("fstype", ""),
                    "model": dev.get("model", ""),
                    "transport": dev.get("tran", ""),  # usb, sata, nvme
                })
                for child in dev.get("children", []):
                    devices.append({
                        "name": f"/dev/{child['name']}",
                        "size": child.get("size", ""),
                        "type": child.get("type", ""),
                        "mount": child.get("mountpoint", ""),
                        "filesystem": child.get("fstype", ""),
                    })
            return devices
        return [{"error": result.stderr.strip()}]
    except FileNotFoundError:
        return [{"error": "lsblk not found"}]


async def disk_mount(device: str, mountpoint: str = "") -> dict:
    """Mount a partition. If no mountpoint given, uses /media/$USER/device-name."""
    if not mountpoint:
        import os
        user = os.environ.get("USER", "user")
        dev_name = device.split("/")[-1]
        mountpoint = f"/media/{user}/{dev_name}"

    try:
        # Use udisksctl for user-level mount (no sudo needed)
        result = subprocess.run(
            ["udisksctl", "mount", "-b", device],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            return {"mounted": True, "device": device, "output": result.stdout.strip()}
        return {"error": result.stderr.strip()}
    except FileNotFoundError:
        # Fallback to mount (needs sudo)
        return {"error": "udisksctl not found. Use: sudo mount {device} {mountpoint}"}


async def disk_unmount(device: str) -> dict:
    """Unmount a partition."""
    try:
        result = subprocess.run(
            ["udisksctl", "unmount", "-b", device],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return {"unmounted": True, "device": device}
        return {"error": result.stderr.strip()}
    except FileNotFoundError:
        return {"error": "udisksctl not found"}


async def disk_eject(device: str) -> dict:
    """Safely eject a removable device (USB drive, etc.)."""
    # Unmount first
    await disk_unmount(device)

    try:
        result = subprocess.run(
            ["udisksctl", "power-off", "-b", device],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return {"ejected": True, "device": device}
        return {"error": result.stderr.strip()}
    except FileNotFoundError:
        return {"error": "udisksctl not found"}


TOOLS = [
    Tool(
        name="disk_list_drives",
        description="List all drives, USB sticks, and partitions with size, filesystem, and mount status",
        fn=disk_list_drives,
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="disk_mount",
        description="Mount a partition (e.g. USB drive). Uses udisksctl (no sudo needed).",
        fn=disk_mount,
        parameters={
            "device": "string (e.g. '/dev/sdb1')",
            "mountpoint": "string (optional, auto-generated if empty)",
        },
        tier=Tier.MUTATE,
    ),
    Tool(
        name="disk_unmount",
        description="Unmount a mounted partition",
        fn=disk_unmount,
        parameters={"device": "string (e.g. '/dev/sdb1')"},
        tier=Tier.MUTATE,
    ),
    Tool(
        name="disk_eject",
        description="Safely eject a removable device (USB drive). Unmounts and powers off.",
        fn=disk_eject,
        parameters={"device": "string (e.g. '/dev/sdb')"},
        tier=Tier.DESTRUCTIVE,
    ),
]
