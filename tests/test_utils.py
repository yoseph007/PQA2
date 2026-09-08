import os
import sys
import tempfile
import pathlib
import subprocess
import unittest
from unittest.mock import patch

try:
    import pytest
except ImportError:
    pytest = None

from app.utils import get_ffmpeg_path, get_video_info, get_subprocess_startupinfo
from app.options_manager import OptionsManager


def test_get_ffmpeg_path_bundled(tmp_path=None):
    if tmp_path is None:
        with tempfile.TemporaryDirectory() as td:
            _test_get_ffmpeg_path_bundled(pathlib.Path(td))
    else:
        _test_get_ffmpeg_path_bundled(tmp_path)


def _test_get_ffmpeg_path_bundled(tmp_path):
    bin_dir = tmp_path / "ffmpeg_bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    exe = bin_dir / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    exe.write_bytes(b"")
    with patch("app.utils.os.path.dirname", return_value=str(tmp_path)):
        assert get_ffmpeg_path() == str(exe)


def test_get_ffmpeg_path_fallback(monkeypatch=None):
    if monkeypatch is not None:
        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/ffmpeg")
        with patch("app.utils.os.path.isfile", return_value=False):
            assert get_ffmpeg_path() == "/usr/bin/ffmpeg"
    else:
        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            with patch("app.utils.os.path.isfile", return_value=False):
                assert get_ffmpeg_path() == "/usr/bin/ffmpeg"


def test_startupinfo_flags():
    si, flags = get_subprocess_startupinfo()
    if os.name == "nt":
        assert si is not None and flags == subprocess.CREATE_NO_WINDOW
    else:
        assert si is None and flags == 0


def test_video_info_total_frames_alias(tmp_path=None):
    if tmp_path is None:
        with tempfile.TemporaryDirectory() as td:
            _test_video_info_total_frames_alias(pathlib.Path(td))
    else:
        _test_video_info_total_frames_alias(tmp_path)


def _test_video_info_total_frames_alias(tmp_path):
    fake = {"total_frames": 100, "frame_count": 100}
    with patch("tests.test_utils.get_video_info", return_value=fake), \
         patch("app.utils.get_video_info", return_value=fake):
        info = get_video_info(str(tmp_path / "v.mp4"))
    assert info["total_frames"] == info["frame_count"]


def test_get_all_settings_alias():
    om = OptionsManager()
    assert om.get_all_settings() == om.get_settings()


class TestUtils(unittest.TestCase):
    def test_get_ffmpeg_path_bundled(self):
        test_get_ffmpeg_path_bundled()

    def test_get_ffmpeg_path_fallback(self):
        test_get_ffmpeg_path_fallback()

    def test_startupinfo_flags(self):
        test_startupinfo_flags()

    def test_video_info_total_frames_alias(self):
        test_video_info_total_frames_alias()

    def test_get_all_settings_alias(self):
        test_get_all_settings_alias()


if __name__ == "__main__":
    unittest.main()
