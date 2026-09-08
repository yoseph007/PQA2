"""
Unit and Integration Tests for Hardware Re-Capture Campaign Runner (scripts/run_recapture_campaign.py).
"""

import os
import sys
import json
import tempfile
import unittest
from unittest.mock import patch, MagicMock

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts.run_recapture_campaign import resolve_capture_files, run_recapture_campaign


class TestRecaptureCampaign(unittest.TestCase):
    """Test suite for Hardware Re-Capture Campaign execution, file resolution, and reporting."""

    def test_resolve_capture_files(self):
        """Verify resolve_capture_files handles explicit files, globs, sorting, and deduplication."""
        with tempfile.TemporaryDirectory() as td:
            f1 = os.path.join(td, "pass_01.mp4")
            f2 = os.path.join(td, "pass_02.mp4")
            f3 = os.path.join(td, "pass_03.mp4")

            for f in [f1, f2, f3]:
                with open(f, "w") as fp:
                    fp.write("dummy")

            # Glob pattern
            glob_pat = os.path.join(td, "pass_*.mp4")
            resolved = resolve_capture_files([glob_pat])
            self.assertEqual(len(resolved), 3)
            self.assertEqual(resolved, [os.path.abspath(f1), os.path.abspath(f2), os.path.abspath(f3)])

            # Explicit list with duplicates
            resolved_dup = resolve_capture_files([f2, f1, f2])
            self.assertEqual(len(resolved_dup), 2)
            self.assertEqual(resolved_dup, [os.path.abspath(f1), os.path.abspath(f2)])

    def test_run_recapture_campaign_minimum_captures_guard(self):
        """Verify error is raised if fewer than 2 capture files are provided."""
        with tempfile.TemporaryDirectory() as td:
            ref = os.path.join(td, "ref.mp4")
            cap1 = os.path.join(td, "cap1.mp4")
            for f in [ref, cap1]:
                with open(f, "w") as fp:
                    fp.write("dummy")

            args = MagicMock(ref=ref, captures=[cap1], model="vmaf_v0.6.1")
            with self.assertRaises(ValueError) as ctx:
                run_recapture_campaign(args)
            self.assertIn("at least 2 capture files", str(ctx.exception))

    def test_run_recapture_campaign_mock_execution(self):
        """Verify full recapture campaign execution with mocked analyzer and PDF generation."""
        with tempfile.TemporaryDirectory() as td:
            ref_path = os.path.join(td, "reference.mp4")
            cap1 = os.path.join(td, "capture_1.mp4")
            cap2 = os.path.join(td, "capture_2.mp4")
            cap3 = os.path.join(td, "capture_3.mp4")
            out_pdf = os.path.join(td, "reports", "recapture_report.pdf")
            log_file = os.path.join(td, "campaign_history.jsonl")

            for p in [ref_path, cap1, cap2, cap3]:
                with open(p, "w") as fp:
                    fp.write("video content bytes")

            # Mock get_video_info
            mock_video_meta = {
                "width": 1920,
                "height": 1080,
                "fps": 29.97,
                "total_frames": 180,
                "duration": 6.0,
            }

            # Mock VMAF scores with slight jitter (e.g. 92.5, 93.0, 92.0)
            mock_scores = [
                {"vmaf_score": 92.5, "psnr_score": 41.0, "ssim_score": 0.985, "measurement_metadata": {}},
                {"vmaf_score": 93.0, "psnr_score": 41.5, "ssim_score": 0.987, "measurement_metadata": {}},
                {"vmaf_score": 92.0, "psnr_score": 40.8, "ssim_score": 0.983, "measurement_metadata": {}},
            ]
            call_idx = 0

            def fake_analyze(*args, **kwargs):
                nonlocal call_idx
                res = mock_scores[call_idx]
                call_idx += 1
                return res

            args = MagicMock(
                ref=ref_path,
                captures=[cap1, cap2, cap3],
                model="vmaf_v0.6.1",
                out_pdf=out_pdf,
                log_path=log_file,
                test_name="Test Hardware Re-Capture",
            )

            with patch("scripts.run_recapture_campaign.get_video_info", return_value=mock_video_meta):
                with patch("scripts.run_recapture_campaign.VMAFAnalyzer.analyze_videos", side_effect=fake_analyze):
                    with patch("scripts.run_recapture_campaign.VMAFAnalyzer.probe_capabilities", return_value={"ffmpeg_version": "test"}):
                        agg = run_recapture_campaign(args)

            # Assert campaign properties
            self.assertIsNotNone(agg)
            self.assertEqual(agg["campaign_type"], "recapture")
            self.assertEqual(agg["n_completed"], 3)
            self.assertEqual(agg["n_requested"], 3)

            # Check stats: mean = (92.5 + 93.0 + 92.0) / 3 = 92.5
            vmaf_s = agg["metrics"]["vmaf"]
            self.assertAlmostEqual(vmaf_s["mean"], 92.5, places=2)
            self.assertGreater(vmaf_s["stddev"], 0.0)  # non-zero empirical jitter!
            self.assertAlmostEqual(vmaf_s["range"], 1.0, places=2)
            self.assertEqual(agg["verdict"], "Acceptable")

            # Check JSONL history was logged
            self.assertTrue(os.path.exists(log_file))
            with open(log_file, "r", encoding="utf-8") as f:
                records = [json.loads(line) for line in f if line.strip()]
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["campaign_type"], "recapture")
            self.assertAlmostEqual(records[0]["vmaf_mean"], 92.5, places=2)

            # Check PDF generated
            self.assertTrue(os.path.exists(out_pdf))
            self.assertGreater(os.path.getsize(out_pdf), 1000)

    def test_run_recapture_campaign_frame_count_mismatch_aborts(self):
        """Verify that captures with differing frame counts are rejected by default (Session Note 2)."""
        with tempfile.TemporaryDirectory() as td:
            ref_path = os.path.join(td, "reference.mp4")
            cap1 = os.path.join(td, "capture_1.mp4")
            cap2 = os.path.join(td, "capture_2.mp4")

            for p in [ref_path, cap1, cap2]:
                with open(p, "w") as fp:
                    fp.write("dummy")

            args = MagicMock(
                ref=ref_path,
                captures=[cap1, cap2],
                model="vmaf_v0.6.1",
                allow_frame_mismatch=False,
            )

            # Different frame counts: ref=180, cap1=180, cap2=175
            def mock_get_info(path):
                if "capture_2" in path:
                    return {"width": 1920, "height": 1080, "fps": 29.97, "total_frames": 175}
                return {"width": 1920, "height": 1080, "fps": 29.97, "total_frames": 180}

            with patch("scripts.run_recapture_campaign.get_video_info", side_effect=mock_get_info):
                with self.assertRaises(ValueError) as ctx:
                    run_recapture_campaign(args)
                self.assertIn("Frame count mismatch", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
