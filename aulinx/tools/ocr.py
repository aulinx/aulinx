"""OCR tools — extract text from screenshots for apps without AT-SPI support."""

import subprocess
import tempfile
import time
from pathlib import Path

from aulinx.tools.base import Tier, Tool


async def screenshot_ocr(region: str = "") -> dict:
    """Take a screenshot and extract text via OCR. For reading canvas-rendered apps.

    region: optional "x,y,width,height" to capture a specific area.
    """
    # Step 1: Take screenshot
    screenshot_path = Path(tempfile.gettempdir()) / f"aulinx-ocr-{int(time.time())}.png"

    screenshot_taken = False
    for cmd in [
        ["grim", str(screenshot_path)],
        ["gnome-screenshot", "-f", str(screenshot_path)],
        ["scrot", str(screenshot_path)],
        ["import", "-window", "root", str(screenshot_path)],
    ]:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and screenshot_path.exists():
                screenshot_taken = True
                break
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    if not screenshot_taken:
        return {"error": "No screenshot tool available (install grim, gnome-screenshot, or scrot)"}

    # Step 2: Crop if region specified
    if region:
        try:
            parts = region.split(",")
            if len(parts) == 4:
                x, y, w, h = [int(p.strip()) for p in parts]
                cropped = screenshot_path.with_suffix(".crop.png")
                result = subprocess.run(
                    ["convert", str(screenshot_path), "-crop", f"{w}x{h}+{x}+{y}", str(cropped)],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0 and cropped.exists():
                    screenshot_path = cropped
        except (ValueError, FileNotFoundError):
            pass  # proceed with full screenshot

    # Step 3: Run OCR
    ocr_text = None

    # Try tesseract
    try:
        result = subprocess.run(
            ["tesseract", str(screenshot_path), "stdout", "--psm", "3"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            ocr_text = result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    if ocr_text is None:
        # Cleanup
        screenshot_path.unlink(missing_ok=True)
        return {"error": "OCR failed. Install tesseract: apt install tesseract-ocr"}

    # Cleanup
    screenshot_path.unlink(missing_ok=True)

    return {
        "text": ocr_text,
        "characters": len(ocr_text),
        "lines": len(ocr_text.splitlines()),
    }


async def image_ocr(path: str) -> dict:
    """Extract text from an image file via OCR."""
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        return {"error": f"File not found: {path}"}

    try:
        result = subprocess.run(
            ["tesseract", str(p), "stdout", "--psm", "3"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            text = result.stdout.strip()
            return {
                "text": text,
                "characters": len(text),
                "lines": len(text.splitlines()),
                "source": str(p),
            }
        return {"error": result.stderr.strip() or "OCR failed"}
    except FileNotFoundError:
        return {"error": "tesseract not found. Install: apt install tesseract-ocr"}
    except subprocess.TimeoutExpired:
        return {"error": "OCR timed out"}


TOOLS = [
    Tool(
        name="screenshot_ocr",
        description="Take a screenshot and extract text via OCR. Use for canvas-rendered apps where AT-SPI doesn't work.",
        fn=screenshot_ocr,
        parameters={"region": "string (optional: x,y,width,height to crop)"},
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="image_ocr",
        description="Extract text from an image file via OCR (tesseract)",
        fn=image_ocr,
        parameters={"path": "string (path to image file)"},
        tier=Tier.OBSERVE,
    ),
]
