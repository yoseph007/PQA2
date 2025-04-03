import os
import logging
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                            QLabel, QComboBox, QGroupBox, QFileDialog, QMessageBox)
from PyQt5.QtCore import Qt
import threading

logger = logging.getLogger(__name__)

class SetupTab(QWidget):
    """Setup tab for selecting reference videos and output settings"""

    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.reference_thread = None
        self._setup_ui()

    def _setup_ui(self):
        """Set up the Setup tab UI"""
        layout = QVBoxLayout(self)

        # Reference video group
        reference_group = QGroupBox("Reference Video")
        reference_layout = QVBoxLayout()

        # Reference file selection
        ref_file_layout = QHBoxLayout()
        self.lbl_reference_path = QLabel("Select a reference video:")
        self.combo_reference_videos = QComboBox()
        self.combo_reference_videos.setMinimumWidth(300)
        self.combo_reference_videos.currentIndexChanged.connect(self.reference_selected)
        self.btn_refresh_references = QPushButton("Refresh List")
        self.btn_refresh_references.clicked.connect(self.refresh_reference_videos)
        ref_file_layout.addWidget(self.lbl_reference_path)
        ref_file_layout.addWidget(self.combo_reference_videos)
        ref_file_layout.addWidget(self.btn_refresh_references)
        reference_layout.addLayout(ref_file_layout)

        # Reference details
        self.lbl_reference_details = QLabel("Reference details: None")
        reference_layout.addWidget(self.lbl_reference_details)

        # Add to group
        reference_group.setLayout(reference_layout)
        layout.addWidget(reference_group)

        # Output settings
        output_group = QGroupBox("Output Settings")
        output_layout = QVBoxLayout()

        # Output directory
        output_dir_layout = QHBoxLayout()
        self.lbl_output_dir = QLabel("Default output directory")
        self.btn_browse_output = QPushButton("Browse...")
        self.btn_browse_output.clicked.connect(self.browse_output_dir)
        output_dir_layout.addWidget(self.lbl_output_dir)
        output_dir_layout.addWidget(self.btn_browse_output)
        output_layout.addLayout(output_dir_layout)

        # Test name
        test_name_layout = QHBoxLayout()
        test_name_layout.addWidget(QLabel("Test Name:"))
        self.txt_test_name = QComboBox()
        self.txt_test_name.setEditable(True)
        self.txt_test_name.addItem("Test_01")
        self.txt_test_name.addItem("Test_02")
        self.txt_test_name.addItem("Test_03")
        test_name_layout.addWidget(self.txt_test_name)
        output_layout.addLayout(test_name_layout)

        # Add to group
        output_group.setLayout(output_layout)
        layout.addWidget(output_group)

        # Setup status
        self.lbl_setup_status = QLabel("Please select a reference video to continue")
        layout.addWidget(self.lbl_setup_status)

        # Navigation buttons
        nav_layout = QHBoxLayout()
        nav_layout.addStretch()
        self.btn_next_to_capture = QPushButton("Next: Capture")
        self.btn_next_to_capture.setEnabled(False)
        nav_layout.addWidget(self.btn_next_to_capture)
        layout.addLayout(nav_layout)

        # Add stretch to push everything up
        layout.addStretch()

    def refresh_reference_videos(self):
        """Refresh the reference video dropdown list"""
        try:
            self.combo_reference_videos.clear()
            self.lbl_reference_details.setText("Reference details: None")

            # Get reference directory from options
            ref_dir = ""
            if hasattr(self.parent, 'options_manager') and self.parent.options_manager:
                paths = self.parent.options_manager.get_setting('paths', {})
                ref_dir = paths.get('reference_video_dir', '')

            if not ref_dir or not os.path.exists(ref_dir):
                self.combo_reference_videos.addItem("No reference directory set")
                return

            # Add a loading indicator
            self.combo_reference_videos.addItem("Loading...")
            self.combo_reference_videos.setEnabled(False)

            # Process events to update UI
            from PyQt5.QtCore import QCoreApplication
            QCoreApplication.processEvents()

            # Start a thread to scan for video files
            self.reference_thread = threading.Thread(
                target=self._scan_references,
                args=(ref_dir,)
            )
            self.reference_thread.daemon = True

            try:
                self.reference_thread.start()
            except KeyboardInterrupt:
                logging.warning("Reference scanning was interrupted by user")
                self.combo_reference_videos.clear()
                self.combo_reference_videos.addItem("Scanning interrupted")
                self.combo_reference_videos.setEnabled(True)
                return

        except Exception as e:
            logger.error(f"Error refreshing reference videos: {str(e)}")
            self.combo_reference_videos.addItem("Error loading videos", "")
            self.combo_reference_videos.setEnabled(True)


    def _scan_references(self, ref_dir):
        video_extensions = ['.mp4', '.mov', '.avi', '.mkv']
        video_files = []
        try:
            for file in os.listdir(ref_dir):
                if any(file.lower().endswith(ext) for ext in video_extensions):
                    video_files.append(os.path.join(ref_dir, file))

            # Update UI on the main thread
            from PyQt5.QtCore import QCoreApplication
            QCoreApplication.processEvents()
            self.combo_reference_videos.clear()
            if video_files:
                for video_path in sorted(video_files):
                    # Ensure the path is a string, not a dict or other unhashable type
                    if isinstance(video_path, str) and os.path.exists(video_path):
                        # Add the item with basename as display text and full path as data
                        self.combo_reference_videos.addItem(os.path.basename(video_path))
                        # Set the item data separately to avoid type issues
                        index = self.combo_reference_videos.count() - 1
                        self.combo_reference_videos.setItemData(index, video_path)
                logger.info(f"Found {len(video_files)} reference videos")
            else:
                self.combo_reference_videos.addItem("No reference videos found")
                self.combo_reference_videos.setItemData(0, "")
                logger.info("No reference videos found in the configured directory")
            self.combo_reference_videos.setEnabled(True)
        except Exception as e:
            logger.error(f"Error loading reference videos: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            self.combo_reference_videos.addItem("Error loading videos")
            self.combo_reference_videos.setItemData(0, "")
            self.combo_reference_videos.setEnabled(True)


    def reference_selected(self, index):
        """Handle reference video selection from dropdown"""
        if index < 0:
            return

        file_path = self.combo_reference_videos.itemData(index)
        if isinstance(file_path, str) and file_path and os.path.exists(file_path):
            # Update UI
            self.lbl_reference_path.setText("Selected: " + os.path.basename(file_path))
            self.lbl_reference_path.setToolTip(file_path)

            # Analyze the reference video
            self.analyze_reference(file_path)
        else:
            self.lbl_reference_path.setText("Invalid reference path")
            self.lbl_setup_status.setText("Please select a valid reference video")

    def analyze_reference(self, file_path):
        """Analyze reference video to extract metadata"""
        self.log_to_setup(f"Analyzing reference video: {os.path.basename(file_path)}")

        # Create analysis thread
        from app.reference_analyzer import ReferenceAnalysisThread
        self.reference_thread = ReferenceAnalysisThread(file_path)
        self.reference_thread.progress_update.connect(self.log_to_setup)
        self.reference_thread.error_occurred.connect(self.handle_reference_error)
        self.reference_thread.analysis_complete.connect(self.handle_reference_analyzed)

        # Start analysis
        self.reference_thread.start()

    def handle_reference_analyzed(self, info):
        """Handle completion of reference video analysis"""
        self.parent.reference_info = info

        # Update UI with reference info
        duration = info['duration']
        frame_rate = info['frame_rate']
        width = info['width']
        height = info['height']
        total_frames = info['total_frames']
        has_bookends = info.get('has_bookends', False)

        details = (f"Duration: {duration:.2f}s ({total_frames} frames), " + 
                f"Resolution: {width}x{height}, {frame_rate:.2f} fps")

        if has_bookends:
            details += "\nWhite bookend frames detected at beginning"

        self.lbl_reference_details.setText(details)

        # Update setup status
        self.lbl_setup_status.setText("Reference video loaded successfully")

        # Enable next buttons
        self.btn_next_to_capture.setEnabled(True)

        # Update capture tab
        self.parent.capture_tab.lbl_capture_summary.setText(
            f"Reference: {os.path.basename(info['path'])}\n{details}"
        )

        # Share reference info with capture manager
        if hasattr(self.parent, 'capture_mgr') and self.parent.capture_mgr:
            self.parent.capture_mgr.set_reference_video(info)

        # Populate the duration combo box with 1-second increments
        # up to the reference video duration
        self.parent.analysis_tab.combo_duration.clear()
        self.parent.analysis_tab.combo_duration.addItem("Full Video", "full")

        # Add duration options based on reference video length
        max_seconds = int(duration)
        if max_seconds <= 60:  # For shorter videos, add every second
            for i in range(1, max_seconds + 1):
                self.parent.analysis_tab.combo_duration.addItem(f"{i} seconds", i)
        else:  # For longer videos, add more reasonable options
            durations = [1, 2, 5, 10, 15, 30, 60]
            durations.extend([d for d in [90, 120, 180, 240, 300] if d < max_seconds])
            for d in durations:
                self.parent.analysis_tab.combo_duration.addItem(f"{d} seconds", d)

        self.log_to_setup("Reference video analysis complete")

    def handle_reference_error(self, error_msg):
        """Handle error in reference video analysis"""
        self.log_to_setup(f"Error: {error_msg}")
        QMessageBox.critical(self, "Reference Analysis Error", error_msg)

    def browse_output_dir(self):
        """Browse for output directory"""
        # Use standard test_results directory as base
        default_dir = self.parent.file_manager.get_default_base_dir() if hasattr(self.parent, 'file_manager') else None

        if not default_dir:
            script_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            default_dir = os.path.join(script_dir, "tests", "test_results")
            os.makedirs(default_dir, exist_ok=True)

        # Show the browser but only for visual confirmation
        directory = QFileDialog.getExistingDirectory(
            self, "Select Output Directory", default_dir
        )

        if directory:
            # Set output directory in UI and managers
            self.lbl_output_dir.setText(directory)
            self.lbl_output_dir.setToolTip(directory)

            if hasattr(self.parent, 'file_manager'):
                self.parent.file_manager.base_dir = directory

            if hasattr(self.parent, 'capture_mgr'):
                self.parent.capture_mgr.set_output_directory(directory)

            self.log_to_setup(f"Output directory set to: {directory}")

    def log_to_setup(self, message):
        """Add message to setup status"""
        self.lbl_setup_status.setText(message)
        self.parent.statusBar().showMessage(message)

    def ensure_threads_finished(self):
        """Ensure all running threads are properly terminated"""
        if hasattr(self, 'reference_thread') and self.reference_thread and self.reference_thread.isRunning():
            logger.info("Reference analysis thread is still running - attempting clean shutdown")
            self.reference_thread.quit()
            if not self.reference_thread.wait(3000):
                logger.warning("Reference thread didn't respond to quit - forcing termination")
                self.reference_thread.terminate()
                self.reference_thread.wait(1000)