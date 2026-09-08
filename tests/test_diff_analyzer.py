"""
Unit and Integration Tests for Metrology Report Diff Analyzer & Comparison Mode.
"""

import os
import sys
import json
import math
import shutil
import tempfile
import unittest
from unittest.mock import patch

from app.diff_analyzer import (
    DiffAnalyzer,
    calculate_combined_uncertainty,
    compare_campaigns,
    generate_diff_pdf,
    DEFAULT_RESOLUTION_FLOOR_SIGMA
)
from scripts.compare_campaigns import format_ascii_diff


class TestDiffAnalyzer(unittest.TestCase):
    """Test suite for Metrology Diff calculations, noise-floor gates, and reporting."""

    def test_combined_sigma_threshold(self):
        """Correction 1: Verify combined quadrature uncertainty formula."""
        # 1. Both variances zero (fixed-pair determinism)
        sigma_delta_zero = calculate_combined_uncertainty(0.0, 0.0, sigma_floor=0.05)
        self.assertAlmostEqual(sigma_delta_zero, 0.05, places=5)
        t_3sigma = 3.0 * sigma_delta_zero
        self.assertAlmostEqual(t_3sigma, 0.15, places=5)

        # 2. Both non-zero
        s1 = 0.1
        s2 = 0.2
        expected = math.sqrt(0.1**2 + 0.2**2 + 0.05**2)  # sqrt(0.01 + 0.04 + 0.0025) = sqrt(0.0525) ~ 0.229128
        sigma_delta = calculate_combined_uncertainty(s1, s2, sigma_floor=0.05)
        self.assertAlmostEqual(sigma_delta, expected, places=5)

        # 3. None / NaN safety
        sigma_delta_none = calculate_combined_uncertainty(None, float('nan'), sigma_floor=0.05)
        self.assertAlmostEqual(sigma_delta_none, 0.05, places=5)

    def test_compare_campaigns_basic_deltas(self):
        """Verify metric deltas and directional strings."""
        b = {
            "vmaf_mean": 90.0,
            "vmaf_stddev": 0.1,
            "cv_pct": 0.11,
            "psnr_mean": 38.0,
            "ssim_mean": 0.95,
            "verdict": "Acceptable",
            "verdict_status": "acceptable",
            "reference_file": "ref.mp4",
            "reference_sha256": "aaaa1111bbbb2222",
            "distorted_file": "dist1.mp4",
            "distorted_sha256": "1111222233334444",
            "model": "vmaf_v0.6.1",
            "ffmpeg_version": "ffmpeg n7.1.1",
        }
        t = {
            "vmaf_mean": 93.5,
            "vmaf_stddev": 0.05,
            "cv_pct": 0.05,
            "psnr_mean": 41.2,
            "ssim_mean": 0.98,
            "verdict": "Acceptable",
            "verdict_status": "acceptable",
            "reference_file": "ref.mp4",
            "reference_sha256": "aaaa1111bbbb2222",
            "distorted_file": "dist2.mp4",
            "distorted_sha256": "5555666677778888",
            "model": "vmaf_v0.6.1",
            "ffmpeg_version": "ffmpeg n7.1.1",
        }

        diff = compare_campaigns(b, t)

        # Deltas
        self.assertAlmostEqual(diff["deltas"]["delta_vmaf"], 3.5, places=2)
        self.assertEqual(diff["deltas"]["delta_vmaf_str"], "▲ +3.50")
        self.assertEqual(diff["deltas"]["delta_vmaf_polarity"], "improved")
        self.assertAlmostEqual(diff["deltas"]["delta_psnr"], 3.2, places=2)
        self.assertEqual(diff["deltas"]["delta_psnr_str"], "▲ +3.20")
        self.assertEqual(diff["deltas"]["delta_psnr_polarity"], "improved")
        self.assertAlmostEqual(diff["deltas"]["delta_ssim"], 0.03, places=4)
        self.assertEqual(diff["deltas"]["delta_ssim_str"], "▲ +0.0300")
        self.assertEqual(diff["deltas"]["delta_ssim_polarity"], "improved")

        # %CV and sigma: lower is better -> negative numeric delta is improvement
        # Numeric direction is ▼, polarity is 'improved'
        self.assertAlmostEqual(diff["deltas"]["delta_sigma"], -0.05, places=4)
        self.assertEqual(diff["deltas"]["delta_sigma_str"], "▼ -0.0500")
        self.assertEqual(diff["deltas"]["delta_sigma_polarity"], "improved")
        self.assertAlmostEqual(diff["deltas"]["delta_cv_pct"], -0.06, places=3)
        self.assertEqual(diff["deltas"]["delta_cv_pct_str"], "▼ -0.060")
        self.assertEqual(diff["deltas"]["delta_cv_pct_polarity"], "improved")

    def test_metric_divergence_detection(self):
        """Verify metric divergence advisory when metrics disagree in sign."""
        b = {"vmaf_mean": 90.0, "psnr_mean": 38.0, "ssim_mean": 0.96}
        t = {"vmaf_mean": 92.0, "psnr_mean": 40.0, "ssim_mean": 0.94}
        diff = compare_campaigns(b, t)
        self.assertIsNotNone(diff["deltas"]["divergence_advisory"])
        self.assertIn("directional divergence detected", diff["deltas"]["divergence_advisory"])
        self.assertIn("VMAF, PSNR", diff["deltas"]["divergence_advisory"])
        self.assertIn("SSIM", diff["deltas"]["divergence_advisory"])

        # No divergence when all agree
        b2 = {"vmaf_mean": 90.0, "psnr_mean": 38.0, "ssim_mean": 0.94}
        t2 = {"vmaf_mean": 92.0, "psnr_mean": 40.0, "ssim_mean": 0.96}
        diff2 = compare_campaigns(b2, t2)
        self.assertIsNone(diff2["deltas"]["divergence_advisory"])

    def test_noise_floor_significance_gates(self):
        """Verify 3-sigma noise floor classifications: improvement, degradation, and noise."""
        b = {"vmaf_mean": 90.0, "vmaf_stddev": 0.0, "verdict": "Acceptable"}

        # 1. Delta > +3*sigma (T_3sigma = 0.15) -> Significant improvement
        t_high = {"vmaf_mean": 92.0, "vmaf_stddev": 0.0, "verdict": "Acceptable"}
        diff_high = compare_campaigns(b, t_high, sigma_floor=0.05)
        self.assertTrue(diff_high["metrology"]["is_significant"])
        self.assertEqual(diff_high["metrology"]["significance_verdict"], "significant_improvement")

        # 2. Delta < -3*sigma -> Significant degradation
        t_low = {"vmaf_mean": 88.0, "vmaf_stddev": 0.0, "verdict": "Acceptable"}
        diff_low = compare_campaigns(b, t_low, sigma_floor=0.05)
        self.assertTrue(diff_low["metrology"]["is_significant"])
        self.assertEqual(diff_low["metrology"]["significance_verdict"], "significant_degradation")

        # 3. |Delta| <= 3*sigma (e.g. 0.08 < 0.15) -> Indistinguishable from noise
        t_noise = {"vmaf_mean": 90.08, "vmaf_stddev": 0.0, "verdict": "Acceptable"}
        diff_noise = compare_campaigns(b, t_noise, sigma_floor=0.05)
        self.assertFalse(diff_noise["metrology"]["is_significant"])
        self.assertEqual(diff_noise["metrology"]["significance_verdict"], "indistinguishable_from_noise")

    def test_cv_suppression_on_insufficient_data(self):
        """Verify %CV delta is suppressed when either run has insufficient_data."""
        b = {"vmaf_mean": 90.0, "cv_pct": 0.10, "verdict_status": "insufficient_data"}
        t = {"vmaf_mean": 91.0, "cv_pct": 0.05, "verdict_status": "acceptable"}
        diff = compare_campaigns(b, t)
        self.assertIsNone(diff["deltas"]["delta_cv_pct"])
        self.assertEqual(diff["deltas"]["delta_cv_pct_str"], "N/A (suppressed)")

    def test_verdict_evolution_display(self):
        """Verify affirmative verdict evolution text for unchanged and changed states."""
        # Unchanged
        b1 = {"verdict": "Acceptable"}
        t1 = {"verdict": "Acceptable"}
        d1 = compare_campaigns(b1, t1)
        self.assertFalse(d1["verdict_evolution"]["verdict_changed"])
        self.assertEqual(d1["verdict_evolution"]["verdict_evolution_text"], "Unchanged (Acceptable -> Acceptable)")

        # Changed
        b2 = {"verdict": "Acceptable"}
        t2 = {"verdict": "Conditional"}
        d2 = compare_campaigns(b2, t2)
        self.assertTrue(d2["verdict_evolution"]["verdict_changed"])
        self.assertEqual(d2["verdict_evolution"]["verdict_evolution_text"], "State Shift: Acceptable -> Conditional")

    def test_fixture_traceability_and_toolchain_check(self):
        """Verify fixture SHA-256 and toolchain consistency checking."""
        b = {
            "reference_sha256": "ref_hash_1",
            "distorted_sha256": "dist_hash_1",
            "model": "vmaf_v0.6.1",
            "ffmpeg_version": "ffmpeg n7.1.1",
        }
        # Compatible case
        t_compat = {
            "reference_sha256": "ref_hash_1",
            "distorted_sha256": "dist_hash_2",
            "model": "vmaf_v0.6.1",
            "ffmpeg_version": "ffmpeg n7.1.1",
        }
        d_compat = compare_campaigns(b, t_compat)
        self.assertTrue(d_compat["traceability"]["reference_match"])
        self.assertFalse(d_compat["traceability"]["distorted_match"])
        self.assertTrue(d_compat["traceability"]["toolchain_compatible"])

        # Incompatible model case
        t_incompat = {
            "reference_sha256": "ref_hash_1",
            "distorted_sha256": "dist_hash_2",
            "model": "vmaf_4k_v0.6.1",
            "ffmpeg_version": "ffmpeg n7.1.1",
        }
        d_incompat = compare_campaigns(b, t_incompat)
        self.assertFalse(d_incompat["traceability"]["toolchain_compatible"])
        self.assertTrue(any("Model mismatch" in r for r in d_incompat["traceability"]["incompatible_reasons"]))

    def test_latest_2_ordering(self):
        """Annotation 2: Verify --latest 2 orders by JSONL append order (baseline=second-to-last, treatment=last)."""
        with tempfile.TemporaryDirectory() as td:
            log_file = os.path.join(td, "history.jsonl")
            recs = [
                {"timestamp": "2026-09-08 10:00:00", "vmaf_mean": 85.0, "verdict": "Run 1"},
                {"timestamp": "2026-09-08 11:00:00", "vmaf_mean": 90.0, "verdict": "Run 2"},
                {"timestamp": "2026-09-08 12:00:00", "vmaf_mean": 95.0, "verdict": "Run 3"},
            ]
            with open(log_file, "w", encoding="utf-8") as f:
                for r in recs:
                    f.write(json.dumps(r) + "\n")

            from app.repeatability_analyzer import read_campaign_history
            all_recs = read_campaign_history(log_path=log_file)
            baseline = all_recs[-2]  # Run 2
            treatment = all_recs[-1]  # Run 3

            diff = compare_campaigns(baseline, treatment)
            self.assertEqual(diff["baseline"]["verdict"], "Run 2")
            self.assertEqual(diff["treatment"]["verdict"], "Run 3")
            self.assertAlmostEqual(diff["deltas"]["delta_vmaf"], 5.0, places=2)

    def test_chart_modes_pooled_bar_and_frame_curve(self):
        """Annotation 4: Verify both chart generation paths (pooled_bar and frame_curve)."""
        with tempfile.TemporaryDirectory() as td:
            analyzer = DiffAnalyzer()

            # Mode 1: Pooled bar
            diff_pooled = compare_campaigns(
                {"vmaf_mean": 92.0, "vmaf_stddev": 0.1, "psnr_mean": 40.0, "ssim_mean": 0.96},
                {"vmaf_mean": 95.0, "vmaf_stddev": 0.15, "psnr_mean": 43.0, "ssim_mean": 0.98}
            )
            self.assertEqual(diff_pooled["chart_mode"], "pooled_bar")
            out_bar = os.path.join(td, "bar_chart.png")
            analyzer.generate_diff_chart(diff_pooled, out_bar)
            self.assertTrue(os.path.isfile(out_bar))
            self.assertGreater(os.path.getsize(out_bar), 1000)

            # Mode 2: Frame curves
            frames_1 = [{"metrics": {"vmaf": 90.0 + i * 0.1}} for i in range(20)]
            frames_2 = [{"metrics": {"vmaf": 92.0 + i * 0.1}} for i in range(20)]
            diff_frames = compare_campaigns(
                {"vmaf_mean": 91.0, "raw_results": {"frames": frames_1}},
                {"vmaf_mean": 93.0, "raw_results": {"frames": frames_2}}
            )
            self.assertEqual(diff_frames["chart_mode"], "frame_curve")
            out_curve = os.path.join(td, "curve_chart.png")
            analyzer.generate_diff_chart(diff_frames, out_curve)
            self.assertTrue(os.path.isfile(out_curve))
            self.assertGreater(os.path.getsize(out_curve), 1000)

    def test_pdf_diff_report_generation(self):
        """Verify ReportLab PDF diff report is created and non-empty."""
        with tempfile.TemporaryDirectory() as td:
            b = {"vmaf_mean": 93.26, "vmaf_stddev": 0.0, "psnr_mean": 39.55, "ssim_mean": 0.99, "verdict": "Acceptable"}
            t = {"vmaf_mean": 96.10, "vmaf_stddev": 0.0, "psnr_mean": 42.10, "ssim_mean": 0.995, "verdict": "Acceptable"}
            diff = compare_campaigns(b, t)

            pdf_out = os.path.join(td, "diff_report.pdf")
            generated_path = generate_diff_pdf(diff, pdf_out)
            self.assertTrue(os.path.isfile(generated_path))
            self.assertGreater(os.path.getsize(generated_path), 5000)

    def test_fail_on_degradation_incomparable_toolchain(self):
        """Annotation 3: Verify CLI exit code semantics for --fail-on-degradation."""
        import subprocess

        # 1. Incomparable records -> should exit with code 2
        with tempfile.TemporaryDirectory() as td:
            f1 = os.path.join(td, "run1.json")
            f2 = os.path.join(td, "run2.json")
            with open(f1, "w") as f:
                json.dump({"vmaf_mean": 95.0, "model": "vmaf_v0.6.1"}, f)
            with open(f2, "w") as f:
                json.dump({"vmaf_mean": 90.0, "model": "vmaf_4k_v0.6.1"}, f)

            cmd = [sys.executable, "scripts/compare_campaigns.py", "--file1", f1, "--file2", f2, "--fail-on-degradation"]
            res = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(res.returncode, 2, f"Expected exit code 2 for toolchain mismatch, got {res.returncode}")

        # 2. Significant degradation -> should exit with code 1
        with tempfile.TemporaryDirectory() as td:
            f1 = os.path.join(td, "run1.json")
            f2 = os.path.join(td, "run2.json")
            with open(f1, "w") as f:
                json.dump({"vmaf_mean": 95.0, "model": "vmaf_v0.6.1"}, f)
            with open(f2, "w") as f:
                json.dump({"vmaf_mean": 90.0, "model": "vmaf_v0.6.1"}, f)

            cmd = [sys.executable, "scripts/compare_campaigns.py", "--file1", f1, "--file2", f2, "--fail-on-degradation"]
            res = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(res.returncode, 1, f"Expected exit code 1 for degradation, got {res.returncode}")

        # 3. Improvement -> should exit with code 0
        with tempfile.TemporaryDirectory() as td:
            f1 = os.path.join(td, "run1.json")
            f2 = os.path.join(td, "run2.json")
            with open(f1, "w") as f:
                json.dump({"vmaf_mean": 90.0, "model": "vmaf_v0.6.1"}, f)
            with open(f2, "w") as f:
                json.dump({"vmaf_mean": 95.0, "model": "vmaf_v0.6.1"}, f)

            cmd = [sys.executable, "scripts/compare_campaigns.py", "--file1", f1, "--file2", f2, "--fail-on-degradation"]
            res = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"Expected exit code 0 for improvement, got {res.returncode}")

    def test_recapture_empirical_sigma_floor_supersedes_declared_floor(self):
        """Verify that when comparing against a recapture campaign, measured sigma_rig supersedes the declared 0.05 floor."""
        b = {
            "campaign_type": "recapture",
            "vmaf_mean": 92.5,
            "vmaf_stddev": 0.35,  # measured sigma_rig
            "cv_pct": 0.378,
            "reference_file": "ref.mp4",
            "distorted_file": "recapture_set",
            "model": "vmaf_v0.6.1",
        }
        t = {
            "vmaf_mean": 92.75,  # delta = +0.25
            "vmaf_stddev": 0.0,
            "cv_pct": 0.0,
            "reference_file": "ref.mp4",
            "distorted_file": "single_pass.mp4",
            "model": "vmaf_v0.6.1",
        }

        diff = compare_campaigns(b, t)

        # Delta is +0.25
        self.assertAlmostEqual(diff["deltas"]["delta_vmaf"], 0.25, places=2)

        # Under declared 0.05 floor, 0.25 > 3*0.05 (0.15), which would be a false positive.
        # Under empirical sigma_rig (0.35), effective floor is 0.35, and threshold T >= 3*0.35 = 1.05 VMAF points.
        # Delta +0.25 must be recognized as indistinguishable from noise!
        self.assertFalse(diff["metrology"]["is_significant"])
        self.assertEqual(diff["metrology"]["significance_verdict"], "indistinguishable_from_noise")
        self.assertTrue(diff["metrology"]["is_empirical_floor"])
        self.assertEqual(diff["metrology"]["sigma_floor_source"], "empirical_sigma_rig")
        self.assertAlmostEqual(diff["metrology"]["sigma_floor_effective"], 0.35, places=2)


if __name__ == "__main__":
    unittest.main()
