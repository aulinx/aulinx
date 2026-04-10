#!/bin/bash
# Aulinx Compositor Demo
#
# Launches the compositor with foot terminals and demonstrates AI agent integration.
#
# Usage:
#   ./demo.sh              # Start compositor + terminals
#   ./demo.sh --ipc-only   # Just run IPC demo against running compositor
#
# Requirements:
#   - Running Wayland session (GNOME, KDE, Sway)
#   - foot terminal installed
#   - Python 3.10+

set -e

COMPOSITOR="$(dirname "$0")/target/debug/aulinx-compositor"
IPC_SOCKET="${XDG_RUNTIME_DIR:-/tmp}/aulinx/semantic.sock"

# Colors
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

ipc_demo() {
    echo -e "${CYAN}=== Aulinx IPC Demo ===${NC}"
    echo ""

    python3 - <<'PYEOF'
import socket, json, time, base64, sys

def connect():
    import os
    path = os.environ.get("AULINX_SOCKET", "")
    if not path:
        xdg = os.environ.get("XDG_RUNTIME_DIR", "")
        path = os.path.join(xdg, "aulinx", "semantic.sock") if xdg else "/tmp/aulinx-semantic.sock"
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(3)
    s.connect(path)
    return s

def rpc(s, method, params={}, rid=1):
    req = json.dumps({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
    s.sendall((req + "\n").encode())
    time.sleep(0.3)
    return json.loads(s.recv(65536).decode().strip())

s = connect()

# 1. Discover available commands
print("\033[1;33m1. Discovering available commands...\033[0m")
cmds = rpc(s, "scene.list_commands").get("result", [])
print(f"   {len(cmds)} commands available")
print()

# 2. List windows
print("\033[1;33m2. Querying windows...\033[0m")
resp = rpc(s, "scene.windows", rid=2)
windows = resp.get("result", [])
for w in windows:
    g = w.get("geometry", {})
    print(f"   Window {w['id']}: {w.get('title', '?')} ({g.get('width')}x{g.get('height')} at {g.get('x')},{g.get('y')})")
print()

# 3. Query element at center
if windows:
    g = windows[0].get("geometry", {})
    cx, cy = g.get("x", 0) + g.get("width", 0) // 2, g.get("y", 0) + g.get("height", 0) // 2
    print(f"\033[1;33m3. What's at ({cx}, {cy})?\033[0m")
    r = rpc(s, "scene.element_at", {"x": cx, "y": cy}, 3)
    elem = r.get("result", {})
    print(f"   {elem.get('app_id', '?')}: {elem.get('title', '?')}")
    print()

# 4. Type text
if windows:
    print("\033[1;33m4. Typing 'Hello from Aulinx AI!' into focused window...\033[0m")
    r = rpc(s, "input.type", {"text": "Hello from Aulinx AI!"}, 4)
    print(f"   Result: {'ok' if r.get('result', {}).get('ok') else r}")
    time.sleep(0.5)
    print()

# 5. Key combo
print("\033[1;33m5. Sending Ctrl+A (select all)...\033[0m")
r = rpc(s, "input.key", {"combo": "ctrl+a"}, 5)
print(f"   Result: {'ok' if r.get('result', {}).get('ok') else r}")
print()

# 6. Screenshot
print("\033[1;33m6. Taking screenshot...\033[0m")
r = rpc(s, "scene.screenshot", rid=6)
if "result" in r:
    png = base64.b64decode(r["result"]["data"])
    with open("/tmp/aulinx_demo.png", "wb") as f:
        f.write(png)
    print(f"   Saved /tmp/aulinx_demo.png ({len(png)} bytes)")
print()

# 7. Subscribe and watch for events
print("\033[1;33m7. Subscribing to events (watching for 5s)...\033[0m")
rpc(s, "scene.subscribe", {"filter": "*"}, 7)
s.settimeout(5)
try:
    while True:
        data = s.recv(65536).decode().strip()
        for line in data.split("\n"):
            event = json.loads(line)
            params = event.get("params", {})
            print(f"   Event: {params.get('event', '?')} (window_id={params.get('window_id', '?')})")
except socket.timeout:
    print("   (no more events)")

s.close()
print()
print("\033[0;32mDemo complete!\033[0m")
PYEOF
}

if [ "$1" = "--ipc-only" ]; then
    ipc_demo
    exit 0
fi

# Build if needed
if [ ! -f "$COMPOSITOR" ]; then
    echo -e "${YELLOW}Building compositor...${NC}"
    cd "$(dirname "$0")"
    cargo build -p aulinx-compositor
fi

# Clean up any previous instance
killall -9 aulinx-compositor 2>/dev/null || true
rm -f "$IPC_SOCKET"
sleep 0.5

echo -e "${GREEN}Starting Aulinx Compositor...${NC}"
RUST_LOG=info "$COMPOSITOR" &
COMP_PID=$!
sleep 2

# Get the Wayland socket
SOCKET=$(grep -oP 'WAYLAND_DISPLAY=\K\S+' /tmp/compositor.log 2>/dev/null || echo "wayland-1")
echo -e "${GREEN}Wayland socket: ${SOCKET}${NC}"
echo -e "${GREEN}IPC socket: ${IPC_SOCKET}${NC}"
echo ""

# Launch terminals
echo -e "${YELLOW}Launching terminals...${NC}"
WAYLAND_DISPLAY="$SOCKET" foot &
sleep 1
WAYLAND_DISPLAY="$SOCKET" foot &
sleep 1

echo -e "${GREEN}Compositor running with 2 terminals${NC}"
echo -e "${YELLOW}Keyboard shortcuts:${NC}"
echo "  Super+Return    Open terminal"
echo "  Super+J/K       Focus next/prev window"
echo "  Super+1..9      Focus window by index"
echo "  Super+Space     Swap with master"
echo "  Super+Shift+Q   Close focused window"
echo "  Super+Escape    Quit compositor"
echo ""
echo -e "${CYAN}Running IPC demo...${NC}"
echo ""

ipc_demo

echo ""
echo -e "${GREEN}Compositor is still running. Press Super+Escape to quit.${NC}"
echo -e "${CYAN}Or connect an AI agent: python3 test_client.py${NC}"

wait $COMP_PID 2>/dev/null
