"""
Metrology Diff & Comparison Engine for VMAF Quality Assessment Runs & Campaigns.

Calculates statistical delta metrics, combined quadrature measurement uncertainty,
instrument noise-floor significance gates, fixture traceability differences,
and generates both visual charts and publication-grade PDF comparison reports.
"""

import os
import sys
import json
import math
import logging
import tempfile
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
)

from app.version import get_version_string, get_git_commit

logger = logging.getLogger(__name__)

# Declared instrument resolution convention (0.05 VMAF points)
# Represents the minimum detectable delta floor for the instrument
DEFAULT_RESOLUTION_FLOOR_SIGMA = 0.05
CONFIDENCE_SIGMA_MULTIPLIER = 3.0  # 3-sigma (99.7% confidence)


def calculate_combined_uncertainty(
    sigma1: Optional[float],
    sigma2: Optional[float],
    sigma_floor: float = DEFAULT_RESOLUTION_FLOOR_SIGMA,
) -> float:
    """
    Calculate combined (quadrature) uncertainty for comparing two independent runs:
        sigma_delta = sqrt(sigma_1^2 + sigma_2^2 + sigma_floor^2)

    Ensures symmetric contribution from both runs and guarantees threshold never
    collapses to zero even when both runs exhibit zero variance (e.g. fixed-pair determinism).
    """
    s1 = float(sigma1) if (sigma1 is not None and not math.isnan(sigma1)) else 0.0
    s2 = float(sigma2) if (sigma2 is not None and not math.isnan(sigma2)) else 0.0
    sf = float(sigma_floor) if sigma_floor > 0 else DEFAULT_RESOLUTION_FLOOR_SIGMA
    return math.sqrt(s1 ** 2 + s2 ** 2 + sf ** 2)


def load_campaign_or_run(
    source: Union[dict, str, int],
    log_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Normalize campaign input into a standard dictionary.

    Args:
        source: A dictionary, a path to a JSON file, or an integer index into campaign_history.jsonl
                (e.g., -1 for most recent, -2 for second-to-last).
        log_path: Optional path to JSONL log file (defaults to logs/campaign_history.jsonl).
    """
    if isinstance(source, dict):
        return source

    if isinstance(source, int):
        from app.repeatability_analyzer import read_campaign_history
        records = read_campaign_history(log_path=log_path)
        if not records:
            raise ValueError(f"Campaign history log is empty; cannot resolve index {source}")
        try:
            return records[source]
        except IndexError:
            raise IndexError(f"Index {source} out of range for campaign history (length {len(records)})")

    if isinstance(source, str):
        if os.path.isfile(source):
            with open(source, "r", encoding="utf-8") as f:
                data = json.load(f)
            # If this is a single-pass vmaf.json, normalize pooled metrics
            if "pooled_metrics" in data:
                pool = data["pooled_metrics"]
                vmaf_val = pool.get("vmaf", {}).get("mean")
                psnr_val = pool.get("psnr", {}).get("mean", pool.get("psnr_y", {}).get("mean"))
                ssim_val = pool.get("ssim", {}).get("mean", pool.get("ssim_y", {}).get("mean"))
                return {
                    "vmaf_mean": vmaf_val,
                    "vmaf_stddev": 0.0,
                    "cv_pct": 0.0,
                    "psnr_mean": psnr_val,
                    "ssim_mean": ssim_val,
                    "verdict": "Single Run",
                    "verdict_status": "acceptable",
                    "n_completed": 1,
                    "n_requested": 1,
                    "raw_results": data,
                }
            return data
        else:
            raise FileNotFoundError(f"Campaign file not found: {source}")

    raise TypeError(f"Unsupported campaign source type: {type(source)}")


class DiffAnalyzer:
    """Metrology comparison engine for quality evaluation runs and campaigns."""

    def __init__(self, sigma_floor: float = DEFAULT_RESOLUTION_FLOOR_SIGMA):
        self.sigma_floor = sigma_floor

    def compare_campaigns(
        self,
        baseline_source: Union[dict, str, int],
        treatment_source: Union[dict, str, int],
        log_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute metrological diff between baseline and treatment campaigns.

        Note on ordering:
        - Baseline: reference run (e.g. baseline campaign, CRF 28, or second-to-last record)
        - Treatment: comparison run (e.g. candidate build, CRF 24, or last record)
        """
        baseline = load_campaign_or_run(baseline_source, log_path=log_path)
        treatment = load_campaign_or_run(treatment_source, log_path=log_path)

        # 1. Extract core metrics
        vmaf_1 = baseline.get("vmaf_mean")
        if vmaf_1 is None and "metrics" in baseline:
            vmaf_1 = baseline["metrics"].get("vmaf", {}).get("mean")
        vmaf_1 = float(vmaf_1) if vmaf_1 is not None else None

        vmaf_2 = treatment.get("vmaf_mean")
        if vmaf_2 is None and "metrics" in treatment:
            vmaf_2 = treatment["metrics"].get("vmaf", {}).get("mean")
        vmaf_2 = float(vmaf_2) if vmaf_2 is not None else None

        psnr_1 = baseline.get("psnr_mean")
        if psnr_1 is None and "metrics" in baseline:
            psnr_1 = baseline["metrics"].get("psnr", {}).get("mean")
        psnr_1 = float(psnr_1) if psnr_1 is not None else None

        psnr_2 = treatment.get("psnr_mean")
        if psnr_2 is None and "metrics" in treatment:
            psnr_2 = treatment["metrics"].get("psnr", {}).get("mean")
        psnr_2 = float(psnr_2) if psnr_2 is not None else None

        ssim_1 = baseline.get("ssim_mean")
        if ssim_1 is None and "metrics" in baseline:
            ssim_1 = baseline["metrics"].get("ssim", {}).get("mean")
        ssim_1 = float(ssim_1) if ssim_1 is not None else None

        ssim_2 = treatment.get("ssim_mean")
        if ssim_2 is None and "metrics" in treatment:
            ssim_2 = treatment["metrics"].get("ssim", {}).get("mean")
        ssim_2 = float(ssim_2) if ssim_2 is not None else None

        sigma_1 = baseline.get("vmaf_stddev")
        if sigma_1 is None and "metrics" in baseline:
            sigma_1 = baseline["metrics"].get("vmaf", {}).get("stddev")
        sigma_1 = float(sigma_1) if sigma_1 is not None else 0.0

        sigma_2 = treatment.get("vmaf_stddev")
        if sigma_2 is None and "metrics" in treatment:
            sigma_2 = treatment["metrics"].get("vmaf", {}).get("stddev")
        sigma_2 = float(sigma_2) if sigma_2 is not None else 0.0

        cv_1 = baseline.get("cv_pct")
        if cv_1 is None and "metrics" in baseline:
            cv_1 = baseline["metrics"].get("vmaf", {}).get("cv_pct")
        cv_1 = float(cv_1) if cv_1 is not None else None

        cv_2 = treatment.get("cv_pct")
        if cv_2 is None and "metrics" in treatment:
            cv_2 = treatment["metrics"].get("vmaf", {}).get("cv_pct")
        cv_2 = float(cv_2) if cv_2 is not None else None

        # 2. Compute Deltas & Directions
        delta_vmaf = (vmaf_2 - vmaf_1) if (vmaf_1 is not None and vmaf_2 is not None) else None
        delta_psnr = (psnr_2 - psnr_1) if (psnr_1 is not None and psnr_2 is not None) else None
        delta_ssim = (ssim_2 - ssim_1) if (ssim_1 is not None and ssim_2 is not None) else None
        delta_sigma = sigma_2 - sigma_1

        # Check verdict validity for %CV delta suppression
        verdict_status_1 = baseline.get("verdict_status", "acceptable")
        verdict_status_2 = treatment.get("verdict_status", "acceptable")
        suppress_cv_delta = (
            cv_1 is None or cv_2 is None or
            verdict_status_1 == "insufficient_data" or
            verdict_status_2 == "insufficient_data"
        )
        delta_cv_pct = None if suppress_cv_delta else (cv_2 - cv_1)

        # Direction helper: Arrow strictly represents numeric direction (+ / -)
        def _fmt_dir(val: Optional[float], decimals: int = 2) -> str:
            if val is None:
                return "N/A"
            if abs(val) < 1e-6:
                return f"= {0.0:.{decimals}f}"
            if val > 0:
                return f"▲ +{val:.{decimals}f}"
            else:
                return f"▼ {val:.{decimals}f}"

        # Polarity helper: Quality goodness (improved vs degraded)
        def _get_polarity(val: Optional[float], is_lower_better: bool = False) -> str:
            if val is None or abs(val) < 1e-6:
                return "neutral"
            if is_lower_better:
                return "improved" if val < 0 else "degraded"
            return "improved" if val > 0 else "degraded"

        # Metric divergence detection (e.g. VMAF improves while SSIM or PSNR drops)
        quality_signs = []
        if delta_vmaf is not None and abs(delta_vmaf) > 1e-3:
            quality_signs.append(("VMAF", delta_vmaf > 0))
        if delta_psnr is not None and abs(delta_psnr) > 1e-3:
            quality_signs.append(("PSNR", delta_psnr > 0))
        if delta_ssim is not None and abs(delta_ssim) > 1e-4:
            quality_signs.append(("SSIM", delta_ssim > 0))

        divergence_detected = len(set(s[1] for s in quality_signs)) > 1
        divergence_advisory = None
        if divergence_detected:
            pos_metrics = [s[0] for s in quality_signs if s[1]]
            neg_metrics = [s[0] for s in quality_signs if not s[1]]
            divergence_advisory = (
                f"Metrology Advisory: Metric directional divergence detected — "
                f"{', '.join(pos_metrics)} increased while {', '.join(neg_metrics)} decreased. "
                f"Perceptual pooling differences between structural (SSIM) and temporal/detail (VMAF) models."
            )

        # Determine effective uncertainty floor:
        # Check if baseline or treatment is a recapture campaign, extracting measured sigma_rig
        recapture_sigma = None
        for rec in (baseline, treatment):
            if isinstance(rec, dict) and rec.get("campaign_type") == "recapture":
                s_val = rec.get("vmaf_stddev")
                if s_val is None and "metrics" in rec:
                    s_val = rec["metrics"].get("vmaf", {}).get("stddev")
                if s_val is not None and not math.isnan(s_val):
                    recapture_sigma = max(recapture_sigma or 0.0, float(s_val))

        # Respect user-provided self.sigma_floor, but ensure it never falls below DEFAULT_RESOLUTION_FLOOR_SIGMA (0.05)
        # If recapture campaign is present, supersede floor with measured sigma_rig (or floor if sigma_rig < 0.05)
        base_floor = max(DEFAULT_RESOLUTION_FLOOR_SIGMA, float(self.sigma_floor))
        if recapture_sigma is not None:
            effective_sigma_floor = max(base_floor, recapture_sigma)
            is_empirical = effective_sigma_floor > DEFAULT_RESOLUTION_FLOOR_SIGMA
            floor_source = "empirical_sigma_rig" if is_empirical else "declared_convention"
        else:
            effective_sigma_floor = base_floor
            is_empirical = effective_sigma_floor > DEFAULT_RESOLUTION_FLOOR_SIGMA
            floor_source = "custom_override" if is_empirical else "declared_convention"

        # 3. Combined Uncertainty & Noise-Floor Significance
        sigma_delta = calculate_combined_uncertainty(sigma_1, sigma_2, effective_sigma_floor)
        threshold_3sigma = CONFIDENCE_SIGMA_MULTIPLIER * sigma_delta

        if delta_vmaf is not None:
            snr_delta = abs(delta_vmaf) / sigma_delta
            is_significant = abs(delta_vmaf) > threshold_3sigma

            if is_significant:
                if delta_vmaf > 0:
                    significance_verdict = "significant_improvement"
                    significance_label = "Statistically Significant Improvement"
                    significance_desc = (
                        f"Delta (+{delta_vmaf:.2f}) exceeds 3*sigma_delta noise floor ({threshold_3sigma:.3f}). "
                        f"Signal-to-noise ratio SNR = {snr_delta:.1f}x."
                    )
                else:
                    significance_verdict = "significant_degradation"
                    significance_label = "Statistically Significant Degradation"
                    significance_desc = (
                        f"Delta ({delta_vmaf:.2f}) exceeds 3*sigma_delta noise floor ({threshold_3sigma:.3f}). "
                        f"Signal-to-noise ratio SNR = {snr_delta:.1f}x."
                    )
            else:
                significance_verdict = "indistinguishable_from_noise"
                significance_label = "Indistinguishable from Instrument Noise"
                significance_desc = (
                    f"|Delta| ({abs(delta_vmaf):.2f}) is within 3*sigma_delta noise floor ({threshold_3sigma:.3f}). "
                    f"Difference cannot be distinguished from measurement noise at 99.7% confidence."
                )
        else:
            snr_delta = 0.0
            is_significant = False
            significance_verdict = "indeterminate"
            significance_label = "Indeterminate"
            significance_desc = "Missing VMAF metric data in one or both records."

        # 4. Toolchain Consistency Check
        model_1 = baseline.get("model") or baseline.get("measurement_metadata", {}).get("model", "unknown")
        model_2 = treatment.get("model") or treatment.get("measurement_metadata", {}).get("model", "unknown")

        ff_1 = baseline.get("ffmpeg_version") or baseline.get("measurement_metadata", {}).get("ffmpeg_version", "unknown")
        ff_2 = treatment.get("ffmpeg_version") or treatment.get("measurement_metadata", {}).get("ffmpeg_version", "unknown")

        incompatible_reasons = []
        if model_1 != "unknown" and model_2 != "unknown" and model_1 != model_2:
            incompatible_reasons.append(f"Model mismatch: '{model_1}' vs '{model_2}'")

        # Compare FFmpeg main version string if known
        ff_clean_1 = ff_1.split()[2] if len(ff_1.split()) > 2 else ff_1
        ff_clean_2 = ff_2.split()[2] if len(ff_2.split()) > 2 else ff_2
        if ff_1 != "unknown" and ff_2 != "unknown" and ff_clean_1 != ff_clean_2:
            incompatible_reasons.append(f"FFmpeg toolchain mismatch: '{ff_clean_1}' vs '{ff_clean_2}'")

        toolchain_compatible = len(incompatible_reasons) == 0

        # 5. Fixture Traceability
        ref_hash_1 = baseline.get("reference_sha256") or baseline.get("measurement_metadata", {}).get("reference_sha256")
        ref_hash_2 = treatment.get("reference_sha256") or treatment.get("measurement_metadata", {}).get("reference_sha256")
        dist_hash_1 = baseline.get("distorted_sha256") or baseline.get("measurement_metadata", {}).get("distorted_sha256")
        dist_hash_2 = treatment.get("distorted_sha256") or treatment.get("measurement_metadata", {}).get("distorted_sha256")

        reference_match = (ref_hash_1 is not None and ref_hash_1 == ref_hash_2 and ref_hash_1 != "unknown")
        distorted_match = (dist_hash_1 is not None and dist_hash_1 == dist_hash_2 and dist_hash_1 != "unknown")

        # 6. Verdict Evolution
        verdict_1 = baseline.get("verdict", "Unknown")
        verdict_2 = treatment.get("verdict", "Unknown")
        verdict_changed = (verdict_1 != verdict_2)
        verdict_transition = f"{verdict_1} -> {verdict_2}"
        if verdict_changed:
            verdict_evolution_text = f"State Shift: {verdict_1} -> {verdict_2}"
        else:
            verdict_evolution_text = f"Unchanged ({verdict_1} -> {verdict_2})"

        # 7. Chart Mode Determination
        has_frames_1 = "raw_results" in baseline and "frames" in baseline["raw_results"]
        has_frames_2 = "raw_results" in treatment and "frames" in treatment["raw_results"]
        chart_mode = "frame_curve" if (has_frames_1 and has_frames_2) else "pooled_bar"

        report_payload = {
            "timestamp_comparison": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "baseline": {
                "timestamp": baseline.get("timestamp"),
                "campaign_type": baseline.get("campaign_type", "fixed_pair"),
                "vmaf_mean": vmaf_1,
                "vmaf_stddev": sigma_1,
                "cv_pct": cv_1,
                "psnr_mean": psnr_1,
                "ssim_mean": ssim_1,
                "verdict": verdict_1,
                "verdict_status": verdict_status_1,
                "n_completed": baseline.get("n_completed"),
                "reference_file": baseline.get("reference_file"),
                "reference_sha256": ref_hash_1 or "unknown",
                "distorted_file": baseline.get("distorted_file"),
                "distorted_sha256": dist_hash_1 or "unknown",
                "model": model_1,
                "app_version": baseline.get("app_version", "unknown"),
                "git_commit": baseline.get("git_commit", "unknown"),
            },
            "treatment": {
                "timestamp": treatment.get("timestamp"),
                "campaign_type": treatment.get("campaign_type", "fixed_pair"),
                "vmaf_mean": vmaf_2,
                "vmaf_stddev": sigma_2,
                "cv_pct": cv_2,
                "psnr_mean": psnr_2,
                "ssim_mean": ssim_2,
                "verdict": verdict_2,
                "verdict_status": verdict_status_2,
                "n_completed": treatment.get("n_completed"),
                "reference_file": treatment.get("reference_file"),
                "reference_sha256": ref_hash_2 or "unknown",
                "distorted_file": treatment.get("distorted_file"),
                "distorted_sha256": dist_hash_2 or "unknown",
                "model": model_2,
                "app_version": treatment.get("app_version", "unknown"),
                "git_commit": treatment.get("git_commit", "unknown"),
            },
            "deltas": {
                "delta_vmaf": delta_vmaf,
                "delta_vmaf_str": _fmt_dir(delta_vmaf, 2),
                "delta_vmaf_polarity": _get_polarity(delta_vmaf, is_lower_better=False),
                "delta_psnr": delta_psnr,
                "delta_psnr_str": _fmt_dir(delta_psnr, 2),
                "delta_psnr_polarity": _get_polarity(delta_psnr, is_lower_better=False),
                "delta_ssim": delta_ssim,
                "delta_ssim_str": _fmt_dir(delta_ssim, 4),
                "delta_ssim_polarity": _get_polarity(delta_ssim, is_lower_better=False),
                "delta_sigma": delta_sigma,
                "delta_sigma_str": _fmt_dir(delta_sigma, 4),
                "delta_sigma_polarity": _get_polarity(delta_sigma, is_lower_better=True),
                "delta_cv_pct": delta_cv_pct,
                "delta_cv_pct_str": _fmt_dir(delta_cv_pct, 3) if delta_cv_pct is not None else "N/A (suppressed)",
                "delta_cv_pct_polarity": _get_polarity(delta_cv_pct, is_lower_better=True) if delta_cv_pct is not None else "neutral",
                "divergence_advisory": divergence_advisory,
            },
            "metrology": {
                "sigma_floor_convention": round(effective_sigma_floor, 5),
                "sigma_floor_effective": round(effective_sigma_floor, 5),
                "sigma_floor_source": floor_source,
                "is_empirical_floor": is_empirical,
                "sigma_1": sigma_1,
                "sigma_2": sigma_2,
                "combined_sigma_delta": round(sigma_delta, 5),
                "threshold_3sigma": round(threshold_3sigma, 5),
                "snr_delta": round(snr_delta, 2),
                "is_significant": is_significant,
                "significance_verdict": significance_verdict,
                "significance_label": significance_label,
                "significance_description": significance_desc,
            },
            "verdict_evolution": {
                "verdict_baseline": verdict_1,
                "verdict_treatment": verdict_2,
                "verdict_changed": verdict_changed,
                "verdict_transition": verdict_transition,
                "verdict_evolution_text": verdict_evolution_text,
            },
            "traceability": {
                "reference_match": reference_match,
                "distorted_match": distorted_match,
                "toolchain_compatible": toolchain_compatible,
                "incompatible_reasons": incompatible_reasons,
            },
            "chart_mode": chart_mode,
        }

        # Keep raw frame references if available
        if has_frames_1 and has_frames_2:
            report_payload["raw_frames_1"] = baseline["raw_results"]["frames"]
            report_payload["raw_frames_2"] = treatment["raw_results"]["frames"]

        return report_payload

    def generate_diff_chart(self, diff_data: Dict[str, Any], output_png_path: str) -> str:
        """
        Generate visualization chart for the comparison.
        Supports both 'frame_curve' mode (per-frame deltas) and 'pooled_bar' mode.
        """
        os.makedirs(os.path.dirname(os.path.abspath(output_png_path)), exist_ok=True)
        chart_mode = diff_data.get("chart_mode", "pooled_bar")

        if chart_mode == "frame_curve" and "raw_frames_1" in diff_data and "raw_frames_2" in diff_data:
            # Per-frame curve mode
            frames_1 = diff_data["raw_frames_1"]
            frames_2 = diff_data["raw_frames_2"]
            n = min(len(frames_1), len(frames_2))

            v1 = [f.get("metrics", {}).get("vmaf", 0.0) for f in frames_1[:n]]
            v2 = [f.get("metrics", {}).get("vmaf", 0.0) for f in frames_2[:n]]
            delta = [b - a for a, b in zip(v1, v2)]
            x = list(range(n))

            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8.5, 4.5), sharex=True, gridspec_kw={'height_ratios': [2, 1]})

            ax1.plot(x, v1, label="Baseline", color="#2563eb", linewidth=1.5)
            ax1.plot(x, v2, label="Treatment", color="#16a34a", linewidth=1.5, linestyle="--")
            ax1.set_ylabel("VMAF Score")
            ax1.set_title("Per-Frame VMAF Comparison & Delta Curve")
            ax1.legend(loc="lower right")
            ax1.grid(True, linestyle=":", alpha=0.6)

            ax2.plot(x, delta, label="ΔVMAF (Treatment - Baseline)", color="#d97706", linewidth=1.2)
            t3 = diff_data["metrology"]["threshold_3sigma"]
            ax2.axhline(t3, color="#dc2626", linestyle=":", label=f"+3σ Noise Floor ({t3:.2f})")
            ax2.axhline(-t3, color="#dc2626", linestyle=":", label=f"-3σ Noise Floor (-{t3:.2f})")
            ax2.axhline(0, color="gray", linewidth=0.8)
            ax2.set_xlabel("Frame Index")
            ax2.set_ylabel("ΔVMAF")
            ax2.legend(loc="lower right", fontsize=8)
            ax2.grid(True, linestyle=":", alpha=0.6)

            plt.tight_layout()
            fig.savefig(output_png_path, dpi=200)
            plt.close(fig)
            return output_png_path

        # Pooled-bar mode
        b_m = diff_data["baseline"]
        t_m = diff_data["treatment"]

        v1 = b_m.get("vmaf_mean") or 0.0
        v2 = t_m.get("vmaf_mean") or 0.0
        s1 = b_m.get("vmaf_stddev") or 0.0
        s2 = t_m.get("vmaf_stddev") or 0.0

        p1 = b_m.get("psnr_mean") or 0.0
        p2 = t_m.get("psnr_mean") or 0.0

        ss1 = (b_m.get("ssim_mean") or 0.0) * 100.0  # Scale SSIM to 0-100 for visual comparison
        ss2 = (t_m.get("ssim_mean") or 0.0) * 100.0

        fig, ax = plt.subplots(figsize=(8.0, 3.8))
        metrics = ["VMAF", "PSNR (dB)", "SSIM (x100)"]
        baseline_vals = [v1, p1, ss1]
        treatment_vals = [v2, p2, ss2]
        errors_1 = [s1, 0.0, 0.0]
        errors_2 = [s2, 0.0, 0.0]

        x = np.arange(len(metrics))
        width = 0.35

        rects1 = ax.bar(x - width/2, baseline_vals, width, yerr=errors_1, capsize=4,
                        label="Baseline", color="#3b82f6", alpha=0.85, edgecolor="#1d4ed8")
        rects2 = ax.bar(x + width/2, treatment_vals, width, yerr=errors_2, capsize=4,
                        label="Treatment", color="#10b981", alpha=0.85, edgecolor="#047857")

        ax.set_ylabel("Score / Metric Value")
        ax.set_title("Pooled Metric Comparison (Baseline vs Treatment)")
        ax.set_xticks(x)
        ax.set_xticklabels(metrics, fontweight="bold")
        ax.legend(loc="upper right")
        ax.grid(axis="y", linestyle=":", alpha=0.6)

        # Bar label callouts
        for rect in rects1:
            height = rect.get_height()
            if height > 0:
                ax.annotate(f"{height:.2f}",
                            xy=(rect.get_x() + rect.get_width() / 2, height),
                            xytext=(0, 3), textcoords="offset points",
                            ha="center", va="bottom", fontsize=8)

        for rect in rects2:
            height = rect.get_height()
            if height > 0:
                ax.annotate(f"{height:.2f}",
                            xy=(rect.get_x() + rect.get_width() / 2, height),
                            xytext=(0, 3), textcoords="offset points",
                            ha="center", va="bottom", fontsize=8, fontweight="bold")

        plt.tight_layout()
        fig.savefig(output_png_path, dpi=200)
        plt.close(fig)
        return output_png_path

    def generate_diff_pdf(self, diff_data: Dict[str, Any], output_pdf_path: str) -> str:
        """
        Generate a branded, publication-ready PDF diff report.
        """
        os.makedirs(os.path.dirname(os.path.abspath(output_pdf_path)), exist_ok=True)
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            'DiffTitle',
            parent=styles['Heading1'],
            fontSize=16,
            leading=20,
            spaceAfter=6,
            textColor=colors.HexColor('#0f172a')
        )
        subtitle_style = ParagraphStyle(
            'DiffSubtitle',
            parent=styles['Heading2'],
            fontSize=11,
            leading=14,
            spaceAfter=6,
            textColor=colors.HexColor('#334155')
        )
        body_style = ParagraphStyle(
            'DiffBody',
            parent=styles['Normal'],
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor('#1e293b')
        )
        banner_style = ParagraphStyle(
            'DiffBanner',
            parent=styles['Normal'],
            fontSize=9.5,
            leading=13,
            textColor=colors.HexColor('#0f172a')
        )

        doc = SimpleDocTemplate(
            output_pdf_path,
            pagesize=A4,
            leftMargin=36,
            rightMargin=36,
            topMargin=36,
            bottomMargin=36
        )
        elements = []

        # 1. Header
        elements.append(Paragraph("VMAF Quality Assessment — Metrology Diff Report", title_style))
        gen_time = diff_data.get("timestamp_comparison", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        elements.append(Paragraph(
            f"Generated: {gen_time} | Software: {get_version_string()} ({get_git_commit(short=True)})",
            body_style
        ))
        elements.append(Spacer(1, 0.12 * inch))

        # 2. Executive Callout Banner
        sig = diff_data["metrology"]
        verdict_key = sig.get("significance_verdict", "indistinguishable_from_noise")
        label = sig.get("significance_label", "Diff Analysis")
        desc = sig.get("significance_description", "")

        if not diff_data["traceability"]["toolchain_compatible"]:
            bg_col = colors.HexColor('#fee2e2')
            border_col = colors.HexColor('#dc2626')
            banner_title = "<b>INCOMPATIBLE COMPARISON WARNING</b>"
            reasons = "; ".join(diff_data["traceability"]["incompatible_reasons"])
            banner_body = f"{banner_title} — Toolchain mismatch detected: {reasons}. Deltas may reflect toolchain divergence rather than signal quality."
        elif verdict_key == "significant_improvement":
            bg_col = colors.HexColor('#dcfce7')
            border_col = colors.HexColor('#16a34a')
            banner_body = f"<b>{label.upper()}</b> — {desc}"
        elif verdict_key == "significant_degradation":
            bg_col = colors.HexColor('#fee2e2')
            border_col = colors.HexColor('#dc2626')
            banner_body = f"<b>{label.upper()}</b> — {desc}"
        else:
            bg_col = colors.HexColor('#fef3c7')
            border_col = colors.HexColor('#d97706')
            banner_body = f"<b>{label.upper()}</b> — {desc}"

        banner_p = Paragraph(banner_body, banner_style)
        banner_table = Table([[banner_p]], colWidths=[7.4 * inch])
        banner_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), bg_col),
            ('BOX', (0, 0), (-1, -1), 1.5, border_col),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ]))
        elements.append(banner_table)
        elements.append(Spacer(1, 0.15 * inch))

        # 3. Metric Comparison Table
        elements.append(Paragraph("Metric Comparison & Deltas", subtitle_style))
        b = diff_data["baseline"]
        t = diff_data["treatment"]
        d = diff_data["deltas"]

        table_data = [
            ["Metric", "Baseline Run", "Treatment Run", "Delta (Δ)", "Direction / Significance"],
            [
                "VMAF Score",
                f"{b.get('vmaf_mean', 0.0):.2f}" if b.get('vmaf_mean') is not None else "N/A",
                f"{t.get('vmaf_mean', 0.0):.2f}" if t.get('vmaf_mean') is not None else "N/A",
                d.get("delta_vmaf_str", "N/A"),
                "Significant" if sig.get("is_significant") else "Noise Floor"
            ],
            [
                "PSNR (dB)",
                f"{b.get('psnr_mean', 0.0):.2f}" if b.get('psnr_mean') is not None else "N/A",
                f"{t.get('psnr_mean', 0.0):.2f}" if t.get('psnr_mean') is not None else "N/A",
                d.get("delta_psnr_str", "N/A"),
                "—"
            ],
            [
                "SSIM",
                f"{b.get('ssim_mean', 0.0):.4f}" if b.get('ssim_mean') is not None else "N/A",
                f"{t.get('ssim_mean', 0.0):.4f}" if t.get('ssim_mean') is not None else "N/A",
                d.get("delta_ssim_str", "N/A"),
                "—"
            ],
            [
                "VMAF StdDev (σ)",
                f"{b.get('vmaf_stddev', 0.0):.4f}",
                f"{t.get('vmaf_stddev', 0.0):.4f}",
                d.get("delta_sigma_str", "N/A"),
                "—"
            ],
            [
                "Repeatability %CV",
                f"{b.get('cv_pct', 0.0):.3f}%" if b.get('cv_pct') is not None else "N/A",
                f"{t.get('cv_pct', 0.0):.3f}%" if t.get('cv_pct') is not None else "N/A",
                d.get("delta_cv_pct_str", "N/A"),
                "—"
            ],
            [
                "Gage R&R Verdict",
                str(b.get("verdict", "N/A")),
                str(t.get("verdict", "N/A")),
                diff_data["verdict_evolution"]["verdict_evolution_text"],
                "State Match" if not diff_data["verdict_evolution"]["verdict_changed"] else "State Shift"
            ],
        ]

        m_table = Table(table_data, colWidths=[1.5 * inch, 1.3 * inch, 1.3 * inch, 1.4 * inch, 1.9 * inch])
        m_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ]))
        elements.append(m_table)
        elements.append(Spacer(1, 0.05 * inch))

        conv_style = ParagraphStyle(
            'ConventionNote',
            parent=styles['Normal'],
            fontName='Helvetica-Oblique',
            fontSize=7.5,
            leading=10,
            textColor=colors.HexColor('#64748b')
        )
        elements.append(Paragraph(
            "Convention: Arrows (▲/▼) indicate numeric direction (+/-). Metrological significance and polarity evaluated relative to combined uncertainty.",
            conv_style
        ))
        elements.append(Spacer(1, 0.08 * inch))

        if d.get("divergence_advisory"):
            adv_style = ParagraphStyle(
                'DivergenceAdvisory',
                parent=styles['Normal'],
                fontName='Helvetica',
                fontSize=8,
                leading=11,
                textColor=colors.HexColor('#92400e')
            )
            adv_p = Paragraph(f"<b>Metrology Notice:</b> {d['divergence_advisory']}", adv_style)
            adv_table = Table([[adv_p]], colWidths=[7.4 * inch])
            adv_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fffbeb')),
                ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#f59e0b')),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ]))
            elements.append(adv_table)
            elements.append(Spacer(1, 0.1 * inch))
        else:
            elements.append(Spacer(1, 0.07 * inch))

        # 4. Uncertainty & Noise Floor Explanation
        elements.append(Paragraph("Metrological Uncertainty Budget", subtitle_style))
        floor_param = "Empirical Rig Noise Floor" if sig.get("is_empirical_floor") else "Resolution Convention"
        floor_sym = "σ_rig" if sig.get("is_empirical_floor") else "σ_floor"
        floor_interp = "Measured hardware capture-chain uncertainty (Gage R&R repeatability)" if sig.get("is_empirical_floor") else "Declared instrument resolution floor convention (0.05)"
        comb_sym = "σ_Δ = √(σ_1² + σ_2² + σ_rig²)" if sig.get("is_empirical_floor") else "σ_Δ = √(σ_1² + σ_2² + σ_floor²)"
        comb_interp = "Quadrature combined uncertainty from empirical repeatability" if sig.get("is_empirical_floor") else "Quadrature combined measurement uncertainty"

        u_data = [
            ["Parameter", "Symbol / Formula", "Value", "Interpretation"],
            ["Baseline Variance", "σ_1", f"{sig['sigma_1']:.4f}", "Sample standard deviation of baseline campaign"],
            ["Treatment Variance", "σ_2", f"{sig['sigma_2']:.4f}", "Sample standard deviation of treatment campaign"],
            [floor_param, floor_sym, f"{sig['sigma_floor_convention']:.4f}", floor_interp],
            ["Combined Uncertainty", comb_sym, f"{sig['combined_sigma_delta']:.4f}", comb_interp],
            ["3σ Detection Floor", "T_3σ = 3 × σ_Δ", f"{sig['threshold_3sigma']:.4f}", "Minimum delta for 99.7% confidence significance"],
            ["Signal-to-Noise Ratio", "SNR = |ΔVMAF| / σ_Δ", f"{sig['snr_delta']:.2f}x", "Effect size relative to combined uncertainty"],
        ]
        u_table = Table(u_data, colWidths=[1.8 * inch, 2.2 * inch, 1.1 * inch, 2.3 * inch])
        u_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f1f5f9')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (2, 0), (2, -1), 'CENTER'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ]))
        elements.append(u_table)

        if sig.get("is_empirical_floor"):
            u_note = (
                "<font size=7.5 color='#166534'><b>Metrological Notice:</b> The 3σ detection threshold is derived from empirical "
                "hardware re-capture repeatability (σ_rig), replacing the declared resolution convention with measured instrument uncertainty.</font>"
            )
            elements.append(Paragraph(u_note, styles['Normal']))
            elements.append(Spacer(1, 0.08 * inch))
        else:
            elements.append(Spacer(1, 0.15 * inch))

        # 5. Embedded Comparison Chart
        elements.append(Paragraph(
            f"Comparison Chart ({'Per-Frame Delta Curve' if diff_data['chart_mode'] == 'frame_curve' else 'Pooled Metric Distribution'})",
            subtitle_style
        ))
        with tempfile.TemporaryDirectory() as tmp_dir:
            chart_png = os.path.join(tmp_dir, "diff_chart.png")
            self.generate_diff_chart(diff_data, chart_png)
            if os.path.isfile(chart_png):
                elements.append(Image(chart_png, width=7.2 * inch, height=3.2 * inch))
                elements.append(Spacer(1, 0.12 * inch))

            # 6. Traceability & Fixture Verification Table
            elements.append(Paragraph("Fixture & Toolchain Traceability", subtitle_style))
            tr = diff_data["traceability"]
            t_data = [
                ["Attribute", "Baseline Run", "Treatment Run", "Match Status"],
                [
                    "Reference Fixture",
                    f"{b.get('reference_file')} ({b.get('reference_sha256')})",
                    f"{t.get('reference_file')} ({t.get('reference_sha256')})",
                    "MATCH" if tr["reference_match"] else "DIFFERENT"
                ],
                [
                    "Distorted Fixture",
                    f"{b.get('distorted_file')} ({b.get('distorted_sha256')})",
                    f"{t.get('distorted_file')} ({t.get('distorted_sha256')})",
                    "MATCH" if tr["distorted_match"] else "DIFFERENT (Expected for Quality Delta)"
                ],
                [
                    "VMAF Model",
                    str(b.get("model", "unknown")),
                    str(t.get("model", "unknown")),
                    "MATCH" if b.get("model") == t.get("model") else "MISMATCH"
                ],
                [
                    "App Version",
                    str(b.get("app_version", "unknown")),
                    str(t.get("app_version", "unknown")),
                    "MATCH" if b.get("app_version") == t.get("app_version") else "DIFFERENT"
                ],
                [
                    "Git Commit",
                    str(b.get("git_commit", "unknown")),
                    str(t.get("git_commit", "unknown")),
                    "MATCH" if b.get("git_commit") == t.get("git_commit") else "DIFFERENT"
                ],
            ]
            tr_table = Table(t_data, colWidths=[1.5 * inch, 2.3 * inch, 2.3 * inch, 1.3 * inch])
            tr_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8fafc')),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 7.5),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('ALIGN', (3, 0), (3, -1), 'CENTER'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ]))
            elements.append(tr_table)

            doc.build(elements)

        logger.info(f"Generated PDF diff report: {output_pdf_path}")
        return output_pdf_path


def compare_campaigns(
    baseline_source: Union[dict, str, int],
    treatment_source: Union[dict, str, int],
    sigma_floor: float = DEFAULT_RESOLUTION_FLOOR_SIGMA,
    log_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Convenience helper to compare two campaigns or runs."""
    analyzer = DiffAnalyzer(sigma_floor=sigma_floor)
    return analyzer.compare_campaigns(baseline_source, treatment_source, log_path=log_path)


def generate_diff_pdf(
    diff_data: Dict[str, Any],
    output_pdf_path: str,
    sigma_floor: float = DEFAULT_RESOLUTION_FLOOR_SIGMA,
) -> str:
    """Convenience helper to generate a PDF diff report."""
    analyzer = DiffAnalyzer(sigma_floor=sigma_floor)
    return analyzer.generate_diff_pdf(diff_data, output_pdf_path)
