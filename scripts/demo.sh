#!/bin/bash
# Aulinx Demo Script
# Run this inside the Docker container or on a real Linux desktop.
# Record with: asciinema rec demo.cast
# Convert to GIF: agg demo.cast demo.gif

set -e

MODEL="qwen2.5:14b"
BASE_URL="http://host.docker.internal:11434"
export DISPLAY=:1

echo ""
echo "=== Aulinx Demo ==="
echo "Make sure Ollama is running and gedit is open."
echo ""

# Function to send a command and wait
demo_cmd() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Demo: $1"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    aulinx -m "$MODEL" --base-url "$BASE_URL" -c "$1"
    echo ""
    sleep 2
}

# Demo sequence — each shows a different capability
demo_cmd "who am I?"
demo_cmd "what time is it?"
demo_cmd "what windows are open?"
demo_cmd "what's using the most CPU?"
demo_cmd "how much disk space do I have?"
demo_cmd "find all buttons in gedit"
demo_cmd "list files in /home/aulinx"
demo_cmd "show git log for /opt/aulinx"

echo ""
echo "=== Demo Complete ==="
echo ""
