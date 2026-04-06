#!/bin/bash
set -e

echo "=== Starting Aulinx Test Desktop ==="

# Start D-Bus
eval $(dbus-launch --sh-syntax)
export DBUS_SESSION_BUS_ADDRESS

# Start AT-SPI registry
/usr/libexec/at-spi2-registryd &
sleep 1

# Start VNC server (Xfce desktop on :1)
vncserver :1 \
    -geometry 1920x1080 \
    -depth 24 \
    -SecurityTypes VncAuth \
    -xstartup /usr/bin/startxfce4 \
    2>/dev/null

echo "  VNC server on :5901"

# Start noVNC (browser access)
/usr/share/novnc/utils/novnc_proxy \
    --vnc localhost:5901 \
    --listen 6080 \
    > /dev/null 2>&1 &

echo "  noVNC on http://localhost:6080"
echo ""
echo "  Open http://localhost:6080 in your browser"
echo "  VNC password: aulinx"
echo ""
echo "  To run aulinx inside the container:"
echo "    aulinx -m gemma3:12b --base-url http://host.docker.internal:11434"
echo ""
echo "  Or start the WebSocket server:"
echo "    aulinx --serve -m gemma3:12b --base-url http://host.docker.internal:11434"
echo ""
echo "=== Desktop Ready ==="

# Keep container running
tail -f /dev/null
