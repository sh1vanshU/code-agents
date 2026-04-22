"""Tests for chat_clipboard.py — clipboard image reading, pending images, multimodal content."""

from __future__ import annotations

import base64
import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest


class TestGetPendingImages:
    """Test get_pending_images and has_pending_images."""

    def setup_method(self):
        from code_agents.chat import chat_clipboard
        chat_clipboard._pending_images.clear()

    def test_empty(self):
        from code_agents.chat.chat_clipboard import get_pending_images, has_pending_images
        assert not has_pending_images()
        assert get_pending_images() == []

    def test_with_images(self):
        from code_agents.chat.chat_clipboard import (
            get_pending_images, has_pending_images, add_pending_image,
        )
        img = {"type": "image", "media_type": "image/png", "data": "abc", "size_bytes": 3}
        add_pending_image(img)
        assert has_pending_images()
        result = get_pending_images()
        assert len(result) == 1
        assert result[0] == img
        # After get, should be cleared
        assert not has_pending_images()

    def test_add_returns_count(self):
        from code_agents.chat.chat_clipboard import add_pending_image
        img = {"type": "image"}
        assert add_pending_image(img) == 1
        assert add_pending_image(img) == 2


class TestReadClipboardImage:
    """Test read_clipboard_image dispatches by platform."""

    @patch("code_agents.chat.chat_clipboard.platform")
    @patch("code_agents.chat.chat_clipboard._read_clipboard_image_macos")
    def test_darwin(self, mock_macos, mock_platform):
        from code_agents.chat.chat_clipboard import read_clipboard_image
        mock_platform.system.return_value = "Darwin"
        mock_macos.return_value = {"type": "image"}
        assert read_clipboard_image() == {"type": "image"}
        mock_macos.assert_called_once()

    @patch("code_agents.chat.chat_clipboard.platform")
    @patch("code_agents.chat.chat_clipboard._read_clipboard_image_linux")
    def test_linux(self, mock_linux, mock_platform):
        from code_agents.chat.chat_clipboard import read_clipboard_image
        mock_platform.system.return_value = "Linux"
        mock_linux.return_value = {"type": "image"}
        assert read_clipboard_image() == {"type": "image"}
        mock_linux.assert_called_once()

    @patch("code_agents.chat.chat_clipboard.platform")
    def test_unsupported(self, mock_platform):
        from code_agents.chat.chat_clipboard import read_clipboard_image
        mock_platform.system.return_value = "Windows"
        assert read_clipboard_image() is None


class TestReadClipboardImageMacOS:
    """Test _read_clipboard_image_macos."""

    @patch("code_agents.chat.chat_clipboard.subprocess")
    @patch("code_agents.chat.chat_clipboard._file_to_image_dict")
    def test_success_pngf(self, mock_file_dict, mock_subprocess):
        from code_agents.chat.chat_clipboard import _read_clipboard_image_macos
        # Check returns PNGf
        check_result = MagicMock()
        check_result.stdout = "«class PNGf»"
        # Write returns success
        write_result = MagicMock()
        write_result.returncode = 0
        mock_subprocess.run.side_effect = [check_result, write_result]
        mock_file_dict.return_value = {"type": "image", "data": "abc"}

        result = _read_clipboard_image_macos()
        assert result == {"type": "image", "data": "abc"}

    @patch("code_agents.chat.chat_clipboard.subprocess")
    def test_no_image_in_clipboard(self, mock_subprocess):
        from code_agents.chat.chat_clipboard import _read_clipboard_image_macos
        check_result = MagicMock()
        check_result.stdout = "«class utf8»"
        mock_subprocess.run.return_value = check_result
        assert _read_clipboard_image_macos() is None

    @patch("code_agents.chat.chat_clipboard._cleanup_tmp")
    @patch("code_agents.chat.chat_clipboard.subprocess")
    def test_osascript_fails(self, mock_subprocess, mock_cleanup):
        from code_agents.chat.chat_clipboard import _read_clipboard_image_macos
        check_result = MagicMock()
        check_result.stdout = "PNGf"
        write_result = MagicMock()
        write_result.returncode = 1
        write_result.stderr = "some error"
        mock_subprocess.run.side_effect = [check_result, write_result]

        assert _read_clipboard_image_macos() is None
        mock_cleanup.assert_called_once()

    @patch("code_agents.chat.chat_clipboard.subprocess.run")
    def test_timeout(self, mock_run):
        import subprocess
        from code_agents.chat.chat_clipboard import _read_clipboard_image_macos
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 3)
        assert _read_clipboard_image_macos() is None

    @patch("code_agents.chat.chat_clipboard.subprocess.run")
    def test_os_error(self, mock_run):
        from code_agents.chat.chat_clipboard import _read_clipboard_image_macos
        mock_run.side_effect = OSError("no osascript")
        assert _read_clipboard_image_macos() is None

    @patch("code_agents.chat.chat_clipboard.subprocess")
    @patch("code_agents.chat.chat_clipboard._file_to_image_dict")
    def test_tiff_clipboard(self, mock_file_dict, mock_subprocess):
        from code_agents.chat.chat_clipboard import _read_clipboard_image_macos
        check_result = MagicMock()
        check_result.stdout = "TIFF data"
        write_result = MagicMock()
        write_result.returncode = 0
        mock_subprocess.run.side_effect = [check_result, write_result]
        mock_file_dict.return_value = {"type": "image"}
        assert _read_clipboard_image_macos() is not None


class TestReadClipboardImageLinux:
    """Test _read_clipboard_image_linux."""

    @patch("code_agents.chat.chat_clipboard._file_to_image_dict")
    @patch("code_agents.chat.chat_clipboard.subprocess")
    def test_success(self, mock_subprocess, mock_file_dict):
        from code_agents.chat.chat_clipboard import _read_clipboard_image_linux
        check_result = MagicMock()
        check_result.stdout = "image/png\ntext/plain"
        write_result = MagicMock()
        write_result.returncode = 0
        write_result.stdout = b"\x89PNG\r\n"
        mock_subprocess.run.side_effect = [check_result, write_result]
        mock_file_dict.return_value = {"type": "image"}
        assert _read_clipboard_image_linux() is not None

    @patch("code_agents.chat.chat_clipboard.subprocess")
    def test_no_image_target(self, mock_subprocess):
        from code_agents.chat.chat_clipboard import _read_clipboard_image_linux
        check_result = MagicMock()
        check_result.stdout = "text/plain"
        mock_subprocess.run.return_value = check_result
        assert _read_clipboard_image_linux() is None

    @patch("code_agents.chat.chat_clipboard._cleanup_tmp")
    @patch("code_agents.chat.chat_clipboard.subprocess")
    def test_xclip_fails(self, mock_subprocess, mock_cleanup):
        from code_agents.chat.chat_clipboard import _read_clipboard_image_linux
        check_result = MagicMock()
        check_result.stdout = "image/png"
        write_result = MagicMock()
        write_result.returncode = 1
        write_result.stdout = b""
        mock_subprocess.run.side_effect = [check_result, write_result]
        assert _read_clipboard_image_linux() is None

    @patch("code_agents.chat.chat_clipboard._cleanup_tmp")
    @patch("code_agents.chat.chat_clipboard.subprocess")
    def test_xclip_empty_stdout(self, mock_subprocess, mock_cleanup):
        from code_agents.chat.chat_clipboard import _read_clipboard_image_linux
        check_result = MagicMock()
        check_result.stdout = "image/png"
        write_result = MagicMock()
        write_result.returncode = 0
        write_result.stdout = b""
        mock_subprocess.run.side_effect = [check_result, write_result]
        assert _read_clipboard_image_linux() is None

    @patch("code_agents.chat.chat_clipboard.subprocess.run")
    def test_file_not_found(self, mock_run):
        from code_agents.chat.chat_clipboard import _read_clipboard_image_linux
        mock_run.side_effect = FileNotFoundError("xclip not installed")
        assert _read_clipboard_image_linux() is None

    @patch("code_agents.chat.chat_clipboard.subprocess.run")
    def test_timeout(self, mock_run):
        import subprocess
        from code_agents.chat.chat_clipboard import _read_clipboard_image_linux
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 3)
        assert _read_clipboard_image_linux() is None


class TestReadImageFile:
    """Test read_image_file."""

    def test_valid_png(self, tmp_path):
        from code_agents.chat.chat_clipboard import read_image_file
        img = tmp_path / "test.png"
        img.write_bytes(b"\x89PNG\r\n" + b"data")
        result = read_image_file(str(img))
        assert result is not None
        assert result["type"] == "image"
        assert result["media_type"] == "image/png"
        assert result["size_bytes"] > 0

    def test_valid_jpeg(self, tmp_path):
        from code_agents.chat.chat_clipboard import read_image_file
        img = tmp_path / "photo.jpg"
        img.write_bytes(b"\xff\xd8\xff" + b"data")
        result = read_image_file(str(img))
        assert result is not None
        assert result["media_type"] == "image/jpeg"

    def test_valid_gif(self, tmp_path):
        from code_agents.chat.chat_clipboard import read_image_file
        img = tmp_path / "anim.gif"
        img.write_bytes(b"GIF89a" + b"data")
        result = read_image_file(str(img))
        assert result is not None
        assert result["media_type"] == "image/gif"

    def test_valid_webp(self, tmp_path):
        from code_agents.chat.chat_clipboard import read_image_file
        img = tmp_path / "test.webp"
        img.write_bytes(b"RIFF" + b"data")
        result = read_image_file(str(img))
        assert result is not None
        assert result["media_type"] == "image/webp"

    def test_unsupported_extension(self, tmp_path):
        from code_agents.chat.chat_clipboard import read_image_file
        f = tmp_path / "test.bmp"
        f.write_bytes(b"BM" + b"data")
        assert read_image_file(str(f)) is None

    def test_nonexistent_file(self):
        from code_agents.chat.chat_clipboard import read_image_file
        assert read_image_file("/nonexistent/path/test.png") is None

    def test_tilde_expansion(self, tmp_path):
        from code_agents.chat.chat_clipboard import read_image_file
        with patch("os.path.expanduser", return_value=str(tmp_path / "test.png")):
            img = tmp_path / "test.png"
            img.write_bytes(b"\x89PNG" + b"data")
            result = read_image_file("~/test.png")
            assert result is not None


class TestFileToImageDict:
    """Test _file_to_image_dict."""

    def test_success(self, tmp_path):
        from code_agents.chat.chat_clipboard import _file_to_image_dict
        f = tmp_path / "test.png"
        f.write_bytes(b"test data")
        result = _file_to_image_dict(str(f), cleanup=False)
        assert result is not None
        assert result["type"] == "image"
        assert result["media_type"] == "image/png"
        decoded = base64.b64decode(result["data"])
        assert decoded == b"test data"
        assert result["size_bytes"] == 9

    def test_empty_file(self, tmp_path):
        from code_agents.chat.chat_clipboard import _file_to_image_dict
        f = tmp_path / "empty.png"
        f.write_bytes(b"")
        result = _file_to_image_dict(str(f), cleanup=False)
        assert result is None

    def test_cleanup_removes_file(self, tmp_path):
        from code_agents.chat.chat_clipboard import _file_to_image_dict
        f = tmp_path / "tmp.png"
        f.write_bytes(b"data")
        _file_to_image_dict(str(f), cleanup=True)
        assert not f.exists()

    def test_cleanup_false_keeps_file(self, tmp_path):
        from code_agents.chat.chat_clipboard import _file_to_image_dict
        f = tmp_path / "keep.png"
        f.write_bytes(b"data")
        _file_to_image_dict(str(f), cleanup=False)
        assert f.exists()

    def test_custom_media_type(self, tmp_path):
        from code_agents.chat.chat_clipboard import _file_to_image_dict
        f = tmp_path / "test.jpg"
        f.write_bytes(b"jpeg data")
        result = _file_to_image_dict(str(f), media_type="image/jpeg", cleanup=False)
        assert result["media_type"] == "image/jpeg"

    def test_os_error(self):
        from code_agents.chat.chat_clipboard import _file_to_image_dict
        result = _file_to_image_dict("/nonexistent/file.png", cleanup=False)
        assert result is None


class TestCleanupTmp:
    """Test _cleanup_tmp."""

    def test_removes_file(self, tmp_path):
        from code_agents.chat.chat_clipboard import _cleanup_tmp
        f = tmp_path / "tmp.png"
        f.write_bytes(b"data")
        _cleanup_tmp(str(f))
        assert not f.exists()

    def test_nonexistent_no_error(self):
        from code_agents.chat.chat_clipboard import _cleanup_tmp
        _cleanup_tmp("/nonexistent/file.png")  # Should not raise


class TestBuildMultimodalContent:
    """Test build_multimodal_content."""

    def test_text_only(self):
        from code_agents.chat.chat_clipboard import build_multimodal_content
        result = build_multimodal_content("hello", [])
        assert result == [{"type": "text", "text": "hello"}]

    def test_empty_text(self):
        from code_agents.chat.chat_clipboard import build_multimodal_content
        result = build_multimodal_content("", [])
        assert result == []

    def test_with_image(self):
        from code_agents.chat.chat_clipboard import build_multimodal_content
        images = [{"media_type": "image/png", "data": "abc123"}]
        result = build_multimodal_content("describe this", images)
        assert len(result) == 2
        assert result[0]["type"] == "image_url"
        assert "data:image/png;base64,abc123" in result[0]["image_url"]["url"]
        assert result[1] == {"type": "text", "text": "describe this"}

    def test_multiple_images(self):
        from code_agents.chat.chat_clipboard import build_multimodal_content
        images = [
            {"media_type": "image/png", "data": "aaa"},
            {"media_type": "image/jpeg", "data": "bbb"},
        ]
        result = build_multimodal_content("compare", images)
        assert len(result) == 3
        assert all(r["type"] == "image_url" for r in result[:2])
        assert result[2]["type"] == "text"

    def test_images_no_text(self):
        from code_agents.chat.chat_clipboard import build_multimodal_content
        images = [{"media_type": "image/png", "data": "x"}]
        result = build_multimodal_content("", images)
        assert len(result) == 1
        assert result[0]["type"] == "image_url"