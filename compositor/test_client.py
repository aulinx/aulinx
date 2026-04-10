#!/usr/bin/env python3
"""Test client for Aulinx compositor / semantic daemon.

Demos all IPC features: scene queries, input injection, window management,
and event subscriptions.

Usage:
    python3 test_client.py                    # Use default socket
    python3 test_client.py --no-inject        # Skip input injection
    AULINX_SOCKET=/tmp/test.sock python3 test_client.py
"""

import json
import os
import socket
import sys


def get_socket_path():
    if "AULINX_SOCKET" in os.environ:
        return os.environ["AULINX_SOCKET"]
    xdg = os.environ.get("XDG_RUNTIME_DIR", "")
    if xdg:
        return os.path.join(xdg, "aulinx", "semantic.sock")
    return "/tmp/aulinx-semantic.sock"


def send_request(sock, method, params=None, request_id=1):
    """Send a JSON-RPC request and return the response."""
    request = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": params or {},
    }
    line = json.dumps(request) + "\n"
    sock.sendall(line.encode())

    # Read response (newline-delimited)
    data = b""
    while b"\n" not in data:
        chunk = sock.recv(65536)
        if not chunk:
            break
        data += chunk

    response = json.loads(data.decode().strip())
    return response


def main():
    path = get_socket_path()
    print(f"Connecting to {path}...")

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(path)
    except FileNotFoundError:
        print(f"Socket not found: {path}")
        print("Make sure aulinx-semanticd is running.")
        sys.exit(1)

    print("Connected!\n")

    # 0. Status overview
    print("=== scene.status ===")
    resp = send_request(sock, "scene.status", request_id=0)
    if "result" in resp:
        s = resp["result"]
        print(f"  Compositor v{s.get('version')} ({s.get('backend')} backend)")
        print(f"  {s.get('window_count', 0)} windows, uptime {s.get('uptime_seconds', 0)}s")
        print(f"  Config: gap={s.get('config', {}).get('gap')} master_ratio={s.get('config', {}).get('master_ratio'):.1f}")

    # 1. Get all windows
    print("\n=== scene.windows ===")
    resp = send_request(sock, "scene.windows", request_id=1)
    if "result" in resp:
        windows = resp["result"]
        print(f"Found {len(windows)} windows:")
        for w in windows:
            print(f"  [{w.get('pid', '?')}] {w.get('app_id', '?')}: {w.get('title', '?')}")
    else:
        print(f"Error: {resp.get('error', resp)}")

    # 2. Get focused window
    print("\n=== scene.focused ===")
    resp = send_request(sock, "scene.focused", request_id=2)
    if "result" in resp:
        print(f"Focused: {resp['result']}")
    else:
        print(f"Error: {resp.get('error', resp)}")

    # 3. Find buttons
    print("\n=== scene.find('Close') ===")
    resp = send_request(sock, "scene.find", {"query": "Close"}, request_id=3)
    if "result" in resp:
        results = resp["result"]
        print(f"Found {len(results)} matches:")
        for r in results[:5]:
            print(f"  [{r.get('role', '?')}] {r.get('label', '?')}")
    else:
        print(f"Error: {resp.get('error', resp)}")

    # 4. Get full scene graph
    print("\n=== scene.graph (truncated) ===")
    resp = send_request(sock, "scene.graph", request_id=4)
    if "result" in resp:
        pretty = json.dumps(resp["result"], indent=2)
        # Show first 50 lines
        lines = pretty.split("\n")
        for line in lines[:50]:
            print(line)
        if len(lines) > 50:
            print(f"  ... ({len(lines) - 50} more lines)")
    else:
        print(f"Error: {resp.get('error', resp)}")

    # 5. Input injection
    inject = "--no-inject" not in sys.argv
    if inject and windows:
        print("\n=== Input Injection ===")

        print("  input.type 'hello aulinx'...")
        resp = send_request(sock, "input.type", {"text": "hello aulinx"}, request_id=10)
        status = "ok" if resp.get("result", {}).get("ok") else resp.get("error", {}).get("message", "?")
        print(f"  Result: {status}")

        print("  input.key 'ctrl+a' (select all)...")
        resp = send_request(sock, "input.key", {"combo": "ctrl+a"}, request_id=11)
        status = "ok" if resp.get("result", {}).get("ok") else resp.get("error", {}).get("message", "?")
        print(f"  Result: {status}")

    # 6. Window management
    if windows:
        wid = windows[0].get("id", 0)
        title = windows[0].get("title", "?")
        print(f"\n=== Window Management (id={wid}, title={title}) ===")

        print(f"  window.focus {wid}...")
        resp = send_request(sock, "window.focus", {"window_id": wid}, request_id=20)
        status = "ok" if resp.get("result", {}).get("ok") else resp.get("error", {}).get("message", "?")
        print(f"  Result: {status}")

        if "--close" in sys.argv:
            print(f"  window.close {wid}...")
            resp = send_request(sock, "window.close", {"window_id": wid}, request_id=21)
            status = "ok" if resp.get("result", {}).get("ok") else resp.get("error", {}).get("message", "?")
            print(f"  Result: {status}")

    # 7. Subscribe to events
    print("\n=== scene.subscribe('*') ===")
    resp = send_request(sock, "scene.subscribe", {"filter": "*"}, request_id=5)
    if "result" in resp:
        print(f"Subscribed: {resp['result']}")
        print("Listening for events (open/close windows to trigger, Ctrl+C to exit)...")

        # Listen for events
        try:
            sock.settimeout(10.0)
            while True:
                data = sock.recv(65536)
                if not data:
                    break
                for line in data.decode().strip().split("\n"):
                    event = json.loads(line)
                    print(f"  Event: {json.dumps(event, indent=2)}")
        except socket.timeout:
            print("  (no events received in 10s)")
        except KeyboardInterrupt:
            print("\n  (interrupted)")
    else:
        print(f"Error: {resp.get('error', resp)}")

    sock.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
