import logging
import json
from datetime import datetime
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                           QLabel, QComboBox, QProgressBar, QGroupBox, QMessageBox,
                           QTextEdit, QStyle)
from PyQt5.QtCore import Qt
import os  # Required for file path operations

logger = logging.getLogger(__name__)

class AnalysisTab(QWidget):
    """Analysis tab for video alignment and VMAF analysis"""

    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.alignment_thread = None
        self.vmaf_thread = None
        self._setup_ui()

    def _setup_ui(self):
        """Set up the Analysis tab with improved layout and combined workflow"""
        layout = QVBoxLayout(self)

        # Summary of files
        self.lbl_analysis_summary = QLabel("No videos ready for analysis")
        layout.addWidget(self.lbl_analysis_summary)

        # Analysis settings and controls
        settings_group = QGroupBox("Analysis Settings")
        settings_layout = QVBoxLayout()

        # Model selection and duration
        settings_row = QHBoxLayout()

        # VMAF model selection
        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel("VMAF Model:"))
        self.combo_vmaf_model = QComboBox()
        # We'll populate this from the models directory
        self._populate_vmaf_models()
        model_layout.addWidget(self.combo_vmaf_model)
        settings_row.addLayout(model_layout)

        settings_row.addSpacing(10)

        # Duration selection
        duration_layout = QHBoxLayout()
        duration_layout.addWidget(QLabel("Analysis Duration:"))
        self.combo_duration = QComboBox()
        self.combo_duration.addItem("Full Video", "full")
        self.combo_duration.addItem("1 second", 1)
        self.combo_duration.addItem("5 seconds", 5)
        self.combo_duration.addItem("10 seconds", 10)
        self.combo_duration.addItem("30 seconds", 30)
        self.combo_duration.addItem("60 seconds", 60)
        duration_layout.addWidget(self.combo_duration)
        settings_row.addLayout(duration_layout)

        settings_row.addStretch()
        settings_layout.addLayout(settings_row)

        # Combined analysis controls
        actions_row = QHBoxLayout()

        # Run combined analysis button
        self.btn_run_combined_analysis = QPushButton("Run Analysis (Alignment + VMAF)")
        self.btn_run_combined_analysis.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.btn_run_combined_analysis.setEnabled(False)
        self.btn_run_combined_analysis.clicked.connect(self.run_combined_analysis)
        actions_row.addWidget(self.btn_run_combined_analysis)

        actions_row.addStretch()
        settings_layout.addLayout(actions_row)

        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)

        # Progress and status section
        progress_group = QGroupBox("Analysis Progress")
        progress_layout = QVBoxLayout()

        # Alignment progress
        alignment_header = QHBoxLayout()
        alignment_header.addWidget(QLabel("Alignment:"))
        self.lbl_alignment_status = QLabel("Not aligned")
        alignment_header.addWidget(self.lbl_alignment_status)
        alignment_header.addStretch()
        progress_layout.addLayout(alignment_header)

        self.pb_alignment_progress = QProgressBar()
        self.pb_alignment_progress.setTextVisible(True)
        self.pb_alignment_progress.setAlignment(Qt.AlignCenter)
        progress_layout.addWidget(self.pb_alignment_progress)

        # VMAF analysis progress
        vmaf_header = QHBoxLayout()
        vmaf_header.addWidget(QLabel("VMAF Analysis:"))
        self.lbl_vmaf_status = QLabel("Not analyzed")
        vmaf_header.addWidget(self.lbl_vmaf_status)
        vmaf_header.addStretch()
        progress_layout.addLayout(vmaf_header)

        self.pb_vmaf_progress = QProgressBar()
        self.pb_vmaf_progress.setTextVisible(True)
        self.pb_vmaf_progress.setAlignment(Qt.AlignCenter)
        progress_layout.addWidget(self.pb_vmaf_progress)

        progress_group.setLayout(progress_layout)
        layout.addWidget(progress_group)

        # Logs section with two columns
        logs_group = QGroupBox("Analysis Logs")
        logs_layout = QHBoxLayout()

        # Left column - Analysis log
        left_log_layout = QVBoxLayout()
        left_log_label = QLabel("Analysis Log:")
        left_log_label.setStyleSheet("font-weight: bold;")
        left_log_layout.addWidget(left_log_label)

        self.txt_analysis_log = QTextEdit()
        self.txt_analysis_log.setReadOnly(True)
        self.txt_analysis_log.setLineWrapMode(QTextEdit.WidgetWidth)
        self.txt_analysis_log.setMinimumHeight(150)
        self.txt_analysis_log.setMaximumHeight(200)
        left_log_layout.addWidget(self.txt_analysis_log)
        logs_layout.addLayout(left_log_layout)

        # Right column - Alignment and VMAF results
        right_log_layout = QVBoxLayout()
        right_log_label = QLabel("Alignment & Results:")
        right_log_label.setStyleSheet("font-weight: bold;")
        right_log_layout.addWidget(right_log_label)

        self.txt_alignment_log = QTextEdit()
        self.txt_alignment_log.setReadOnly(True)
        self.txt_alignment_log.setLineWrapMode(QTextEdit.WidgetWidth)
        self.txt_alignment_log.setMinimumHeight(150)
        self.txt_alignment_log.setMaximumHeight(200)
        right_log_layout.addWidget(self.txt_alignment_log)
        logs_layout.addLayout(right_log_layout)

        logs_group.setLayout(logs_layout)
        layout.addWidget(logs_group)

        # Navigation buttons
        nav_layout = QHBoxLayout()
        self.btn_prev_to_capture = QPushButton("Back: Capture")
        nav_layout.addWidget(self.btn_prev_to_capture)

        nav_layout.addStretch()

        self.btn_next_to_results = QPushButton("Next: Results")
        self.btn_next_to_results.setEnabled(False)
        nav_layout.addWidget(self.btn_next_to_results)

        layout.addLayout(nav_layout)

    def run_combined_analysis(self):
        """Run video alignment and VMAF analysis in sequence"""
        if not self.parent.reference_info or not self.parent.capture_path:
            self.log_to_analysis("Missing reference or captured video")
            return

        # Reset progress bars
        self.pb_alignment_progress.setValue(0)
        self.pb_vmaf_progress.setValue(0)

        # Reset status labels
        self.lbl_alignment_status.setText("Starting alignment...")
        self.lbl_vmaf_status.setText("Waiting for alignment to complete...")

        # Clear log
        self.txt_analysis_log.clear()
        self.log_to_analysis("Starting combined analysis process...")

        # Get analysis settings
        self.selected_model = self.combo_vmaf_model.currentData()
        # If model data is None, use the text instead
        if self.selected_model is None:
            self.selected_model = self.combo_vmaf_model.currentText()
        # Ensure we have a default if still None
        if not self.selected_model:
            self.selected_model = "vmaf_v0.6.1"

        # Convert duration option to seconds
        duration_option = self.combo_duration.currentData()
        if duration_option == "full":
            self.selected_duration = None
        else:
            self.selected_duration = float(duration_option)

        self.log_to_analysis(f"Using VMAF model: {self.selected_model}")
        self.log_to_analysis(f"Duration: {self.selected_duration if self.selected_duration else 'Full video'}")

        # Disable all analysis buttons during process
        self.btn_run_combined_analysis.setEnabled(False)
        self.parent.vmaf_running = True # Set vmaf_running flag before starting analysis

        # Start the alignment process
        self.align_videos_for_combined_workflow()

    def align_videos_for_combined_workflow(self):
        """Start video alignment as part of the combined workflow using bookend method"""
        self.log_to_analysis("Starting video alignment using bookend method...")

        # Create bookend alignment thread
        from app.bookend_alignment import BookendAlignmentThread
        self.alignment_thread = BookendAlignmentThread(
            self.parent.reference_info['path'],
            self.parent.capture_path
        )

        # Connect signals with dual logging
        self.alignment_thread.alignment_progress.connect(self.pb_alignment_progress.setValue)
        self.alignment_thread.status_update.connect(self._log_alignment_update)
        self.alignment_thread.error_occurred.connect(self.handle_alignment_error)

        # Connect to special handler for combined workflow
        self.alignment_thread.alignment_complete.connect(self.handle_alignment_for_combined_workflow)

        # Start alignment
        self.alignment_thread.start()

    def handle_alignment_for_combined_workflow(self, results):
        """Handle completion of video alignment in combined workflow"""
        # Process alignment results
        offset_frames = results['offset_frames']
        offset_seconds = results['offset_seconds']
        confidence = results['confidence']

        aligned_reference = results['aligned_reference']
        aligned_captured = results['aligned_captured']

        # Store aligned paths
        self.parent.aligned_paths = {
            'reference': aligned_reference,
            'captured': aligned_captured
        }

        # Update UI
        self.lbl_alignment_status.setText(
            f"Aligned using bookend method (conf: {confidence:.2f})"
        )
        self.log_to_analysis(f"Alignment complete!")
        self.log_to_analysis(f"Aligned reference: {os.path.basename(aligned_reference)}")
        self.log_to_analysis(f"Aligned captured: {os.path.basename(aligned_captured)}")

        # Proceed to VMAF analysis
        self.log_to_analysis("Proceeding to VMAF analysis...")
        self.lbl_vmaf_status.setText("Starting VMAF analysis...")

        try:
            # Start VMAF analysis
            self.start_vmaf_for_combined_workflow()
        except Exception as e:
            # Handle any errors during VMAF start
            error_msg = f"Error starting VMAF analysis: {str(e)}"
            self.log_to_analysis(f"Error: {error_msg}")
            self.lbl_vmaf_status.setText("VMAF analysis failed to start")

            # Re-enable buttons
            self.btn_run_combined_analysis.setEnabled(True)

            # Show error to user
            QMessageBox.critical(self, "VMAF Error", error_msg)




    def start_vmaf_for_combined_workflow(self):
        """Start VMAF analysis as part of combined workflow"""
        # Reset VMAF progress
        self.pb_vmaf_progress.setValue(0)

        # Get test metadata from setup tab
        # Check if txt_test_name is a QComboBox or QLineEdit
        if hasattr(self.parent.setup_tab.txt_test_name, 'currentText') and callable(self.parent.setup_tab.txt_test_name.currentText):
            test_name = self.parent.setup_tab.txt_test_name.currentText()
        else:
            test_name = self.parent.setup_tab.txt_test_name.text()

        # Get tester name and location
        tester_name = self.parent.setup_tab.txt_tester_name.text()
        test_location = self.parent.setup_tab.txt_test_location.text()

        # Save test metadata to file after VMAF analysis
        self.test_metadata = {
            "test_name": test_name,
            "tester_name": tester_name,
            "test_location": test_location,
            "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S")
        }

        # Get output directory - use a safer approach that doesn't rely on specific methods
        output_dir = None
        
        # Try to get from options manager
        if hasattr(self.parent, 'options_manager') and self.parent.options_manager:
            try:
                paths = self.parent.options_manager.get_setting('paths')
                if isinstance(paths, dict) and 'output_dir' in paths:
                    output_dir = paths['output_dir']
                    logger.info(f"Using output directory from options: {output_dir}")
            except Exception as e:
                logger.warning(f"Error getting output directory from options: {e}")
        
        # If not found in options, use the reference path parent directory
        if not output_dir and hasattr(self.parent, 'reference_info') and self.parent.reference_info:
            ref_path = self.parent.reference_info.get('path')
            if ref_path:
                # Try to use the parent of the parent directory (assuming references are in a subdirectory)
                ref_dir = os.path.dirname(ref_path)
                parent_dir = os.path.dirname(ref_dir)
                test_results_dir = os.path.join(parent_dir, "test_results")
                
                # Use test_results if it exists, otherwise use the reference directory
                if os.path.exists(test_results_dir) and os.path.isdir(test_results_dir):
                    output_dir = test_results_dir
                    logger.info(f"Using test_results directory as output: {output_dir}")
                else:
                    output_dir = ref_dir
                    logger.info(f"Using reference directory as output: {output_dir}")
        
        # If still not found, use the directory of the captured video
        if not output_dir and hasattr(self.parent, 'aligned_paths') and 'captured' in self.parent.aligned_paths:
            output_dir = os.path.dirname(self.parent.aligned_paths['captured'])
            logger.info(f"Using captured video directory as output: {output_dir}")
            
        # Final fallback - use current directory
        if not output_dir:
            output_dir = os.getcwd()
            logger.info(f"Using current directory as output: {output_dir}")

        # Create analysis thread
        from app.vmaf_analyzer import VMAFAnalysisThread
        self.vmaf_thread = VMAFAnalysisThread(
            self.parent.aligned_paths['reference'],
            self.parent.aligned_paths['captured'],
            self.selected_model,
            self.selected_duration
        )

        # Set output directory and test name if available
        if output_dir:
            self.vmaf_thread.set_output_directory(output_dir)
        if test_name:
            self.vmaf_thread.set_test_name(test_name)

        # Connect signals with improved progress handling
        self.vmaf_thread.analysis_progress.connect(self._update_vmaf_progress)
        self.vmaf_thread.status_update.connect(self.log_to_analysis)
        self.vmaf_thread.error_occurred.connect(self.handle_vmaf_error)
        self.vmaf_thread.analysis_complete.connect(self.handle_vmaf_complete)

        # Start analysis
        self.vmaf_thread.start()



    def handle_alignment_error(self, error_msg):
        """Handle error in video alignment"""
        self.lbl_alignment_status.setText(f"Alignment failed")
        self.log_to_analysis(f"Error: {error_msg}")
        QMessageBox.critical(self, "Alignment Error", error_msg)

        # Re-enable button
        self.btn_run_combined_analysis.setEnabled(True)

    def handle_vmaf_complete(self, results):
        """Handle completion of VMAF analysis"""
        # Check if we've already processed this result (prevent duplicate processing)
        if hasattr(self, '_last_result_id') and self._last_result_id == id(results):
            logger.warning("Ignoring duplicate VMAF analysis result")
            return

        # Store the ID of this result object to prevent duplicate processing
        self._last_result_id = id(results)

        self.parent.vmaf_results = results

        vmaf_score = results.get('vmaf_score')
        psnr = results.get('psnr')
        ssim = results.get('ssim')

        # Save test metadata to JSON file in the test directory
        try:
            if hasattr(self, 'test_metadata') and results.get('json_path'):
                # Get the test directory from the VMAF results
                test_dir = os.path.dirname(results.get('json_path'))

                # Add results to metadata
                metadata = self.test_metadata.copy()
                metadata.update({
                    "vmaf_score": vmaf_score,
                    "psnr_score": psnr,
                    "ssim_score": ssim,
                    "reference_path": results.get('reference_path'),
                    "distorted_path": results.get('distorted_path')
                })

                # Save metadata to JSON file
                metadata_path = os.path.join(test_dir, f"{self.test_metadata['test_name']}_{self.test_metadata['timestamp']}_metadata.json")
                with open(metadata_path, 'w') as f:
                    json.dump(metadata, f, indent=4)

                logger.info(f"Test metadata saved to: {metadata_path}")
                self.log_to_analysis(f"Test metadata saved to test directory")
        except Exception as e:
            logger.error(f"Error saving test metadata: {str(e)}")
            self.log_to_analysis(f"Error saving test metadata: {str(e)}")

        # Ensure progress bar shows 100% when complete
        self.pb_vmaf_progress.setValue(100)

        # Re-enable analysis button
        self.btn_run_combined_analysis.setEnabled(True)
        self.parent.vmaf_running = False # Reset vmaf_running flag

        # Update UI with vmaf score
        if vmaf_score is not None:
            self.lbl_vmaf_status.setText(f"VMAF Score: {vmaf_score:.2f}")
            self.log_to_analysis(f"VMAF analysis complete! Score: {vmaf_score:.2f}")
        else:
            self.lbl_vmaf_status.setText("VMAF Score: N/A")
            self.log_to_analysis("VMAF analysis complete! Score: N/A")

        # Add PSNR/SSIM metrics to log
        if psnr is not None:
            self.log_to_analysis(f"PSNR: {psnr:.2f} dB")
        else:
            self.log_to_analysis("PSNR: N/A")

        if ssim is not None:
            self.log_to_analysis(f"SSIM: {ssim:.4f}")
        else:
            self.log_to_analysis("SSIM: N/A")

        # Enable results tab
        self.btn_next_to_results.setEnabled(True)

        # Update results tab with results data
        self.parent.results_tab.update_results(results)

        # Show message with VMAF score
        if vmaf_score is not None:
            QMessageBox.information(self, "Analysis Complete", 
                                f"VMAF analysis complete!\n\nVMAF Score: {vmaf_score:.2f}")
        else:
            QMessageBox.information(self, "Analysis Complete", 
                                "VMAF analysis complete!")

        # Switch to results tab
        self.parent.tabs.setCurrentIndex(3)

    def handle_vmaf_error(self, error_msg):
        """Handle error in VMAF analysis"""
        self.lbl_vmaf_status.setText(f"VMAF analysis failed")
        self.log_to_analysis(f"Error: {error_msg}")
        QMessageBox.critical(self, "VMAF Analysis Error", error_msg)

        # Reset vmaf_running flag to allow new analysis
        self.parent.vmaf_running = False

        # Re-enable analysis button
        self.btn_run_combined_analysis.setEnabled(True)

    def log_to_analysis(self, message):
        """Add message to analysis log column"""
        self.txt_analysis_log.append(message)
        self.txt_analysis_log.verticalScrollBar().setValue(
            self.txt_analysis_log.verticalScrollBar().maximum()
        )
        self.parent.statusBar().showMessage(message)

    def _log_alignment_update(self, message):
        """Log alignment updates to both columns"""
        # Log to general analysis log
        self.log_to_analysis(message)

        # Add to alignment log with highlighted formatting
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message}"

        # Add special formatting for important messages
        if "complete" in message.lower() or "finished" in message.lower() or "success" in message.lower():
            formatted_message = f'<span style="color: #388E3C; font-weight: bold;">{formatted_message}</span>'

        # Ensure it also appears in alignment log
        self.txt_alignment_log.append(formatted_message)
        self.txt_alignment_log.verticalScrollBar().setValue(
            self.txt_alignment_log.verticalScrollBar().maximum()
        )

    def _update_vmaf_progress(self, progress):
        """Update VMAF progress bar with better feedback"""
        # Ensure progress is between 0-100
        progress = max(0, min(100, progress))

        # Update the progress bar
        self.pb_vmaf_progress.setValue(progress)

        # Also update status text with percentage
        if progress < 100:
            self.lbl_vmaf_status.setText(f"VMAF Analysis: {progress}% complete")
        else:
            self.lbl_vmaf_status.setText("VMAF Analysis: Complete!")

    def _populate_vmaf_models(self):
        """Scan models directory and populate the VMAF model dropdown"""
        try:
            # Clear current items
            self.combo_vmaf_model.clear()

            # Find models directory
            import os
            root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            models_dir = os.path.join(root_dir, "models")

            # Get custom models directory from options if available
            vmaf_models_dir = None
            if hasattr(self.parent, 'options_manager') and self.parent.options_manager:
                try:
                    # Try to get models_dir from paths
                    paths_settings = self.parent.options_manager.get_setting("paths")
                    if paths_settings and isinstance(paths_settings, dict) and 'models_dir' in paths_settings:
                        vmaf_models_dir = paths_settings['models_dir']
                except Exception as e:
                    logger.warning(f"Error accessing models directory from settings: {e}")

            # Use custom directory if specified, otherwise use default
            if vmaf_models_dir and os.path.exists(vmaf_models_dir):
                models_dir = vmaf_models_dir

            logger.info(f"Scanning for VMAF models in: {models_dir}")

            # Scan for .json VMAF model files
            if os.path.exists(models_dir):
                model_files = []
                for file in os.listdir(models_dir):
                    if file.endswith('.json'):
                        model_name = os.path.splitext(file)[0]  # Remove .json extension
                        model_files.append(model_name)

                # Sort models alphabetically for better UX
                model_files.sort()

                # Add each model to the dropdown
                for model in model_files:
                    self.combo_vmaf_model.addItem(model)

                logger.info(f"Populated VMAF model dropdown with {len(model_files)} models")

                # Select default model from settings if available
                if hasattr(self.parent, 'options_manager') and self.parent.options_manager:
                    try:
                        vmaf_settings = self.parent.options_manager.get_setting("vmaf")
                        default_model = vmaf_settings.get("default_model", "vmaf_v0.6.1")

                        # Find and select the default model
                        index = self.combo_vmaf_model.findText(default_model)
                        if index >= 0:
                            self.combo_vmaf_model.setCurrentIndex(index)
                    except Exception as e:
                        logger.warning(f"Error selecting default VMAF model: {e}")
            else:
                logger.warning(f"Models directory not found: {models_dir}")
                # Add fallback default models
                default_models = ["vmaf_v0.6.1", "vmaf_4k_v0.6.1", "vmaf_b_v0.6.3"]
                for model in default_models:
                    self.combo_vmaf_model.addItem(model)
                logger.info("Using fallback default model list")
        except Exception as e:
            logger.error(f"Error populating VMAF models: {e}")
            import traceback
            logger.error(traceback.format_exc())

            # Add fallback default models
            default_models = ["vmaf_v0.6.1", "vmaf_4k_v0.6.1", "vmaf_b_v0.6.3"]
            for model in default_models:
                self.combo_vmaf_model.addItem(model)

    def ensure_threads_finished(self):
        """Ensure all running threads are properly terminated"""
        # Check for vmaf_thread
        if hasattr(self, 'vmaf_thread') and self.vmaf_thread and self.vmaf_thread.isRunning():
            logger.info("VMAF thread is still running - attempting clean shutdown")
            # Try to quit gracefully first
            self.vmaf_thread.quit()

            # Give it a reasonable timeout
            if not self.vmaf_thread.wait(5000):  # 5 seconds
                logger.warning("VMAF thread didn't respond to quit - forcing termination")
                # Force termination if it doesn't respond
                self.vmaf_thread.terminate()
                self.vmaf_thread.wait(2000)  # Give it 2 more seconds to terminate

        # Check for alignment_thread
        if hasattr(self, 'alignment_thread') and self.alignment_thread and self.alignment_thread.isRunning():
            logger.info("Alignment thread is still running - attempting clean shutdown")
            self.alignment_thread.quit()
            if not self.alignment_thread.wait(3000):
                logger.warning("Alignment thread didn't respond to quit - forcing termination")
                self.alignment_thread.terminate()
                self.alignment_thread.wait(1000)