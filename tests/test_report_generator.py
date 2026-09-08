import os
import sys
import tempfile
import pathlib
import unittest
from unittest.mock import patch, MagicMock

try:
    import pytest
except ImportError:
    pytest = None

from app.report_generator import ReportGenerator


def test_interpret_vmaf():
    gen = ReportGenerator.__new__(ReportGenerator)
    assert "bad" in gen._interpret_vmaf(10).lower()
    assert "excellent" in gen._interpret_vmaf(98).lower()


def test_interpret_psnr_ssim():
    gen = ReportGenerator.__new__(ReportGenerator)
    assert isinstance(gen._interpret_psnr(35.0), str)
    assert isinstance(gen._interpret_ssim(0.97), str)


def _run_cleanup_test(mock_doc, tmp_path):
    mock_doc.return_value.build.side_effect = RuntimeError("build failed")
    gen = ReportGenerator.__new__(ReportGenerator)
    gen.charts_data = []
    ok = gen.generate_report(str(tmp_path / "out.pdf"), {}, [])
    assert ok is False
    # tmp dir is auto-removed; no orphan PNGs remain in tmp_path
    assert not any(f.endswith(".png") for f in os.listdir(tmp_path))


@patch("app.report_generator.SimpleDocTemplate")
def test_cleanup_on_build_failure(mock_doc, tmp_path=None):
    if tmp_path is None:
        with tempfile.TemporaryDirectory() as td:
            _run_cleanup_test(mock_doc, pathlib.Path(td))
    else:
        _run_cleanup_test(mock_doc, tmp_path)


def test_measurement_conditions_section():
    gen = ReportGenerator()
    with tempfile.TemporaryDirectory() as td:
        out_pdf = os.path.join(td, "report.pdf")
        results = {
            "vmaf_score": 95.0,
            "psnr": 40.0,
            "ssim": 0.98,
            "measurement_metadata": {
                "model": "vmaf_v0.6.1",
                "libvmaf_version": "ffmpeg 7.1.1",
                "libvmaf_path_escaping": "triple_backslash",
                "alignment": {"frame_offset": 5},
                "capture": {"gaps_detected": False},
            }
        }
        built_elements = []
        with patch("app.report_generator.SimpleDocTemplate") as mock_doc_cls:
            mock_doc = MagicMock()
            def capture_build(elements):
                built_elements.extend(elements)
            mock_doc.build.side_effect = capture_build
            mock_doc_cls.return_value = mock_doc

            ok = gen.generate_report(out_pdf, results, {})
            assert bool(ok)


        from reportlab.platypus import Paragraph, Table
        para_texts = [el.text for el in built_elements if isinstance(el, Paragraph)]
        assert any("Measurement Conditions" in text for text in para_texts)

        tables = [el for el in built_elements if isinstance(el, Table)]
        table_found = False
        escaping_found = False
        for t in tables:
            for row in t._cellvalues:
                if any("vmaf_v0.6.1" in str(cell) for cell in row):
                    table_found = True
                if any("Model Path Escaping" in str(cell) for cell in row) and any("triple_backslash" in str(cell) for cell in row):
                    escaping_found = True
        assert table_found
        assert escaping_found


class TestReportGenerator(unittest.TestCase):
    def test_interpret_vmaf(self):
        test_interpret_vmaf()

    def test_interpret_psnr_ssim(self):
        test_interpret_psnr_ssim()

    def test_cleanup_on_build_failure(self):
        test_cleanup_on_build_failure()

    def test_measurement_conditions_section(self):
        test_measurement_conditions_section()

    def test_gage_rr_report_section_renders_with_n_gte_2(self):
        gen = ReportGenerator()
        with tempfile.TemporaryDirectory() as td:
            out_pdf = os.path.join(td, "report_gage_rr.pdf")
            results = {
                "vmaf_score": 93.5,
                "psnr": 42.0,
                "ssim": 0.98,
                "repeatability": {
                    "n_requested": 3,
                    "n_completed": 3,
                    "partial_run": False,
                    "caveat": "",
                    "metrics": {
                        "vmaf": {"n": 3, "mean": 93.5, "stddev": 0.45, "min": 93.0, "max": 93.9, "range": 0.9, "cv_pct": 0.481},
                        "psnr": {"n": 3, "mean": 42.0, "stddev": 0.10, "min": 41.9, "max": 42.1, "range": 0.2, "cv_pct": 0.238},
                        "ssim": {"n": 3, "mean": 0.98, "stddev": 0.002, "min": 0.978, "max": 0.982, "range": 0.004, "cv_pct": 0.204},
                    },
                    "runs": [
                        {"pass": 1, "status": "success", "vmaf_score": 93.0},
                        {"pass": 2, "status": "success", "vmaf_score": 93.6},
                        {"pass": 3, "status": "success", "vmaf_score": 93.9},
                    ],
                    "verdict": "Acceptable",
                    "verdict_status": "acceptable",
                    "verdict_description": "Instrument uncertainty < 10% (Repeatability acceptable)",
                    "warnings": [],
                }
            }

            built_elements = []
            with patch("app.report_generator.SimpleDocTemplate") as mock_doc_cls:
                mock_doc = MagicMock()
                mock_doc.build.side_effect = lambda els: built_elements.extend(els)
                mock_doc_cls.return_value = mock_doc

                ok = gen.generate_report(out_pdf, results, {})
                self.assertTrue(bool(ok))

            from reportlab.platypus import Paragraph, Table, Image
            all_texts = [el.text for el in built_elements if isinstance(el, Paragraph)]
            for el in built_elements:
                if isinstance(el, Table):
                    for row in el._cellvalues:
                        for cell in row:
                            if isinstance(cell, Paragraph):
                                all_texts.append(cell.text)
                            elif isinstance(cell, str):
                                all_texts.append(cell)

            self.assertTrue(any("Gage R&R Repeatability Analysis" in text for text in all_texts))
            self.assertTrue(any("Acceptable" in text for text in all_texts))

            # Table should contain VMAF distribution
            tables = [el for el in built_elements if isinstance(el, Table)]
            vmaf_row_found = False
            for t in tables:
                for row in t._cellvalues:
                    if any("VMAF" in str(cell) for cell in row) and any("93.5" in str(cell) for cell in row):
                        vmaf_row_found = True
                        break
            self.assertTrue(vmaf_row_found)

            # Sequence chart should be included
            images = [el for el in built_elements if isinstance(el, Image)]
            self.assertTrue(len(images) > 0)

    def test_gage_rr_report_section_graceful_at_n_1(self):
        gen = ReportGenerator()
        with tempfile.TemporaryDirectory() as td:
            out_pdf = os.path.join(td, "report_n1.pdf")
            results = {
                "vmaf_score": 94.0,
                "repeatability": {
                    "n_requested": 1,
                    "n_completed": 1,
                    "partial_run": False,
                    "metrics": {
                        "vmaf": {"n": 1, "mean": 94.0, "stddev": 0.0, "min": 94.0, "max": 94.0, "range": 0.0, "cv_pct": 0.0}
                    },
                    "runs": [{"pass": 1, "status": "success", "vmaf_score": 94.0}],
                }
            }

            built_elements = []
            with patch("app.report_generator.SimpleDocTemplate") as mock_doc_cls:
                mock_doc = MagicMock()
                mock_doc.build.side_effect = lambda els: built_elements.extend(els)
                mock_doc_cls.return_value = mock_doc

                ok = gen.generate_report(out_pdf, results, {})
                self.assertTrue(bool(ok))

            from reportlab.platypus import Paragraph
            para_texts = [el.text for el in built_elements if isinstance(el, Paragraph)]
            self.assertTrue(any("requires at least N=2 runs" in text for text in para_texts))



if __name__ == "__main__":
    unittest.main()

