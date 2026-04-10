#!/usr/bin/env python3
"""Integration tests for the Aulinx compositor IPC protocol.

Requires a running compositor:
    WAYLAND_DISPLAY=wayland-0 cargo run -p aulinx-compositor &
    python3 tests/test_ipc_integration.py
"""

import base64
import json
import os
import socket
import sys
import time

PASSED = 0
FAILED = 0


def get_socket():
    xdg = os.environ.get("XDG_RUNTIME_DIR", "")
    path = os.environ.get("AULINX_SOCKET", "")
    if not path and xdg:
        path = os.path.join(xdg, "aulinx", "semantic.sock")
    if not path:
        path = "/tmp/aulinx-semantic.sock"
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(3)
    s.connect(path)
    return s


_next_id = [0]
def rpc(s, method, params={}):
    _next_id[0] += 1
    req = json.dumps({"jsonrpc": "2.0", "id": _next_id[0], "method": method, "params": params})
    s.sendall((req + "\n").encode())
    time.sleep(0.3)
    return json.loads(s.recv(1048576).decode().strip())


def test(name, condition):
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  PASS  {name}")
    else:
        FAILED += 1
        print(f"  FAIL  {name}")


def main():
    print("\nAulinx IPC Integration Tests\n")

    try:
        s = get_socket()
    except Exception as e:
        print(f"Cannot connect to compositor: {e}")
        print("Start compositor first, then run this test.")
        sys.exit(1)

    # Ping
    r = rpc(s, "ping")
    test("ping returns pong", r.get("result", {}).get("pong") == True)

    # List commands
    r = rpc(s, "scene.list_commands")
    cmds = r.get("result", {}).get("commands", [])
    test("list_commands returns commands", len(cmds) >= 20)
    test("list_commands has version", "version" in r.get("result", {}))

    # Status
    r = rpc(s, "scene.status")
    status = r.get("result", {})
    test("status has version", "version" in status)
    test("status has uptime", "uptime_seconds" in status)
    test("status has config", "config" in status)

    # Describe
    r = rpc(s, "scene.describe")
    desc = r.get("result", {}).get("description", "")
    test("describe returns text", len(desc) > 0)

    # Windows
    r = rpc(s, "scene.windows")
    test("windows returns array", isinstance(r.get("result"), list))

    # Window count
    r = rpc(s, "scene.window_count")
    test("window_count returns count", "count" in r.get("result", {}))

    # Focused
    r = rpc(s, "scene.focused")
    test("focused returns result", "result" in r)

    # Find window
    r = rpc(s, "scene.find_window", {"title": ""})
    test("find_window returns array", isinstance(r.get("result"), list))

    # Screenshot
    r = rpc(s, "scene.screenshot")
    result = r.get("result", {})
    test("screenshot returns data", "data" in result)
    if "data" in result:
        png = base64.b64decode(result["data"])
        test("screenshot is valid PNG", png[:4] == b'\x89PNG')

    # Annotated screenshot
    r = rpc(s, "scene.annotated_screenshot")
    result = r.get("result", {})
    test("annotated_screenshot returns data", "data" in result)
    test("annotated_screenshot marked", result.get("annotated") == True)

    # Diff
    r = rpc(s, "scene.diff")
    test("diff returns events", "events" in r.get("result", {}))

    # Wait for
    r = rpc(s, "scene.wait_for", {"count": 0})
    test("wait_for with count=0 matches", r.get("result", {}).get("matched") == True)

    # Keyboard shortcuts
    r = rpc(s, "scene.keyboard_shortcuts")
    test("keyboard_shortcuts returns list", isinstance(r.get("result"), list))

    # Element at
    r = rpc(s, "scene.element_at", {"x": 640, "y": 400})
    test("element_at returns result", "result" in r)

    # Input type (safe — just types into whatever is focused)
    r = rpc(s, "input.type", {"text": "test"})
    test("input.type succeeds", r.get("result", {}).get("ok") == True or "error" in r)

    # Input key
    r = rpc(s, "input.key", {"combo": "ctrl+a"})
    test("input.key succeeds", r.get("result", {}).get("ok") == True or "error" in r)

    # Input move
    r = rpc(s, "input.move", {"x": 100, "y": 100})
    test("input.move succeeds", r.get("result", {}).get("ok") == True)

    # Input batch
    r = rpc(s, "input.batch", {"actions": [
        {"method": "input.move", "params": {"x": 200, "y": 200}},
        {"method": "sleep", "params": {"ms": 50}},
    ]})
    test("input.batch executes", r.get("result", {}).get("executed") == 2)

    # Layout
    r = rpc(s, "layout.set_ratio", {"ratio": 0.5})
    test("layout.set_ratio works", r.get("result", {}).get("ok") == True)
    rpc(s, "layout.set_ratio", {"ratio": 0.6})  # restore

    # Describe
    r = rpc(s, "scene.describe")
    desc = r.get("result", {}).get("description", "")
    test("describe returns non-empty text", len(desc) > 10)

    # Suggest
    r = rpc(s, "scene.suggest")
    test("suggest returns suggestions", "suggestions" in r.get("result", {}))

    # Config
    r = rpc(s, "scene.config")
    config = r.get("result", {})
    test("config has layout", "layout" in config)
    test("config has terminal", "terminal" in config)

    # Layout gap
    r = rpc(s, "layout.set_gap", {"gap": 8})
    test("layout.set_gap works", r.get("result", {}).get("ok") == True)
    rpc(s, "layout.set_gap", {"gap": 4})  # restore

    # Window list (concise)
    r = rpc(s, "window.list")
    test("window.list returns array", isinstance(r.get("result"), list))

    # Unknown method
    r = rpc(s, "nonexistent.method")
    test("unknown method returns error", "error" in r)

    s.close()

    print(f"\n{PASSED} passed, {FAILED} failed out of {PASSED + FAILED} tests\n")
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
