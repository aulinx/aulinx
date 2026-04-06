FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=en_US.UTF-8
ENV DISPLAY=:1

# Core system + desktop
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Desktop environment
    xfce4 xfce4-terminal xfce4-goodies dbus-x11 \
    # VNC + noVNC
    tigervnc-standalone-server tigervnc-common \
    novnc websockify \
    # AT-SPI accessibility
    at-spi2-core libatk-adaptor python3-pyatspi \
    # Common Linux desktop apps for testing
    gedit nautilus firefox eog evince \
    # System tools aulinx needs
    procps psmisc net-tools iproute2 \
    systemd-sysv \
    network-manager \
    pulseaudio \
    brightnessctl \
    xdg-utils \
    notify-osd libnotify-bin \
    # Build tools
    python3 python3-pip python3-venv python3-gi \
    git curl wget sudo \
    # Misc
    locales fonts-noto-color-emoji \
    && locale-gen en_US.UTF-8 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Create test user
RUN useradd -m -s /bin/bash -G sudo aulinx \
    && echo "aulinx:aulinx" | chpasswd \
    && echo "aulinx ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# VNC setup
RUN mkdir -p /home/aulinx/.vnc \
    && echo "aulinx" | vncpasswd -f > /home/aulinx/.vnc/passwd \
    && chmod 600 /home/aulinx/.vnc/passwd \
    && chown -R aulinx:aulinx /home/aulinx/.vnc

# Install aulinx
COPY . /opt/aulinx
RUN cd /opt/aulinx && pip3 install --break-system-packages -e . 2>/dev/null || pip3 install -e .

# Startup script
COPY docker/start.sh /start.sh
RUN chmod +x /start.sh

USER aulinx
WORKDIR /home/aulinx

EXPOSE 5901 6080 8765

CMD ["/start.sh"]
