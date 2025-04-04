import os
import json
import logging
import platform
import subprocess
from datetime import datetime
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                           QLabel, QTabWidget, QGroupBox, QListWidget, 
                           QListWidgetItem, QTableWidget, QTableWidgetItem,
                           QAbstractItemView, QHeaderView, QMessageBox, QTextEdit)
from PyQt5.QtCore import Qt

logger = logging.getLogger(__name__)

class ResultsTab(QWidget):
    """Results tab for displaying and interacting with analysis results"""

    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self._setup_ui()

    def _setup_ui(self):
        """Set up the Results tab with data grid for historical results"""
        layout = QVBoxLayout(self)

        # Results summary
        self.lbl_results_summary = QLabel("No VMAF analysis results yet")
        layout.addWidget(self.lbl_results_summary)

        # Create tabs for current result and history
        results_tabs = QTabWidget()
        current_tab = QWidget()
        history_tab = QWidget()
        results_tabs.addTab(current_tab, "Current Result")
        results_tabs.addTab(history_tab, "History")

        # Setup current result tab
        current_layout = QVBoxLayout(current_tab)

        # VMAF score display
        score_group = QGroupBox("VMAF Scores")
        score_layout = QVBoxLayout()

        self.lbl_vmaf_score = QLabel("VMAF Score: --")
        self.lbl_vmaf_score.setStyleSheet("font-size: 24px; font-weight: bold;")
        score_layout.addWidget(self.lbl_vmaf_score)

        scores_detail = QHBoxLayout()
        self.lbl_psnr_score = QLabel("PSNR: --")
        self.lbl_ssim_score = QLabel("SSIM: --")
        scores_detail.addWidget(self.lbl_psnr_score)
        scores_detail.addWidget(self.lbl_ssim_score)
        scores_detail.addStretch()
        score_layout.addLayout(scores_detail)

        score_group.setLayout(score_layout)
        current_layout.addWidget(score_group)

        # Export options
        export_group = QGroupBox("Export Results")
        export_layout = QVBoxLayout()

        export_buttons = QHBoxLayout()
        self.btn_export_pdf = QPushButton("Export PDF Certificate")
        self.btn_export_pdf.clicked.connect(self.export_pdf_certificate)
        self.btn_export_pdf.setEnabled(False)

        self.btn_export_csv = QPushButton("Export CSV Data")
        self.btn_export_csv.clicked.connect(self.export_csv_data)
        self.btn_export_csv.setEnabled(False)

        export_buttons.addWidget(self.btn_export_pdf)
        export_buttons.addWidget(self.btn_export_csv)
        export_buttons.addStretch()
        export_layout.addLayout(export_buttons)

        export_group.setLayout(export_layout)
        current_layout.addWidget(export_group)

        # Results files
        files_group = QGroupBox("Result Files")
        files_layout = QVBoxLayout()

        self.list_result_files = QListWidget()
        self.list_result_files.itemDoubleClicked.connect(self.open_result_file)
        files_layout.addWidget(self.list_result_files)

        files_group.setLayout(files_layout)
        current_layout.addWidget(files_group)

        # Setup history tab with data grid
        history_layout = QVBoxLayout(history_tab)

        # Create table for results history
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(8)
        self.results_table.setHorizontalHeaderLabels([
            "Test Name", "Date/Time", "VMAF Score", "PSNR", "SSIM", 
            "Reference", "Duration", "Actions"
        ])
        self.results_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        # Add controls above table
        history_controls = QHBoxLayout()
        self.btn_refresh_history = QPushButton("Refresh History")
        self.btn_refresh_history.clicked.connect(self.load_results_history)
        history_controls.addWidget(self.btn_refresh_history)

        self.btn_delete_selected = QPushButton("Delete Selected")
        self.btn_delete_selected.clicked.connect(self.delete_selected_results)
        history_controls.addWidget(self.btn_delete_selected)

        self.btn_export_selected = QPushButton("Export Selected")
        self.btn_export_selected.clicked.connect(self.export_selected_results)
        history_controls.addWidget(self.btn_export_selected)

        history_controls.addStretch()

        history_layout.addLayout(history_controls)
        history_layout.addWidget(self.results_table)

        # Add results tabs to main layout
        layout.addWidget(results_tabs)

        # Navigation buttons at the bottom
        nav_layout = QHBoxLayout()
        self.btn_prev_to_analysis = QPushButton("Back: Analysis")
        nav_layout.addWidget(self.btn_prev_to_analysis)

        nav_layout.addStretch()

        self.btn_new_test = QPushButton("Start New Test")
        self.btn_new_test.clicked.connect(self.start_new_test)
        nav_layout.addWidget(self.btn_new_test)

        layout.addLayout(nav_layout)

        # Load results history
        self.load_results_history()

    def update_with_results(self, results):
        """Update UI with VMAF analysis results"""
        # Update test name in header
        test_name = self.parent.setup_tab.txt_test_name.text()
        self.lbl_results_summary.setText(f"VMAF Analysis Results for {test_name}")

        # Update metrics display
        vmaf_score = results.get('vmaf_score')
        psnr = results.get('psnr')
        ssim = results.get('ssim')

        if vmaf_score is not None:
            self.lbl_vmaf_score.setText(f"VMAF Score: {vmaf_score:.2f}")
        else:
            self.lbl_vmaf_score.setText("VMAF Score: N/A")

        if psnr is not None:
            self.lbl_psnr_score.setText(f"PSNR: {psnr:.2f} dB")
        else:
            self.lbl_psnr_score.setText("PSNR: N/A")

        if ssim is not None:
            self.lbl_ssim_score.setText(f"SSIM: {ssim:.4f}")
        else:
            self.lbl_ssim_score.setText("SSIM: N/A")

        # Enable export buttons
        self.btn_export_pdf.setEnabled(True)
        self.btn_export_csv.setEnabled(True)

        # Update result files list
        self.update_result_files_list(results)

    def update_result_files_list(self, results):
        """Update the list of result files"""
        self.list_result_files.clear()

        # Add final output files
        json_path = results.get('json_path')
        if json_path and os.path.exists(json_path):
            item = QListWidgetItem(f"VMAF Results: {os.path.basename(json_path)}")
            item.setData(Qt.UserRole, json_path)
            self.list_result_files.addItem(item)

        psnr_log = results.get('psnr_log')
        if psnr_log and os.path.exists(psnr_log):
            item = QListWidgetItem(f"PSNR Log: {os.path.basename(psnr_log)}")
            item.setData(Qt.UserRole, psnr_log)
            self.list_result_files.addItem(item)

        ssim_log = results.get('ssim_log')
        if ssim_log and os.path.exists(ssim_log):
            item = QListWidgetItem(f"SSIM Log: {os.path.basename(ssim_log)}")
            item.setData(Qt.UserRole, ssim_log)
            self.list_result_files.addItem(item)

        csv_path = results.get('csv_path')
        if csv_path and os.path.exists(csv_path):
            item = QListWidgetItem(f"VMAF CSV: {os.path.basename(csv_path)}")
            item.setData(Qt.UserRole, csv_path)
            self.list_result_files.addItem(item)

        ref_path = results.get('reference_path')
        if ref_path and os.path.exists(ref_path):
            item = QListWidgetItem(f"Reference: {os.path.basename(ref_path)}")
            item.setData(Qt.UserRole, ref_path)
            self.list_result_files.addItem(item)

        dist_path = results.get('distorted_path')
        if dist_path and os.path.exists(dist_path):
            item = QListWidgetItem(f"Captured: {os.path.basename(dist_path)}")
            item.setData(Qt.UserRole, dist_path)
            self.list_result_files.addItem(item)

        # Add aligned videos
        if self.parent.aligned_paths:
            for key, path in self.parent.aligned_paths.items():
                if path and os.path.exists(path):
                    item = QListWidgetItem(f"Aligned {key.title()}: {os.path.basename(path)}")
                    item.setData(Qt.UserRole, path)
                    self.list_result_files.addItem(item)

    def export_pdf_certificate(self):
        """Export VMAF results as PDF certificate"""
        if not hasattr(self.parent, 'vmaf_results') or not self.parent.vmaf_results:
            QMessageBox.warning(self, "Export Error", "No VMAF results available to export.")
            return
            
        try:
            from PyQt5.QtWidgets import QFileDialog, QProgressDialog
            from PyQt5.QtCore import Qt
            
            # Get test metadata
            test_name = self.parent.setup_tab.txt_test_name.text()
            tester_name = self.parent.setup_tab.txt_tester_name.text() if hasattr(self.parent.setup_tab, 'txt_tester_name') else ""
            test_location = self.parent.setup_tab.txt_test_location.text() if hasattr(self.parent.setup_tab, 'txt_test_location') else ""
            
            test_metadata = {
                "test_name": test_name,
                "tester_name": tester_name,
                "test_location": test_location,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            # Get output file path
            default_filename = f"{test_name}_vmaf_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            output_path = QFileDialog.getSaveFileName(
                self,
                "Save VMAF Report",
                os.path.join(os.path.expanduser("~"), default_filename),
                "PDF Files (*.pdf)"
            )[0]
            
            if not output_path:
                return
                
            # Create progress dialog
            progress = QProgressDialog("Generating PDF report...", "Cancel", 0, 100, self)
            progress.setWindowTitle("Exporting Report")
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(0)
            progress.setValue(0)
            progress.show()
            
            # Import report generator
            from app.report_generator import ReportGeneratorThread
            
            # Create and start generator thread
            self.report_thread = ReportGeneratorThread(
                self.parent.vmaf_results,
                test_metadata,
                output_path
            )
            
            # Connect signals
            self.report_thread.report_progress.connect(progress.setValue)
            self.report_thread.report_complete.connect(self._handle_report_complete)
            self.report_thread.report_error.connect(self._handle_report_error)
            self.report_thread.finished.connect(progress.close)
            
            # Start report generation
            self.report_thread.start()
            
        except Exception as e:
            logger.error(f"Error starting report export: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            QMessageBox.critical(self, "Export Error", f"Failed to export report: {str(e)}")
    
    def _handle_report_complete(self, path):
        """Handle report generation completion"""
        QMessageBox.information(
            self,
            "Export Complete",
            f"VMAF report successfully exported to:\n{path}"
        )
        
        # Ask if user wants to open the report
        reply = QMessageBox.question(
            self,
            "Open Report",
            "Would you like to open the report now?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        
        if reply == QMessageBox.Yes:
            try:
                if platform.system() == 'Windows':
                    os.startfile(path)
                elif platform.system() == 'Darwin':  # macOS
                    subprocess.run(['open', path], check=True)
                else:  # Linux
                    subprocess.run(['xdg-open', path], check=True)
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Open Failed",
                    f"Could not open the report: {str(e)}"
                )
    
    def _handle_report_error(self, error_msg):
        """Handle report generation error"""
        QMessageBox.critical(
            self,
            "Export Error",
            f"Failed to generate report: {error_msg}"
        )

    def export_csv_data(self):
        """Export VMAF results as CSV data"""
        if not hasattr(self.parent, 'vmaf_results') or not self.parent.vmaf_results:
            QMessageBox.warning(self, "Export Error", "No VMAF results available to export.")
            return
            
        try:
            from PyQt5.QtWidgets import QFileDialog
            import csv
            
            # Get test name
            test_name = self.parent.setup_tab.txt_test_name.text()
            
            # Get output file path
            default_filename = f"{test_name}_vmaf_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            output_path = QFileDialog.getSaveFileName(
                self,
                "Save VMAF Data",
                os.path.join(os.path.expanduser("~"), default_filename),
                "CSV Files (*.csv)"
            )[0]
            
            if not output_path:
                return
                
            # Extract data
            vmaf_score = self.parent.vmaf_results.get('vmaf_score', 'N/A')
            psnr_score = self.parent.vmaf_results.get('psnr', 'N/A')
            ssim_score = self.parent.vmaf_results.get('ssim', 'N/A')
            reference_path = self.parent.vmaf_results.get('reference_path', 'N/A')
            distorted_path = self.parent.vmaf_results.get('distorted_path', 'N/A')
            
            # Write summary data
            with open(output_path, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                
                # Write header and summary data
                writer.writerow(['Test Name', 'Date', 'VMAF Score', 'PSNR Score', 'SSIM Score'])
                writer.writerow([
                    test_name,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    vmaf_score if isinstance(vmaf_score, str) else f"{vmaf_score:.4f}",
                    psnr_score if isinstance(psnr_score, str) else f"{psnr_score:.4f}",
                    ssim_score if isinstance(ssim_score, str) else f"{ssim_score:.4f}"
                ])
                
                writer.writerow([])  # Empty row
                writer.writerow(['Reference File', reference_path])
                writer.writerow(['Distorted File', distorted_path])
                writer.writerow([])  # Empty row
                
                # Write frame data if available
                if 'raw_results' in self.parent.vmaf_results and 'frames' in self.parent.vmaf_results['raw_results']:
                    frames = self.parent.vmaf_results['raw_results']['frames']
                    
                    if frames:
                        # Determine which metrics are available
                        first_frame = frames[0]
                        metrics = first_frame.get('metrics', {})
                        available_metrics = list(metrics.keys())
                        
                        # Write frame data header
                        header = ['Frame Number']
                        for metric in available_metrics:
                            header.append(metric)
                        writer.writerow(header)
                        
                        # Write each frame's data
                        for frame in frames:
                            frame_num = frame.get('frameNum', 'N/A')
                            metrics = frame.get('metrics', {})
                            
                            row = [frame_num]
                            for metric in available_metrics:
                                value = metrics.get(metric, 'N/A')
                                if isinstance(value, (int, float)):
                                    value = f"{value:.4f}"
                                row.append(value)
                            
                            writer.writerow(row)
            
            QMessageBox.information(
                self,
                "Export Complete",
                f"VMAF data successfully exported to CSV:\n{output_path}"
            )
            
            # Ask if user wants to open the CSV
            reply = QMessageBox.question(
                self,
                "Open CSV",
                "Would you like to open the CSV file now?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            
            if reply == QMessageBox.Yes:
                try:
                    if platform.system() == 'Windows':
                        os.startfile(output_path)
                    elif platform.system() == 'Darwin':  # macOS
                        subprocess.run(['open', output_path], check=True)
                    else:  # Linux
                        subprocess.run(['xdg-open', output_path], check=True)
                except Exception as e:
                    QMessageBox.warning(
                        self,
                        "Open Failed",
                        f"Could not open the CSV file: {str(e)}"
                    )
                    
        except Exception as e:
            logger.error(f"Error exporting CSV: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            QMessageBox.critical(self, "Export Error", f"Failed to export CSV: {str(e)}")


    def _export_historical_pdf(self, test_dir, test_name, json_data):
        """Export a historical test result as PDF report"""
        try:
            from PyQt5.QtWidgets import QFileDialog, QProgressDialog
            from PyQt5.QtCore import Qt
            
            # Build results dictionary
            results = {}
            
            if json_data:
                # Extract basic metrics from JSON data
                if "pooled_metrics" in json_data:
                    pool = json_data["pooled_metrics"]
                    results['vmaf_score'] = pool.get("vmaf", {}).get("mean", 0)
                    results['psnr'] = pool.get("psnr", pool.get("psnr_y", {})).get("mean", 0)
                    results['ssim'] = pool.get("ssim", pool.get("ssim_y", {})).get("mean", 0)
                    
                # Include raw results for charts
                results['raw_results'] = json_data
                
            # Find file paths
            results['json_path'] = os.path.join(test_dir, "vmaf.json")  # Default path
            
            # Look for actual JSON file
            for f in os.listdir(test_dir):
                if f.endswith("_vmaf.json") or f.endswith("_vmaf_enhanced.json"):
                    results['json_path'] = os.path.join(test_dir, f)
                    break
            
            # Look for reference and distorted videos
            for f in os.listdir(test_dir):
                if "reference" in f.lower() or "ref" in f.lower():
                    results['reference_path'] = os.path.join(test_dir, f)
                if "distorted" in f.lower() or "capture" in f.lower():
                    results['distorted_path'] = os.path.join(test_dir, f)
            
            # Get output file path
            default_filename = f"{test_name}_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            output_path = QFileDialog.getSaveFileName(
                self,
                "Save Test Report",
                os.path.join(os.path.expanduser("~"), default_filename),
                "PDF Files (*.pdf)"
            )[0]
            
            if not output_path:
                return
                
            # Create progress dialog
            progress = QProgressDialog("Generating PDF report...", "Cancel", 0, 100, self)
            progress.setWindowTitle("Exporting Report")
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(0)
            progress.setValue(0)
            progress.show()
            
            # Get test metadata
            timestamp = ""
            dir_name = os.path.basename(test_dir)
            parts = dir_name.split("_")
            if len(parts) >= 3:
                date_str = "_".join(parts[2:])
                try:
                    dt = datetime.strptime(date_str, "%Y%m%d_%H%M%S")
                    timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    timestamp = date_str
                    
            test_metadata = {
                "test_name": test_name,
                "timestamp": timestamp,
                "tester_name": "Unknown",
                "test_location": "Unknown"
            }
            
            # Import report generator
            from app.report_generator import ReportGeneratorThread
            
            # Create and start generator thread
            self.report_thread = ReportGeneratorThread(
                results,
                test_metadata,
                output_path
            )
            
            # Connect signals
            self.report_thread.report_progress.connect(progress.setValue)
            self.report_thread.report_complete.connect(self._handle_report_complete)
            self.report_thread.report_error.connect(self._handle_report_error)
            self.report_thread.finished.connect(progress.close)
            
            # Start report generation
            self.report_thread.start()
            
        except Exception as e:
            logger.error(f"Error exporting historical PDF: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            QMessageBox.critical(self, "Export Error", f"Failed to export PDF report: {str(e)}")
            
    def _export_historical_csv(self, test_dir, test_name, json_data):
        """Export a historical test result as CSV"""
        try:
            from PyQt5.QtWidgets import QFileDialog
            import csv
            
            # Get output file path
            default_filename = f"{test_name}_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            output_path = QFileDialog.getSaveFileName(
                self,
                "Save Test Data",
                os.path.join(os.path.expanduser("~"), default_filename),
                "CSV Files (*.csv)"
            )[0]
            
            if not output_path:
                return
            
            # Extract data
            vmaf_score = None
            psnr_score = None
            ssim_score = None
            
            if json_data:
                if "pooled_metrics" in json_data:
                    pool = json_data["pooled_metrics"]
                    vmaf_score = pool.get("vmaf", {}).get("mean", None)
                    psnr_score = pool.get("psnr", pool.get("psnr_y", {})).get("mean", None)
                    ssim_score = pool.get("ssim", pool.get("ssim_y", {})).get("mean", None)
            
            # Find reference and distorted videos
            reference_path = "Unknown"
            distorted_path = "Unknown"
            
            for f in os.listdir(test_dir):
                if "reference" in f.lower() or "ref" in f.lower():
                    reference_path = os.path.join(test_dir, f)
                if "distorted" in f.lower() or "capture" in f.lower():
                    distorted_path = os.path.join(test_dir, f)
            
            # Get timestamp
            timestamp = ""
            dir_name = os.path.basename(test_dir)
            parts = dir_name.split("_")
            if len(parts) >= 3:
                date_str = "_".join(parts[2:])
                try:
                    dt = datetime.strptime(date_str, "%Y%m%d_%H%M%S")
                    timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    timestamp = date_str
            
            # Write CSV file
            with open(output_path, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                
                # Write header and summary data
                writer.writerow(['Test Name', 'Date', 'VMAF Score', 'PSNR Score', 'SSIM Score'])
                writer.writerow([
                    test_name,
                    timestamp,
                    f"{vmaf_score:.4f}" if isinstance(vmaf_score, (int, float)) else 'N/A',
                    f"{psnr_score:.4f}" if isinstance(psnr_score, (int, float)) else 'N/A',
                    f"{ssim_score:.4f}" if isinstance(ssim_score, (int, float)) else 'N/A'
                ])
                
                writer.writerow([])  # Empty row
                writer.writerow(['Reference File', reference_path])
                writer.writerow(['Distorted File', distorted_path])
                writer.writerow([])  # Empty row
                
                # Write frame data if available
                if json_data and 'frames' in json_data:
                    frames = json_data['frames']
                    
                    if frames:
                        # Determine which metrics are available
                        first_frame = frames[0]
                        metrics = first_frame.get('metrics', {})
                        available_metrics = sorted(metrics.keys())
                        
                        # Write header
                        header = ['Frame Number']
                        header.extend(available_metrics)
                        writer.writerow(header)
                        
                        # Write each frame's data
                        for frame in frames:
                            frame_num = frame.get('frameNum', 'N/A')
                            metrics = frame.get('metrics', {})
                            
                            row = [frame_num]
                            for metric in available_metrics:
                                value = metrics.get(metric, 'N/A')
                                if isinstance(value, (int, float)):
                                    value = f"{value:.4f}"
                                row.append(value)
                            
                            writer.writerow(row)
            
            QMessageBox.information(
                self,
                "Export Complete",
                f"VMAF data successfully exported to CSV:\n{output_path}"
            )
            
            # Ask if user wants to open the CSV
            reply = QMessageBox.question(
                self,
                "Open CSV",
                "Would you like to open the CSV file now?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            
            if reply == QMessageBox.Yes:
                try:
                    if platform.system() == 'Windows':
                        os.startfile(output_path)
                    elif platform.system() == 'Darwin':  # macOS
                        subprocess.run(['open', output_path], check=True)
                    else:  # Linux
                        subprocess.run(['xdg-open', output_path], check=True)
                except Exception as e:
                    QMessageBox.warning(
                        self,
                        "Open Failed",
                        f"Could not open the CSV file: {str(e)}"
                    )
        except Exception as e:
            logger.error(f"Error exporting historical CSV: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            QMessageBox.critical(self, "Export Error", f"Failed to export CSV: {str(e)}")

    def open_result_file(self, item):
        """Open selected result file"""
        file_path = item.data(Qt.UserRole)
        if file_path and os.path.exists(file_path):
            # Use system default application to open the file
            try:
                if platform.system() == 'Windows':
                    os.startfile(file_path)
                elif platform.system() == 'Darwin':  # macOS
                    subprocess.run(['open', file_path], check=True)
                else:  # Linux
                    subprocess.run(['xdg-open', file_path], check=True)
            except Exception as e:
                QMessageBox.warning(self, "Error Opening File", 
                                  f"Could not open file: {str(e)}")

    def load_results_history(self):
        """Load historical test results into the data grid"""
        try:
            self.results_table.setRowCount(0)

            # Get output directory
            output_dir = ""
            # Check if output_dir exists in options manager
            if hasattr(self.parent, 'options_manager') and self.parent.options_manager:
                paths = self.parent.options_manager.get_setting('paths', {})
                output_dir = paths.get('default_output_dir', '')
                if hasattr(self.parent, 'file_mgr') and hasattr(self.parent.file_mgr, 'get_default_base_dir'):
                    output_dir = self.parent.file_mgr.get_default_base_dir()
                elif hasattr(self.parent, 'options_manager'):
                    # Get path from options manager
                    paths = self.parent.options_manager.get_setting('paths', {})
                    output_dir = paths.get('default_output_dir', '')
                    if not output_dir:
                        output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "tests", "test_results")
                else:
                    # Fallback to a default directory
                    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "tests", "test_results")
                
                # Ensure directory exists
                os.makedirs(output_dir, exist_ok=True)
                logger.info(f"Using results directory: {output_dir}")

            if not os.path.exists(output_dir):
                logger.warning(f"Output directory does not exist: {output_dir}")
                return

            # Find all test directories
            test_dirs = []
            for item in os.listdir(output_dir):
                item_path = os.path.join(output_dir, item)
                if os.path.isdir(item_path) and item.startswith("Test_"):
                    test_dirs.append(item_path)

            # Sort by most recent
            test_dirs.sort(key=os.path.getmtime, reverse=True)

            # Process each test directory
            row = 0
            for test_dir in test_dirs:
                # Look for VMAF JSON result files
                json_files = [f for f in os.listdir(test_dir) if f.endswith("_vmaf.json")]

                for json_file in json_files:
                    try:
                        json_path = os.path.join(test_dir, json_file)

                        # Extract test name and date
                        dir_name = os.path.basename(test_dir)
                        parts = dir_name.split("_")

                        # Default values
                        test_name = "Unknown"
                        timestamp = ""

                        # Try to parse test name and timestamp
                        if len(parts) >= 3:
                            test_name = parts[0] + "_" + parts[1]
                            date_str = "_".join(parts[2:])
                            try:
                                dt = datetime.strptime(date_str, "%Y%m%d_%H%M%S")
                                timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
                            except:
                                timestamp = date_str

                        # Get data from JSON file
                        with open(json_path, 'r') as f:
                            data = json.load(f)

                        # Extract scores
                        vmaf_score = None
                        psnr_score = None
                        ssim_score = None
                        duration = None

                        # Try to get from pooled metrics first
                        if "pooled_metrics" in data:
                            pool = data["pooled_metrics"]
                            if "vmaf" in pool:
                                vmaf_score = pool["vmaf"]["mean"]
                            if "psnr" in pool or "psnr_y" in pool:
                                psnr_score = pool.get("psnr", {}).get("mean", pool.get("psnr_y", {}).get("mean"))
                            if "ssim" in pool or "ssim_y" in pool:
                                ssim_score = pool.get("ssim", {}).get("mean", pool.get("ssim_y", {}).get("mean"))

                        # Look in frames if not found in pooled metrics
                        if "frames" in data and (vmaf_score is None or psnr_score is None or ssim_score is None):
                            frames = data["frames"]
                            if frames:
                                # Get the metrics from the first frame as fallback
                                metrics = frames[0].get("metrics", {})
                                if vmaf_score is None and "vmaf" in metrics:
                                    vmaf_score = metrics["vmaf"]
                                if psnr_score is None and ("psnr" in metrics or "psnr_y" in metrics):
                                    psnr_score = metrics.get("psnr", metrics.get("psnr_y"))
                                if ssim_score is None and ("ssim" in metrics or "ssim_y" in metrics):
                                    ssim_score = metrics.get("ssim", metrics.get("ssim_y"))

                                # Estimate duration from frame count
                                duration = len(frames) / 30.0  # Assuming 30fps

                        # Figure out reference name
                        reference_name = "Unknown"
                        for f in os.listdir(test_dir):
                            if "reference" in f.lower() or "ref" in f.lower():
                                reference_name = f
                                break

                        # Add row to table
                        self.results_table.insertRow(row)

                        # Add test name
                        self.results_table.setItem(row, 0, QTableWidgetItem(test_name))

                        # Add timestamp
                        self.results_table.setItem(row, 1, QTableWidgetItem(timestamp))

                        # Add VMAF score
                        vmaf_str = f"{vmaf_score:.2f}" if vmaf_score is not None else "N/A"
                        self.results_table.setItem(row, 2, QTableWidgetItem(vmaf_str))

                        # Add PSNR score
                        psnr_str = f"{psnr_score:.2f}" if psnr_score is not None else "N/A"
                        self.results_table.setItem(row, 3, QTableWidgetItem(psnr_str))

                        # Add SSIM score
                        ssim_str = f"{ssim_score:.4f}" if ssim_score is not None else "N/A"
                        self.results_table.setItem(row, 4, QTableWidgetItem(ssim_str))

                        # Add reference name
                        self.results_table.setItem(row, 5, QTableWidgetItem(reference_name))

                        # Add duration
                        duration_str = f"{duration:.2f}s" if duration is not None else "N/A"
                        self.results_table.setItem(row, 6, QTableWidgetItem(duration_str))

                        # Create action buttons
                        actions_widget = QWidget()
                        actions_layout = QHBoxLayout(actions_widget)
                        actions_layout.setContentsMargins(0, 0, 0, 0)

                        # Add buttons for view/export/delete
                        btn_view = QPushButton("View")
                        btn_view.setProperty("row", row)
                        btn_view.setProperty("dir", test_dir)
                        btn_view.clicked.connect(self._view_result)
                        actions_layout.addWidget(btn_view)

                        btn_export = QPushButton("Export")
                        btn_export.setProperty("row", row)
                        btn_export.setProperty("dir", test_dir)
                        btn_export.clicked.connect(self._export_result)
                        actions_layout.addWidget(btn_export)

                        btn_delete = QPushButton("Delete")
                        btn_delete.setProperty("row", row)
                        btn_delete.setProperty("dir", test_dir)
                        btn_delete.clicked.connect(self._delete_result)
                        actions_layout.addWidget(btn_delete)

                        self.results_table.setCellWidget(row, 7, actions_widget)

                        # Store metadata in the row
                        for col in range(7):
                            item = self.results_table.item(row, col)
                            if item:
                                item.setData(Qt.UserRole, {
                                    "test_dir": test_dir,
                                    "json_path": json_path,
                                    "test_name": test_name,
                                    "timestamp": timestamp
                                })

                        row += 1
                    except Exception as e:
                        logger.error(f"Error processing result file {json_file}: {str(e)}")

            # Update row count label
            if row > 0:
                self.results_table.setToolTip(f"Found {row} historical test results")
            else:
                self.results_table.setToolTip("No historical test results found")

        except Exception as e:
            logger.error(f"Error loading results history: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())

    def _view_result(self):
        """View a historical test result with detailed visualizations"""
        sender = self.sender()
        row = sender.property("row")
        test_dir = sender.property("dir")

        try:
            # Show the results in a dialog
            from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QLabel, QPushButton, 
                                      QScrollArea, QTabWidget, QSplitter, QFrame,
                                      QGridLayout, QProgressBar, QTableWidget, 
                                      QTableWidgetItem, QHeaderView)
            from PyQt5.QtChart import QChart, QChartView, QLineSeries, QValueAxis
            from PyQt5.QtCore import Qt, QPointF
            from PyQt5.QtGui import QPainter, QColor, QFont, QPen

            dialog = QDialog(self)
            dialog.setWindowTitle("Test Result Details")
            dialog.resize(900, 700)

            layout = QVBoxLayout(dialog)

            # Get test details
            item = self.results_table.item(row, 0)
            test_name = item.text() if item else "Unknown"

            item = self.results_table.item(row, 1)
            timestamp = item.text() if item else "Unknown"
            
            item = self.results_table.item(row, 2)
            vmaf_score = item.text() if item else "N/A"
            
            item = self.results_table.item(row, 3)
            psnr_score = item.text() if item else "N/A"
            
            item = self.results_table.item(row, 4)
            ssim_score = item.text() if item else "N/A"

            # Create header with test info
            header_widget = QWidget()
            header_layout = QVBoxLayout(header_widget)
            header_layout.setContentsMargins(0, 0, 0, 0)
            
            title_label = QLabel(f"<h2>{test_name} - {timestamp}</h2>")
            title_label.setAlignment(Qt.AlignCenter)
            header_layout.addWidget(title_label)
            
            # Create tabs for different views
            tabs = QTabWidget()
            
            # Summary tab
            summary_tab = QWidget()
            summary_layout = QVBoxLayout(summary_tab)
            
            # Create a grid layout for score summary
            scores_widget = QWidget()
            scores_layout = QGridLayout(scores_widget)
            scores_layout.setColumnStretch(1, 1)  # Make the right column expand
            
            # VMAF score with progress bar
            scores_layout.addWidget(QLabel("<b>VMAF Score:</b>"), 0, 0)
            
            vmaf_widget = QWidget()
            vmaf_layout = QHBoxLayout(vmaf_widget)
            vmaf_layout.setContentsMargins(0, 0, 0, 0)
            
            vmaf_bar = QProgressBar()
            try:
                vmaf_val = float(vmaf_score)
                vmaf_bar.setValue(int(vmaf_val))
                
                # Set color based on value
                if vmaf_val >= 80:
                    vmaf_bar.setStyleSheet("QProgressBar::chunk { background-color: #4CAF50; }")
                elif vmaf_val >= 60:
                    vmaf_bar.setStyleSheet("QProgressBar::chunk { background-color: #FFC107; }")
                else:
                    vmaf_bar.setStyleSheet("QProgressBar::chunk { background-color: #F44336; }")
            except (ValueError, TypeError):
                vmaf_bar.setValue(0)
                
            vmaf_layout.addWidget(vmaf_bar)
            vmaf_layout.addWidget(QLabel(vmaf_score))
            
            scores_layout.addWidget(vmaf_widget, 0, 1)
            
            # PSNR score with progress bar
            scores_layout.addWidget(QLabel("<b>PSNR Score:</b>"), 1, 0)
            
            psnr_widget = QWidget()
            psnr_layout = QHBoxLayout(psnr_widget)
            psnr_layout.setContentsMargins(0, 0, 0, 0)
            
            psnr_bar = QProgressBar()
            try:
                psnr_val = float(psnr_score.replace(" dB", ""))
                # Scale PSNR to 0-100 range (assuming 50 dB is max)
                psnr_scaled = min(100, int(psnr_val * 2))
                psnr_bar.setValue(psnr_scaled)
                
                # Set color based on value
                if psnr_val >= 35:
                    psnr_bar.setStyleSheet("QProgressBar::chunk { background-color: #4CAF50; }")
                elif psnr_val >= 25:
                    psnr_bar.setStyleSheet("QProgressBar::chunk { background-color: #FFC107; }")
                else:
                    psnr_bar.setStyleSheet("QProgressBar::chunk { background-color: #F44336; }")
            except (ValueError, TypeError):
                psnr_bar.setValue(0)
                
            psnr_layout.addWidget(psnr_bar)
            psnr_layout.addWidget(QLabel(psnr_score))
            
            scores_layout.addWidget(psnr_widget, 1, 1)
            
            # SSIM score with progress bar
            scores_layout.addWidget(QLabel("<b>SSIM Score:</b>"), 2, 0)
            
            ssim_widget = QWidget()
            ssim_layout = QHBoxLayout(ssim_widget)
            ssim_layout.setContentsMargins(0, 0, 0, 0)
            
            ssim_bar = QProgressBar()
            try:
                ssim_val = float(ssim_score)
                # Scale SSIM to 0-100 range
                ssim_scaled = int(ssim_val * 100)
                ssim_bar.setValue(ssim_scaled)
                
                # Set color based on value
                if ssim_val >= 0.9:
                    ssim_bar.setStyleSheet("QProgressBar::chunk { background-color: #4CAF50; }")
                elif ssim_val >= 0.8:
                    ssim_bar.setStyleSheet("QProgressBar::chunk { background-color: #FFC107; }")
                else:
                    ssim_bar.setStyleSheet("QProgressBar::chunk { background-color: #F44336; }")
            except (ValueError, TypeError):
                ssim_bar.setValue(0)
                
            ssim_layout.addWidget(ssim_bar)
            ssim_layout.addWidget(QLabel(ssim_score))
            
            scores_layout.addWidget(ssim_widget, 2, 1)
            
            summary_layout.addWidget(scores_widget)
            
            # Add interpretation of scores
            interpretation_frame = QFrame()
            interpretation_frame.setFrameShape(QFrame.StyledPanel)
            interpretation_frame.setFrameShadow(QFrame.Raised)
            interpretation_layout = QVBoxLayout(interpretation_frame)
            
            interpretation_title = QLabel("<h3>Score Interpretation</h3>")
            interpretation_layout.addWidget(interpretation_title)
            
            # VMAF interpretation
            try:
                vmaf_val = float(vmaf_score)
                if vmaf_val >= 90:
                    vmaf_interp = "Excellent quality (transparent)"
                elif vmaf_val >= 80:
                    vmaf_interp = "Good quality (perceptible but not annoying)"
                elif vmaf_val >= 70:
                    vmaf_interp = "Fair quality (slightly annoying)"
                elif vmaf_val >= 60:
                    vmaf_interp = "Poor quality (annoying)"
                else:
                    vmaf_interp = "Bad quality (very annoying)"
            except (ValueError, TypeError):
                vmaf_interp = "Unable to interpret"
                
            interpretation_layout.addWidget(QLabel(f"<b>VMAF {vmaf_score}:</b> {vmaf_interp}"))
            
            # PSNR interpretation
            try:
                psnr_val = float(psnr_score.replace(" dB", ""))
                if psnr_val >= 40:
                    psnr_interp = "Excellent quality"
                elif psnr_val >= 30:
                    psnr_interp = "Good quality"
                elif psnr_val >= 20:
                    psnr_interp = "Acceptable quality"
                else:
                    psnr_interp = "Poor quality"
            except (ValueError, TypeError):
                psnr_interp = "Unable to interpret"
                
            interpretation_layout.addWidget(QLabel(f"<b>PSNR {psnr_score}:</b> {psnr_interp}"))
            
            # SSIM interpretation
            try:
                ssim_val = float(ssim_score)
                if ssim_val >= 0.95:
                    ssim_interp = "Excellent quality (imperceptible difference)"
                elif ssim_val >= 0.90:
                    ssim_interp = "Good quality (perceptible but not annoying)"
                elif ssim_val >= 0.80:
                    ssim_interp = "Fair quality (slightly annoying)"
                elif ssim_val >= 0.70:
                    ssim_interp = "Poor quality (annoying)"
                else:
                    ssim_interp = "Bad quality (very annoying)"
            except (ValueError, TypeError):
                ssim_interp = "Unable to interpret"
                
            interpretation_layout.addWidget(QLabel(f"<b>SSIM {ssim_score}:</b> {ssim_interp}"))
            
            summary_layout.addWidget(interpretation_frame)
            
            # Add JSON file path and load data if possible
            json_path = None
            json_data = None
            
            for f in os.listdir(test_dir):
                if f.endswith("_vmaf.json") or f.endswith("_vmaf_enhanced.json"):
                    json_path = os.path.join(test_dir, f)
                    break
                    
            if json_path and os.path.exists(json_path):
                interpretation_layout.addWidget(QLabel(f"<b>Source:</b> {json_path}"))
                
                try:
                    with open(json_path, 'r') as f:
                        json_data = json.load(f)
                except Exception as e:
                    logger.error(f"Failed to load JSON data: {e}")
            
            summary_layout.addStretch()
            
            # Charts tab if we have frame data
            charts_tab = QWidget()
            charts_layout = QVBoxLayout(charts_tab)
            
            if json_data and 'frames' in json_data:
                # Extract frame data
                frames = json_data['frames']
                if frames:
                    try:
                        # Create series for each metric
                        vmaf_series = QLineSeries()
                        vmaf_series.setName("VMAF")
                        
                        psnr_series = QLineSeries()
                        psnr_series.setName("PSNR")
                        
                        ssim_series = QLineSeries()
                        ssim_series.setName("SSIM")
                        
                        # Process frame data
                        frame_nums = []
                        vmaf_values = []
                        psnr_values = []
                        ssim_values = []
                        
                        for i, frame in enumerate(frames):
                            frame_nums.append(i)
                            metrics = frame.get('metrics', {})
                            
                            # VMAF
                            vmaf_val = metrics.get('vmaf', None)
                            if vmaf_val is not None:
                                vmaf_values.append(vmaf_val)
                                vmaf_series.append(QPointF(i, vmaf_val))
                                
                            # PSNR (try psnr_y if psnr not available)
                            psnr_val = metrics.get('psnr', metrics.get('psnr_y', None))
                            if psnr_val is not None:
                                psnr_values.append(psnr_val)
                                psnr_series.append(QPointF(i, psnr_val))
                                
                            # SSIM (try ssim_y if ssim not available)
                            ssim_val = metrics.get('ssim', metrics.get('ssim_y', None))
                            if ssim_val is not None:
                                ssim_values.append(ssim_val)
                                ssim_series.append(QPointF(i, ssim_val))
                        
                        # Create charts if we have data
                        if vmaf_values:
                            vmaf_chart = QChart()
                            vmaf_chart.addSeries(vmaf_series)
                            vmaf_chart.setTitle("VMAF Over Time")
                            
                            axisX = QValueAxis()
                            axisX.setTitleText("Frame")
                            
                            axisY = QValueAxis()
                            axisY.setTitleText("VMAF")
                            axisY.setRange(0, 100)
                            
                            vmaf_chart.addAxis(axisX, Qt.AlignBottom)
                            vmaf_chart.addAxis(axisY, Qt.AlignLeft)
                            
                            vmaf_series.attachAxis(axisX)
                            vmaf_series.attachAxis(axisY)
                            
                            vmaf_series.setPen(QPen(QColor("blue"), 2))
                            
                            vmaf_chart_view = QChartView(vmaf_chart)
                            vmaf_chart_view.setRenderHint(QPainter.Antialiasing)
                            charts_layout.addWidget(vmaf_chart_view)
                        
                        if psnr_values:
                            psnr_chart = QChart()
                            psnr_chart.addSeries(psnr_series)
                            psnr_chart.setTitle("PSNR Over Time")
                            
                            axisX = QValueAxis()
                            axisX.setTitleText("Frame")
                            
                            axisY = QValueAxis()
                            axisY.setTitleText("PSNR (dB)")
                            
                            max_psnr = max(psnr_values) * 1.1
                            min_psnr = max(0, min(psnr_values) * 0.9)
                            axisY.setRange(min_psnr, max_psnr)
                            
                            psnr_chart.addAxis(axisX, Qt.AlignBottom)
                            psnr_chart.addAxis(axisY, Qt.AlignLeft)
                            
                            psnr_series.attachAxis(axisX)
                            psnr_series.attachAxis(axisY)
                            
                            psnr_series.setPen(QPen(QColor("green"), 2))
                            
                            psnr_chart_view = QChartView(psnr_chart)
                            psnr_chart_view.setRenderHint(QPainter.Antialiasing)
                            charts_layout.addWidget(psnr_chart_view)
                        
                        if ssim_values:
                            ssim_chart = QChart()
                            ssim_chart.addSeries(ssim_series)
                            ssim_chart.setTitle("SSIM Over Time")
                            
                            axisX = QValueAxis()
                            axisX.setTitleText("Frame")
                            
                            axisY = QValueAxis()
                            axisY.setTitleText("SSIM")
                            axisY.setRange(0, 1)
                            
                            ssim_chart.addAxis(axisX, Qt.AlignBottom)
                            ssim_chart.addAxis(axisY, Qt.AlignLeft)
                            
                            ssim_series.attachAxis(axisX)
                            ssim_series.attachAxis(axisY)
                            
                            ssim_series.setPen(QPen(QColor("red"), 2))
                            
                            ssim_chart_view = QChartView(ssim_chart)
                            ssim_chart_view.setRenderHint(QPainter.Antialiasing)
                            charts_layout.addWidget(ssim_chart_view)
                    
                    except Exception as e:
                        logger.error(f"Error creating charts: {str(e)}")
                        charts_layout.addWidget(QLabel(f"Error creating charts: {str(e)}"))
                else:
                    charts_layout.addWidget(QLabel("No frame data available for charts"))
            else:
                charts_layout.addWidget(QLabel("No frame data available for charts"))
                
            # Data tab with frame-level metrics
            data_tab = QWidget()
            data_layout = QVBoxLayout(data_tab)
            
            if json_data and 'frames' in json_data:
                frames = json_data['frames']
                if frames:
                    try:
                        # Create table for frame data
                        frame_table = QTableWidget()
                        
                        # Determine available metrics from first frame
                        first_frame = frames[0]
                        metrics = first_frame.get('metrics', {})
                        headers = ['Frame']
                        headers.extend(sorted(metrics.keys()))
                        
                        # Set up table
                        frame_table.setColumnCount(len(headers))
                        frame_table.setHorizontalHeaderLabels(headers)
                        frame_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
                        
                        # Fill table
                        frame_table.setRowCount(len(frames))
                        
                        for i, frame in enumerate(frames):
                            # Frame number
                            frame_num = frame.get('frameNum', i)
                            frame_table.setItem(i, 0, QTableWidgetItem(str(frame_num)))
                            
                            # Metrics
                            metrics = frame.get('metrics', {})
                            for col, metric in enumerate(headers[1:], 1):
                                value = metrics.get(metric, 'N/A')
                                if isinstance(value, (int, float)):
                                    value = f"{value:.4f}"
                                frame_table.setItem(i, col, QTableWidgetItem(str(value)))
                        
                        data_layout.addWidget(frame_table)
                    except Exception as e:
                        logger.error(f"Error creating frame data table: {str(e)}")
                        data_layout.addWidget(QLabel(f"Error creating frame data table: {str(e)}"))
                else:
                    data_layout.addWidget(QLabel("No frame data available"))
            else:
                data_layout.addWidget(QLabel("No frame data available"))
                
            # Files tab
            files_tab = QWidget()
            files_layout = QVBoxLayout(files_tab)
            
            file_list = QListWidget()
            for f in sorted(os.listdir(test_dir)):
                file_path = os.path.join(test_dir, f)
                if os.path.isfile(file_path):
                    item = QListWidgetItem(f)
                    item.setData(Qt.UserRole, file_path)
                    file_list.addItem(item)
            
            file_list.itemDoubleClicked.connect(self.open_result_file)
            files_layout.addWidget(QLabel("<b>Double-click to open a file:</b>"))
            files_layout.addWidget(file_list)
            
            # Add tabs
            tabs.addTab(summary_tab, "Summary")
            tabs.addTab(charts_tab, "Charts")
            tabs.addTab(data_tab, "Data")
            tabs.addTab(files_tab, "Files")
            
            # Create final layout
            layout.addWidget(header_widget)
            layout.addWidget(tabs, 1)  # Give tab widget more stretch
            
            # Add buttons at the bottom
            button_layout = QHBoxLayout()
            
            btn_export_pdf = QPushButton("Export PDF Report")
            btn_export_pdf.clicked.connect(lambda: self._export_historical_pdf(test_dir, test_name, json_data))
            button_layout.addWidget(btn_export_pdf)
            
            btn_export_csv = QPushButton("Export CSV Data")
            btn_export_csv.clicked.connect(lambda: self._export_historical_csv(test_dir, test_name, json_data))
            button_layout.addWidget(btn_export_csv)
            
            btn_close = QPushButton("Close")
            btn_close.clicked.connect(dialog.accept)
            button_layout.addWidget(btn_close)
            
            layout.addLayout(button_layout)
            
            # Show dialog
            dialog.exec_()

        except Exception as e:
            logger.error(f"Error viewing result: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            QMessageBox.critical(self, "Error", f"Failed to view result details: {str(e)}")

    def _export_result(self, test_dir=None):
        """Export a test result"""
        if test_dir is None:
            sender = self.sender()
            test_dir = sender.property("dir")

        try:
            # Create export dialog
            from PyQt5.QtWidgets import QFileDialog

            # Get default export filename
            basename = os.path.basename(test_dir)
            export_pdf = QFileDialog.getSaveFileName(
                self,
                "Export Result as PDF",
                os.path.join(os.path.expanduser("~"), f"{basename}_report.pdf"),
                "PDF Files (*.pdf)"
            )[0]

            if export_pdf:
                # For now just show a placeholder message
                QMessageBox.information(
                    self,
                    "Export to PDF",
                    f"Result would be exported to: {export_pdf}\n\nThis feature will be fully implemented in the future."
                )

        except Exception as e:
            logger.error(f"Error exporting result: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())

    def _delete_result(self):
        """Delete a test result directory"""
        sender = self.sender()
        row = sender.property("row")
        test_dir = sender.property("dir")

        try:
            # Confirm deletion
            msg_box = QMessageBox()
            msg_box.setIcon(QMessageBox.Warning)
            msg_box.setText(f"Are you sure you want to delete this test result?\n\nDirectory: {test_dir}")
            msg_box.setWindowTitle("Confirm Deletion")
            msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            msg_box.setDefaultButton(QMessageBox.No)

            if msg_box.exec_() == QMessageBox.Yes:
                import shutil

                # Delete the directory
                shutil.rmtree(test_dir)

                # Remove row from table
                self.results_table.removeRow(row)

                QMessageBox.information(
                    self,
                    "Deletion Complete",
                    f"Test result has been deleted."
                )

        except Exception as e:
            logger.error(f"Error deleting result: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())

            QMessageBox.critical(
                self,
                "Deletion Failed",
                f"Failed to delete test result: {str(e)}"
            )

    def delete_selected_results(self):
        """Delete selected results from the history table"""
        try:
            # Get selected rows
            selected_rows = set()
            for item in self.results_table.selectedItems():
                selected_rows.add(item.row())

            if not selected_rows:
                QMessageBox.information(
                    self,
                    "No Selection",
                    "Please select at least one test result to delete."
                )
                return

            # Confirm deletion
            msg_box = QMessageBox()
            msg_box.setIcon(QMessageBox.Warning)
            msg_box.setText(f"Are you sure you want to delete {len(selected_rows)} selected test results?")
            msg_box.setWindowTitle("Confirm Deletion")
            msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            msg_box.setDefaultButton(QMessageBox.No)

            if msg_box.exec_() == QMessageBox.Yes:
                # Delete from bottom to top to avoid index issues
                for row in sorted(selected_rows, reverse=True):
                    try:
                        # Get directory
                        item = self.results_table.item(row, 0)
                        if item:
                            data = item.data(Qt.UserRole)
                            if data and "test_dir" in data:
                                test_dir = data["test_dir"]

                                # Delete directory
                                import shutil
                                shutil.rmtree(test_dir)

                                # Remove row
                                self.results_table.removeRow(row)
                    except Exception as e:
                        logger.error(f"Error deleting row {row}: {str(e)}")

                QMessageBox.information(
                    self,
                    "Deletion Complete",
                    f"Selected test results have been deleted."
                )
        except Exception as e:
            logger.error(f"Error deleting selected results: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())

            QMessageBox.critical(
                self,
                "Deletion Failed",
                f"Failed to delete selected results: {str(e)}"
            )

    def export_selected_results(self):
        """Export selected results from the history table"""
        try:
            # Get selected rows
            selected_rows = set()
            for item in self.results_table.selectedItems():
                selected_rows.add(item.row())

            if not selected_rows:
                QMessageBox.information(
                    self,
                    "No Selection",
                    "Please select at least one test result to export."
                )
                return

            # Ask for export format
            from PyQt5.QtWidgets import QDialog, QVBoxLayout, QRadioButton, QPushButton, QButtonGroup, QLabel, QFileDialog, QProgressDialog, QCheckBox
            
            dialog = QDialog(self)
            dialog.setWindowTitle("Export Selected Results")
            dialog.resize(400, 250)
            
            layout = QVBoxLayout(dialog)
            
            layout.addWidget(QLabel(f"<b>Export {len(selected_rows)} selected results as:</b>"))
            
            # Format selection
            format_group = QButtonGroup(dialog)
            
            pdf_radio = QRadioButton("PDF Reports (one per test)")
            format_group.addButton(pdf_radio, 1)
            layout.addWidget(pdf_radio)
            
            csv_radio = QRadioButton("CSV Data Files (one per test)")
            format_group.addButton(csv_radio, 2)
            layout.addWidget(csv_radio)
            
            combined_csv_radio = QRadioButton("Combined CSV Summary (all tests in one file)")
            format_group.addButton(combined_csv_radio, 3)
            layout.addWidget(combined_csv_radio)
            
            # Set default selection
            pdf_radio.setChecked(True)
            
            # Add zip option
            layout.addWidget(QLabel("<b>Options:</b>"))
            zip_check = QCheckBox("Create ZIP archive of exported files")
            zip_check.setChecked(True)
            layout.addWidget(zip_check)
            
            # Add open when done option
            open_check = QCheckBox("Open exported files when complete")
            open_check.setChecked(True)
            layout.addWidget(open_check)
            
            # Add buttons
            button_layout = QHBoxLayout()
            
            btn_cancel = QPushButton("Cancel")
            btn_cancel.clicked.connect(dialog.reject)
            button_layout.addWidget(btn_cancel)
            
            btn_export = QPushButton("Export")
            btn_export.clicked.connect(dialog.accept)
            button_layout.addWidget(btn_export)
            
            layout.addLayout(button_layout)
            
            # Show dialog
            if dialog.exec_() != QDialog.Accepted:
                return
            
            # Get selected format
            export_format = format_group.checkedId()
            zip_files = zip_check.isChecked()
            open_when_done = open_check.isChecked()
            
            # Get output directory
            if export_format == 3:  # Combined CSV
                output_path = QFileDialog.getSaveFileName(
                    self,
                    "Save Combined CSV",
                    os.path.join(os.path.expanduser("~"), f"vmaf_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"),
                    "CSV Files (*.csv)"
                )[0]
                
                if not output_path:
                    return
                    
                self._export_combined_csv(selected_rows, output_path, open_when_done)
            else:
                # Get directory for individual files
                output_dir = QFileDialog.getExistingDirectory(
                    self,
                    "Select Output Directory",
                    os.path.expanduser("~")
                )
                
                if not output_dir:
                    return
                
                # Create progress dialog
                progress = QProgressDialog("Exporting results...", "Cancel", 0, len(selected_rows), self)
                progress.setWindowTitle("Export Progress")
                progress.setWindowModality(Qt.WindowModal)
                progress.setMinimumDuration(0)
                progress.show()
                
                # Process each selected row
                exported_files = []
                canceled = False
                
                for i, row in enumerate(sorted(selected_rows)):
                    if progress.wasCanceled():
                        canceled = True
                        break
                        
                    progress.setValue(i)
                    progress.setLabelText(f"Exporting {i+1} of {len(selected_rows)}...")
                    
                    try:
                        # Get row data
                        item = self.results_table.item(row, 0)
                        if not item:
                            continue
                            
                        data = item.data(Qt.UserRole)
                        if not data or "test_dir" not in data:
                            continue
                            
                        test_dir = data["test_dir"]
                        test_name = data.get("test_name", f"Test_{i}")
                        
                        # Export based on format
                        if export_format == 1:  # PDF
                            pdf_path = self._batch_export_pdf(test_dir, test_name, output_dir)
                            if pdf_path:
                                exported_files.append(pdf_path)
                        elif export_format == 2:  # CSV
                            csv_path = self._batch_export_csv(test_dir, test_name, output_dir)
                            if csv_path:
                                exported_files.append(csv_path)
                    except Exception as e:
                        logger.error(f"Error exporting row {row}: {str(e)}")
                
                progress.setValue(len(selected_rows))
                
                # Create ZIP if requested
                if zip_files and exported_files and not canceled:
                    import zipfile
                    
                    # Create ZIP filename
                    zip_path = os.path.join(output_dir, f"vmaf_exports_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip")
                    
                    try:
                        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                            for file in exported_files:
                                zipf.write(file, os.path.basename(file))
                                
                        # Add ZIP to exported files
                        exported_files = [zip_path]
                    except Exception as e:
                        logger.error(f"Error creating ZIP file: {str(e)}")
                
                # Show completion message
                if canceled:
                    QMessageBox.warning(
                        self,
                        "Export Canceled",
                        f"Export was canceled after processing {i} of {len(selected_rows)} items."
                    )
                elif exported_files:
                    message = f"Successfully exported {len(exported_files)} file{'s' if len(exported_files) > 1 else ''}."
                    if zip_files:
                        message += f"\nAll files were compressed into {os.path.basename(zip_path)}"
                    
                    QMessageBox.information(
                        self,
                        "Export Complete",
                        message
                    )
                    
                    # Open if requested
                    if open_when_done and exported_files:
                        try:
                            for file in exported_files:
                                if platform.system() == 'Windows':
                                    os.startfile(file)
                                elif platform.system() == 'Darwin':  # macOS
                                    subprocess.run(['open', file], check=True)
                                else:  # Linux
                                    subprocess.run(['xdg-open', file], check=True)
                        except Exception as e:
                            QMessageBox.warning(
                                self,
                                "Open Failed",
                                f"Could not open exported file(s): {str(e)}"
                            )
                else:
                    QMessageBox.warning(
                        self,
                        "Export Failed",
                        "No files were successfully exported."
                    )
        except Exception as e:
            logger.error(f"Error exporting selected results: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            QMessageBox.critical(self, "Export Error", f"Failed to export results: {str(e)}")
    
    def _batch_export_pdf(self, test_dir, test_name, output_dir):
        """Export a single test result as PDF for batch processing"""
        try:
            # Load JSON data
            json_data = None
            json_path = None
            
            for f in os.listdir(test_dir):
                if f.endswith("_vmaf.json") or f.endswith("_vmaf_enhanced.json"):
                    json_path = os.path.join(test_dir, f)
                    break
                    
            if json_path and os.path.exists(json_path):
                try:
                    with open(json_path, 'r') as f:
                        json_data = json.load(f)
                except Exception as e:
                    logger.error(f"Failed to load JSON data: {e}")
            
            # Build results dictionary
            results = {}
            
            if json_data:
                # Extract basic metrics from JSON data
                if "pooled_metrics" in json_data:
                    pool = json_data["pooled_metrics"]
                    results['vmaf_score'] = pool.get("vmaf", {}).get("mean", 0)
                    results['psnr'] = pool.get("psnr", pool.get("psnr_y", {})).get("mean", 0)
                    results['ssim'] = pool.get("ssim", pool.get("ssim_y", {})).get("mean", 0)
                    
                # Include raw results for charts
                results['raw_results'] = json_data
                
            # Include file paths
            results['json_path'] = json_path
            
            # Look for reference and distorted videos
            for f in os.listdir(test_dir):
                if "reference" in f.lower() or "ref" in f.lower():
                    results['reference_path'] = os.path.join(test_dir, f)
                if "distorted" in f.lower() or "capture" in f.lower():
                    results['distorted_path'] = os.path.join(test_dir, f)
            
            # Get output path
            output_path = os.path.join(output_dir, f"{test_name}_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
            
            # Get test metadata
            timestamp = ""
            dir_name = os.path.basename(test_dir)
            parts = dir_name.split("_")
            if len(parts) >= 3:
                date_str = "_".join(parts[2:])
                try:
                    dt = datetime.strptime(date_str, "%Y%m%d_%H%M%S")
                    timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    timestamp = date_str
                    
            test_metadata = {
                "test_name": test_name,
                "timestamp": timestamp,
                "tester_name": "Unknown",
                "test_location": "Unknown"
            }
            
            # Generate report directly (not in thread for batch processing)
            from app.report_generator import ReportGenerator
            generator = ReportGenerator()
            result_path = generator.generate_report(results, test_metadata, output_path)
            
            return result_path
            
        except Exception as e:
            logger.error(f"Error in batch PDF export: {str(e)}")
            return None
    
    def _batch_export_csv(self, test_dir, test_name, output_dir):
        """Export a single test result as CSV for batch processing"""
        try:
            # Load JSON data
            json_data = None
            json_path = None
            
            for f in os.listdir(test_dir):
                if f.endswith("_vmaf.json") or f.endswith("_vmaf_enhanced.json"):
                    json_path = os.path.join(test_dir, f)
                    break
                    
            if json_path and os.path.exists(json_path):
                try:
                    with open(json_path, 'r') as f:
                        json_data = json.load(f)
                except Exception as e:
                    logger.error(f"Failed to load JSON data: {e}")
            
            # Extract data
            vmaf_score = None
            psnr_score = None
            ssim_score = None
            
            if json_data:
                if "pooled_metrics" in json_data:
                    pool = json_data["pooled_metrics"]
                    vmaf_score = pool.get("vmaf", {}).get("mean", None)
                    psnr_score = pool.get("psnr", pool.get("psnr_y", {})).get("mean", None)
                    ssim_score = pool.get("ssim", pool.get("ssim_y", {})).get("mean", None)
            
            # Find reference and distorted videos
            reference_path = "Unknown"
            distorted_path = "Unknown"
            
            for f in os.listdir(test_dir):
                if "reference" in f.lower() or "ref" in f.lower():
                    reference_path = os.path.join(test_dir, f)
                if "distorted" in f.lower() or "capture" in f.lower():
                    distorted_path = os.path.join(test_dir, f)
            
            # Get timestamp
            timestamp = ""
            dir_name = os.path.basename(test_dir)
            parts = dir_name.split("_")
            if len(parts) >= 3:
                date_str = "_".join(parts[2:])
                try:
                    dt = datetime.strptime(date_str, "%Y%m%d_%H%M%S")
                    timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    timestamp = date_str
            
            # Output path
            output_path = os.path.join(output_dir, f"{test_name}_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
            
            # Write CSV file
            import csv
            with open(output_path, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                
                # Write header and summary data
                writer.writerow(['Test Name', 'Date', 'VMAF Score', 'PSNR Score', 'SSIM Score'])
                writer.writerow([
                    test_name,
                    timestamp,
                    f"{vmaf_score:.4f}" if isinstance(vmaf_score, (int, float)) else 'N/A',
                    f"{psnr_score:.4f}" if isinstance(psnr_score, (int, float)) else 'N/A',
                    f"{ssim_score:.4f}" if isinstance(ssim_score, (int, float)) else 'N/A'
                ])
                
                writer.writerow([])  # Empty row
                writer.writerow(['Reference File', reference_path])
                writer.writerow(['Distorted File', distorted_path])
                writer.writerow([])  # Empty row
                
                # Write frame data if available
                if json_data and 'frames' in json_data:
                    frames = json_data['frames']
                    
                    if frames:
                        # Determine which metrics are available
                        first_frame = frames[0]
                        metrics = first_frame.get('metrics', {})
                        available_metrics = sorted(metrics.keys())
                        
                        # Write header
                        header = ['Frame Number']
                        header.extend(available_metrics)
                        writer.writerow(header)
                        
                        # Write each frame's data
                        for frame in frames:
                            frame_num = frame.get('frameNum', 'N/A')
                            metrics = frame.get('metrics', {})
                            
                            row = [frame_num]
                            for metric in available_metrics:
                                value = metrics.get(metric, 'N/A')
                                if isinstance(value, (int, float)):
                                    value = f"{value:.4f}"
                                row.append(value)
                            
                            writer.writerow(row)
            
            return output_path
            
        except Exception as e:
            logger.error(f"Error in batch CSV export: {str(e)}")
            return None
        
    def _export_combined_csv(self, selected_rows, output_path, open_when_done):
        """Export a combined CSV summary of multiple test results"""
        try:
            import csv
            
            # Create CSV file
            with open(output_path, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                
                # Write header
                writer.writerow([
                    'Test Name', 'Date', 'VMAF Score', 'PSNR Score', 'SSIM Score',
                    'Reference File', 'Distorted File', 'Test Directory'
                ])
                
                # Process each row
                for row in sorted(selected_rows):
                    try:
                        # Get test info
                        test_name = self.results_table.item(row, 0).text() if self.results_table.item(row, 0) else "Unknown"
                        timestamp = self.results_table.item(row, 1).text() if self.results_table.item(row, 1) else "Unknown"
                        vmaf_score = self.results_table.item(row, 2).text() if self.results_table.item(row, 2) else "N/A"
                        psnr_score = self.results_table.item(row, 3).text() if self.results_table.item(row, 3) else "N/A"
                        ssim_score = self.results_table.item(row, 4).text() if self.results_table.item(row, 4) else "N/A"
                        reference = self.results_table.item(row, 5).text() if self.results_table.item(row, 5) else "Unknown"
                        
                        # Get test directory
                        test_dir = ""
                        item = self.results_table.item(row, 0)
                        if item:
                            data = item.data(Qt.UserRole)
                            if data and "test_dir" in data:
                                test_dir = data["test_dir"]
                                
                        # Find distorted video file
                        distorted = "Unknown"
                        if test_dir:
                            for f in os.listdir(test_dir):
                                if "distorted" in f.lower() or "capture" in f.lower():
                                    distorted = f
                                    break
                        
                        # Write row
                        writer.writerow([
                            test_name, timestamp, vmaf_score, psnr_score, ssim_score,
                            reference, distorted, test_dir
                        ])
                        
                    except Exception as e:
                        logger.error(f"Error processing row {row} for combined CSV: {str(e)}")
                        continue
            
            # Show completion message
            QMessageBox.information(
                self,
                "Export Complete",
                f"Successfully exported combined summary to:\n{output_path}"
            )
            
            # Open if requested
            if open_when_done:
                try:
                    if platform.system() == 'Windows':
                        os.startfile(output_path)
                    elif platform.system() == 'Darwin':  # macOS
                        subprocess.run(['open', output_path], check=True)
                    else:  # Linux
                        subprocess.run(['xdg-open', output_path], check=True)
                except Exception as e:
                    QMessageBox.warning(
                        self,
                        "Open Failed",
                        f"Could not open the CSV file: {str(e)}"
                    )
                    
        except Exception as e:
            logger.error(f"Error exporting combined CSV: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            QMessageBox.critical(self, "Export Error", f"Failed to export combined CSV: {str(e)}")

    def start_new_test(self):
        """Reset application for a new test"""
        # Reset state variables in parent
        self.parent.ensure_threads_finished()
        self.parent.capture_path = None
        self.parent.aligned_paths = None
        self.parent.vmaf_results = None

        # Clear logs
        self.parent.capture_tab.txt_capture_log.clear()
        self.parent.analysis_tab.txt_analysis_log.clear()

        # Reset progress bars
        self.parent.capture_tab.pb_capture_progress.setValue(0)
        self.parent.analysis_tab.pb_alignment_progress.setValue(0)
        self.parent.analysis_tab.pb_vmaf_progress.setValue(0)

        # Reset status
        self.parent.capture_tab.lbl_capture_status.setText("Ready to capture")
        self.parent.analysis_tab.lbl_alignment_status.setText("Not aligned")
        self.parent.analysis_tab.lbl_vmaf_status.setText("Not analyzed")

        # Disable buttons
        self.parent.capture_tab.btn_next_to_analysis.setEnabled(False)
        self.parent.analysis_tab.btn_next_to_results.setEnabled(False)
        self.parent.analysis_tab.btn_run_combined_analysis.setEnabled(False)
        self.btn_export_pdf.setEnabled(False)
        self.btn_export_csv.setEnabled(False)

        # Reset results
        self.lbl_vmaf_score.setText("VMAF Score: --")
        self.lbl_psnr_score.setText("PSNR: --")
        self.lbl_ssim_score.setText("SSIM: --")
        self.list_result_files.clear()

        # Update summaries
        if self.parent.reference_info:
            capture_text = f"Reference: {os.path.basename(self.parent.reference_info['path'])}\nNo capture yet"
            self.parent.capture_tab.lbl_capture_summary.setText(capture_text)
            self.parent.analysis_tab.lbl_analysis_summary.setText("No captured video yet for analysis")
        else:
            self.parent.capture_tab.lbl_capture_summary.setText("No reference video selected")
            self.parent.analysis_tab.lbl_analysis_summary.setText("No videos ready for analysis")

        self.lbl_results_summary.setText("No VMAF analysis results yet")

        # Increment test number
        test_name = self.parent.setup_tab.txt_test_name.text()
        if test_name.startswith("Test_") and len(test_name) > 5 and test_name[5:].isdigit():
            next_num = int(test_name[5:]) + 1
            self.parent.setup_tab.txt_test_name.setText(f"Test_{next_num:02d}")

        # Go back to capture tab
        self.parent.tabs.setCurrentIndex(1)