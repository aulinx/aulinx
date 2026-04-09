#!/usr/bin/env python3
"""Test client for aulinx-semanticd.

Connects to the semantic IPC socket and runs some queries.

Usage:
    python3 test_client.py                    # Use default socket
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

    # 1. Get all windows
    print("=== scene.windows ===")
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

    # 5. Subscribe to events
    print("\n=== scene.subscribe('window.*') ===")
    resp = send_request(sock, "scene.subscribe", {"filter": "window.*"}, request_id=5)
    if "result" in resp:
        print(f"Subscribed: {resp['result']}")
        print("(Open/close a window to see events, or Ctrl+C to exit)")

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
