"""
PyQt6 Dialog for Metrology Campaign & Run Diff Comparison.

Allows visual comparison of historical Gage R&R campaigns and single runs,
displaying metric deltas, combined uncertainty budgets, and exporting branded PDF diff reports.
"""

import os
import sys
import subprocess
import platform
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QFileDialog, QMessageBox, QFrame
)

from app.repeatability_analyzer import read_campaign_history, get_campaign_history_log_path
from app.diff_analyzer import compare_campaigns, generate_diff_pdf

logger = logging.getLogger(__name__)


class CampaignDiffDialog(QDialog):
    """Interactive modal dialog for comparing two campaigns or runs."""

    def __init__(self, parent=None, log_path: Optional[str] = None):
        super().__init__(parent)
        self.setWindowTitle("VMAF Metrology Diff — Campaign & Run Comparison")
        self.resize(880, 720)
        self.log_path = log_path or get_campaign_history_log_path()
        self.records: List[Dict[str, Any]] = []
        self.current_diff: Optional[Dict[str, Any]] = None

        self._setup_ui()
        self._load_records()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 1. Selection Header
        selector_group = QGroupBox("Select Campaigns to Compare")
        sel_layout = QVBoxLayout(selector_group)

        # Baseline row
        r1_layout = QHBoxLayout()
        lbl_r1 = QLabel("Baseline Run (Reference):")
        lbl_r1.setFixedWidth(160)
        lbl_r1.setStyleSheet("font-weight: bold;")
        self.combo_baseline = QComboBox()
        self.combo_baseline.currentIndexChanged.connect(self._on_selection_changed)
        r1_layout.addWidget(lbl_r1)
        r1_layout.addWidget(self.combo_baseline)
        sel_layout.addLayout(r1_layout)

        # Treatment row
        r2_layout = QHBoxLayout()
        lbl_r2 = QLabel("Treatment Run (Candidate):")
        lbl_r2.setFixedWidth(160)
        lbl_r2.setStyleSheet("font-weight: bold;")
        self.combo_treatment = QComboBox()
        self.combo_treatment.currentIndexChanged.connect(self._on_selection_changed)
        r2_layout.addWidget(lbl_r2)
        r2_layout.addWidget(self.combo_treatment)
        sel_layout.addLayout(r2_layout)

        layout.addWidget(selector_group)

        # 2. Executive Callout Banner
        self.banner_frame = QFrame()
        self.banner_frame.setFrameShape(QFrame.Shape.StyledPanel)
        banner_layout = QVBoxLayout(self.banner_frame)
        self.lbl_banner_title = QLabel("DIFF SUMMARY")
        self.lbl_banner_title.setStyleSheet("font-size: 13px; font-weight: bold;")
        self.lbl_banner_desc = QLabel("Select two campaigns above to compute metrology deltas.")
        self.lbl_banner_desc.setWordWrap(True)
        banner_layout.addWidget(self.lbl_banner_title)
        banner_layout.addWidget(self.lbl_banner_desc)
        layout.addWidget(self.banner_frame)

        # 3. Metric Comparison Table
        table_group = QGroupBox("Metric Deltas")
        tg_layout = QVBoxLayout(table_group)

        self.table_metrics = QTableWidget()
        self.table_metrics.setColumnCount(4)
        self.table_metrics.setHorizontalHeaderLabels([
            "Metric", "Baseline Value", "Treatment Value", "Delta (Direction)"
        ])
        self.table_metrics.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_metrics.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_metrics.setAlternatingRowColors(True)
        tg_layout.addWidget(self.table_metrics)

        # Convention Note
        self.lbl_convention_note = QLabel(
            "Convention: Arrows (▲/▼) indicate numeric direction (+/-). Green = improved quality / stability; Red = degraded."
        )
        self.lbl_convention_note.setStyleSheet("font-size: 10px; color: #64748b; font-style: italic; margin-top: 2px;")
        tg_layout.addWidget(self.lbl_convention_note)

        # Metric Divergence Advisory Callout
        self.lbl_divergence_note = QLabel()
        self.lbl_divergence_note.setWordWrap(True)
        self.lbl_divergence_note.setStyleSheet(
            "background-color: #fffbeb; border: 1px solid #f59e0b; border-radius: 4px; padding: 6px; font-size: 11px; color: #92400e; margin-top: 4px;"
        )
        self.lbl_divergence_note.setVisible(False)
        tg_layout.addWidget(self.lbl_divergence_note)

        layout.addWidget(table_group)

        # 4. Uncertainty & Traceability Info
        info_layout = QHBoxLayout()

        # Uncertainty Box
        self.group_uncertainty = QGroupBox("Metrological Uncertainty Budget")
        u_box_layout = QVBoxLayout(self.group_uncertainty)
        self.lbl_u_sigma = QLabel("Combined Uncertainty (σ_Δ): N/A")
        self.lbl_u_threshold = QLabel("3-Sigma Detection Floor: N/A")
        self.lbl_u_snr = QLabel("Signal-to-Noise Ratio (SNR): N/A")
        self.lbl_u_sig = QLabel("Significance: N/A")
        u_box_layout.addWidget(self.lbl_u_sigma)
        u_box_layout.addWidget(self.lbl_u_threshold)
        u_box_layout.addWidget(self.lbl_u_snr)
        u_box_layout.addWidget(self.lbl_u_sig)
        info_layout.addWidget(self.group_uncertainty)

        # Traceability Box
        self.group_traceability = QGroupBox("Fixture && Toolchain Traceability")
        t_box_layout = QVBoxLayout(self.group_traceability)
        self.lbl_t_ref = QLabel("Reference: N/A")
        self.lbl_t_dist = QLabel("Distorted: N/A")
        self.lbl_t_model = QLabel("VMAF Model: N/A")
        self.lbl_t_commit = QLabel("Git Commit: N/A")
        t_box_layout.addWidget(self.lbl_t_ref)
        t_box_layout.addWidget(self.lbl_t_dist)
        t_box_layout.addWidget(self.lbl_t_model)
        t_box_layout.addWidget(self.lbl_t_commit)
        info_layout.addWidget(self.group_traceability)

        layout.addLayout(info_layout)

        # 5. Dialog Action Buttons
        btn_layout = QHBoxLayout()
        self.btn_export_pdf = QPushButton("Export Diff PDF Report...")
        self.btn_export_pdf.setEnabled(False)
        self.btn_export_pdf.clicked.connect(self._export_pdf)
        btn_layout.addWidget(self.btn_export_pdf)

        btn_layout.addStretch()

        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

    def _load_records(self):
        """Load records from campaign history into combo boxes."""
        self.records = read_campaign_history(log_path=self.log_path)
        self.combo_baseline.blockSignals(True)
        self.combo_treatment.blockSignals(True)

        self.combo_baseline.clear()
        self.combo_treatment.clear()

        if not self.records:
            self.combo_baseline.addItem("No historical campaigns found")
            self.combo_treatment.addItem("No historical campaigns found")
            self.combo_baseline.blockSignals(False)
            self.combo_treatment.blockSignals(False)
            return

        for idx, rec in enumerate(self.records):
            ts = rec.get("timestamp", "unknown")
            c_type = rec.get("campaign_type", "fixed_pair")
            v_val = f"{rec.get('vmaf_mean'):.2f}" if rec.get("vmaf_mean") is not None else "N/A"
            dist_f = os.path.basename(str(rec.get("distorted_file") or "unknown"))
            label = f"#{idx+1}: [{ts}] {dist_f} — VMAF={v_val} ({c_type})"
            self.combo_baseline.addItem(label, idx)
            self.combo_treatment.addItem(label, idx)

        # Default ordering per Annotation 2:
        # Baseline = second-to-last (records[-2]), Treatment = last (records[-1])
        if len(self.records) >= 2:
            self.combo_baseline.setCurrentIndex(len(self.records) - 2)
            self.combo_treatment.setCurrentIndex(len(self.records) - 1)
        else:
            self.combo_baseline.setCurrentIndex(0)
            self.combo_treatment.setCurrentIndex(0)

        self.combo_baseline.blockSignals(False)
        self.combo_treatment.blockSignals(False)

        self._on_selection_changed()

    def _on_selection_changed(self):
        """Recompute diff when either dropdown selection changes."""
        idx1 = self.combo_baseline.currentIndex()
        idx2 = self.combo_treatment.currentIndex()

        if idx1 < 0 or idx2 < 0 or not self.records or idx1 >= len(self.records) or idx2 >= len(self.records):
            return

        rec1 = self.records[idx1]
        rec2 = self.records[idx2]

        try:
            self.current_diff = compare_campaigns(rec1, rec2)
            self._render_diff(self.current_diff)
            self.btn_export_pdf.setEnabled(True)
        except Exception as e:
            logger.error(f"Error computing diff: {e}")
            self.btn_export_pdf.setEnabled(False)

    def _render_diff(self, diff: Dict[str, Any]):
        """Render computed diff payload into UI components."""
        sig = diff["metrology"]
        v_key = sig.get("significance_verdict")
        label = sig.get("significance_label", "Diff Analysis")
        desc = sig.get("significance_description", "")
        tr = diff["traceability"]

        # Banner styling
        if not tr.get("toolchain_compatible", True):
            bg = "#fee2e2"
            border = "#dc2626"
            text_col = "#991b1b"
            title = "INCOMPATIBLE COMPARISON"
            desc = f"Toolchain mismatch: {'; '.join(tr['incompatible_reasons'])}"
        elif v_key == "significant_improvement":
            bg = "#dcfce7"
            border = "#16a34a"
            text_col = "#166534"
            title = label.upper()
        elif v_key == "significant_degradation":
            bg = "#fee2e2"
            border = "#dc2626"
            text_col = "#991b1b"
            title = label.upper()
        else:
            bg = "#fef3c7"
            border = "#d97706"
            text_col = "#92400e"
            title = label.upper()

        self.banner_frame.setStyleSheet(
            f"QFrame {{ background-color: {bg}; border: 2px solid {border}; border-radius: 6px; padding: 6px; }}"
        )
        self.lbl_banner_title.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {text_col};")
        self.lbl_banner_title.setText(title)
        self.lbl_banner_desc.setStyleSheet(f"font-size: 11px; color: {text_col};")
        self.lbl_banner_desc.setText(desc)

        # Table rows
        b = diff["baseline"]
        t = diff["treatment"]
        d = diff["deltas"]

        rows = [
            ("VMAF Score", b.get("vmaf_mean"), t.get("vmaf_mean"), d.get("delta_vmaf_str"), d.get("delta_vmaf_polarity"), 2),
            ("PSNR (dB)", b.get("psnr_mean"), t.get("psnr_mean"), d.get("delta_psnr_str"), d.get("delta_psnr_polarity"), 2),
            ("SSIM", b.get("ssim_mean"), t.get("ssim_mean"), d.get("delta_ssim_str"), d.get("delta_ssim_polarity"), 4),
            ("VMAF StdDev (σ)", b.get("vmaf_stddev"), t.get("vmaf_stddev"), d.get("delta_sigma_str"), d.get("delta_sigma_polarity"), 4),
            ("Repeatability %CV", b.get("cv_pct"), t.get("cv_pct"), d.get("delta_cv_pct_str"), d.get("delta_cv_pct_polarity"), 3, "%"),
            ("Gage R&R Verdict", b.get("verdict"), t.get("verdict"), diff["verdict_evolution"]["verdict_evolution_text"], "neutral", None),
        ]

        self.table_metrics.setRowCount(len(rows))
        for r_idx, row in enumerate(rows):
            name, v1, v2, delta_str, polarity, decimals = row[0], row[1], row[2], row[3], row[4], row[5]
            suffix = row[6] if len(row) > 6 else ""

            v1_str = f"{v1:.{decimals}f}{suffix}" if (v1 is not None and decimals is not None) else str(v1 or "N/A")
            v2_str = f"{v2:.{decimals}f}{suffix}" if (v2 is not None and decimals is not None) else str(v2 or "N/A")

            item_name = QTableWidgetItem(name)
            item_v1 = QTableWidgetItem(v1_str)
            item_v2 = QTableWidgetItem(v2_str)
            item_delta = QTableWidgetItem(str(delta_str or "N/A"))

            item_v1.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_v2.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_delta.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            # Delta coloring based on metrological polarity (decoupled from numeric direction)
            if polarity == "improved":
                item_delta.setForeground(Qt.GlobalColor.darkGreen)
            elif polarity == "degraded":
                item_delta.setForeground(Qt.GlobalColor.red)
            else:
                item_delta.setForeground(Qt.GlobalColor.darkGray)

            self.table_metrics.setItem(r_idx, 0, item_name)
            self.table_metrics.setItem(r_idx, 1, item_v1)
            self.table_metrics.setItem(r_idx, 2, item_v2)
            self.table_metrics.setItem(r_idx, 3, item_delta)

        # Metric Divergence Notice
        if d.get("divergence_advisory"):
            self.lbl_divergence_note.setText(f"<b>Notice:</b> {d['divergence_advisory']}")
            self.lbl_divergence_note.setVisible(True)
        else:
            self.lbl_divergence_note.setVisible(False)

        # Uncertainty labels
        self.lbl_u_sigma.setText(f"Combined Uncertainty (σ_Δ): {sig['combined_sigma_delta']:.4f}")
        self.lbl_u_threshold.setText(f"3-Sigma Detection Floor: {sig['threshold_3sigma']:.4f} VMAF")
        self.lbl_u_snr.setText(f"Signal-to-Noise Ratio (SNR): {sig['snr_delta']:.2f}x")
        self.lbl_u_sig.setText(f"Significance: {'Significant [PASS]' if sig['is_significant'] else 'Within Noise Floor'}")

        # Traceability labels
        ref_status = "MATCH" if tr["reference_match"] else "DIFFERENT"
        dist_status = "MATCH" if tr["distorted_match"] else "DIFFERENT"
        self.lbl_t_ref.setText(f"Reference: {b.get('reference_file')} [{ref_status}]")
        self.lbl_t_dist.setText(f"Distorted: {b.get('distorted_file')} vs {t.get('distorted_file')} [{dist_status}]")
        self.lbl_t_model.setText(f"Model: {b.get('model')} vs {t.get('model')}")
        self.lbl_t_commit.setText(f"Git Commit: {b.get('git_commit')} vs {t.get('git_commit')}")

    def _export_pdf(self):
        """Export PDF report for current comparison."""
        if not self.current_diff:
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"vmaf_diff_report_{timestamp}.pdf"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Diff PDF Report",
            os.path.join(os.path.expanduser("~"), default_name),
            "PDF Files (*.pdf)"
        )

        if not file_path:
            return

        try:
            generate_diff_pdf(self.current_diff, file_path)
            reply = QMessageBox.question(
                self,
                "PDF Export Complete",
                f"Diff report successfully exported to:\n{file_path}\n\nWould you like to open it now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            if reply == QMessageBox.StandardButton.Yes:
                if platform.system() == "Windows":
                    os.startfile(file_path)
                elif platform.system() == "Darwin":
                    subprocess.run(["open", file_path], check=False)
                else:
                    subprocess.run(["xdg-open", file_path], check=False)
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Failed to generate diff PDF: {e}")
