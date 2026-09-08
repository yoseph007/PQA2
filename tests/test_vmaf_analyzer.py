import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from PyQt5.QtWidgets import QApplication

app = QApplication.instance()
if not app:
    app = QApplication([])

import re
from app.vmaf_analyzer import (
    AnalysisCapabilityError,
    VMAFAnalyzer,
    build_vmaf_model_option,
)


def extracted_stats_paths(filter_str: str):
    matches = re.findall(r"stats_file=(?:'([^']+)'|([^\s:;,]+))", filter_str)
    paths = []
    for m in matches:
        raw_p = m[0] or m[1]
        clean_p = raw_p.replace(r"\:", ":")
        paths.append(clean_p)
    return paths


class TestVMAFAnalyzer(unittest.TestCase):
    def test_model_option_named_builtin(self):
        opt = build_vmaf_model_option("vmaf_v0.6.1")
        self.assertEqual(opt, "version=vmaf_v0.6.1")

    def test_model_option_file_path(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            tf.write(b"{}")
            temp_path = tf.name

        try:
            opt = build_vmaf_model_option(temp_path)
            self.assertTrue(opt.startswith("path="))
            self.assertIn(".json", opt)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_model_option_4k_uses_path(self):
        opt = build_vmaf_model_option("vmaf_4k_v0.6.1")
        self.assertTrue(opt.startswith("path="))
        self.assertIn("vmaf_4k_v0.6.1.json", opt)

    def test_distorted_cleanup_only_when_aligned(self):
        analyzer = VMAFAnalyzer()
        with tempfile.TemporaryDirectory() as td:
            # Case 1: delete_aligned_original = True
            analyzer.delete_aligned_original = True
            orig1 = os.path.join(td, "capture.mp4")
            aligned1 = os.path.join(td, "capture_aligned.mp4")
            with open(orig1, "w") as f:
                f.write("orig")
            with open(aligned1, "w") as f:
                f.write("aligned")

            json_file1 = os.path.join(td, "res1.json")
            with open(json_file1, "w") as f:
                json.dump({"pooled_metrics": {"vmaf": {"mean": 90.0}}}, f)

            with patch.object(analyzer, "get_video_metadata", return_value={}):
                analyzer._parse_vmaf_results(
                    json_path=json_file1,
                    distorted_path=aligned1,
                    reference_path=orig1,
                )

            self.assertFalse(os.path.exists(orig1))
            self.assertTrue(os.path.exists(aligned1))

            # Case 2: delete_aligned_original = False
            analyzer.delete_aligned_original = False
            orig2 = os.path.join(td, "capture2.mp4")
            aligned2 = os.path.join(td, "capture2_aligned.mp4")
            with open(orig2, "w") as f:
                f.write("orig2")
            with open(aligned2, "w") as f:
                f.write("aligned2")

            json_file2 = os.path.join(td, "res2.json")
            with open(json_file2, "w") as f:
                json.dump({"pooled_metrics": {"vmaf": {"mean": 90.0}}}, f)

            with patch.object(analyzer, "get_video_metadata", return_value={}):
                analyzer._parse_vmaf_results(
                    json_path=json_file2,
                    distorted_path=aligned2,
                    reference_path=orig2,
                )

            self.assertTrue(os.path.exists(orig2))
            self.assertTrue(os.path.exists(aligned2))

    def test_no_max_samples_in_filter(self):
        analyzer = VMAFAnalyzer()
        analyzer.feature_subsample = 4

        captured_cmds = []

        def fake_run(cmd, *args, **kwargs):
            captured_cmds.append(cmd)
            res = MagicMock()
            res.returncode = 0
            return res

        with patch("subprocess.run", side_effect=fake_run):
            analyzer._run_psnr_ssim_analysis(
                ffmpeg_exe="ffmpeg",
                distorted_path="dist.mp4",
                reference_path="ref.mp4",
                psnr_path="psnr.txt",
                ssim_path="ssim.txt",
            )

        self.assertEqual(len(captured_cmds), 2)
        for cmd in captured_cmds:
            cmd_str = " ".join(cmd)
            self.assertNotIn(":max_samples=", cmd_str)
            self.assertNotIn("max_samples", cmd_str)

    def test_metadata_json_parsing(self):
        analyzer = VMAFAnalyzer()
        fake_ffprobe_output = {
            "streams": [
                {
                    "codec_type": "video",
                    "width": 1920,
                    "height": 1080,
                    "avg_frame_rate": "30000/1001",
                    "nb_frames": "300",
                    "pix_fmt": "yuv420p",
                    "codec_name": "h264",
                }
            ],
            "format": {
                "duration": "10.01",
                "bit_rate": "5000000",
            },
        }

        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = json.dumps(fake_ffprobe_output)

        with patch("os.path.exists", return_value=True):
            with patch("subprocess.run", return_value=mock_res):
                meta = analyzer.get_video_metadata("dummy.mp4", ffprobe_exe="ffprobe")

        self.assertIsNotNone(meta)
        self.assertEqual(meta["width"], 1920)
        self.assertEqual(meta["height"], 1080)
        self.assertAlmostEqual(meta["frame_rate"], 29.97, places=2)
        self.assertEqual(meta["nb_frames"], 300)
        self.assertEqual(meta["total_frames"], 300)
        self.assertEqual(meta["codec_name"], "h264")

    def test_metadata_embedded_in_results(self):
        analyzer = VMAFAnalyzer()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            data = {
                "pooled_metrics": {
                    "vmaf": {"mean": 96.25},
                    "float_ssim": {"mean": 0.985},
                    "psnr_y": {"mean": 43.10},
                }
            }
            tf.write(json.dumps(data).encode("utf-8"))
            json_path = tf.name

        try:
            with patch.object(analyzer, "get_video_metadata", return_value={"width": 1920, "height": 1080}):
                results = analyzer._parse_vmaf_results(
                    json_path=json_path,
                    distorted_path="aligned.mp4",
                    reference_path="ref.mp4",
                    model="vmaf_v0.6.1",
                    alignment_metadata={"frame_offset": 8},
                    capture_metadata={"gaps_detected": False},
                    caps={"ffmpeg_version": "ffmpeg 7.1.1"},
                )

            self.assertIsNotNone(results)
            self.assertEqual(results["vmaf_score"], 96.25)
            self.assertEqual(results["ssim_score"], 0.985)
            self.assertEqual(results["psnr_score"], 43.10)
            self.assertIn("aligned_path", results)
            self.assertIn("distorted_path", results)
            self.assertIn("measurement_metadata", results)
            meas = results["measurement_metadata"]
            self.assertEqual(meas["model"], "vmaf_v0.6.1")
            self.assertEqual(meas["alignment"]["frame_offset"], 8)
            self.assertFalse(meas["capture"]["gaps_detected"])
            self.assertEqual(meas["libvmaf_version"], "ffmpeg 7.1.1")
        finally:
            if os.path.exists(json_path):
                os.remove(json_path)

    def test_fallback_subsample_select_filter(self):
        analyzer = VMAFAnalyzer()
        filt = analyzer._build_fallback_chain(metric="psnr", stats_file="psnr.log", feature_subsample=3)
        self.assertIn("not(mod(n\\,3))", filt)
        self.assertNotIn("max_samples", filt)

    def test_fallback_stats_paths_absolute(self):
        analyzer = VMAFAnalyzer()
        filt = analyzer._build_fallback_chain(metric="psnr", stats_file="psnr.log", feature_subsample=1)
        paths = extracted_stats_paths(filt)
        self.assertTrue(len(paths) > 0)
        self.assertTrue(all(os.path.isabs(p) for p in paths))

    def test_probe_model_path_form_success(self):
        # Reset cached capabilities
        VMAFAnalyzer._cached_capabilities = None

        # Mock dryrun so candidate 0 (triple_backslash) fails, candidate 1 (single_backslash) succeeds
        def fake_dryrun(ffmpeg_exe, model_opt):
            return "single_backslash" in model_opt or (r"\:" in model_opt and r"\\\:" not in model_opt)

        with patch.object(VMAFAnalyzer, "_one_frame_dryrun", side_effect=fake_dryrun):
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
                tf.write(b"{}")
                sample_model = tf.name
            try:
                winning = VMAFAnalyzer._probe_model_path_form("ffmpeg", sample_model_path=sample_model)
                self.assertEqual(winning, "single_backslash")
            finally:
                if os.path.exists(sample_model):
                    os.remove(sample_model)

        # Also verify via probe_capabilities that libvmaf_path_escaping is cached
        VMAFAnalyzer._cached_capabilities = None
        mock_v_res = MagicMock()
        mock_v_res.returncode = 0
        mock_v_res.stdout = "ffmpeg version 7.1.1 --enable-libvmaf"
        mock_h_res = MagicMock()
        mock_h_res.returncode = 0
        mock_h_res.stdout = "libvmaf AVOptions"

        with patch("subprocess.run", side_effect=[mock_v_res, mock_h_res]):
            with patch.object(VMAFAnalyzer, "_probe_model_path_form", return_value="single_backslash"):
                caps = VMAFAnalyzer.probe_capabilities("ffmpeg")
                self.assertEqual(caps["libvmaf_path_escaping"], "single_backslash")

        # Clean up cache
        VMAFAnalyzer._cached_capabilities = None

    def test_probe_model_path_form_all_fail_raises(self):
        VMAFAnalyzer._cached_capabilities = None
        with patch.object(VMAFAnalyzer, "_one_frame_dryrun", return_value=False):
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
                tf.write(b"{}")
                sample_model = tf.name
            try:
                with self.assertRaises(AnalysisCapabilityError):
                    VMAFAnalyzer._probe_model_path_form("ffmpeg", sample_model_path=sample_model)
            finally:
                if os.path.exists(sample_model):
                    os.remove(sample_model)
        VMAFAnalyzer._cached_capabilities = None

    def test_probe_model_path_form_malformed_json_differentiates(self):
        VMAFAnalyzer._cached_capabilities = None
        # Simulate dryrun returning model JSON corruption error
        with patch.object(VMAFAnalyzer, "_one_frame_dryrun", return_value=(False, "could not read model: invalid json syntax")):
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
                tf.write(b"bad json")
                sample_model = tf.name
            try:
                with self.assertRaises(AnalysisCapabilityError) as ctx:
                    VMAFAnalyzer._probe_model_path_form("ffmpeg", sample_model_path=sample_model)
                self.assertIn("malformed or corrupted model JSON", str(ctx.exception))
            finally:
                if os.path.exists(sample_model):
                    os.remove(sample_model)
        VMAFAnalyzer._cached_capabilities = None


if __name__ == "__main__":
    unittest.main()
