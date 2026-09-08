#!/usr/bin/env python3
"""
Hardware Re-Capture Gage R&R Campaign Runner.

Capstone Metrology Runner:
    Analyzes multiple independent physical video captures (e.g. from DeckLink / HDMI capture)
    against a common reference video using libvmaf, computing empirical capture-chain variance (sigma_rig)
    and repeatability (%CV_rig).

    Logs the campaign to logs/campaign_history.jsonl as campaign_type='recapture' and generates a branded PDF report.
"""

import argparse
import glob
import json
import logging
import os
import sys
import time
from typing import Dict, Any, List

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.options_manager import OptionsManager
from app.repeatability_analyzer import (
    calculate_metric_statistics,
    calculate_gage_rr_verdict,
    aggregate_campaign_results,
    log_campaign_history,
    get_campaign_history_log_path,
)
from app.report_generator import ReportGenerator
from app.utils import get_video_info, get_file_sha256
from app.version import get_version_string, get_git_commit
from app.vmaf_analyzer import VMAFAnalyzer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("recapture_campaign")


def resolve_capture_files(capture_args: List[str]) -> List[str]:
    """Resolve glob patterns or multiple file arguments into sorted unique absolute file paths."""
    resolved = []
    for arg in capture_args:
        if any(c in arg for c in ["*", "?", "["]):
            matches = glob.glob(arg)
            resolved.extend([os.path.abspath(m) for m in matches])
        elif os.path.isfile(arg):
            resolved.append(os.path.abspath(arg))
        else:
            logger.warning(f"File or pattern not found: {arg}")

    unique_files = sorted(list(dict.fromkeys(resolved)))
    return unique_files


def run_recapture_campaign(args: argparse.Namespace) -> Dict[str, Any]:
    """Execute the multi-capture Gage R&R campaign and return the aggregated payload."""
    ref_path = os.path.abspath(args.ref)
    if not os.path.exists(ref_path):
        raise FileNotFoundError(f"Reference video file not found: {ref_path}")

    capture_files = resolve_capture_files(args.captures)
    if len(capture_files) < 2:
        raise ValueError(
            f"Hardware re-capture campaign requires at least 2 capture files (found {len(capture_files)}). "
            f"Pass multiple capture files: --captures cap1.mp4 cap2.mp4 ... or a glob pattern."
        )

    ref_meta = get_video_info(ref_path)
    if not ref_meta:
        raise ValueError(f"Could not extract metadata from reference: {ref_path}")

    print("\n" + "=" * 76)
    print(f" HARDWARE RE-CAPTURE GAGE R&R CAMPAIGN — {get_version_string()}")
    print(f" Mode: Hardware Re-Capture Repeatability (N={len(capture_files)} physical captures)")
    print(f" Reference: {ref_path} ({ref_meta.get('width')}x{ref_meta.get('height')} @ {ref_meta.get('fps', 0):.2f} fps)")
    print(f" VMAF Model: {args.model}")
    print(f" Captures ({len(capture_files)} files):")
    for idx, c_path in enumerate(capture_files, 1):
        c_size_mb = os.path.getsize(c_path) / (1024 * 1024)
        print(f"  [{idx}/{len(capture_files)}] {os.path.basename(c_path)} ({c_size_mb:.2f} MB)")
    print("=" * 76 + "\n")

    analyzer = VMAFAnalyzer()
    opts = OptionsManager()
    analyzer.set_options_from_manager(opts)

    # Session Note 2: Explicit pre-flight gate assertion on frame count uniformity and alignment
    ref_frames = ref_meta.get("total_frames")
    allow_mismatch = getattr(args, "allow_frame_mismatch", False)
    cap_frame_counts = {}

    for c_path in capture_files:
        c_name = os.path.basename(c_path)
        c_meta = get_video_info(c_path)
        if not c_meta:
            raise ValueError(f"Could not extract metadata from capture: {c_path}")
        if c_meta.get("width") != ref_meta.get("width") or c_meta.get("height") != ref_meta.get("height"):
            raise ValueError(
                f"Dimension mismatch in {c_name}: {c_meta.get('width')}x{c_meta.get('height')} "
                f"vs ref {ref_meta.get('width')}x{ref_meta.get('height')}"
            )
        c_frames = c_meta.get("total_frames")
        cap_frame_counts[c_name] = c_frames

    # Assert uniform frame count across captures
    unique_counts = set(cap_frame_counts.values())
    if len(unique_counts) > 1 and not allow_mismatch:
        counts_str = ", ".join([f"{k}: {v} frames" for k, v in cap_frame_counts.items()])
        raise ValueError(
            f"Frame count mismatch across captures: [{counts_str}]. "
            f"All captures must be frame-aligned to identical lengths via bookends for valid Gage R&R repeatability. "
            f"Pass --allow-frame-mismatch to bypass."
        )

    # Assert capture frame count matches reference if ref_frames is known
    if ref_frames and any(v != ref_frames for v in cap_frame_counts.values()) and not allow_mismatch:
        mismatched = {k: v for k, v in cap_frame_counts.items() if v != ref_frames}
        counts_str = ", ".join([f"{k}: {v} frames" for k, v in mismatched.items()])
        raise ValueError(
            f"Capture frame count does not match reference ({ref_frames} frames): [{counts_str}]. "
            f"All captures must be bookend-aligned to the reference span. Pass --allow-frame-mismatch to bypass."
        )

    runs_data = []
    t_start = time.time()

    for pass_idx, cap_file in enumerate(capture_files, 1):
        cap_basename = os.path.basename(cap_file)
        logger.info(f"--- Running Analysis on Capture [{pass_idx}/{len(capture_files)}]: {cap_basename} ---")
        p_start = time.time()

        try:

            # Analyze pass
            pass_res = analyzer.analyze_videos(
                distorted=cap_file,
                reference=ref_path,
                model=args.model
            )

            p_duration = round(time.time() - p_start, 2)

            if pass_res and pass_res.get("vmaf_score") is not None:
                record = {
                    "pass": pass_idx,
                    "status": "success",
                    "duration_seconds": p_duration,
                    "vmaf_score": pass_res.get("vmaf_score"),
                    "psnr_score": pass_res.get("psnr_score"),
                    "ssim_score": pass_res.get("ssim_score"),
                    "distorted_file": cap_basename,
                    "distorted_path": cap_file,
                    "distorted_sha256": get_file_sha256(cap_file),
                    "raw_results": pass_res.get("raw_results"),
                    "measurement_metadata": pass_res.get("measurement_metadata"),
                }
                logger.info(
                    f"Pass {pass_idx}/{len(capture_files)} SUCCESS ({p_duration}s): "
                    f"VMAF={record['vmaf_score']:.2f}, PSNR={record['psnr_score']}, SSIM={record['ssim_score']}"
                )
            else:
                record = {
                    "pass": pass_idx,
                    "status": "failed",
                    "duration_seconds": p_duration,
                    "vmaf_score": None,
                    "distorted_file": cap_basename,
                    "distorted_path": cap_file,
                    "distorted_sha256": get_file_sha256(cap_file),
                    "error": "Analysis returned empty or null VMAF score",
                }
                logger.warning(f"Pass {pass_idx}/{len(capture_files)} FAILED: {record['error']}")

        except Exception as e:
            p_duration = round(time.time() - p_start, 2)
            record = {
                "pass": pass_idx,
                "status": "failed",
                "duration_seconds": p_duration,
                "vmaf_score": None,
                "distorted_file": cap_basename,
                "distorted_path": cap_file,
                "distorted_sha256": get_file_sha256(cap_file) if os.path.exists(cap_file) else "unknown",
                "error": str(e),
            }
            logger.error(f"Pass {pass_idx}/{len(capture_files)} EXCEPTION: {e}")

        runs_data.append(record)

    total_duration = round(time.time() - t_start, 2)

    # Build traceability metadata & run configuration
    device_name = getattr(args, "device", None) or opts.get_setting("capture", "device_name") or "Blackmagic DeckLink / HDMI Ingestion"
    display_setting = getattr(args, "display_setting", None) or "1080p29.97 SDR HDMI Native"

    pair_metadata = {
        "reference_file": os.path.basename(ref_path),
        "reference_path": ref_path,
        "reference_sha256": get_file_sha256(ref_path),
        "distorted_file": f"recapture_set_{len(capture_files)}_passes",
        "distorted_path": os.path.dirname(capture_files[0]),
        "distorted_sha256": "multi_capture_set",
        "model": args.model,
        "ffmpeg_version": analyzer.probe_capabilities().get("ffmpeg_version", "unknown"),
        "campaign_type": "recapture",
        "device": device_name,
        "display_setting": display_setting,
        "resolution": f"{ref_meta.get('width')}x{ref_meta.get('height')}",
        "fps": ref_meta.get("fps"),
        "total_frames": ref_meta.get("total_frames"),
        "app_version": get_version_string(),
        "git_commit": get_git_commit(short=True),
    }

    # Aggregate Gage R&R
    drift_threshold = float(opts.get_setting("analysis", "stability_threshold") or 1.0)
    aggregated = aggregate_campaign_results(
        runs=runs_data,
        warning_threshold_drift=drift_threshold,
        total_requested=len(capture_files),
        campaign_type="recapture",
        pair_metadata=pair_metadata,
    )

    # Log to JSONL
    log_path = args.log_path or get_campaign_history_log_path()
    try:
        log_campaign_history(aggregated, log_path=log_path)
        logger.info(f"Appended hardware re-capture campaign to JSONL history: {log_path}")
    except Exception as e:
        logger.warning(f"Could not append to JSONL history: {e}")

    # Print ASCII Summary
    vmaf_s = aggregated["metrics"]["vmaf"]
    psnr_s = aggregated["metrics"]["psnr"]
    ssim_s = aggregated["metrics"]["ssim"]

    print("\n" + "=" * 76)
    print(" HARDWARE RE-CAPTURE GAGE R&R METROLOGY CERTIFICATE")
    print("=" * 76)
    print(f" Passes Completed : {aggregated['n_completed']} / {aggregated['n_requested']}")
    print(f" Total Duration   : {total_duration:.2f}s")
    print(f" Campaign Type    : recapture (Physical Hardware Capture-Chain)")
    print(f" Reference Fixture: {pair_metadata['reference_file']} ({pair_metadata['reference_sha256']})")
    print(f" Gage R&R Verdict : {aggregated['verdict']} [{aggregated['verdict_status'].upper()}]")
    print(f" Verdict Details  : {aggregated['verdict_description']}")
    print("-" * 76)
    print(f" VMAF Distribution: Mean = {vmaf_s['mean']:.2f} | StdDev (sigma_rig) = {vmaf_s['stddev']:.4f} | Range = {vmaf_s['range']:.4f} | %CV_rig = {vmaf_s['cv_pct']:.3f}%")
    if psnr_s.get("mean"):
        print(f" PSNR Distribution: Mean = {psnr_s['mean']:.2f} dB | StdDev = {psnr_s['stddev']:.4f} dB | Range = {psnr_s['range']:.4f} dB")
    if ssim_s.get("mean"):
        print(f" SSIM Distribution: Mean = {ssim_s['mean']:.4f} | StdDev = {ssim_s['stddev']:.6f} | Range = {ssim_s['range']:.6f}")
    print("-" * 76)

    print("\n Individual Capture Passes:")
    print(f" {'Pass':<6} | {'Capture File':<32} | {'VMAF':<8} | {'PSNR (dB)':<10} | {'SSIM':<8} | {'Duration':<8}")
    print("-" * 76)
    for r in runs_data:
        p_num = f"#{r['pass']}"
        f_name = r.get("distorted_file", "unknown")[:32]
        v_str = f"{r['vmaf_score']:.2f}" if r.get("vmaf_score") is not None else "FAILED"
        p_str = f"{r['psnr_score']:.2f}" if r.get("psnr_score") is not None else "—"
        s_str = f"{r['ssim_score']:.4f}" if r.get("ssim_score") is not None else "—"
        d_str = f"{r.get('duration_seconds', 0.0):.2f}s"
        print(f" {p_num:<6} | {f_name:<32} | {v_str:<8} | {p_str:<10} | {s_str:<8} | {d_str:<8}")
    print("-" * 76)

    # Generate PDF Report
    out_pdf = os.path.abspath(args.out_pdf)
    os.makedirs(os.path.dirname(out_pdf), exist_ok=True)
    report_gen = ReportGenerator()

    analysis_results = {
        "vmaf_score": vmaf_s.get("mean"),
        "psnr_score": psnr_s.get("mean"),
        "ssim_score": ssim_s.get("mean"),
        "repeatability": aggregated,
        "measurement_metadata": pair_metadata,
    }

    report_metadata = {
        "reference_path": ref_path,
        "distorted_path": capture_files[0],
        "test_name": args.test_name or f"Hardware Re-Capture Gage R&R ({len(capture_files)} passes)",
        "description": f"Empirical capture-chain uncertainty characterized across {len(capture_files)} independent physical display passes on {device_name} ({display_setting}).",
    }

    print(f"\nGenerating Hardware Re-Capture PDF Report -> {out_pdf}")
    pdf_path = report_gen.generate_report(out_pdf, analysis_results, report_metadata)
    if pdf_path and os.path.exists(pdf_path):
        print(f" [PASS] PDF report generated: {pdf_path} ({os.path.getsize(pdf_path):,} bytes)")
    else:
        logger.error(f"Failed to generate PDF report at {out_pdf}")

    print("=" * 76 + "\n")
    return aggregated


def main():
    parser = argparse.ArgumentParser(description="Execute Hardware Re-Capture Gage R&R Campaign")
    parser.add_argument(
        "--ref",
        required=True,
        help="Path to golden reference video file"
    )
    parser.add_argument(
        "--captures",
        nargs="+",
        required=True,
        help="List of physical capture video files, or a quoted glob pattern (e.g. 'captures/pass*.mp4')"
    )
    parser.add_argument(
        "--model",
        default="vmaf_v0.6.1",
        help="VMAF model name (default: vmaf_v0.6.1)"
    )
    parser.add_argument(
        "--device",
        default=None,
        help="Capture hardware device name (default: from settings or auto-detected)"
    )
    parser.add_argument(
        "--display-setting",
        default=None,
        help="Display loop settings (e.g. '1080p29.97 SDR HDMI Native')"
    )
    parser.add_argument(
        "--allow-frame-mismatch",
        action="store_true",
        help="Allow capture passes with varying frame counts (warning: content misalignment invalidates Gage R&R)"
    )
    parser.add_argument(
        "--out-pdf",
        default=os.path.join("reports", "gage_rr_hardware_recapture.pdf"),
        help="Output PDF path for the Gage R&R certificate"
    )
    parser.add_argument(
        "--log-path",
        default=None,
        help="Custom JSONL campaign history path"
    )
    parser.add_argument(
        "--test-name",
        default=None,
        help="Custom test title for PDF report"
    )

    args = parser.parse_args()
    try:
        run_recapture_campaign(args)
        sys.exit(0)
    except Exception as e:
        logger.error(f"Hardware Re-Capture Campaign failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
