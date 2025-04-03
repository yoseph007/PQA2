import os
import logging
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                            QLabel, QComboBox, QGroupBox, QFileDialog, QMessageBox,
                            QLineEdit)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPixmap
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

        # Reference file selection - direct file selector
        ref_file_layout = QHBoxLayout()
        self.lbl_reference_path = QLabel("Reference video:")
        self.txt_reference_path = QLineEdit()
        self.txt_reference_path.setMinimumWidth(300)
        self.txt_reference_path.setReadOnly(True)
        self.btn_browse_reference = QPushButton("Browse...")
        self.btn_browse_reference.clicked.connect(self.browse_reference_video)
        
        ref_file_layout.addWidget(self.lbl_reference_path)
        ref_file_layout.addWidget(self.txt_reference_path)
        ref_file_layout.addWidget(self.btn_browse_reference)
        reference_layout.addLayout(ref_file_layout)

        # Reference directory path display
        dir_layout = QHBoxLayout()
        self.lbl_ref_dir_title = QLabel("Reference videos directory:")
        self.lbl_ref_dir_path = QLabel("Not set")
        self.lbl_ref_dir_path.setStyleSheet("font-style: italic;")
        dir_layout.addWidget(self.lbl_ref_dir_title)
        dir_layout.addWidget(self.lbl_ref_dir_path)
        dir_layout.addStretch()
        reference_layout.addLayout(dir_layout)

        # Reference details
        self.lbl_reference_details = QLabel("Reference details: None")
        reference_layout.addWidget(self.lbl_reference_details)
        
        # Video preview - arrange side by side with details for larger screens
        preview_area = QHBoxLayout()
        
        # Left side - preview
        preview_layout = QVBoxLayout()
        preview_layout.addWidget(QLabel("Reference Video Preview:"))
        self.video_preview = QLabel()
        self.video_preview.setMinimumSize(480, 270)  # Increased size
        self.video_preview.setMaximumSize(800, 450)  # Increased max size
        self.video_preview.setAlignment(Qt.AlignCenter)
        # Use theme-aware background that adapts to light/dark mode
        self.video_preview.setStyleSheet("background-color: rgba(0, 0, 0, 0.8); color: white; border-radius: 4px;")
        self.video_preview.setText("No video selected")
        preview_layout.addWidget(self.video_preview)
        preview_layout.addStretch()
        
        preview_area.addLayout(preview_layout)
        reference_layout.addLayout(preview_area)

        # Add to group
        reference_group.setLayout(reference_layout)
        layout.addWidget(reference_group)

        # Output settings with improved layout
        output_group = QGroupBox("Output Settings")
        output_layout = QVBoxLayout()

        # Output directory with better layout
        output_dir_layout = QHBoxLayout()
        self.lbl_output_dir_title = QLabel("Output directory:")
        self.txt_output_dir = QLineEdit()
        self.txt_output_dir.setReadOnly(True)
        self.btn_browse_output = QPushButton("Browse...")
        self.btn_browse_output.clicked.connect(self.browse_output_dir)
        output_dir_layout.addWidget(self.lbl_output_dir_title)
        output_dir_layout.addWidget(self.txt_output_dir, 1)  # Give the text field more space
        output_dir_layout.addWidget(self.btn_browse_output)
        output_layout.addLayout(output_dir_layout)

        # Test name with better layout
        test_name_layout = QHBoxLayout()
        test_name_layout.addWidget(QLabel("Test Name:"))
        self.txt_test_name = QLineEdit("Test_01")
        self.txt_test_name.setPlaceholderText("Enter test name...")
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

    def browse_reference_video(self):
        """Browse for a reference video file"""
        # Determine starting directory
        start_dir = ""
        if hasattr(self.parent, 'options_manager') and self.parent.options_manager:
            paths = self.parent.options_manager.get_setting('paths')
            if isinstance(paths, dict):
                start_dir = paths.get('reference_video_dir', '')
            
        if not start_dir or not os.path.exists(start_dir):
            start_dir = os.path.expanduser("~")
            
        # Store reference directory for display
        self.lbl_ref_dir_path.setText(start_dir)
        self.lbl_ref_dir_path.setToolTip(start_dir)
            
        # Show file dialog
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Reference Video",
            start_dir,
            "Video Files (*.mp4 *.mov *.avi *.mkv);;All Files (*.*)"
        )
        
        if file_path and os.path.exists(file_path):
            # Update UI
            self.txt_reference_path.setText(file_path)
            self.txt_reference_path.setToolTip(file_path)
            
            # Update directory display
            ref_dir = os.path.dirname(file_path)
            self.lbl_ref_dir_path.setText(ref_dir)
            self.lbl_ref_dir_path.setToolTip(ref_dir)
            
            # Save the directory to options
            if hasattr(self.parent, 'options_manager') and self.parent.options_manager:
                paths = self.parent.options_manager.get_setting('paths')
                if not isinstance(paths, dict):
                    paths = {}
                paths['reference_video_dir'] = ref_dir
                self.parent.options_manager.update_category('paths', paths)
                
            # Analyze the selected video
            self.analyze_reference(file_path)
            
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
        
        # Load video preview
        self.load_video_preview(info['path'])

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
            self.txt_output_dir.setText(directory)
            self.txt_output_dir.setToolTip(directory)

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

    def load_video_preview(self, video_path):
        """Load and display a preview frame from the video"""
        try:
            import cv2
            from PyQt5.QtGui import QImage, QPixmap
            
            # Open the video file
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                self.video_preview.setText("Error: Could not open video")
                return
                
            # Read the first frame
            ret, frame = cap.read()
            if not ret:
                self.video_preview.setText("Error: Could not read video frame")
                cap.release()
                return
                
            # Get the middle frame for preview
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total_frames > 10:
                # Seek to middle frame
                cap.set(cv2.CAP_PROP_POS_FRAMES, total_frames // 2)
                ret, frame = cap.read()
                if not ret:
                    # Fall back to first frame if middle frame fails
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, frame = cap.read()
            
            # Convert frame to RGB format (OpenCV uses BGR)
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Calculate scaled dimensions to fit the preview area
            h, w, ch = frame_rgb.shape
            preview_w = self.video_preview.width()
            preview_h = self.video_preview.height()
            
            # Calculate aspect ratio-preserving dimensions
            if w/h > preview_w/preview_h:  # Width-limited
                new_w = preview_w
                new_h = int(h * (preview_w / w))
            else:  # Height-limited
                new_h = preview_h
                new_w = int(w * (preview_h / h))
            
            # Resize the frame
            resized = cv2.resize(frame_rgb, (new_w, new_h))
            
            # Convert the resized frame to QImage and then to QPixmap
            bytes_per_line = ch * new_w
            q_img = QImage(resized.data, new_w, new_h, bytes_per_line, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(q_img)
            
            # Set the pixmap to the QLabel
            self.video_preview.setPixmap(pixmap)
            self.video_preview.setAlignment(Qt.AlignCenter)
            
            # Release the video capture
            cap.release()
            
        except Exception as e:
            logger.error(f"Error creating video preview: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            self.video_preview.setText(f"Error loading preview: {str(e)}")
