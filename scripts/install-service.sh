#!/bin/bash
# Install Aulinx as a systemd user service
set -e

SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_FILE="$SERVICE_DIR/aulinx.service"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Installing Aulinx systemd service..."

# Create service directory
mkdir -p "$SERVICE_DIR"

# Copy service file
cp "$SCRIPT_DIR/aulinx.service" "$SERVICE_FILE"

# Ensure ydotoold can be started
if command -v ydotoold &>/dev/null; then
    echo "  ydotoold found"
else
    echo "  WARNING: ydotoold not found. Install: sudo apt install ydotool"
fi

# Ensure aulinx is in PATH
if command -v aulinx &>/dev/null; then
    echo "  aulinx found at $(which aulinx)"
else
    echo "  WARNING: aulinx not in PATH. Run: pip install aulinx"
fi

# Reload systemd and enable
systemctl --user daemon-reload
systemctl --user enable aulinx.service

echo ""
echo "Installed! Commands:"
echo "  systemctl --user start aulinx    # start now"
echo "  systemctl --user stop aulinx     # stop"
echo "  systemctl --user status aulinx   # check status"
echo "  journalctl --user -u aulinx -f   # view logs"
echo ""
echo "Aulinx will auto-start on next login."
