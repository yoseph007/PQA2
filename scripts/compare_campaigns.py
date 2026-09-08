#!/usr/bin/env python3
"""
CLI Campaign & Run Diff Utility for VMAF Quality Assessment Application.

Compares two campaign records or run JSON files, computes statistical delta metrics,
evaluates the 3-sigma instrument noise floor gate, and optionally exports a PDF report.

Exit codes for --fail-on-degradation:
  0: Success (improved, neutral, or within instrument noise floor)
  1: Statistically significant degradation detected (is_significant AND delta_vmaf < 0)
  2: Incomparable records (toolchain or model mismatch)
"""

import os
import sys
import json
import argparse
from typing import Optional, List, Dict, Any

# Ensure console supports UTF-8 on Windows
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.version import get_version_string, get_git_commit
from app.repeatability_analyzer import read_campaign_history, get_campaign_history_log_path
from app.diff_analyzer import DiffAnalyzer, compare_campaigns, generate_diff_pdf


def format_ascii_diff(diff: Dict[str, Any]) -> str:
    """Format structured diff data into a clean, aligned terminal display."""
    lines = []
    lines.append("=" * 76)
    lines.append(f" VMAF QUALITY METROLOGY DIFF — {get_version_string()}")
    lines.append(f" Timestamp: {diff.get('timestamp_comparison')} | Workspace: {PROJECT_ROOT}")
    lines.append("=" * 76)

    # Executive Banner
    sig = diff["metrology"]
    label = sig.get("significance_label", "Diff")
    desc = sig.get("significance_description", "")
    tr = diff["traceability"]

    if not tr.get("toolchain_compatible", True):
        lines.append("\n [WARNING: INCOMPATIBLE COMPARISON]")
        lines.append(f" Toolchain Mismatch: {'; '.join(tr['incompatible_reasons'])}")
        lines.append(" Deltas may reflect toolchain divergence rather than signal quality.\n")
    else:
        lines.append(f"\n [EXECUTIVE VERDICT: {label.upper()}]")
        lines.append(f" {desc}\n")

    # Metrics Table
    b = diff["baseline"]
    t = diff["treatment"]
    d = diff["deltas"]

    lines.append("-" * 76)
    lines.append(f" {'Metric':<22} | {'Baseline':<12} | {'Treatment':<12} | {'Delta (Direction)':<18}")
    lines.append("-" * 76)

    def _fmt(val, decimals=2):
        return f"{val:.{decimals}f}" if val is not None else "N/A"

    def _annotated_delta(val_str, polarity):
        if not val_str or val_str == "N/A" or "suppressed" in val_str:
            return val_str
        if polarity == "improved":
            return f"{val_str} [better]"
        elif polarity == "degraded":
            return f"{val_str} [worse]"
        return val_str

    lines.append(f" {'VMAF Score':<22} | {_fmt(b.get('vmaf_mean')):<12} | {_fmt(t.get('vmaf_mean')):<12} | {_annotated_delta(d.get('delta_vmaf_str'), d.get('delta_vmaf_polarity')):<18}")
    lines.append(f" {'PSNR (dB)':<22} | {_fmt(b.get('psnr_mean')):<12} | {_fmt(t.get('psnr_mean')):<12} | {_annotated_delta(d.get('delta_psnr_str'), d.get('delta_psnr_polarity')):<18}")
    lines.append(f" {'SSIM':<22} | {_fmt(b.get('ssim_mean'), 4):<12} | {_fmt(t.get('ssim_mean'), 4):<12} | {_annotated_delta(d.get('delta_ssim_str'), d.get('delta_ssim_polarity')):<18}")
    lines.append(f" {'VMAF StdDev (sigma)':<22} | {_fmt(b.get('vmaf_stddev'), 4):<12} | {_fmt(t.get('vmaf_stddev'), 4):<12} | {_annotated_delta(d.get('delta_sigma_str'), d.get('delta_sigma_polarity')):<18}")
    lines.append(f" {'Repeatability %CV':<22} | {_fmt(b.get('cv_pct'), 3) + '%':<12} | {_fmt(t.get('cv_pct'), 3) + '%':<12} | {_annotated_delta(d.get('delta_cv_pct_str'), d.get('delta_cv_pct_polarity')):<18}")
    lines.append(f" {'Gage R&R Verdict':<22} | {str(b.get('verdict')):<12} | {str(t.get('verdict')):<12} | {diff['verdict_evolution']['verdict_evolution_text']:<18}")
    lines.append("-" * 76)
    lines.append(" Convention: ▲/▼ indicates numeric direction (+/-). [better]/[worse] indicates metrological quality.")

    # Metric Divergence Notice if applicable
    if d.get("divergence_advisory"):
        lines.append(f"\n [ADVISORY] {d['divergence_advisory']}")

    # Uncertainty Budget Table
    lines.append("\n METROLOGICAL UNCERTAINTY BUDGET (Quadrature Combined sigma_delta):")
    lines.append(f"  * Baseline Variance (sigma_1)        : {sig['sigma_1']:.4f}")
    lines.append(f"  * Treatment Variance (sigma_2)       : {sig['sigma_2']:.4f}")
    floor_label = "Measured Rig Noise Floor (sigma_rig)" if sig.get("is_empirical_floor") else "Declared Resolution Floor (sigma_f)"
    lines.append(f"  * {floor_label:<35}: {sig['sigma_floor_convention']:.4f}")
    lines.append(f"  * Combined Uncertainty (sigma_delta) : {sig['combined_sigma_delta']:.4f}")
    lines.append(f"  * 3-Sigma Noise Floor Threshold (T)  : {sig['threshold_3sigma']:.4f} VMAF points")
    lines.append(f"  * Observed Signal-to-Noise (SNR)     : {sig['snr_delta']:.2f}x")
    lines.append(f"  * Statistically Significant?         : {'YES [PASS]' if sig['is_significant'] else 'NO (within instrument noise floor)'}")

    # Traceability
    lines.append("\n FIXTURE & TOOLCHAIN TRACEABILITY:")
    lines.append(f"  * Reference Fixtures : {b.get('reference_file')} ({b.get('reference_sha256')}) vs {t.get('reference_file')} ({t.get('reference_sha256')})")
    lines.append(f"  * Distorted Fixtures : {b.get('distorted_file')} ({b.get('distorted_sha256')}) vs {t.get('distorted_file')} ({t.get('distorted_sha256')})")
    lines.append(f"  * Models             : {b.get('model')} vs {t.get('model')} [{'MATCH' if b.get('model') == t.get('model') else 'MISMATCH'}]")
    lines.append(f"  * App Versions       : {b.get('app_version')} vs {t.get('app_version')}")
    lines.append(f"  * Git Commits        : {b.get('git_commit')} vs {t.get('git_commit')}")
    lines.append("=" * 76)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Metrology Diff Mode between VMAF campaigns or runs")
    parser.add_argument("--latest", type=int, default=None, help="Compare the last N campaigns in history (default: 2, comparing second-to-last as baseline vs last as treatment)")
    parser.add_argument("--baseline", type=int, default=None, help="Integer index of baseline campaign in history log (e.g. -2 or 0)")
    parser.add_argument("--treatment", type=int, default=None, help="Integer index of treatment campaign in history log (e.g. -1 or 1)")
    parser.add_argument("--file1", type=str, default=None, help="Path to baseline JSON run file")
    parser.add_argument("--file2", type=str, default=None, help="Path to treatment JSON run file")
    parser.add_argument("--type", type=str, default=None, help="Filter campaign history by type ('fixed_pair' or 'recapture')")
    parser.add_argument("--sigma-floor", type=float, default=None, help="Custom uncertainty floor (default: max(0.05, measured sigma_rig if recapture campaign))")
    parser.add_argument("--log-path", type=str, default=None, help="Custom campaign history JSONL log path")
    parser.add_argument("--pdf", type=str, default=None, help="Output file path to generate PDF comparison report")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON to stdout")
    parser.add_argument("--fail-on-degradation", action="store_true", help="Exit code 1 if significant degradation detected; exit code 2 if toolchain incompatible")

    args = parser.parse_args()

    # Resolve baseline and treatment records
    analyzer = DiffAnalyzer(sigma_floor=args.sigma_floor if args.sigma_floor is not None else 0.05)

    if args.file1 and args.file2:
        baseline_src = args.file1
        treatment_src = args.file2
    elif args.baseline is not None and args.treatment is not None:
        baseline_src = args.baseline
        treatment_src = args.treatment
    else:
        # Default: --latest 2
        # Annotation 2: Order explicitly by append order in JSONL
        records = read_campaign_history(log_path=args.log_path, campaign_type=args.type)
        if len(records) < 2:
            print(f"[ERROR] Insufficient campaign history: found {len(records)} records (at least 2 required for diff).", file=sys.stderr)
            sys.exit(2)
        # Baseline = second-to-last, Treatment = last
        baseline_src = records[-2]
        treatment_src = records[-1]

    try:
        diff_payload = analyzer.compare_campaigns(baseline_src, treatment_src, log_path=args.log_path)
    except Exception as e:
        print(f"[ERROR] Failed to compute campaign diff: {e}", file=sys.stderr)
        sys.exit(2)

    # Optional PDF generation
    if args.pdf:
        try:
            out_pdf = os.path.abspath(args.pdf)
            analyzer.generate_diff_pdf(diff_payload, out_pdf)
            print(f"[INFO] PDF diff report generated: {out_pdf}")
        except Exception as e:
            print(f"[ERROR] Failed to generate PDF report: {e}", file=sys.stderr)

    # Output formatting
    if args.json:
        # Strip large raw frames array if present to keep stdout clean
        clean_payload = {k: v for k, v in diff_payload.items() if not k.startswith("raw_frames")}
        print(json.dumps(clean_payload, indent=2))
    else:
        print(format_ascii_diff(diff_payload))

    # Annotation 3: --fail-on-degradation exit code logic
    if args.fail_on_degradation:
        # 1. Toolchain compatibility check: exit 2 if incompatible
        if not diff_payload["traceability"]["toolchain_compatible"]:
            print("\n[GATE FAILED] Incomparable records: toolchain mismatch detected.", file=sys.stderr)
            sys.exit(2)

        # 2. Significant degradation check: exit 1 if is_significant AND delta_vmaf < 0
        sig = diff_payload["metrology"]
        delta_v = diff_payload["deltas"].get("delta_vmaf")
        if sig.get("is_significant") and delta_v is not None and delta_v < 0:
            print(f"\n[GATE FAILED] Statistically significant degradation detected: ΔVMAF = {delta_v:.2f} (< -{sig['threshold_3sigma']:.3f})", file=sys.stderr)
            sys.exit(1)

        print("\n[GATE PASSED] Quality threshold maintained (no significant degradation).")
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
