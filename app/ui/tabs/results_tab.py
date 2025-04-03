
import os
import json
import logging
import platform
import subprocess
from datetime import datetime
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                           QLabel, QTabWidget, QGroupBox, QListWidget, 
                           QListWidgetItem, QTableWidget, QTableWidgetItem,
                           QAbstractItemView, QHeaderView, QMessageBox)
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
        # For now, we'll just show a placeholder message
        QMessageBox.information(self, "Export PDF", 
                              "This feature is not yet implemented.\n\nIn a complete implementation, this would generate a PDF certificate with all test details and results.")

    def export_csv_data(self):
        """Export VMAF results as CSV data"""
        # For now, we'll just show a placeholder message
        QMessageBox.information(self, "Export CSV", 
                              "This feature is not yet implemented.\n\nIn a complete implementation, this would export all analysis data to a CSV file.")

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
            # Clear current table
            self.results_table.setRowCount(0)
            
            # Get output directory
            output_dir = self.parent.setup_tab.txt_output_dir.text()
            if output_dir == "Default output directory" and hasattr(self.parent, 'file_manager'):
                output_dir = self.parent.file_manager.get_default_base_dir()
            
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
        """View a historical test result"""
        sender = self.sender()
        row = sender.property("row")
        test_dir = sender.property("dir")
        
        try:
            # Show the results in a dialog
            from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QScrollArea
            
            dialog = QDialog(self)
            dialog.setWindowTitle("Test Result Details")
            dialog.resize(600, 400)
            
            layout = QVBoxLayout(dialog)
            
            # Create a scroll area for content
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            
            content_widget = QWidget()
            content_layout = QVBoxLayout(content_widget)
            
            # Add test name and timestamp
            item = self.results_table.item(row, 0)
            test_name = item.text() if item else "Unknown"
            
            item = self.results_table.item(row, 1)
            timestamp = item.text() if item else "Unknown"
            
            content_layout.addWidget(QLabel(f"<h2>{test_name} - {timestamp}</h2>"))
            
            # Add VMAF, PSNR, SSIM scores
            score_layout = QVBoxLayout()
            
            item = self.results_table.item(row, 2)
            vmaf_score = item.text() if item else "N/A"
            vmaf_label = QLabel(f"<b>VMAF Score:</b> {vmaf_score}")
            vmaf_label.setStyleSheet("font-size: 16px;")
            score_layout.addWidget(vmaf_label)
            
            item = self.results_table.item(row, 3)
            psnr_score = item.text() if item else "N/A"
            score_layout.addWidget(QLabel(f"<b>PSNR:</b> {psnr_score}"))
            
            item = self.results_table.item(row, 4)
            ssim_score = item.text() if item else "N/A"
            score_layout.addWidget(QLabel(f"<b>SSIM:</b> {ssim_score}"))
            
            content_layout.addLayout(score_layout)
            
            # Add list of files in the test directory
            content_layout.addWidget(QLabel("<h3>Result Files:</h3>"))
            
            file_list = QListWidget()
            for f in sorted(os.listdir(test_dir)):
                file_path = os.path.join(test_dir, f)
                if os.path.isfile(file_path):
                    item = QListWidgetItem(f)
                    item.setData(Qt.UserRole, file_path)
                    file_list.addItem(item)
            
            file_list.itemDoubleClicked.connect(self.open_result_file)
            file_list.setMinimumHeight(200)
            content_layout.addWidget(file_list)
            
            # Add buttons at the bottom
            button_layout = QHBoxLayout()
            
            btn_export = QPushButton("Export Report")
            btn_export.clicked.connect(lambda: self._export_result(test_dir=test_dir))
            button_layout.addWidget(btn_export)
            
            btn_close = QPushButton("Close")
            btn_close.clicked.connect(dialog.accept)
            button_layout.addWidget(btn_close)
            
            # Set content widget in scroll area
            scroll.setWidget(content_widget)
            layout.addWidget(scroll)
            layout.addLayout(button_layout)
            
            dialog.exec_()
            
        except Exception as e:
            logger.error(f"Error viewing result: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
    
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
            
            # For now just show a placeholder message
            QMessageBox.information(
                self,
                "Export Selected Results",
                f"Would export {len(selected_rows)} selected results.\n\nThis feature will be fully implemented in the future."
            )
        except Exception as e:
            logger.error(f"Error exporting selected results: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            
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
