"""Repeatability & Gage R&R Analysis Engine.

Performs multi-pass VMAF/PSNR/SSIM evaluation to characterize measurement
system uncertainty, sample standard deviation (n-1 degrees of freedom),
range, %CV, and metrology acceptance thresholds (<10% Acceptable, 10-30% Conditional,
>30% Rig-Dominated).
"""

import logging
import math
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from .vmaf_analyzer import VMAFAnalyzer

logger = logging.getLogger(__name__)


def calculate_metric_statistics(
    values: List[float],
    warning_threshold_drift: float = 1.0,
) -> Dict[str, Any]:
    """
    Calculate sample statistics for a list of metric observations.
    Uses sample standard deviation with Bessel's correction (n - 1 degrees of freedom).
    """
    clean_vals = [float(v) for v in values if v is not None and not math.isnan(float(v))]
    n = len(clean_vals)

    if n == 0:
        return {
            "n": 0,
            "mean": None,
            "stddev": None,
            "min": None,
            "max": None,
            "range": None,
            "cv_pct": None,
            "max_step_drift": 0.0,
            "drift_detected": False,
        }

    mean_val = sum(clean_vals) / n
    min_val = min(clean_vals)
    max_val = max(clean_vals)
    val_range = max_val - min_val

    # Annotation 3: Drift defined as max(|x_i - mean|), advisory-only
    max_dev_from_mean = max(abs(x - mean_val) for x in clean_vals) if clean_vals else 0.0

    if n == 1:
        return {
            "n": 1,
            "mean": round(mean_val, 4),
            "stddev": 0.0,
            "min": round(min_val, 4),
            "max": round(max_val, 4),
            "range": 0.0,
            "cv_pct": 0.0,
            "max_deviation_from_mean": 0.0,
            "drift_detected": False,
        }

    # Sample variance with (n - 1) degrees of freedom
    variance = sum((x - mean_val) ** 2 for x in clean_vals) / (n - 1)
    stddev = math.sqrt(variance)

    cv_pct = (stddev / abs(mean_val) * 100.0) if abs(mean_val) > 1e-9 else 0.0
    drift_detected = max_dev_from_mean > warning_threshold_drift

    return {
        "n": n,
        "mean": round(mean_val, 4),
        "stddev": round(stddev, 4),
        "min": round(min_val, 4),
        "max": round(max_val, 4),
        "range": round(val_range, 4),
        "cv_pct": round(cv_pct, 3),
        "max_deviation_from_mean": round(max_dev_from_mean, 4),
        "drift_detected": drift_detected,
    }


def calculate_gage_rr_verdict(
    vmaf_cv_pct: Optional[float],
    n_valid: int = 0,
    total_requested: int = 0,
) -> Dict[str, str]:
    """
    Classify Gage R&R acceptability strictly from VMAF %CV:
    - n_valid < 2 or excessive failure rate (>=50% failed): Insufficient Data
    - %CV < 10%: Acceptable
    - 10% <= %CV <= 30%: Conditional
    - %CV > 30%: Rig-Dominated
    """
    half_threshold = math.ceil(total_requested / 2.0) if total_requested >= 2 else 2
    if n_valid < 2 or (total_requested >= 2 and n_valid < half_threshold) or vmaf_cv_pct is None:
        return {
            "verdict": "Insufficient Data",
            "status": "insufficient_data",
            "description": "Effective successful passes (N < 2 or >= 50% failure rate) insufficient to calculate Gage R&R repeatability.",
        }

    if vmaf_cv_pct < 10.0:
        return {
            "verdict": "Acceptable",
            "status": "acceptable",
            "description": "Instrument uncertainty < 10% (Repeatability acceptable for quality testing).",
        }
    elif vmaf_cv_pct <= 30.0:
        return {
            "verdict": "Conditional",
            "status": "conditional",
            "description": "Instrument uncertainty 10–30% (Conditional - acceptable depending on application tolerance).",
        }
    else:
        return {
            "verdict": "Rig-Dominated",
            "status": "rig_dominated",
            "description": "Instrument uncertainty > 30% (Measurement system variability dominates; rig uncapable).",
        }


def aggregate_campaign_results(
    runs: List[Dict[str, Any]],
    warning_threshold_drift: float = 1.0,
    total_requested: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Aggregate individual repeatability pass results into a comprehensive Gage R&R report structure.
    Verdict is strictly derived from VMAF %CV.
    """
    total = total_requested or len(runs)
    valid_runs = [r for r in runs if r.get("status") == "success" and r.get("vmaf_score") is not None]
    n_valid = len(valid_runs)

    vmaf_vals = [r["vmaf_score"] for r in valid_runs if r.get("vmaf_score") is not None]
    psnr_vals = [r["psnr_score"] for r in valid_runs if r.get("psnr_score") is not None]
    ssim_vals = [r["ssim_score"] for r in valid_runs if r.get("ssim_score") is not None]

    vmaf_stats = calculate_metric_statistics(vmaf_vals, warning_threshold_drift)
    psnr_stats = calculate_metric_statistics(psnr_vals, warning_threshold_drift)
    ssim_stats = calculate_metric_statistics(ssim_vals, warning_threshold_drift)

    # Annotation 1 & 2: Verdict derived strictly from VMAF %CV with Insufficient Data check
    verdict_info = calculate_gage_rr_verdict(vmaf_stats.get("cv_pct"), n_valid=n_valid, total_requested=total)

    warnings: List[str] = []
    partial_run = n_valid < total
    caveat = ""

    if partial_run:
        caveat = f"{n_valid} of {total} requested passes succeeded. Statistics computed on available runs only."
        warnings.append(f"Partial Run Caveat: {caveat}")

    # Annotation 3: Max deviation advisory warning
    if vmaf_stats.get("drift_detected"):
        warnings.append(
            f"Advisory: Maximum VMAF deviation from mean ({vmaf_stats.get('max_deviation_from_mean')} pts) "
            f"exceeds stability threshold ({warning_threshold_drift:.1f} pts)."
        )

    # Observation 1 Sanity Check: Identical or near-lossless comparison pair
    if ssim_vals and all(s is not None and s > 0.999 for s in ssim_vals):
        near_lossless_warning = (
            "Advisory: Comparison pair appears identical or near-lossless (SSIM > 0.999 across all passes). "
            "Campaign discriminative power is nil; near-zero variance is mathematically trivial, not empirical proof of rig stability."
        )
        warnings.append(near_lossless_warning)

    # Traceability metadata from winning run or first pass
    measurement_metadata = {}
    for r in valid_runs:
        if r.get("measurement_metadata"):
            measurement_metadata = r["measurement_metadata"]
            break

    return {
        "n_requested": total,
        "n_completed": n_valid,
        "partial_run": partial_run,
        "caveat": caveat,
        "metrics": {
            "vmaf": vmaf_stats,
            "psnr": psnr_stats,
            "ssim": ssim_stats,
        },
        "runs": runs,
        "verdict": verdict_info["verdict"],
        "verdict_status": verdict_info["status"],
        "verdict_description": verdict_info["description"],
        "warnings": warnings,
        "measurement_metadata": measurement_metadata,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


class RepeatabilityAnalyzer(QObject):
    """
    Coordinates multi-pass Gage R&R repeatability campaigns.
    Ensures no intermediate file destruction across passes.
    """
    campaign_progress = pyqtSignal(int)      # Overall progress (0-100%)
    pass_complete = pyqtSignal(int, dict)    # pass_index (1-based), pass_result
    campaign_complete = pyqtSignal(dict)     # aggregated repeatability results
    error_occurred = pyqtSignal(str)
    status_update = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._terminate_requested = False
        self._active_analyzer: Optional[VMAFAnalyzer] = None

    def terminate_campaign(self):
        """Request termination of the active campaign"""
        self._terminate_requested = True
        if self._active_analyzer:
            self._active_analyzer.terminate_analysis()

    def run_campaign(
        self,
        distorted_path: str,
        reference_path: str,
        model: str = "vmaf_v0.6.1",
        runs: int = 5,
        options_manager = None,
        cleanup_after_campaign: bool = True,
        alignment_metadata: Optional[dict] = None,
        capture_metadata: Optional[dict] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Execute N identical analysis passes against the same reference/distorted pair.
        Never mutates or deletes intermediate files between passes.
        """
        self._terminate_requested = False

        drift_threshold = 1.0
        delete_aligned_original_setting = True

        if options_manager:
            try:
                rep_opts = options_manager.get_setting("repeatability") or {}
                runs = int(rep_opts.get("runs", runs))
                drift_threshold = float(rep_opts.get("drift_warning_threshold", drift_threshold))

                vmaf_opts = options_manager.get_setting("vmaf") or {}
                delete_aligned_original_setting = vmaf_opts.get("delete_aligned_original", True)
            except Exception as e:
                logger.warning(f"Error reading options for repeatability campaign: {e}")

        logger.info(f"Starting Gage R&R repeatability campaign: N={runs} runs against model={model}")
        self.status_update.emit(f"Starting Gage R&R campaign (N={runs} runs)...")
        self.campaign_progress.emit(0)

        # 1. Session Capability Probe (Runs once per campaign)
        try:
            VMAFAnalyzer.probe_capabilities()
        except Exception as e:
            logger.warning(f"Capability probe warning during campaign start: {e}")

        runs_data: List[Dict[str, Any]] = []
        aligned_capture_file = None

        for pass_idx in range(1, runs + 1):
            if self._terminate_requested:
                logger.info("Repeatability campaign terminated by user request")
                self.status_update.emit("Campaign cancelled by user.")
                break

            self.status_update.emit(f"Running pass {pass_idx}/{runs}...")
            pass_start = time.time()

            analyzer = VMAFAnalyzer()
            self._active_analyzer = analyzer

            if options_manager:
                analyzer.set_options_from_manager(options_manager)

            # CRITICAL METROLOGY REQUIREMENT: Disable file deletion between passes
            analyzer.delete_aligned_original = False

            try:
                pass_res = analyzer.analyze_videos(
                    reference_path=reference_path,
                    distorted_path=distorted_path,
                    model=model,
                    alignment_metadata=alignment_metadata,
                    capture_metadata=capture_metadata,
                )

                pass_duration = round(time.time() - pass_start, 2)

                # Annotation 4: Truncation-flagged pass = failed pass
                is_truncated = False
                if pass_res:
                    if pass_res.get("truncation_detected") or pass_res.get("is_truncated"):
                        is_truncated = True
                    cap_meta = pass_res.get("capture_metadata") or {}
                    if cap_meta.get("is_truncated") or cap_meta.get("truncated"):
                        is_truncated = True

                if pass_res and pass_res.get("vmaf_score") is not None and not is_truncated:
                    aligned_capture_file = pass_res.get("aligned_path") or pass_res.get("distorted_path")
                    record = {
                        "pass": pass_idx,
                        "status": "success",
                        "duration_seconds": pass_duration,
                        "vmaf_score": pass_res.get("vmaf_score"),
                        "psnr_score": pass_res.get("psnr_score"),
                        "ssim_score": pass_res.get("ssim_score"),
                        "raw_results": pass_res.get("raw_results"),
                        "measurement_metadata": pass_res.get("measurement_metadata"),
                    }
                    logger.info(
                        f"Pass {pass_idx}/{runs} completed in {pass_duration}s: "
                        f"VMAF={record['vmaf_score']:.2f}, PSNR={record['psnr_score']}, SSIM={record['ssim_score']}"
                    )
                else:
                    fail_reason = "Pass flagged as truncated capture" if is_truncated else "Pass returned empty or invalid results"
                    record = {
                        "pass": pass_idx,
                        "status": "failed",
                        "duration_seconds": pass_duration,
                        "vmaf_score": None,
                        "error": fail_reason,
                    }
                    logger.warning(f"Pass {pass_idx}/{runs} failed: {record['error']}")

            except Exception as pe:
                pass_duration = round(time.time() - pass_start, 2)
                record = {
                    "pass": pass_idx,
                    "status": "failed",
                    "duration_seconds": pass_duration,
                    "vmaf_score": None,
                    "error": str(pe),
                }
                logger.error(f"Pass {pass_idx}/{runs} encountered exception: {pe}")

            runs_data.append(record)
            self.pass_complete.emit(pass_idx, record)

            overall_progress = int((pass_idx / runs) * 100)
            self.campaign_progress.emit(overall_progress)

        self._active_analyzer = None

        # Post-campaign cleanup: delete original unaligned capture file once if configured
        if cleanup_after_campaign and delete_aligned_original_setting and aligned_capture_file:
            if "aligned" in os.path.basename(aligned_capture_file).lower():
                candidate_orig = aligned_capture_file.replace("_aligned", "")
                if candidate_orig != aligned_capture_file and os.path.isfile(candidate_orig):
                    try:
                        logger.info(f"Campaign complete: deleting original unaligned capture {candidate_orig}")
                        os.remove(candidate_orig)
                    except Exception as ce:
                        logger.warning(f"Could not delete original capture file after campaign: {ce}")

        if not runs_data:
            error_msg = "Repeatability campaign finished with no passes executed"
            self.error_occurred.emit(error_msg)
            return None

        # Aggregate results across all passes
        aggregated = aggregate_campaign_results(
            runs=runs_data,
            warning_threshold_drift=drift_threshold,
            total_requested=runs,
        )

        self.campaign_complete.emit(aggregated)
        self.status_update.emit(
            f"Gage R&R Campaign Complete: N={aggregated['n_completed']}/{aggregated['n_requested']}, "
            f"Verdict={aggregated['verdict']}"
        )
        return aggregated


class RepeatabilityCampaignThread(QThread):
    """QThread worker to run repeatability campaigns asynchronously off the UI thread"""
    campaign_progress = pyqtSignal(int)
    pass_complete = pyqtSignal(int, dict)
    campaign_complete = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    status_update = pyqtSignal(str)

    def __init__(
        self,
        distorted_path: str,
        reference_path: str,
        model: str = "vmaf_v0.6.1",
        runs: int = 5,
        options_manager = None,
        cleanup_after_campaign: bool = True,
        alignment_metadata: Optional[dict] = None,
        capture_metadata: Optional[dict] = None,
    ):
        super().__init__()
        self.distorted_path = distorted_path
        self.reference_path = reference_path
        self.model = model
        self.runs = runs
        self.options_manager = options_manager
        self.cleanup_after_campaign = cleanup_after_campaign
        self.alignment_metadata = alignment_metadata
        self.capture_metadata = capture_metadata

        self.analyzer = RepeatabilityAnalyzer()
        self.analyzer.campaign_progress.connect(self.campaign_progress.emit)
        self.analyzer.pass_complete.connect(self.pass_complete.emit)
        self.analyzer.campaign_complete.connect(self.campaign_complete.emit)
        self.analyzer.error_occurred.connect(self.error_occurred.emit)
        self.analyzer.status_update.connect(self.status_update.emit)

    def run(self):
        self.analyzer.run_campaign(
            distorted_path=self.distorted_path,
            reference_path=self.reference_path,
            model=self.model,
            runs=self.runs,
            options_manager=self.options_manager,
            cleanup_after_campaign=self.cleanup_after_campaign,
            alignment_metadata=self.alignment_metadata,
            capture_metadata=self.capture_metadata,
        )

    def terminate(self):
        self.analyzer.terminate_campaign()
        super().terminate()
