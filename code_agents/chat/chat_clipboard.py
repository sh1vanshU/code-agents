"""Clipboard integration — image paste (Ctrl+V) and content paste (Cmd+V).

macOS:  osascript to read clipboard image as PNG, pbpaste for text.
Linux:  xclip -selection clipboard -t image/png, xclip -o for text.

Cmd+V is handled natively by the terminal (text paste).
Ctrl+V is intercepted by prompt_toolkit to read clipboard image.
"""

from __future__ import annotations

import base64
import logging
import os
import platform
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.chat.chat_clipboard")

# Pending image attachments for the next message
_pending_images: list[dict] = []


def get_pending_images() -> list[dict]:
    """Get and clear pending image attachments."""
    global _pending_images
    images = list(_pending_images)
    _pending_images.clear()
    return images


def has_pending_images() -> bool:
    """Check if there are pending image attachments."""
    return len(_pending_images) > 0


def read_clipboard_image() -> Optional[dict]:
    """Read image from system clipboard. Returns dict with base64 data or None.

    Returns:
        {"type": "image", "media_type": "image/png", "data": "<base64>", "size_bytes": int}
        or None if no image in clipboard.
    """
    system = platform.system()

    if system == "Darwin":
        return _read_clipboard_image_macos()
    elif system == "Linux":
        return _read_clipboard_image_linux()
    else:
        logger.debug("clipboard image not supported on %s", system)
        return None


def _read_clipboard_image_macos() -> Optional[dict]:
    """Read clipboard image on macOS using osascript."""
    try:
        # Check if clipboard has image data
        check = subprocess.run(
            ["osascript", "-e", 'clipboard info'],
            capture_output=True, text=True, timeout=3,
        )
        if "PNGf" not in check.stdout and "TIFF" not in check.stdout:
            logger.debug("clipboard has no image (info: %s)", check.stdout[:100])
            return None

        # Write clipboard image to temp file
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name

        # Use osascript to save clipboard image as PNG
        script = f'''
        set imgData to the clipboard as «class PNGf»
        set filePath to POSIX file "{tmp_path}"
        set fileRef to open for access filePath with write permission
        write imgData to fileRef
        close access fileRef
        '''
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=5,
        )

        if result.returncode != 0:
            logger.debug("osascript failed: %s", result.stderr[:200])
            _cleanup_tmp(tmp_path)
            return None

        return _file_to_image_dict(tmp_path)

    except (subprocess.TimeoutExpired, OSError) as e:
        logger.debug("clipboard image read failed: %s", e)
        return None


def _read_clipboard_image_linux() -> Optional[dict]:
    """Read clipboard image on Linux using xclip."""
    try:
        # Check available targets
        check = subprocess.run(
            ["xclip", "-selection", "clipboard", "-t", "TARGETS", "-o"],
            capture_output=True, text=True, timeout=3,
        )
        if "image/png" not in check.stdout:
            logger.debug("clipboard has no image/png")
            return None

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name

        result = subprocess.run(
            ["xclip", "-selection", "clipboard", "-t", "image/png", "-o"],
            capture_output=True, timeout=5,
        )
        if result.returncode != 0 or not result.stdout:
            _cleanup_tmp(tmp_path)
            return None

        with open(tmp_path, "wb") as f:
            f.write(result.stdout)

        return _file_to_image_dict(tmp_path)

    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        logger.debug("xclip failed: %s", e)
        return None


def read_image_file(path: str) -> Optional[dict]:
    """Read an image file and return base64 dict."""
    path = os.path.expanduser(path.strip())
    if not os.path.isfile(path):
        return None

    ext = Path(path).suffix.lower()
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    media_type = media_types.get(ext)
    if not media_type:
        return None

    return _file_to_image_dict(path, media_type=media_type, cleanup=False)


def _file_to_image_dict(
    path: str,
    media_type: str = "image/png",
    cleanup: bool = True,
) -> Optional[dict]:
    """Read file, convert to base64 image dict."""
    try:
        data = Path(path).read_bytes()
        if not data:
            return None
        size = len(data)
        b64 = base64.b64encode(data).decode("ascii")
        logger.info("clipboard image: %d bytes, %s", size, media_type)
        return {
            "type": "image",
            "media_type": media_type,
            "data": b64,
            "size_bytes": size,
        }
    except OSError as e:
        logger.debug("failed to read image file: %s", e)
        return None
    finally:
        if cleanup:
            _cleanup_tmp(path)


def _cleanup_tmp(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def add_pending_image(image: dict) -> int:
    """Add an image to the pending attachments. Returns count."""
    _pending_images.append(image)
    return len(_pending_images)


def build_multimodal_content(text: str, images: list[dict]) -> list[dict]:
    """Build OpenAI-compatible multimodal content array.

    Returns:
        [
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}},
            {"type": "text", "text": "user message"}
        ]
    """
    parts: list[dict] = []

    for img in images:
        data_url = f"data:{img['media_type']};base64,{img['data']}"
        parts.append({
            "type": "image_url",
            "image_url": {"url": data_url},
        })

    if text:
        parts.append({"type": "text", "text": text})

    return parts
