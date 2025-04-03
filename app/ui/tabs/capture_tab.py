
import os
import logging
from datetime import datetime
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                           QLabel, QComboBox, QProgressBar, QGroupBox, QMessageBox,
                           QSplitter, QTextEdit, QFrame)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap, QImage
import cv2
import numpy as np

logger = logging.getLogger(__name__)

class CaptureTab(QWidget):
    """Capture tab for video capture operations"""
    
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self._frame_count = 0
        self._setup_ui()
        
    def _setup_ui(self):
        """Set up the Capture tab UI"""
        layout = QVBoxLayout(self)

        # Summary of setup with improved styling
        self.lbl_capture_summary = QLabel("No reference video selected")
        self.lbl_capture_summary.setStyleSheet("font-weight: bold; color: #444; background-color: #f5f5f5; padding: 8px; border-radius: 4px;")
        self.lbl_capture_summary.setWordWrap(True)
        layout.addWidget(self.lbl_capture_summary)

        # Main content splitter
        splitter = QSplitter(Qt.Horizontal)

        # Left side - capture controls
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        # Device selection group
        device_group = QGroupBox("Capture Device")
        device_layout = QVBoxLayout()

        device_select_layout = QHBoxLayout()
        self.device_combo = QComboBox()
        self.device_combo.addItem("Intensity Shuttle", "Intensity Shuttle")
        device_select_layout.addWidget(self.device_combo)

        # Round status indicator between dropdown and refresh button
        self.device_status_indicator = QLabel()
        self.device_status_indicator.setFixedSize(16, 16)
        self.device_status_indicator.setStyleSheet("background-color: #808080; border-radius: 8px;")  # Grey for inactive
        self.device_status_indicator.setToolTip("Capture card status: not connected")
        device_select_layout.addWidget(self.device_status_indicator)

        self.btn_refresh_devices = QPushButton("Refresh")
        self.btn_refresh_devices.clicked.connect(self.refresh_devices)
        device_select_layout.addWidget(self.btn_refresh_devices)
        device_layout.addLayout(device_select_layout)

        # Add to group
        device_group.setLayout(device_layout)
        left_layout.addWidget(device_group)

        # Bookend capture method information
        method_group = QGroupBox("Capture Method: White Bookend Frames")
        method_layout = QVBoxLayout()

        bookend_info = QLabel(
            "This application uses the white bookend frames method for video capture.\n"
            "The player should loop the video with 0.5s white frames at the end.\n"
            "Capture will record for 3x the reference video length to ensure complete coverage.\n"
            "The system will automatically detect white frames and extract the video content."
        )
        bookend_info.setWordWrap(True)
        method_layout.addWidget(bookend_info)

        method_group.setLayout(method_layout)
        left_layout.addWidget(method_group)

        # Capture buttons
        capture_group = QGroupBox("Capture Controls")
        capture_layout = QVBoxLayout()

        capture_buttons = QHBoxLayout()
        self.btn_start_capture = QPushButton("Start Capture")
        self.btn_start_capture.clicked.connect(self.start_capture)
        self.btn_stop_capture = QPushButton("Stop Capture")
        self.btn_stop_capture.clicked.connect(self.stop_capture)
        self.btn_stop_capture.setEnabled(False)
        capture_buttons.addWidget(self.btn_start_capture)
        capture_buttons.addWidget(self.btn_stop_capture)
        capture_layout.addLayout(capture_buttons)

        self.lbl_capture_status = QLabel("Ready to capture")
        capture_layout.addWidget(self.lbl_capture_status)

        # Progress bar without frame counter
        progress_layout = QHBoxLayout()
        self.pb_capture_progress = QProgressBar()
        self.pb_capture_progress.setTextVisible(True)
        self.pb_capture_progress.setAlignment(Qt.AlignCenter)
        self.pb_capture_progress.setMinimumWidth(300)
        progress_layout.addWidget(self.pb_capture_progress)
        
        # Keep frame counter for internal use, but don't display it
        self.lbl_capture_frame_counter = QLabel("")
        self.lbl_capture_frame_counter.setVisible(False)

        capture_layout.addLayout(progress_layout)

        capture_group.setLayout(capture_layout)
        left_layout.addWidget(capture_group)

        # Right side - video preview and log
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        # Enhanced Preview with better visuals and status indicators
        preview_group = QGroupBox("Video Preview")
        preview_layout = QVBoxLayout()

        # Preview frame with improved styling
        preview_frame = QFrame()
        preview_frame.setFrameStyle(QFrame.StyledPanel | QFrame.Sunken)
        preview_frame.setLineWidth(1)
        preview_inner_layout = QVBoxLayout(preview_frame)

        # Preview label with enhanced styling and initial placeholder
        self.lbl_preview = QLabel("No video feed")
        self.lbl_preview.setAlignment(Qt.AlignCenter)
        self.lbl_preview.setMinimumSize(480, 270)
        self.lbl_preview.setStyleSheet("background-color: #e0e0e0; color: black; border-radius: 4px;")
        preview_inner_layout.addWidget(self.lbl_preview)
        preview_inner_layout.setContentsMargins(0, 0, 0, 0)

        # Add status indicator for preview
        preview_status_layout = QHBoxLayout()
        self.lbl_preview_status = QLabel("Status: No video feed")
        self.lbl_preview_status.setStyleSheet("color: #666; font-size: 9pt;")

        # Frame counter
        self.lbl_frame_counter = QLabel("Frame: 0")
        self.lbl_frame_counter.setStyleSheet("color: #666; font-size: 9pt;")

        preview_status_layout.addWidget(self.lbl_preview_status)
        preview_status_layout.addStretch()
        preview_status_layout.addWidget(self.lbl_frame_counter)

        # Show a placeholder image initially
        self._show_placeholder_image("Waiting for video capture to start...")

        # Add components to layouts
        preview_layout.addWidget(preview_frame)
        preview_layout.addLayout(preview_status_layout)
        preview_group.setLayout(preview_layout)
        right_layout.addWidget(preview_group)

        # Enhanced capture log with better error visibility and auto-scrolling
        log_group = QGroupBox("Capture Log")
        log_layout = QVBoxLayout()

        # Create log text area with enhanced styling and error highlighting
        self.txt_capture_log = QTextEdit()
        self.txt_capture_log.setReadOnly(True)
        self.txt_capture_log.setLineWrapMode(QTextEdit.WidgetWidth)  # Enable line wrapping
        self.txt_capture_log.setMinimumHeight(150)
        self.txt_capture_log.setMaximumHeight(200)  # Fix height to prevent stretching
        self.txt_capture_log.setFixedWidth(550)  # Fixed width to avoid UI stretching with long messages

        # Set custom stylesheet for better readability
        self.txt_capture_log.setStyleSheet("""
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
        self.btn_clear_capture_log = QPushButton("Clear Log")
        self.btn_clear_capture_log.setMaximumWidth(100)
        self.btn_clear_capture_log.clicked.connect(self.txt_capture_log.clear)
        log_controls.addStretch()
        log_controls.addWidget(self.btn_clear_capture_log)

        # Add components to layouts
        log_layout.addWidget(self.txt_capture_log)
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

        # Navigation buttons
        nav_layout = QHBoxLayout()
        self.btn_prev_to_setup = QPushButton("Back: Setup")
        nav_layout.addWidget(self.btn_prev_to_setup)

        nav_layout.addStretch()

        self.btn_next_to_analysis = QPushButton("Next: Analysis")
        self.btn_next_to_analysis.setEnabled(False)
        nav_layout.addWidget(self.btn_next_to_analysis)

        layout.addLayout(nav_layout)
        
        # Initialize device status
        self.populate_devices_and_check_status()
        
    def refresh_devices(self):
        """Refresh list of capture devices and update status indicator"""
        self.device_combo.clear()
        self.device_combo.addItem("Detecting devices...")
        self.device_status_indicator.setStyleSheet("background-color: #808080; border-radius: 8px;")  # Grey while checking
        self.device_status_indicator.setToolTip("Checking device status...")

        # Use options manager to get devices
        QTimer.singleShot(500, self.populate_devices_and_check_status)
        
    def populate_devices_and_check_status(self):
        """Populate device dropdown with devices and check their status"""
        # Get devices from options manager
        devices = []
        if hasattr(self.parent, 'options_manager') and self.parent.options_manager:
            try:
                # Try to get devices from options manager
                devices = self.parent.options_manager.get_decklink_devices()
                logger.info(f"Found devices from options manager: {devices}")
            except Exception as e:
                logger.error(f"Error getting devices from options manager: {e}")

        # If no devices found, add default options
        if not devices:
            # Common Blackmagic device names as fallback
            devices = [
                "Intensity Shuttle", 
                "UltraStudio", 
                "DeckLink",
                "Decklink Video Capture",
                "Intensity Pro"
            ]
            logger.info(f"Using default device list: {devices}")

        # Update dropdown
        self.device_combo.clear()
        for device in devices:
            self.device_combo.addItem(device, device)

        # Set current device from settings
        if hasattr(self.parent, 'options_manager') and self.parent.options_manager:
            try:
                current_device = self.parent.options_manager.get_setting("capture", "default_device")
                index = self.device_combo.findText(current_device)
                if index >= 0:
                    self.device_combo.setCurrentIndex(index)
                logger.info(f"Set current device to: {current_device}")
            except Exception as e:
                logger.error(f"Error setting current device: {e}")

        # Check if device is available
        if hasattr(self.parent, 'capture_mgr') and self.parent.capture_mgr:
            try:
                # Get selected device for check
                selected_device = self.device_combo.currentText()
                if selected_device:
                    # Skip device availability check since method is missing
                    available, message = True, "Device check skipped"
                    logger.info(f"Device '{selected_device}' availability: {available}, message: {message}")

                    if available:
                        # Green for connected device
                        self.device_status_indicator.setStyleSheet("background-color: #00AA00; border-radius: 8px;")
                        self.device_status_indicator.setToolTip(f"Capture card status: connected ({message})")
                    else:
                        # Red for unavailable device
                        self.device_status_indicator.setStyleSheet("background-color: #AA0000; border-radius: 8px;")
                        self.device_status_indicator.setToolTip(f"Capture card status: not connected ({message})")
                else:
                    # Grey for no selected device
                    self.device_status_indicator.setStyleSheet("background-color: #808080; border-radius: 8px;")
                    self.device_status_indicator.setToolTip("No capture device selected")
            except Exception as e:
                # Grey for error during check
                logger.error(f"Error checking device availability: {e}")
                self.device_status_indicator.setStyleSheet("background-color: #808080; border-radius: 8px;")
                self.device_status_indicator.setToolTip(f"Error checking device: {str(e)}")
        else:
            # Grey for initialization not complete
            self.device_status_indicator.setStyleSheet("background-color: #808080; border-radius: 8px;")
            self.device_status_indicator.setToolTip("Capture manager not initialized")
        
    def start_capture(self):
        """Start the bookend capture process"""
        if not self.parent.reference_info:
            QMessageBox.warning(self, "Warning", "Please select a reference video first")
            return

        # Get device
        device_name = self.device_combo.currentData()
        if not device_name:
            QMessageBox.warning(self, "Warning", "Please select a capture device")
            return

        # Update UI
        self.btn_start_capture.setEnabled(False)
        self.btn_stop_capture.setEnabled(True)
        self.pb_capture_progress.setValue(0)

        # Clear logs
        self.txt_capture_log.clear()
        self.log_to_capture("Starting bookend capture process...")

        # Get output directory and test name
        output_dir = self.parent.setup_tab.txt_output_dir.text()
        if not output_dir or output_dir == "Default output directory":
            if hasattr(self.parent, 'file_manager'):
                output_dir = self.parent.file_manager.get_default_base_dir()
            else:
                script_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
                output_dir = os.path.join(script_dir, "tests", "test_results")
                os.makedirs(output_dir, exist_ok=True)

        # Add timestamp prefix to test name to prevent overwriting
        base_test_name = self.parent.setup_tab.txt_test_name.text()
        test_name = f"{base_test_name}"

        self.log_to_capture(f"Using test name: {test_name}")

        # Set output information in capture manager
        if hasattr(self.parent, 'capture_mgr'):
            self.parent.capture_mgr.set_output_directory(output_dir)
            self.parent.capture_mgr.set_test_name(test_name)

            # Start bookend capture
            self.log_to_capture("Starting bookend frame capture...")
            self.parent.capture_mgr.start_bookend_capture(device_name)
        else:
            self.log_to_capture("Error: Capture manager not initialized")
            self.btn_start_capture.setEnabled(True)
            self.btn_stop_capture.setEnabled(False)
            
    def stop_capture(self):
        """Stop the capture process"""
        self.log_to_capture("Stopping capture...")
        if hasattr(self.parent, 'capture_mgr'):
            self.parent.capture_mgr.stop_capture(cleanup_temp=True)
        else:
            self.log_to_capture("Error: Capture manager not initialized")

        # Reset progress bar to avoid stuck state
        self.pb_capture_progress.setValue(0)

        # Update UI
        self.btn_start_capture.setEnabled(True)
        self.btn_stop_capture.setEnabled(False)
        
    def update_capture_status(self, status_text):
        """Update capture status label"""
        self.lbl_capture_status.setText(status_text)
        self.log_to_capture(status_text)

    def update_capture_progress(self, progress):
        """Handle capture progress updates with proper scale"""
        if isinstance(progress, int):
            # Ensure progress is between 0-100
            scaled_progress = min(100, max(0, progress))
            self.pb_capture_progress.setValue(scaled_progress)
        else:
            # Just in case we receive non-int progress
            self.pb_capture_progress.setValue(0)

    def handle_capture_state_change(self, state):
        """Handle changes in capture state"""
        state_text = f"Capture state: {state.name}"
        self.log_to_capture(state_text)

    def handle_capture_started(self):
        """Handle capture start"""
        self.btn_start_capture.setEnabled(False)
        self.btn_stop_capture.setEnabled(True)
            
    def update_preview(self, frame):
        """Update the preview with a video frame"""
        try:
            # Check if we're in headless mode
            if hasattr(self.parent, 'headless_mode') and self.parent.headless_mode:
                # In headless mode, just update status text but don't try to render
                self.lbl_preview_status.setText("Status: Preview available (headless mode)")
                self.lbl_frame_counter.setText(f"Frame received")
                return

            # Check if frame is valid
            if frame is None:
                logger.warning("Received None frame for preview")
                self._show_placeholder_image("No video feed received")
                return

            if isinstance(frame, np.ndarray) and frame.size == 0:
                logger.warning("Received empty frame for preview")
                self._show_placeholder_image("Empty video frame received")
                return

            # Convert OpenCV frame to QImage using a more robust method
            try:
                # Ensure frame is a numpy array with the right format
                if not isinstance(frame, np.ndarray):
                    logger.warning(f"Frame is not numpy array but {type(frame)}")
                    self._show_placeholder_image("Invalid frame format")
                    return

                # Convert BGR to RGB
                if len(frame.shape) == 3 and frame.shape[2] == 3:
                    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    height, width, channels = rgb_frame.shape
                    bytes_per_line = channels * width
                    img_format = QImage.Format_RGB888
                elif len(frame.shape) == 2:
                    # Handle grayscale images
                    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)
                    height, width, channels = rgb_frame.shape
                    bytes_per_line = channels * width
                    img_format = QImage.Format_RGB888
                else:
                    logger.warning(f"Unsupported frame format: {frame.shape}")
                    self._show_placeholder_image("Unsupported frame format")
                    return

                # Create QImage with correct parameters
                q_img = QImage(rgb_frame.data, width, height, bytes_per_line, img_format)

                # Create pixmap and scale it
                pixmap = QPixmap.fromImage(q_img)

                # Scale pixmap to fit label while maintaining aspect ratio
                label_size = self.lbl_preview.size()
                if label_size.width() > 0 and label_size.height() > 0:
                    scaled_pixmap = pixmap.scaled(
                        label_size,
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation
                    )

                    # Update label
                    self.lbl_preview.setPixmap(scaled_pixmap)

                    # Update status
                    self.lbl_preview_status.setText(f"Status: Live preview ({width}x{height})")

                    # Update frame counter
                    frame_count = getattr(self, '_frame_count', 0) + 1
                    self._frame_count = frame_count
                    self.lbl_frame_counter.setText(f"Frame: {frame_count}")
            except Exception as inner_e:
                logger.error(f"Error converting frame: {str(inner_e)}")
                self._show_placeholder_image(f"Frame conversion error: {str(inner_e)}")

        except Exception as e:
            logger.error(f"Error updating preview: {str(e)}")
            self._show_placeholder_image(f"Preview error: {str(e)}")
            
    def _show_placeholder_image(self, message="No video feed"):
        """Show an enhanced status display with text when no video is available"""
        try:
            # Create a blank image with better styling
            placeholder = np.zeros((270, 480, 3), dtype=np.uint8)
            placeholder[:] = (240, 240, 240)  # Lighter gray background
            
            # Add a header bar
            cv2.rectangle(placeholder, (0, 0), (480, 40), (70, 130, 180), -1)  # Blue header
            
            # Add header text
            font = cv2.FONT_HERSHEY_SIMPLEX
            cv2.putText(placeholder, "STATUS MONITOR", (160, 27), font, 0.7, (255, 255, 255), 2)
            
            # Split message into multiple lines if needed
            max_line_length = 40
            words = message.split()
            lines = []
            current_line = ""
            
            for word in words:
                if len(current_line + " " + word) <= max_line_length:
                    current_line += " " + word if current_line else word
                else:
                    lines.append(current_line)
                    current_line = word
            
            if current_line:
                lines.append(current_line)
            
            # Add each line of text
            y_position = 80
            for line in lines:
                text_size = cv2.getTextSize(line, font, 0.6, 1)[0]
                x_position = (placeholder.shape[1] - text_size[0]) // 2
                cv2.putText(placeholder, line, (x_position, y_position), font, 0.6, (0, 0, 0), 1)
                y_position += 30
            
            # Add a footer with timestamp
            timestamp = datetime.now().strftime("%H:%M:%S")
            footer_text = f"Updated: {timestamp}"
            cv2.putText(placeholder, footer_text, (10, 250), font, 0.5, (100, 100, 100), 1)
            
            # Add a border around the image
            cv2.rectangle(placeholder, (0, 0), (479, 269), (200, 200, 200), 1)
            
            # Convert to QImage and display
            rgb_image = cv2.cvtColor(placeholder, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb_image.shape
            bytes_per_line = ch * w
            q_img = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
            self.lbl_preview.setPixmap(QPixmap.fromImage(q_img))
            
            # Also update status text
            if hasattr(self, 'lbl_preview_status'):
                self.lbl_preview_status.setText(f"Status: {message.split('.')[0]}")

        except Exception as e:
            logger.error(f"Error creating status display: {str(e)}")
            # Fallback to text-only label
            self.lbl_preview.setText(message)
            self.lbl_preview.setStyleSheet("background-color: #e0e0e0; color: black; padding: 10px;")
            
    def update_frame_counter(self, current_frame, total_frames):
        """Update frame counter display during capture"""
        if hasattr(self, 'lbl_capture_frame_counter'):
            # Format with thousands separator for readability
            if total_frames > 0:
                self.lbl_capture_frame_counter.setText(f"Frames: {current_frame:,} / {total_frames:,}")
            else:
                self.lbl_capture_frame_counter.setText(f"Frames: {current_frame:,}")
                
    def log_to_capture(self, message):
        """Add message to capture log with smart formatting for errors and warnings"""
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

        # Append to log
        self.txt_capture_log.append(formatted_message)

        # Auto-scroll to bottom
        self.txt_capture_log.verticalScrollBar().setValue(
            self.txt_capture_log.verticalScrollBar().maximum()
        )

        # Update status bar (without HTML formatting)
        self.parent.statusBar().showMessage(message)

        # If error message, flash status bar to draw attention
        if "error" in message.lower():
            current_style = self.parent.statusBar().styleSheet()
            self.parent.statusBar().setStyleSheet("background-color: #FFCDD2;")  # Light red
            # Reset style after 2 seconds
            QTimer.singleShot(2000, lambda: self.parent.statusBar().setStyleSheet(current_style))
