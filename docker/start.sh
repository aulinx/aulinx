#!/bin/bash
set -e

echo "=== Starting Aulinx Test Desktop ==="

# Create xstartup for VNC
mkdir -p ~/.vnc
cat > ~/.vnc/xstartup << 'XEOF'
#!/bin/bash
export XDG_CURRENT_DESKTOP=XFCE
export DISPLAY=:1
# Start D-Bus session
eval $(dbus-launch --sh-syntax)
export DBUS_SESSION_BUS_ADDRESS
# Start AT-SPI
/usr/libexec/at-spi2-registryd &
# Start Xfce
exec startxfce4
XEOF
chmod +x ~/.vnc/xstartup

# Set VNC password if not set
if [ ! -f ~/.vnc/passwd ]; then
    printf "aulinx\naulinx\nn\n" | vncpasswd 2>/dev/null || true
fi

# Start VNC server
export USER=aulinx
vncserver :1 -geometry 1920x1080 -depth 24 2>&1 || {
    echo "VNC failed, trying cleanup..."
    vncserver -kill :1 2>/dev/null || true
    rm -f /tmp/.X1-lock /tmp/.X11-unix/X1
    vncserver :1 -geometry 1920x1080 -depth 24 2>&1
}

echo "  VNC server started on :5901"

# Start noVNC (browser-based VNC client)
websockify --web=/usr/share/novnc/ 6080 localhost:5901 > /dev/null 2>&1 &

echo ""
echo "  ============================================"
echo "  Open http://localhost:6080/vnc.html"
echo "  VNC password: aulinx"
echo "  ============================================"
echo ""
echo "  Inside container, run:"
echo "    aulinx -m gemma3:12b --base-url http://host.docker.internal:11434"
echo ""
echo "=== Desktop Ready ==="

# Keep container alive
tail -f /dev/null
