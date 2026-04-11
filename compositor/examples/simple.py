#!/usr/bin/env python3
"""Minimal Aulinx compositor example — 10 lines to control your desktop."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from aulinx_compositor import connect

with connect() as c:
    print(c.describe())       # What's on screen
    print(c.ascii())          # Visual layout
    for s in c._rpc("scene.suggest").get("suggestions", []):
        print(f"  Suggestion: {s['reason']}")
