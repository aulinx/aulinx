#!/usr/bin/env python3
"""Aulinx AI Agent Demo — autonomous compositor control.

This script demonstrates an AI agent that:
1. Connects to the Aulinx compositor via IPC
2. Observes the desktop state
3. Performs actions autonomously (spawn apps, type text, manage windows)
4. Reacts to events in real-time

Usage:
    # Start the compositor first, then:
    python3 examples/ai_agent.py

    # Or with the demo script:
    ./demo.sh  # starts compositor + runs this
"""

import os
import sys
import time

# Add compositor dir to path for the client library
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from aulinx_compositor import AulinxCompositor, connect
except ImportError:
    print("Error: aulinx_compositor.py not found. Run from the compositor/ directory.")
    sys.exit(1)


def demo_observe(c: AulinxCompositor):
    """Phase 1: Observe the desktop."""
    print("\n\033[1;36m=== Phase 1: Observe ===\033[0m")

    status = c.status()
    print(f"  Compositor v{status['version']} ({status['backend']} backend)")
    print(f"  Uptime: {status['uptime_seconds']}s")
    print(f"  Windows: {status['window_count']}")
    print(f"  Config: gap={status['config']['gap']}, ratio={status['config']['master_ratio']:.1f}")

    # Natural language description
    desc = c.describe()
    print(f"\n  Desktop: {desc}")

    # AI suggestions
    suggestions = c._rpc("scene.suggest").get("suggestions", [])
    if suggestions:
        print("\n  AI suggests:")
        for s in suggestions:
            print(f"    -> {s['action']}: {s['reason']}")


def demo_spawn(c: AulinxCompositor):
    """Phase 2: Spawn applications."""
    print("\n\033[1;33m=== Phase 2: Spawn Applications ===\033[0m")

    # Spawn first terminal
    pid1 = c.spawn("foot")
    print(f"  Spawned foot terminal (pid={pid1})")
    time.sleep(2)

    # Spawn second terminal
    pid2 = c.spawn("foot")
    print(f"  Spawned foot terminal (pid={pid2})")
    time.sleep(2)

    # Check layout
    windows = c.windows()
    print(f"\n  Layout after spawning ({len(windows)} windows):")
    for w in windows:
        g = w.get("geometry", {})
        pos = "master" if g.get("x", 0) == 4 else "stack"
        print(f"    [{w['id']}] {w.get('title', '?')} — {pos} ({g.get('width')}x{g.get('height')})")


def demo_interact(c: AulinxCompositor):
    """Phase 3: Interact with windows."""
    print("\n\033[1;32m=== Phase 3: Interact ===\033[0m")

    windows = c.windows()
    if not windows:
        print("  No windows to interact with")
        return

    # Focus first window
    wid = windows[0]["id"]
    c.focus_window(wid)
    print(f"  Focused window {wid}")
    time.sleep(0.5)

    # Type text
    c.type_text("echo 'Hello from Aulinx AI Agent!'")
    print("  Typed: echo 'Hello from Aulinx AI Agent!'")
    time.sleep(0.5)

    # Send Enter
    c.key("return")
    print("  Pressed Enter")
    time.sleep(1)

    # Type another command
    c.type_text("uname -a")
    c.key("return")
    print("  Ran: uname -a")
    time.sleep(0.5)


def demo_layout(c: AulinxCompositor):
    """Phase 4: Window management."""
    print("\n\033[1;35m=== Phase 4: Window Management ===\033[0m")

    windows = c.windows()
    if len(windows) < 2:
        print("  Need at least 2 windows for layout demo")
        return

    # Swap second window to master
    wid = windows[1]["id"]
    c.swap_master(wid)
    print(f"  Swapped window {wid} to master position")
    time.sleep(1)

    # Verify new layout
    windows = c.windows()
    for w in windows:
        g = w.get("geometry", {})
        pos = "master" if g.get("x", 0) == 4 else "stack"
        print(f"    [{w['id']}] {pos} ({g.get('width')}x{g.get('height')})")


def demo_screenshot(c: AulinxCompositor):
    """Phase 5: Capture screenshots."""
    print("\n\033[1;34m=== Phase 5: Screenshots ===\033[0m")

    png = c.screenshot("/tmp/aulinx_ai_demo.png")
    print(f"  Plain: /tmp/aulinx_ai_demo.png ({len(png)} bytes)")

    annotated = c.annotated_screenshot("/tmp/aulinx_ai_annotated.png")
    print(f"  Annotated: /tmp/aulinx_ai_annotated.png ({len(annotated)} bytes)")

    # Describe what we see
    desc = c.describe()
    print(f"\n  Desktop state: {desc}")


def demo_events(c: AulinxCompositor):
    """Phase 6: Watch for events."""
    print("\n\033[1;31m=== Phase 6: Event Monitoring ===\033[0m")
    print("  Subscribing to events (5 second window)...")

    # Close a window to generate events
    windows = c.windows()
    if len(windows) >= 2:
        wid = windows[-1]["id"]
        print(f"  Closing window {wid}...")
        c.close_window(wid)
        time.sleep(1)

    # Check diff for events
    diff = c.diff()
    if diff:
        for event in diff:
            print(f"  Event: {event.get('event')} (window_id={event.get('window_id')})")
    else:
        print("  No events captured (they may have been consumed by subscription push)")


def demo_batch(c: AulinxCompositor):
    """Phase 7: Batch actions."""
    print("\n\033[1;33m=== Phase 7: Batch Actions ===\033[0m")

    result = c.batch([
        {"method": "input.type", "params": {"text": "# Batch demo"}},
        {"method": "input.key", "params": {"combo": "return"}},
        {"method": "sleep", "params": {"ms": 200}},
        {"method": "input.type", "params": {"text": "echo 'Atomic multi-step!'"}},
        {"method": "input.key", "params": {"combo": "return"}},
    ])
    print(f"  Executed {result.get('executed', 0)} actions atomically")


def main():
    print("\033[1m")
    print("  ╔══════════════════════════════════════╗")
    print("  ║  Aulinx AI Agent Demo                ║")
    print("  ║  Autonomous compositor control        ║")
    print("  ╚══════════════════════════════════════╝")
    print("\033[0m")

    try:
        c = connect()
    except Exception as e:
        print(f"\n  Error: {e}")
        print("  Start the compositor first: WAYLAND_DISPLAY=wayland-0 aulinx-compositor")
        sys.exit(1)

    try:
        demo_observe(c)
        demo_spawn(c)
        demo_interact(c)
        demo_layout(c)
        demo_screenshot(c)
        demo_batch(c)
        demo_events(c)

        print("\n\033[1;32m=== Demo Complete ===\033[0m")
        final_count = c.window_count()
        print(f"  Final state: {final_count} window(s)")
        print("  Compositor is still running — press Super+Escape to quit\n")

    except KeyboardInterrupt:
        print("\n  Interrupted")
    finally:
        c.close()


if __name__ == "__main__":
    main()
