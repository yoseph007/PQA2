import math
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from PyQt6.QtWidgets import QApplication

app = QApplication.instance()
if not app:
    app = QApplication([])

from app.repeatability_analyzer import (
    RepeatabilityAnalyzer,
    RepeatabilityCampaignThread,
    aggregate_campaign_results,
    calculate_gage_rr_verdict,
    calculate_metric_statistics,
)


class TestRepeatability(unittest.TestCase):
    def test_aggregation_math_known_distribution(self):
        # Known distribution: [90.0, 92.0, 94.0]
        # n = 3
        # mean = (90 + 92 + 94) / 3 = 92.0
        # variance = ((90-92)^2 + (92-92)^2 + (94-92)^2) / (3 - 1) = (4 + 0 + 4) / 2 = 4.0
        # sample stddev = sqrt(4.0) = 2.0
        # range = 94.0 - 90.0 = 4.0
        # %CV = (2.0 / 92.0) * 100 = 2.1739...%
        vals = [90.0, 92.0, 94.0]
        stats = calculate_metric_statistics(vals, warning_threshold_drift=5.0)

        self.assertEqual(stats["n"], 3)
        self.assertAlmostEqual(stats["mean"], 92.0, places=4)
        self.assertAlmostEqual(stats["stddev"], 2.0, places=4)
        self.assertAlmostEqual(stats["min"], 90.0, places=4)
        self.assertAlmostEqual(stats["max"], 94.0, places=4)
        self.assertAlmostEqual(stats["range"], 4.0, places=4)
        self.assertAlmostEqual(stats["cv_pct"], 2.174, places=2)
        self.assertFalse(stats["drift_detected"])

    def test_sample_stddev_bessel_correction(self):
        # Explicitly verify n-1 degrees of freedom vs population n
        vals = [10.0, 20.0]
        # Population variance: ((10-15)^2 + (20-15)^2) / 2 = 50 / 2 = 25 -> std = 5.0
        # Sample variance: 50 / (2 - 1) = 50 -> std = sqrt(50) = 7.071067...
        stats = calculate_metric_statistics(vals)
        self.assertAlmostEqual(stats["stddev"], math.sqrt(50), places=4)
        self.assertNotAlmostEqual(stats["stddev"], 5.0, places=2)

    def test_instability_warning_flag(self):
        # Case 1: Max deviation from mean exceeds 1.0 point
        # Mean = 94.0; 92.5 deviates by 1.5 > 1.0
        drifting_vals = [92.5, 94.0, 95.5]
        stats_drift = calculate_metric_statistics(drifting_vals, warning_threshold_drift=1.0)
        self.assertTrue(stats_drift["drift_detected"])
        self.assertAlmostEqual(stats_drift["max_deviation_from_mean"], 1.5, places=2)

        # Case 2: Max deviation within 1.0 point
        # Mean = 93.2; max deviation is 0.2 <= 1.0
        stable_vals = [93.0, 93.2, 93.4]
        stats_stable = calculate_metric_statistics(stable_vals, warning_threshold_drift=1.0)
        self.assertFalse(stats_stable["drift_detected"])
        self.assertAlmostEqual(stats_stable["max_deviation_from_mean"], 0.2, places=2)

    def test_gage_rr_verdict_categories(self):
        # < 10% -> Acceptable
        v_acc = calculate_gage_rr_verdict(4.5, n_valid=5, total_requested=5)
        self.assertEqual(v_acc["status"], "acceptable")
        self.assertEqual(v_acc["verdict"], "Acceptable")

        # 10% - 30% -> Conditional
        v_cond1 = calculate_gage_rr_verdict(10.0, n_valid=5, total_requested=5)
        self.assertEqual(v_cond1["status"], "conditional")
        v_cond2 = calculate_gage_rr_verdict(25.0, n_valid=5, total_requested=5)
        self.assertEqual(v_cond2["status"], "conditional")

        # > 30% -> Rig-Dominated
        v_dom = calculate_gage_rr_verdict(35.2, n_valid=5, total_requested=5)
        self.assertEqual(v_dom["status"], "rig_dominated")
        self.assertEqual(v_dom["verdict"], "Rig-Dominated")

        # N < 2 -> Insufficient Data
        v_n1 = calculate_gage_rr_verdict(1.5, n_valid=1, total_requested=5)
        self.assertEqual(v_n1["status"], "insufficient_data")
        self.assertEqual(v_n1["verdict"], "Insufficient Data")

        # None CV -> Insufficient Data
        v_none = calculate_gage_rr_verdict(None, n_valid=5, total_requested=5)
        self.assertEqual(v_none["status"], "insufficient_data")

    def test_no_intermediate_file_cleanup_during_campaign(self):
        analyzer = RepeatabilityAnalyzer()

        with tempfile.TemporaryDirectory() as td:
            orig_file = os.path.join(td, "capture.mp4")
            aligned_file = os.path.join(td, "capture_aligned.mp4")
            ref_file = os.path.join(td, "reference.mp4")

            with open(orig_file, "w") as f:
                f.write("original")
            with open(aligned_file, "w") as f:
                f.write("aligned")
            with open(ref_file, "w") as f:
                f.write("ref")

            # Mock VMAFAnalyzer.run_analysis
            pass_call_count = 0
            original_exists_during_passes = []

            def fake_run_analysis(*args, **kwargs):
                nonlocal pass_call_count
                pass_call_count += 1
                # Check that original file still exists during each pass execution
                original_exists_during_passes.append(os.path.exists(orig_file))
                return {
                    "vmaf_score": 93.5 + pass_call_count * 0.1,
                    "psnr_score": 42.0,
                    "ssim_score": 0.98,
                    "aligned_path": aligned_file,
                    "distorted_path": aligned_file,
                    "measurement_metadata": {"model": "vmaf_v0.6.1"},
                }

            with patch("app.repeatability_analyzer.VMAFAnalyzer.analyze_videos", side_effect=fake_run_analysis):
                results = analyzer.run_campaign(
                    distorted_path=aligned_file,
                    reference_path=ref_file,
                    runs=3,
                    cleanup_after_campaign=True,
                )

            # Assert 3 passes ran
            self.assertEqual(pass_call_count, 3)
            # Assert original file existed throughout all passes
            self.assertEqual(original_exists_during_passes, [True, True, True])
            # Assert original was deleted once only AFTER the campaign completed
            self.assertFalse(os.path.exists(orig_file))
            # Assert aligned file remains preserved
            self.assertTrue(os.path.exists(aligned_file))
            self.assertEqual(results["n_completed"], 3)

    def test_partial_run_handling(self):
        analyzer = RepeatabilityAnalyzer()

        with tempfile.TemporaryDirectory() as td:
            aligned_file = os.path.join(td, "aligned.mp4")
            ref_file = os.path.join(td, "ref.mp4")
            with open(aligned_file, "w") as f:
                f.write("data")
            with open(ref_file, "w") as f:
                f.write("data")

            # Pass 1 succeeds, Pass 2 fails, Pass 3 succeeds
            results_pool = [
                {"vmaf_score": 94.0, "psnr_score": 42.0, "ssim_score": 0.98},
                None,  # failed pass
                {"vmaf_score": 95.0, "psnr_score": 43.0, "ssim_score": 0.99},
            ]
            call_idx = 0

            def fake_run(*args, **kwargs):
                nonlocal call_idx
                res = results_pool[call_idx]
                call_idx += 1
                return res

            with patch("app.repeatability_analyzer.VMAFAnalyzer.analyze_videos", side_effect=fake_run):
                campaign_res = analyzer.run_campaign(
                    distorted_path=aligned_file,
                    reference_path=ref_file,
                    runs=3,
                    cleanup_after_campaign=False,
                )

            self.assertIsNotNone(campaign_res)
            self.assertEqual(campaign_res["n_requested"], 3)
            self.assertEqual(campaign_res["n_completed"], 2)
            self.assertTrue(campaign_res["partial_run"])
            self.assertIn("2 of 3", campaign_res["caveat"])
            # Statistics should be calculated across the 2 successful passes (94 and 95 -> mean = 94.5)
            self.assertEqual(campaign_res["metrics"]["vmaf"]["n"], 2)
            self.assertAlmostEqual(campaign_res["metrics"]["vmaf"]["mean"], 94.5, places=2)

    def test_probe_called_once_per_campaign(self):
        analyzer = RepeatabilityAnalyzer()

        with patch("app.repeatability_analyzer.VMAFAnalyzer.probe_capabilities") as mock_probe:
            with patch("app.repeatability_analyzer.VMAFAnalyzer.analyze_videos", return_value={"vmaf_score": 95.0}):
                analyzer.run_campaign(
                    distorted_path="dummy_dist.mp4",
                    reference_path="dummy_ref.mp4",
                    runs=5,
                    cleanup_after_campaign=False,
                )

            # Probe should be invoked exactly once at campaign start
            self.assertEqual(mock_probe.call_count, 1)

    def test_campaign_thread_signals(self):
        thread = RepeatabilityCampaignThread(
            distorted_path="dist.mp4",
            reference_path="ref.mp4",
            runs=2,
            cleanup_after_campaign=False,
        )

        completed_signals = []
        progress_signals = []

        thread.campaign_complete.connect(lambda res: completed_signals.append(res))
        thread.campaign_progress.connect(lambda p: progress_signals.append(p))

        with patch.object(thread.analyzer, "run_campaign") as mock_run:
            mock_run.return_value = {"verdict": "Acceptable"}
            thread.run()

        mock_run.assert_called_once()

    def test_verdict_derived_from_vmaf_only(self):
        """Annotation 1: Verdict must key exclusively off VMAF %CV, even if PSNR/SSIM diverge."""
        # VMAF is tightly clustered: CV ~ 0.5% -> Acceptable
        # PSNR is wildly varying: CV > 35% -> would be Rig-Dominated if considered
        runs = [
            {"status": "success", "vmaf_score": 95.0, "psnr_score": 20.0, "ssim_score": 0.80},
            {"status": "success", "vmaf_score": 95.5, "psnr_score": 45.0, "ssim_score": 0.99},
            {"status": "success", "vmaf_score": 94.8, "psnr_score": 22.0, "ssim_score": 0.75},
        ]
        agg = aggregate_campaign_results(runs)
        self.assertEqual(agg["verdict"], "Acceptable")
        self.assertEqual(agg["verdict_status"], "acceptable")
        self.assertLess(agg["metrics"]["vmaf"]["cv_pct"], 1.0)
        self.assertGreater(agg["metrics"]["psnr"]["cv_pct"], 30.0)

    def test_insufficient_data_verdict_when_n_lt_2_or_half_failed(self):
        """Annotation 2: Effective N < 2 or >= 50% failure rate yields Insufficient Data verdict."""
        # N=1 run only
        runs_n1 = [{"status": "success", "vmaf_score": 95.0, "psnr_score": 40.0, "ssim_score": 0.95}]
        agg_n1 = aggregate_campaign_results(runs_n1, total_requested=1)
        self.assertEqual(agg_n1["verdict"], "Insufficient Data")
        self.assertEqual(agg_n1["verdict_status"], "insufficient_data")

        # 3 requested, but 2 failed (>= 50% failed)
        runs_half_fail = [
            {"status": "success", "vmaf_score": 95.0, "psnr_score": 40.0, "ssim_score": 0.95},
            {"status": "failed", "vmaf_score": None},
            {"status": "failed", "vmaf_score": None},
        ]
        agg_fail = aggregate_campaign_results(runs_half_fail, total_requested=3)
        self.assertEqual(agg_fail["verdict"], "Insufficient Data")
        self.assertEqual(agg_fail["verdict_status"], "insufficient_data")

    def test_truncation_flagged_pass_treated_as_failed(self):
        """Annotation 4: Truncation-flagged pass is treated as a failed pass."""
        analyzer = RepeatabilityAnalyzer()
        with tempfile.TemporaryDirectory() as td:
            aligned_file = os.path.join(td, "aligned.mp4")
            ref_file = os.path.join(td, "ref.mp4")
            with open(aligned_file, "w") as f:
                f.write("data")
            with open(ref_file, "w") as f:
                f.write("data")

            # Pass 1: normal, Pass 2: returns vmaf_score but flagged as truncated
            results_pool = [
                {"vmaf_score": 94.0, "psnr_score": 42.0, "ssim_score": 0.98},
                {"vmaf_score": 94.0, "psnr_score": 42.0, "ssim_score": 0.98, "truncation_detected": True},
            ]
            call_idx = 0

            def fake_run(*args, **kwargs):
                nonlocal call_idx
                res = results_pool[call_idx]
                call_idx += 1
                return res

            with patch("app.repeatability_analyzer.VMAFAnalyzer.analyze_videos", side_effect=fake_run):
                campaign_res = analyzer.run_campaign(
                    distorted_path=aligned_file,
                    reference_path=ref_file,
                    runs=2,
                    cleanup_after_campaign=False,
                )

            self.assertEqual(campaign_res["n_requested"], 2)
            self.assertEqual(campaign_res["n_completed"], 1)  # Only 1 pass succeeded
            self.assertTrue(campaign_res["partial_run"])
            self.assertIn("truncated capture", campaign_res["runs"][1]["error"])

    def test_near_lossless_pair_warning(self):
        """Observation 1: Near-lossless pair (SSIM > 0.999) emits an advisory warning."""
        runs = [
            {"status": "success", "vmaf_score": 99.8, "psnr_score": 60.0, "ssim_score": 1.0},
            {"status": "success", "vmaf_score": 99.8, "psnr_score": 60.0, "ssim_score": 1.0},
        ]
        agg = aggregate_campaign_results(runs)
        self.assertTrue(any("discriminative power is nil" in w for w in agg["warnings"]))


if __name__ == "__main__":
    unittest.main()
