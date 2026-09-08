import os
import sys
import tempfile
import pathlib
import unittest
from unittest.mock import MagicMock, patch

try:
    import pytest
except ImportError:
    pytest = None

from app.bookend_alignment import (
    AlignmentState, BookendAligner, MAX_REPAIR_ATTEMPTS,
)


def test_enum_accessible():
    assert AlignmentState.IDLE.value == "idle"


def test_dedup_prefers_longest():
    aligner = BookendAligner()
    cands = [
        {"start_frame": 0, "end_frame": 10, "brightness": 255},
        {"start_frame": 0, "end_frame": 30, "brightness": 250},  # overlaps, longer
        {"start_frame": 50, "end_frame": 60, "brightness": 255},
    ]
    result = aligner._deduplicate_bookends(cands)
    assert len(result) == 2
    assert result[0]["end_frame"] == 30


def test_dedup_does_not_mutate_input():
    aligner = BookendAligner()
    cands = [{"start_frame": 0, "end_frame": 10, "brightness": 255}]
    original = list(cands)
    aligner._deduplicate_bookends(cands)
    assert cands == original


def test_options_propagation():
    om = MagicMock()
    om.get_settings.return_value = {"frame_offset": 5, "white_threshold": 235}
    aligner = BookendAligner(options_manager=om)
    assert aligner.frame_offset == 5
    assert aligner.white_threshold == 235.0


def _run_repair_test(mock_rm, mock_rep, mock_isf, mock_run, tmp_path):
    mock_run.return_value = MagicMock(returncode=0)
    aligner = BookendAligner()
    video = str(tmp_path / "v.mp4")
    (tmp_path / "v.mp4").write_bytes(b"x")
    assert aligner.repair_video_file(video) is True
    mock_rep.assert_called_once()


@patch("app.bookend_alignment.subprocess.run")
@patch("app.bookend_alignment.os.path.isfile", return_value=True)
@patch("app.bookend_alignment.os.replace")
@patch("app.bookend_alignment.os.remove")
def test_repair_uses_os_replace_and_cleans_up(mock_rm, mock_rep, mock_isf, mock_run, tmp_path=None):
    if tmp_path is None:
        with tempfile.TemporaryDirectory() as td:
            _run_repair_test(mock_rm, mock_rep, mock_isf, mock_run, pathlib.Path(td))
    else:
        _run_repair_test(mock_rm, mock_rep, mock_isf, mock_run, tmp_path)


def test_repair_retry_bound():
    assert MAX_REPAIR_ATTEMPTS >= 1


class TestBookendAlignment(unittest.TestCase):
    def test_enum_accessible(self):
        test_enum_accessible()

    def test_dedup_prefers_longest(self):
        test_dedup_prefers_longest()

    def test_dedup_does_not_mutate_input(self):
        test_dedup_does_not_mutate_input()

    def test_options_propagation(self):
        test_options_propagation()

    def test_repair_uses_os_replace_and_cleans_up(self):
        test_repair_uses_os_replace_and_cleans_up()

    def test_repair_retry_bound(self):
        test_repair_retry_bound()


if __name__ == "__main__":
    unittest.main()
