import json
import logging
import os  # Required for file path operations
import platform
import subprocess
from datetime import datetime

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (QComboBox, QGroupBox, QHBoxLayout, QLabel, QMessageBox,
                             QProgressBar, QPushButton, QStyle, QTextEdit,
                             QVBoxLayout, QWidget)



logger = logging.getLogger(__name__)

class AnalysisTab(QWidget):
    """Analysis tab for video alignment and VMAF analysis"""
    analysis_started = pyqtSignal()
    analysis_completed = pyqtSignal(dict)  # Add this signal definition  

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
        # In the _setup_ui method in analysis_tab.py
        self.btn_reset_analysis = QPushButton("Reset Analysis")
        self.btn_reset_analysis.clicked.connect(self.reset_analysis_state)
        actions_row.addWidget(self.btn_reset_analysis)
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
        self.txt_analysis_log.setMinimumHeight(200)
        self.txt_analysis_log.setMaximumHeight(400)
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
        self.txt_alignment_log.setMinimumHeight(200)
        self.txt_alignment_log.setMaximumHeight(400)
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


        # Reset alignment handled flag
        self._alignment_handled = False

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



        # Get bookend settings from options_manager instead of UI controls
        try:
            # Access the options_manager to get bookend settings
            if hasattr(self, 'options_manager') and self.options_manager:
                bookend_settings = self.options_manager.get_setting("bookend")

                # Extract individual settings with fallbacks
                bookend_duration = bookend_settings.get('bookend_duration', 0.2)
                min_loops = bookend_settings.get('min_loops', 3)
                white_threshold = bookend_settings.get('white_threshold', 200)
                frame_sampling_rate = bookend_settings.get('frame_sampling_rate', 5)
            else:
                # Fallback to defaults if options_manager is not available
                bookend_duration = 0.2
                min_loops = 3
                white_threshold = 200
                frame_sampling_rate = 5
                logger.warning("Options manager not available, using default bookend settings")

            self.log_to_analysis(f"Bookend Duration: {bookend_duration}")
            self.log_to_analysis(f"Minimum Loops: {min_loops}")
            self.log_to_analysis(f"White Threshold: {white_threshold}")
            self.log_to_analysis(f"Frame Sampling Rate: {frame_sampling_rate}")
        except Exception as e:
            logger.error(f"Error getting bookend settings: {e}")
            # Fallback to defaults if there's an error
            bookend_duration = 0.2
            min_loops = 3
            white_threshold = 200
            frame_sampling_rate = 5
            self.log_to_analysis("Error getting bookend settings, using defaults")













        # Disable all analysis buttons during process
        self.btn_run_combined_analysis.setEnabled(False)
        self.parent.vmaf_running = True # Set vmaf_running flag before starting analysis

        # Start the alignment process
        self.align_videos_for_combined_workflow(bookend_duration, min_loops, white_threshold, frame_sampling_rate)









    def align_videos_for_combined_workflow(self, bookend_duration, min_loops, white_threshold, frame_sampling_rate):
        """Start video alignment as part of the combined workflow using bookend method"""
        self.log_to_analysis("Starting video alignment using bookend method...")
        print("STARTING VIDEO ALIGNMENT - DIRECT CONSOLE OUTPUT")

        # Create bookend alignment thread
        from app.bookend_alignment import BookendAlignmentThread

        # Ensure any previous thread is cleaned up
        if hasattr(self, 'alignment_thread') and self.alignment_thread:
            try:
                self.alignment_thread.alignment_complete.disconnect()
                self.alignment_thread.alignment_progress.disconnect()
                self.alignment_thread.status_update.disconnect()
                self.alignment_thread.error_occurred.disconnect()
            except:
                pass

        # Reset alignment handled flag
        self._alignment_handled = False

        # Create a new options_manager to pass bookend parameters to the alignment thread
        from app.options_manager import OptionsManager
        temp_options_manager = OptionsManager()

        # Set bookend parameters in the options manager
        bookend_settings = {
            'frame_sampling_rate': frame_sampling_rate,
            'adaptive_brightness': True,
            'motion_compensation': False,
            'fallback_to_full_video': True,
            'bookend_duration': bookend_duration,
            'min_loops': min_loops,
            'white_threshold': white_threshold
        }
        temp_options_manager.set_setting('bookend', bookend_settings)

        # Create new thread with options manager containing bookend parameters
        self.alignment_thread = BookendAlignmentThread(
            self.parent.reference_info['path'],
            self.parent.capture_path,
            True,  # delete_primary set to True to ensure original capture file is deleted
            temp_options_manager
        )

        # Log reference and captured paths
        print(f"Reference path: {self.parent.reference_info['path']}")
        print(f"Captured path: {self.parent.capture_path}")

        # Connect signals with dual logging
        self.alignment_thread.alignment_progress.connect(self.pb_alignment_progress.setValue)
        self.alignment_thread.status_update.connect(self._log_alignment_update)
        self.alignment_thread.error_occurred.connect(self.handle_alignment_error)

        # Connect to special handler for combined workflow
        # First disconnect any existing connections
        try:
            self.alignment_thread.alignment_complete.disconnect()
        except:
            pass

        # Connect with a specially named handler to trace in debugging
        print("Connecting alignment_complete signal to handler")
        self.alignment_thread.alignment_complete.connect(self.handle_alignment_for_combined_workflow)

        # Start alignment
        print("Starting alignment thread")
        self.alignment_thread.start()





    def handle_alignment_for_combined_workflow(self, results):
        """Handle completion of video alignment in combined workflow"""
        # Add direct console output for debugging
        print("ALIGNMENT COMPLETE HANDLER CALLED - DIRECT CONSOLE OUTPUT")
        print(f"Results received: {type(results)}")

        # Add a guard to prevent multiple executions
        if hasattr(self, '_alignment_handled') and self._alignment_handled:
            print("DUPLICATE ALIGNMENT HANDLER DETECTED - SKIPPING")
            logger.info("Alignment already handled, skipping duplicate callback")
            return

        # Verify that results is a dictionary and contains expected keys
        if not isinstance(results, dict):
            error_msg = f"Invalid alignment results format: {type(results)}"
            print(f"ERROR: {error_msg}")
            self.log_to_analysis(f"Error: {error_msg}")
            return

        # Check if required keys exist
        if 'aligned_reference' not in results or 'aligned_captured' not in results:
            error_msg = f"Missing alignment paths in results: {list(results.keys())}"
            print(f"ERROR: {error_msg}")
            self.log_to_analysis(f"Error: {error_msg}")
            return

        # Mark as handled to prevent duplicate processing
        self._alignment_handled = True

        # Process alignment results
        results.get('offset_frames', 0)
        results.get('offset_seconds', 0)
        confidence = results.get('confidence', 0)

        aligned_reference = results['aligned_reference']
        aligned_captured = results['aligned_captured']

        # Verify files exist
        if not os.path.exists(aligned_reference):
            error_msg = f"Aligned reference file does not exist: {aligned_reference}"
            print(f"ERROR: {error_msg}")
            self.log_to_analysis(f"Error: {error_msg}")
            return

        if not os.path.exists(aligned_captured):
            error_msg = f"Aligned captured file does not exist: {aligned_captured}"
            print(f"ERROR: {error_msg}")
            self.log_to_analysis(f"Error: {error_msg}")
            return

        # Store aligned paths
        from pathlib import Path
        self.parent.aligned_paths = {
            'reference': str(Path(aligned_reference).resolve()),
            'captured': str(Path(aligned_captured).resolve())
        }

        # Print debug info
        print(f"Reference: {os.path.basename(aligned_reference)}")
        print(f"Captured: {os.path.basename(aligned_captured)}")
        print(f"Proceeding to VMAF analysis...")

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
            print(f"ERROR: {error_msg}")
            self.log_to_analysis(f"Error: {error_msg}")
            self.lbl_vmaf_status.setText("VMAF analysis failed to start")

            # Re-enable buttons
            self.btn_run_combined_analysis.setEnabled(True)

            # Show error to user
            QMessageBox.critical(self, "VMAF Error", error_msg)




    def reset_analysis_state(self):
        """Reset analysis state to allow new analysis attempts"""
        # First, ensure we have a VMAFAnalysisThread class defined
        try:
            # Define a temporary class if needed
            if not 'VMAFAnalysisThread' in globals():
                from PyQt5.QtCore import QThread

                global VMAFAnalysisThread
                class VMAFAnalysisThread(QThread):
                    @staticmethod
                    def reset_thread_tracking():
                        pass  # Just a placeholder
        except Exception as e:
            # Just log the error and continue
            logger.error(f"Error setting up VMAFAnalysisThread: {e}")

        # Reset the thread tracking mechanism - safely
        try:
            if 'VMAFAnalysisThread' in globals():
                VMAFAnalysisThread.reset_thread_tracking()
        except Exception as e:
            logger.warning(f"Could not reset thread tracking: {e}")

        # Reset vmaf_running flag
        if hasattr(self.parent, 'vmaf_running'):
            self.parent.vmaf_running = False

        # Reset UI elements
        self.btn_run_combined_analysis.setEnabled(True)
        self.lbl_vmaf_status.setText("Not analyzed")
        self.log_to_analysis("Analysis state reset")

        # Reset alignment handled flag if it exists
        if hasattr(self, '_alignment_handled'):
            self._alignment_handled = False

        # Also clear any running threads
        self.ensure_threads_finished()





    def start_vmaf_for_combined_workflow(self):
        """Start VMAF analysis as part of combined workflow"""
        print("STARTING VMAF ANALYSIS - DIRECT CONSOLE OUTPUT")
        # Reset VMAF progress
        self.pb_vmaf_progress.setValue(0)

        # Verify aligned paths exist
        if not hasattr(self.parent, 'aligned_paths'):
            error_msg = "Aligned paths not found"
            print(f"ERROR: {error_msg}")
            self.log_to_analysis(error_msg)
            return

        if 'reference' not in self.parent.aligned_paths or 'captured' not in self.parent.aligned_paths:
            error_msg = "Missing reference or captured path in aligned_paths"
            print(f"ERROR: {error_msg}")
            self.log_to_analysis(error_msg)
            return

        # Print the aligned paths
        print(f"Aligned reference: {self.parent.aligned_paths['reference']}")
        print(f"Aligned captured: {self.parent.aligned_paths['captured']}")

        # Check if files exist
        if not os.path.exists(self.parent.aligned_paths['reference']):
            error_msg = f"Aligned reference file does not exist: {self.parent.aligned_paths['reference']}"
            print(f"ERROR: {error_msg}")
            self.log_to_analysis(error_msg)
            return

        if not os.path.exists(self.parent.aligned_paths['captured']):
            error_msg = f"Aligned captured file does not exist: {self.parent.aligned_paths['captured']}"
            print(f"ERROR: {error_msg}")
            self.log_to_analysis(error_msg)
            return

        # Get test metadata from setup tab - explicitly define test_name
        test_name = None
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

        # Get output directory - define output_dir variable
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

        # Remaining directory determination logic
        if not output_dir and hasattr(self.parent, 'reference_info') and self.parent.reference_info:
            ref_path = self.parent.reference_info.get('path')
            if ref_path:
                ref_dir = os.path.dirname(ref_path)
                parent_dir = os.path.dirname(ref_dir)
                test_results_dir = os.path.join(parent_dir, "test_results")

                if os.path.exists(test_results_dir) and os.path.isdir(test_results_dir):
                    output_dir = test_results_dir
                    logger.info(f"Using test_results directory as output: {output_dir}")
                else:
                    output_dir = ref_dir
                    logger.info(f"Using reference directory as output: {output_dir}")

        if not output_dir and hasattr(self.parent, 'aligned_paths') and 'captured' in self.parent.aligned_paths:
            output_dir = os.path.dirname(self.parent.aligned_paths['captured'])
            logger.info(f"Using captured video directory as output: {output_dir}")

        if not output_dir:
            output_dir = os.getcwd()
            logger.info(f"Using current directory as output: {output_dir}")

        # Now define the VMAFAnalysisThread class so it can be imported elsewhere
        # Make it global to the module
        from app.vmaf_analyzer import VMAFAnalyzer
        from PyQt5.QtCore import QThread

        # Define the class and make it global to the module
        global VMAFAnalysisThread
        class VMAFAnalysisThread(QThread):
            def __init__(self, reference_path, distorted_path, model, duration):
                super().__init__()
                self.vmaf_analyzer = VMAFAnalyzer()
                self.reference_path = reference_path
                self.distorted_path = distorted_path
                self.model = model
                self.duration = duration

                # Forward signals
                self.analysis_progress = self.vmaf_analyzer.analysis_progress
                self.analysis_complete = self.vmaf_analyzer.analysis_complete
                self.error_occurred = self.vmaf_analyzer.error_occurred
                self.status_update = self.vmaf_analyzer.status_update

            def set_output_directory(self, output_dir):
                self.vmaf_analyzer.set_output_directory(output_dir)

            def set_test_name(self, test_name):
                self.vmaf_analyzer.set_test_name(test_name)

            def run(self):
                self.vmaf_analyzer.analyze_videos(
                    self.reference_path, 
                    self.distorted_path, 
                    self.model, 
                    self.duration
                )

            @staticmethod
            def reset_thread_tracking():
                """Static method to reset thread tracking state"""
                pass  # This is just a placeholder to match the expected interface

        # Now create the thread with our exported class
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

        # Connect signals
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
        try:
            # Check if we've already processed this result (prevent duplicate processing)
            if hasattr(self, '_last_result_id') and self._last_result_id == id(results):
                logger.warning("Ignoring duplicate VMAF analysis result")
                return

            # Store the ID of this result object to prevent duplicate processing
            self._last_result_id = id(results)

            # Store results in parent for access by other tabs
            self.parent.analysis_results = results

            # Extract main scores
            vmaf_score = results.get('vmaf_score', 'N/A')
            psnr_score = results.get('psnr_score', 'N/A')
            ssim_score = results.get('ssim_score', 'N/A')

            # Save test metadata to JSON file in the test directory
            try:
                if results.get('json_path'):
                    # Get the test directory from the VMAF results
                    test_dir = os.path.dirname(results.get('json_path'))

                    # Add results to metadata (safely)
                    metadata = self.test_metadata.copy() if hasattr(self, 'test_metadata') and self.test_metadata else {}

                    # Get file names safely
                    reference_file = results.get('reference_video', '')
                    distorted_file = results.get('distorted_video', '')
                    psnr_file = os.path.basename(results.get('psnr_log', '')) if results.get('psnr_log') else ''
                    ssim_file = os.path.basename(results.get('ssim_log', '')) if results.get('ssim_log') else ''
                    json_file = os.path.basename(results.get('json_path', '')) if results.get('json_path') else ''
                    
                    # Get video dimensions and metrics
                    width = results.get('width', 0)
                    height = results.get('height', 0)
                    resolution = f"{width}x{height}" if width and height else "Unknown"

                    # Extract frame count, duration, and fps from results
                    frame_count = 0
                    video_duration = 0
                    fps = 0
                    
                    # Try to get from metadata if available
                    if 'metadata' in results and 'video' in results['metadata']:
                        video_meta = results['metadata']['video']
                        frame_count = video_meta.get('frame_count', 0)
                        video_duration = video_meta.get('duration', 0)
                        fps = video_meta.get('fps', 0)
                    # Fallback to raw_results
                    elif 'raw_results' in results and 'frames' in results['raw_results']:
                        frames = results['raw_results']['frames']
                        frame_count = len(frames)
                        # Try to calculate duration if fps is available
                        if fps > 0:
                            video_duration = frame_count / fps

                    # Get VMAF model information
                    vmaf_model = results.get('model', '')
                    if not vmaf_model and 'metadata' in results:
                        vmaf_model = results['metadata'].get('test', {}).get('model', 'vmaf_v0.6.1')

                    # Get analysis settings from vmaf_analyzer if available
                    vmaf_options = {}
                    if hasattr(self, 'vmaf_analyzer') and self.vmaf_analyzer:
                        vmaf_options = {
                            'model': vmaf_model,
                            'pool_method': self.vmaf_analyzer.pool_method,
                            'feature_subsample': self.vmaf_analyzer.feature_subsample,
                            'enable_motion_score': self.vmaf_analyzer.enable_motion_score,
                            'enable_temporal_features': self.vmaf_analyzer.enable_temporal_features,
                            'psnr_enabled': self.vmaf_analyzer.psnr_enabled,
                            'ssim_enabled': self.vmaf_analyzer.ssim_enabled
                        }
                    # Fallback to metadata if available
                    elif 'metadata' in results and 'vmaf_options' in results['metadata']:
                        vmaf_options = results['metadata']['vmaf_options']

                    # Get capture settings
                    capture_settings = {}
                    if hasattr(self.parent, 'options_manager') and self.parent.options_manager:
                        capture_settings = self.parent.options_manager.get_setting('capture', {})

                    # Get FFmpeg version info
                    try:
                        ffmpeg_exe, _, _ = get_ffmpeg_path()
                        process = subprocess.run([ffmpeg_exe, "-version"], capture_output=True, text=True)
                        ffmpeg_version = process.stdout.split('\n')[0] if process.returncode == 0 else "Unknown"
                    except Exception:
                        ffmpeg_version = "Unknown"

                    # Organize metadata in logical groups
                    metadata.update({
                        # Test Results
                        "vmaf_score": vmaf_score,

                        # File Information
                        "reference_video": reference_file,
                        "distorted_video": distorted_file,
                        "psnr_file": psnr_file,
                        "ssim_file": ssim_file,
                        "json_result": json_file,

                        # Video Characteristics
                        "video_details": {
                            "resolution": resolution,
                            "width": width,
                            "height": height,
                            "fps": fps,
                            "frame_count": frame_count,
                            "duration_seconds": video_duration
                        },

                        # Analysis Details
                        "analysis_settings": vmaf_options,

                        # Capture Device Information
                        "capture_details": capture_settings,

                        # System Information
                        "system_info": {
                            "ffmpeg_version": ffmpeg_version,
                            "os": platform.system(),
                            "os_version": platform.version(),
                            "processor": platform.processor()
                        }
                    })

                    # Save metadata to JSON file
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    test_name = metadata.get('test_name', 'test') if 'test_name' in metadata else (
                        self.test_metadata.get('test_name', 'test') if hasattr(self, 'test_metadata') and self.test_metadata else 'test'
                    )
                    metadata_path = os.path.join(test_dir, f"{test_name}_{timestamp}_metadata.json")
                    
                    with open(metadata_path, 'w') as f:
                        json.dump(metadata, f, indent=4)

                    logger.info(f"Test metadata saved to: {metadata_path}")
                    self.log_to_analysis(f"Test metadata saved to test directory")
            except Exception as e:
                logger.error(f"Error saving test metadata: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                self.log_to_analysis(f"Error saving test metadata: {str(e)}")

            # Ensure progress bar shows 100% when complete
            self.pb_vmaf_progress.setValue(100)

            # Re-enable analysis button
            self.btn_run_combined_analysis.setEnabled(True)
            self.analysis_running = False
            
            if hasattr(self.parent, 'vmaf_running'):
                self.parent.vmaf_running = False

            # Update UI with vmaf score
            if isinstance(vmaf_score, (int, float)):
                self.lbl_vmaf_status.setText(f"VMAF Score: {vmaf_score:.2f}")
                self.log_to_analysis(f"VMAF analysis complete! Score: {vmaf_score:.2f}")
            else:
                self.lbl_vmaf_status.setText(f"VMAF Score: {vmaf_score}")
                self.log_to_analysis(f"VMAF analysis complete! Score: {vmaf_score}")

            # Add PSNR/SSIM metrics to log
            if isinstance(psnr_score, (int, float)):
                self.log_to_analysis(f"PSNR: {psnr_score:.2f} dB")
            else:
                self.log_to_analysis(f"PSNR: {psnr_score}")

            if isinstance(ssim_score, (int, float)):
                self.log_to_analysis(f"SSIM: {ssim_score:.4f}")
            else:
                self.log_to_analysis(f"SSIM: {ssim_score}")

            # Enable results tab
            self.btn_next_to_results.setEnabled(True)

            # Update results tab using available methods
            if hasattr(self.parent, 'on_analysis_completed'):
                try:
                    # Call the parent's method to handle results
                    self.parent.on_analysis_completed(results)
                except Exception as e:
                    logger.error(f"Error calling parent.on_analysis_completed: {str(e)}")
                    import traceback
                    logger.error(traceback.format_exc())
            else:
                # Try different ways to update the results tab
                try:
                    # Option 1: Direct method call (removed - was causing error)
                    # self.parent.results_tab.update_results(results)
                    
                    # Option 2: Use MainWindow's on_analysis_completed if it exists
                    if hasattr(self.parent, 'on_analysis_completed'):
                        self.parent.on_analysis_completed(results)
                    
                    # Option 3: Set results in results_tab directly
                    if hasattr(self.parent, 'results_tab'):
                        # Update basic UI elements directly
                        results_tab = self.parent.results_tab
                        
                        # Update labels if they exist
                        if hasattr(results_tab, 'lbl_vmaf_score') and isinstance(vmaf_score, (int, float)):
                            results_tab.lbl_vmaf_score.setText(f"VMAF Score: {vmaf_score:.2f}")
                        
                        if hasattr(results_tab, 'lbl_psnr_score'):
                            if isinstance(psnr_score, (int, float)):
                                results_tab.lbl_psnr_score.setText(f"PSNR: {psnr_score:.2f} dB")
                            else:
                                results_tab.lbl_psnr_score.setText(f"PSNR: {psnr_score}")
                        
                        if hasattr(results_tab, 'lbl_ssim_score'):
                            if isinstance(ssim_score, (int, float)):
                                results_tab.lbl_ssim_score.setText(f"SSIM: {ssim_score:.4f}")
                            else:
                                results_tab.lbl_ssim_score.setText(f"SSIM: {ssim_score}")
                        
                        # Update result files list if method exists
                        if hasattr(results_tab, 'update_result_files_list'):
                            results_tab.update_result_files_list(results)
                        
                        # Enable export buttons if they exist
                        if hasattr(results_tab, 'btn_export_pdf'):
                            results_tab.btn_export_pdf.setEnabled(True)
                        if hasattr(results_tab, 'btn_export_csv'):
                            results_tab.btn_export_csv.setEnabled(True)
                except Exception as e:
                    logger.error(f"Error updating results tab directly: {str(e)}")
                    import traceback
                    logger.error(traceback.format_exc())

            # Show message with VMAF score
            if isinstance(vmaf_score, (int, float)):
                QMessageBox.information(self, "Analysis Complete", 
                                    f"VMAF analysis complete!\n\nVMAF Score: {vmaf_score:.2f}")
            else:
                QMessageBox.information(self, "Analysis Complete", 
                                    "VMAF analysis complete!")

            # Switch to results tab if available
            try:
                if hasattr(self.parent, 'tabs') and self.parent.tabs is not None:
                    results_tab_index = 4  # Typically the results tab is index 4
                    if self.parent.tabs.count() > results_tab_index:
                        self.parent.tabs.setCurrentIndex(results_tab_index)
            except Exception as e:
                logger.error(f"Error switching to results tab: {str(e)}")
                
        except Exception as e:
            logger.error(f"Error in handle_vmaf_complete: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            
            # Ensure UI is updated even on error
            self.pb_vmaf_progress.setValue(100)
            self.btn_run_combined_analysis.setEnabled(True)
            self.analysis_running = False
            
            if hasattr(self.parent, 'vmaf_running'):
                self.parent.vmaf_running = False
                
            QMessageBox.critical(self, "Analysis Error", 
                            f"An error occurred when processing analysis results:\n\n{str(e)}")















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

    def _update_frame_sampling_label(self):
        self.lbl_frame_sampling_rate.setText(str(self.frame_sampling_slider.value()))

    def load_settings(self):
        """Load settings from options manager"""
        try:
            # Load bookend settings if options manager is available
            if hasattr(self.parent, 'options_manager') and self.parent.options_manager:
                try:
                    # Get bookend settings
                    bookend_settings = self.parent.options_manager.get_setting("bookend", {})

                    # Update UI controls with settings values
                    if hasattr(self, 'spin_bookend_duration'):
                        self.spin_bookend_duration.setValue(float(bookend_settings.get('bookend_duration', 0.5)))

                    if hasattr(self, 'spin_min_loops'):
                        self.spin_min_loops.setValue(int(bookend_settings.get('min_loops', 3)))

                    if hasattr(self, 'spin_bookend_threshold'):
                        self.spin_bookend_threshold.setValue(int(bookend_settings.get('white_threshold', 230)))

                    if hasattr(self, 'frame_sampling_slider'):
                        self.frame_sampling_slider.setValue(int(bookend_settings.get('frame_sampling_rate', 5)))
                        self._update_frame_sampling_label()

                    logger.info("Bookend settings loaded successfully")
                except Exception as e:
                    logger.warning(f"Error loading bookend settings: {e}")

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
        except Exception as e:
            logger.error(f"Error loading settings: {e}")

def get_ffmpeg_path():
    """Helper function to get the path to ffmpeg and ffprobe executables."""
    # Implement your logic here to determine the paths.  This is placeholder code.
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ffmpeg_exe = os.path.join(root_dir, "ffmpeg_bin", "ffmpeg.exe")
    ffprobe_exe = os.path.join(root_dir, "ffmpeg_bin", "ffprobe.exe")
    return ffmpeg_exe, ffprobe_exe, "" #Placeholder for error