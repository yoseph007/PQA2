#!/usr/bin/env python3
"""Gage R&R Baseline Campaign Runner.

Metrology Framing & Expectation:
    This campaign runs a "Fixed-Pair Determinism Baseline", NOT a rig repeatability figure.
    Comparing two static digital files with libvmaf is a deterministic computation (same
    frames in -> same scores out). Therefore:
      - VMAF standard deviation (sigma) across passes will be ~0.0000 (%CV ~0.0%).
      - This proves decode/filter pipeline determinism (an essential prerequisite).
      - CRF 28 transcoding ensures quality drops are non-trivial (VMAF ~75-88, PSNR ~35-42,
        SSIM ~0.94-0.98), exercising the full metric math and silencing near-lossless advisories.
      - Rig repeatability / capture-chain uncertainty requires capturing display output
        across hardware passes; this script accepts parameterized --ref and --dist to
        seamlessly support that follow-up workflow with zero code changes.

Fixture Generation:
    The fixture (e.g. tests/test_references/DANCE__crf28.mp4) is deterministic-per-machine,
    regenerable on demand, and gitignored.
"""

import argparse
import logging
import os
import subprocess
import sys
import time
from typing import Dict, Any

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.options_manager import OptionsManager
from app.repeatability_analyzer import RepeatabilityAnalyzer
from app.report_generator import ReportGenerator
from app.utils import get_ffmpeg_path, get_subprocess_startupinfo, get_video_info
from app.version import get_version_string

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("gage_rr_baseline")


def transcode_fixture_if_needed(
    ref_path: str,
    dist_path: str,
    crf: int = 28,
    preset: str = "fast",
    force: bool = False
) -> None:
    """Ensure the degraded test fixture exists; transcode with libx264 if missing."""
    if os.path.exists(dist_path) and not force:
        logger.info(f"Using existing test fixture: {dist_path}")
        return

    logger.info(f"Generating test fixture from {ref_path} -> {dist_path} (CRF {crf}, preset {preset})...")
    os.makedirs(os.path.dirname(dist_path), exist_ok=True)

    ffmpeg_exe, _, _ = get_ffmpeg_path()
    startupinfo, creationflags = get_subprocess_startupinfo()

    cmd = [
        str(ffmpeg_exe),
        "-hide_banner",
        "-y",
        "-i", ref_path,
        "-c:v", "libx264",
        "-crf", str(crf),
        "-preset", preset,
        "-pix_fmt", "yuv420p",
        dist_path
    ]

    t0 = time.time()
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        startupinfo=startupinfo,
        creationflags=creationflags
    )
    if result.returncode != 0:
        logger.error(f"FFmpeg transcode failed:\n{result.stderr}")
        raise RuntimeError(f"Failed to transcode fixture: {result.stderr}")

    duration = time.time() - t0
    size_mb = os.path.getsize(dist_path) / (1024 * 1024)
    logger.info(f"Fixture generated in {duration:.2f}s ({size_mb:.2f} MB)")


def verify_pair_metadata(ref_path: str, dist_path: str) -> None:
    """Validate that reference and distorted fixtures match dimensions, fps, and frame count."""
    ref_meta = get_video_info(ref_path)
    dist_meta = get_video_info(dist_path)

    if not ref_meta or not dist_meta:
        raise ValueError(f"Could not extract metadata for pair: ref={ref_meta}, dist={dist_meta}")

    logger.info(f"Reference metadata: {ref_meta['width']}x{ref_meta['height']} @ {ref_meta['fps']:.2f} fps, "
                f"{ref_meta['total_frames']} frames, {ref_meta['duration']:.2f}s")
    logger.info(f"Distorted metadata: {dist_meta['width']}x{dist_meta['height']} @ {dist_meta['fps']:.2f} fps, "
                f"{dist_meta['total_frames']} frames, {dist_meta['duration']:.2f}s")

    # Assert dimension match
    assert ref_meta["width"] == dist_meta["width"], (
        f"Width mismatch: {ref_meta['width']} vs {dist_meta['width']}"
    )
    assert ref_meta["height"] == dist_meta["height"], (
        f"Height mismatch: {ref_meta['height']} vs {dist_meta['height']}"
    )

    # Assert frame count match
    assert ref_meta["total_frames"] == dist_meta["total_frames"], (
        f"Frame count mismatch: {ref_meta['total_frames']} vs {dist_meta['total_frames']}"
    )

    # Assert FPS match
    assert abs(ref_meta["fps"] - dist_meta["fps"]) < 0.05, (
        f"FPS mismatch: {ref_meta['fps']} vs {dist_meta['fps']}"
    )


def run_baseline_campaign(args: argparse.Namespace) -> Dict[str, Any]:
    """Execute the Gage R&R baseline campaign and return the payload."""
    ref_path = os.path.abspath(args.ref)
    dist_path = os.path.abspath(args.dist)

    if not os.path.exists(ref_path):
        raise FileNotFoundError(f"Reference file not found: {ref_path}")

    # Step 1: Ensure fixture exists
    transcode_fixture_if_needed(
        ref_path=ref_path,
        dist_path=dist_path,
        crf=args.crf,
        preset=args.preset,
        force=args.force_transcode
    )

    # Step 2: Verify alignment prerequisites (dimensions, fps, frames)
    verify_pair_metadata(ref_path, dist_path)

    # Step 3: Run Gage R&R Campaign via RepeatabilityAnalyzer
    print("\n" + "=" * 72)
    print(f" GAGE R&R BASELINE CAMPAIGN — {get_version_string()}")
    print(f" Mode: Fixed-Pair Determinism Baseline (N={args.runs} passes)")
    print(f" Reference: {ref_path}")
    print(f" Distorted: {dist_path}")
    print(f" VMAF Model: {args.model}")
    print("=" * 72 + "\n")

    analyzer = RepeatabilityAnalyzer()
    opts = OptionsManager()

    t_start = time.time()
    campaign_res = analyzer.run_campaign(
        distorted_path=dist_path,
        reference_path=ref_path,
        model=args.model,
        runs=args.runs,
        options_manager=opts,
        cleanup_after_campaign=False,
        campaign_type=getattr(args, "campaign_type", "fixed_pair"),
    )
    total_duration = time.time() - t_start

    if not campaign_res:
        raise RuntimeError("Campaign execution returned None!")

    # Step 4: Consume results and print summary (NO forked verdict logic)
    metrics = campaign_res["metrics"]
    vmaf_m = metrics["vmaf"]
    psnr_m = metrics["psnr"]
    ssim_m = metrics["ssim"]

    print("\n" + "-" * 72)
    print(" CAMPAIGN METROLOGY SUMMARY")
    print("-" * 72)
    print(f"Passes Completed : {campaign_res['n_completed']} / {campaign_res['n_requested']}")
    print(f"Total Duration   : {total_duration:.2f}s")
    print(f"Campaign Type    : {campaign_res.get('campaign_type', 'fixed_pair')}")
    print(f"Reference Fixture: {campaign_res.get('reference_file')} (sha256: {campaign_res.get('reference_sha256')})")
    print(f"Distorted Fixture: {campaign_res.get('distorted_file')} (sha256: {campaign_res.get('distorted_sha256')})")
    print(f"Gage R&R Verdict : {campaign_res['verdict']} [{campaign_res['verdict_status'].upper()}]")
    print(f"Verdict Details  : {campaign_res['verdict_description']}")
    print("")
    print(f"VMAF Distribution: Mean = {vmaf_m['mean']:.2f} | StdDev = {vmaf_m['stddev']:.4f} | "
          f"Range = {vmaf_m['range']:.4f} | %CV = {vmaf_m['cv_pct']:.3f}%")
    print(f"PSNR Distribution: Mean = {psnr_m['mean']:.2f} dB | StdDev = {psnr_m['stddev']:.4f} dB")
    print(f"SSIM Distribution: Mean = {ssim_m['mean']:.4f} | StdDev = {ssim_m['stddev']:.6f}")

    # Pass Latency Statistics
    timings = campaign_res.get("timings", [])
    if timings:
        mean_t = sum(timings) / len(timings)
        var_t = sum((t - mean_t) ** 2 for t in timings) / len(timings) if len(timings) > 1 else 0
        std_t = var_t ** 0.5
        print(f"Pass Latencies   : Mean = {mean_t:.2f}s | StdDev = {std_t:.3f}s | Min = {min(timings):.2f}s | Max = {max(timings):.2f}s")

    # Warnings / Advisories
    warnings = campaign_res.get("warnings", [])
    print(f"Active Warnings  : {len(warnings)}")
    for w in warnings:
        print(f"  * {w}")

    # Assertions per metrology plan
    print("\n" + "-" * 72)
    print(" METROLOGY GATE ASSERTIONS")
    print("-" * 72)

    # 1. Assert N passes completed
    assert campaign_res["n_completed"] == args.runs, (
        f"Expected {args.runs} passes, but {campaign_res['n_completed']} completed"
    )
    print(f" [PASS] All {args.runs} requested runs completed")

    # 2. Assert near-lossless advisory did NOT fire (CRF 28 proves non-trivial delta)
    near_lossless_fired = any("near-lossless" in str(w).lower() for w in warnings)
    assert not near_lossless_fired, "Near-lossless advisory fired unexpectedly on CRF 28 fixture!"
    print(" [PASS] Near-lossless advisory correctly silent (discriminative quality delta verified)")

    # 3. Assert VMAF discriminative drop
    vmaf_upper_bound = 95.0 if args.crf >= 28 else 99.5
    assert vmaf_m["mean"] < vmaf_upper_bound, f"Expected VMAF < {vmaf_upper_bound} for CRF {args.crf}, got {vmaf_m['mean']:.2f}"
    print(f" [PASS] Discriminative VMAF score confirmed ({vmaf_m['mean']:.2f} < {vmaf_upper_bound})")

    # 4. Assert PSNR non-trivial
    assert psnr_m["mean"] < 55.0, f"Expected PSNR < 55 dB for CRF 28, got {psnr_m['mean']:.2f}"
    print(f" [PASS] Non-trivial PSNR confirmed ({psnr_m['mean']:.2f} dB < 55.0 dB)")

    # 5. Assert determinism holds (sigma ~ 0 on fixed pair)
    assert vmaf_m["stddev"] < 0.05, f"Unexpected pipeline non-determinism: sigma={vmaf_m['stddev']}"
    print(f" [PASS] Fixed-pair determinism confirmed (sigma = {vmaf_m['stddev']:.4f} < 0.05)")

    # 6. Assert fixture SHA-256 identity metadata present
    assert campaign_res.get("reference_sha256") and campaign_res["reference_sha256"] != "unknown"
    assert campaign_res.get("distorted_sha256") and campaign_res["distorted_sha256"] != "unknown"
    print(f" [PASS] Fixture SHA-256 traceability confirmed (Ref: {campaign_res['reference_sha256']}, Dist: {campaign_res['distorted_sha256']})")

    # 7. Assert JSONL trend log exists and contains this campaign record
    import json
    from app.repeatability_analyzer import get_campaign_history_log_path
    history_log = get_campaign_history_log_path()
    assert os.path.exists(history_log), f"History log missing at {history_log}"
    with open(history_log, "r", encoding="utf-8") as f:
        log_records = [json.loads(line.strip()) for line in f if line.strip()]
    assert len(log_records) > 0, "History log is empty"
    last_rec = log_records[-1]
    assert last_rec["campaign_type"] == getattr(args, "campaign_type", "fixed_pair")
    assert last_rec["reference_file"] == campaign_res["reference_file"]
    assert last_rec["distorted_file"] == campaign_res["distorted_file"]
    print(f" [PASS] Longitudinal JSONL trend log updated: {history_log} ({len(log_records)} records logged)")

    # Step 5: Generate official PDF Report
    out_pdf = os.path.abspath(args.out_pdf)
    os.makedirs(os.path.dirname(out_pdf), exist_ok=True)

    report_gen = ReportGenerator()
    analysis_results = {
        "vmaf_score": vmaf_m["mean"],
        "psnr_score": psnr_m["mean"],
        "ssim_score": ssim_m["mean"],
        "repeatability": campaign_res,
        "measurement_metadata": campaign_res.get("measurement_metadata", {}),
    }

    metadata = {
        "reference_path": ref_path,
        "distorted_path": dist_path,
        "test_name": f"Gage R&R Baseline ({args.runs} passes, CRF {args.crf})",
        "description": "Fixed-pair determinism baseline. Validates repeatability engine, metric calculations, and reporting pipeline.",
    }

    print(f"\nGenerating baseline report PDF -> {out_pdf}")
    pdf_path = report_gen.generate_report(out_pdf, analysis_results, metadata)
    if not pdf_path or not os.path.exists(pdf_path):
        raise RuntimeError(f"Failed to generate report at {out_pdf}")

    pdf_size = os.path.getsize(pdf_path)
    print(f" [PASS] PDF report generated: {pdf_path} ({pdf_size:,} bytes)")
    print("=" * 72 + "\n")

    return campaign_res


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Gage R&R Baseline Campaign")
    parser.add_argument(
        "--ref",
        default=os.path.join("tests", "test_references", "DANCE_.mp4"),
        help="Path to reference video"
    )
    parser.add_argument(
        "--dist",
        default=os.path.join("tests", "test_references", "DANCE__crf28.mp4"),
        help="Path to distorted video fixture"
    )
    parser.add_argument(
        "--crf",
        type=int,
        default=28,
        help="CRF compression level for fixture generation"
    )
    parser.add_argument(
        "--preset",
        default="fast",
        help="x264 preset for fixture generation"
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=5,
        help="Number of repeatability campaign passes"
    )
    parser.add_argument(
        "--model",
        default="vmaf_v0.6.1",
        help="VMAF model name"
    )
    parser.add_argument(
        "--out-pdf",
        default=os.path.join("reports", "gage_rr_baseline_crf28.pdf"),
        help="Path for generated baseline PDF report"
    )
    parser.add_argument(
        "--force-transcode",
        action="store_true",
        help="Force re-generation of distorted fixture"
    )
    parser.add_argument(
        "--campaign-type",
        default="fixed_pair",
        choices=["fixed_pair", "recapture"],
        help="Type of campaign: 'fixed_pair' (determinism baseline) or 'recapture' (hardware rig repeatability)"
    )

    args = parser.parse_args()
    try:
        run_baseline_campaign(args)
        sys.exit(0)
    except Exception as e:
        logger.error(f"Gage R&R Baseline Campaign failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
