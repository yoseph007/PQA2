
import os
import logging
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                            QLabel, QComboBox, QGroupBox, QFileDialog, QMessageBox,
                            QLineEdit, QSplitter, QFrame, QTextEdit)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QImage, QPixmap
import threading
from datetime import datetime

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

        # Summary header with improved styling
        self.lbl_setup_summary = QLabel("Select a reference video to begin")
        self.lbl_setup_summary.setStyleSheet("font-weight: bold; color: #444; background-color: #f5f5f5; padding: 8px; border-radius: 4px;")
        self.lbl_setup_summary.setWordWrap(True)
        layout.addWidget(self.lbl_setup_summary)

        # Main content splitter
        splitter = QSplitter(Qt.Horizontal)

        # Left side - reference and output settings
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

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

        # Add to group
        reference_group.setLayout(reference_layout)
        left_layout.addWidget(reference_group)

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
        left_layout.addWidget(output_group)

        # Add instructions group
        instructions_group = QGroupBox("Instructions")
        instructions_layout = QVBoxLayout()
        
        instructions_text = QLabel(
            "1. Select a reference video file using the Browse button above.\n"
            "2. The application will analyze the video and extract metadata.\n"
            "3. Set an output directory for test results (optional).\n"
            "4. Provide a descriptive test name.\n"
            "5. Once reference video is loaded, click 'Next: Capture' to continue."
        )
        instructions_text.setWordWrap(True)
        instructions_layout.addWidget(instructions_text)
        
        instructions_group.setLayout(instructions_layout)
        left_layout.addWidget(instructions_group)

        # Add stretch to push everything up
        left_layout.addStretch()

        # Right side - video preview and status log
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        # Video preview group
        preview_group = QGroupBox("Reference Video Preview")
        preview_layout = QVBoxLayout()

        # Preview frame with improved styling
        preview_frame = QFrame()
        preview_frame.setFrameStyle(QFrame.StyledPanel | QFrame.Sunken)
        preview_frame.setLineWidth(1)
        preview_inner_layout = QVBoxLayout(preview_frame)

        # Preview label with enhanced styling and initial placeholder
        self.video_preview = QLabel("No video selected")
        self.video_preview.setAlignment(Qt.AlignCenter)
        self.video_preview.setMinimumSize(480, 270)
        self.video_preview.setMaximumSize(800, 450)
        self.video_preview.setStyleSheet("background-color: #e0e0e0; color: black; border-radius: 4px;")
        preview_inner_layout.addWidget(self.video_preview)
        preview_inner_layout.setContentsMargins(0, 0, 0, 0)

        # Add status indicator for preview
        preview_status_layout = QHBoxLayout()
        self.lbl_preview_status = QLabel("Status: No video selected")
        self.lbl_preview_status.setStyleSheet("color: #666; font-size: 9pt;")
        preview_status_layout.addWidget(self.lbl_preview_status)
        preview_status_layout.addStretch()

        # Add components to layouts
        preview_layout.addWidget(preview_frame)
        preview_layout.addLayout(preview_status_layout)
        preview_group.setLayout(preview_layout)
        right_layout.addWidget(preview_group)

        # Setup log with enhanced styling
        log_group = QGroupBox("Setup Log")
        log_layout = QVBoxLayout()

        # Create log text area with enhanced styling
        self.txt_setup_log = QTextEdit()
        self.txt_setup_log.setReadOnly(True)
        self.txt_setup_log.setLineWrapMode(QTextEdit.WidgetWidth)
        self.txt_setup_log.setMinimumHeight(150)
        self.txt_setup_log.setMaximumHeight(200)
        self.txt_setup_log.setFixedWidth(550)

        # Set custom stylesheet for better readability
        self.txt_setup_log.setStyleSheet("""
            QTextEdit {
                background-color: #f8f8f8;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 10pt;
                padding: 4px;
                border: 1px solid #ddd;
            }
        """)

        # Add clear log button
        log_controls = QHBoxLayout()
        self.btn_clear_setup_log = QPushButton("Clear Log")
        self.btn_clear_setup_log.setMaximumWidth(100)
        self.btn_clear_setup_log.clicked.connect(self.txt_setup_log.clear)
        log_controls.addStretch()
        log_controls.addWidget(self.btn_clear_setup_log)

        # Add components to layouts
        log_layout.addWidget(self.txt_setup_log)
        log_layout.addLayout(log_controls)
        log_group.setLayout(log_layout)
        right_layout.addWidget(log_group)

        # Add widgets to splitter with 50/50 split
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([500, 500])  # 50/50 split
        
        # Set a minimum width for both panes to prevent unwanted resizing
        left_widget.setMinimumWidth(400)
        right_widget.setMinimumWidth(400)

        # Add splitter to layout
        layout.addWidget(splitter)

        # Setup status and navigation buttons
        nav_layout = QHBoxLayout()

        nav_layout.addStretch()
        
        self.btn_next_to_capture = QPushButton("Next: Capture")
        self.btn_next_to_capture.setEnabled(False)
        nav_layout.addWidget(self.btn_next_to_capture)
        
        layout.addLayout(nav_layout)

        # Initialize with welcome message
        self.log_to_setup("Welcome to VMAF Test App. Please select a reference video to continue.")

    def browse_reference_video(self):
        """Browse for a reference video file"""
        # Determine starting directory
        start_dir = ""
        if hasattr(self.parent, 'options_manager') and self.parent.options_manager:
            paths = self.parent.options_manager.get_setting('paths')
            if isinstance(paths, dict) and 'reference_video_dir' in paths:
                start_dir = paths['reference_video_dir']

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
        self.log_to_setup("Reference video loaded successfully")
        self.lbl_setup_summary.setText(f"Reference: {os.path.basename(info['path'])} - {details}")

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
        default_dir = self.parent.file_mgr.get_default_base_dir() if hasattr(self.parent, 'file_mgr') else None

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

            if hasattr(self.parent, 'file_mgr'):
                self.parent.file_mgr.base_dir = directory

            if hasattr(self.parent, 'capture_mgr'):
                self.parent.capture_mgr.set_output_directory(directory)

            self.log_to_setup(f"Output directory set to: {directory}")

    def log_to_setup(self, message):
        """Add message to setup log with formatting for different message types"""
        # Apply HTML formatting for different message types
        formatted_message = message
        timestamp = datetime.now().strftime("%H:%M:%S")

        # Format errors in red
        if "error" in message.lower() or "failed" in message.lower() or "exception" in message.lower():
            formatted_message = f'<span style="color: #D32F2F; font-weight: bold;">[{timestamp}] {message}</span>'
        # Format warnings in orange
        elif "warning" in message.lower() or "caution" in message.lower():
            formatted_message = f'<span style="color: #FF9800;">[{timestamp}] {message}</span>'
        # Format success messages in green
        elif "success" in message.lower() or "complete" in message.lower() or "finished" in message.lower():
            formatted_message = f'<span style="color: #388E3C; font-weight: bold;">[{timestamp}] {message}</span>'
        # Regular messages with timestamp
        else:
            formatted_message = f'[{timestamp}] {message}'

        # Append to log if the text edit exists
        if hasattr(self, 'txt_setup_log') and self.txt_setup_log:
            self.txt_setup_log.append(formatted_message)
            
            # Auto-scroll to bottom
            self.txt_setup_log.verticalScrollBar().setValue(
                self.txt_setup_log.verticalScrollBar().maximum()
            )

        # Also update status label
        self.lbl_preview_status.setText(f"Status: {message.split('.')[0]}")
        
        # Update main window status bar
        self.parent.statusBar().showMessage(message)

        # If error message, flash status bar to draw attention
        if "error" in message.lower():
            current_style = self.parent.statusBar().styleSheet()
            self.parent.statusBar().setStyleSheet("background-color: #FFCDD2;")  # Light red
            # Reset style after 2 seconds
            QTimer.singleShot(2000, lambda: self.parent.statusBar().setStyleSheet(current_style))

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
                self.log_to_setup("Error: Could not open video file")
                return

            # Read the first frame
            ret, frame = cap.read()
            if not ret:
                self.video_preview.setText("Error: Could not read video frame")
                self.log_to_setup("Error: Could not read video frame")
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
            
            # Update preview status
            fps = cap.get(cv2.CAP_PROP_FPS)
            self.lbl_preview_status.setText(f"Status: Preview loaded ({w}x{h}, {fps:.2f}fps)")

            # Release the video capture
            cap.release()
            
            self.log_to_setup(f"Preview frame loaded from frame {total_frames//2} of {total_frames}")

        except Exception as e:
            logger.error(f"Error creating video preview: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            self.video_preview.setText(f"Error loading preview: {str(e)}")
            self.log_to_setup(f"Error creating video preview: {str(e)}")
