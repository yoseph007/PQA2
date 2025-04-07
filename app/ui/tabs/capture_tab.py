import logging
import os
from datetime import datetime

import cv2
import numpy as np
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (QComboBox, QFrame, QGroupBox, QHBoxLayout, QLabel,
                             QMessageBox, QProgressBar, QPushButton, QSplitter,
                             QTextEdit, QVBoxLayout, QWidget)

logger = logging.getLogger(__name__)

class CaptureTab(QWidget):
    """Capture tab for video capture operations"""

    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self._frame_count = 0
        self._setup_ui()

    def _setup_ui(self):
        """Set up the Capture tab UI with scroll area"""
        from PyQt5.QtWidgets import QScrollArea

        # Create a scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # Create a widget to hold all content
        scroll_content = QWidget()
        scroll_area.setWidget(scroll_content)

        # Create main layout for the content
        layout = QVBoxLayout(scroll_content)

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

        # Show the reference video preview initially
        self._show_reference_preview()

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

        # Set the scroll area as the main widget
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(scroll_area)

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



    def _ensure_signals_connected(self):
        """Ensure all required signals are connected properly"""
        if not hasattr(self, '_signals_connected') or not self._signals_connected:
            if hasattr(self.parent, 'capture_mgr'):
                # Connect status signals
                self.parent.capture_mgr.status_update.connect(self.update_capture_status)
                self.parent.capture_mgr.progress_update.connect(self.update_capture_progress)
                self.parent.capture_mgr.state_changed.connect(self.handle_capture_state_change)
                
                # Connect process signals
                self.parent.capture_mgr.capture_started.connect(self.handle_capture_started)
                self.parent.capture_mgr.capture_finished.connect(self.handle_capture_finished)
                self.parent.capture_mgr.frame_available.connect(self.update_preview)
                
                # Mark signals as connected
                self._signals_connected = True
                logger.info("Connected capture manager signals")

    def _get_output_directory(self):
        """Get appropriate output directory for captures"""
        # First try to use FileManager
        if hasattr(self.parent, 'file_manager') and self.parent.file_manager:
            return self.parent.file_manager.get_default_base_dir()
        
        # Then try to get from options
        if hasattr(self.parent, 'options_manager') and self.parent.options_manager:
            output_dir = self.parent.options_manager.get_setting("paths", "default_output_dir")
            if output_dir and os.path.exists(output_dir):
                return output_dir
        
        # Fall back to reference video directory
        if hasattr(self.parent, 'reference_info') and self.parent.reference_info:
            return os.path.dirname(self.parent.reference_info.get('path', ''))
        
        # Last resort - use home directory
        return os.path.expanduser("~")

    def _get_test_name(self):
        """Get appropriate test name for captures"""
        # Generate default based on timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"test_{timestamp}"
        
        # Try to get name from setup tab if available
        if hasattr(self.parent, 'setup_tab'):
            for attr_name in ['test_name', 'txt_test_name', 'test_name_field']:
                if hasattr(self.parent.setup_tab, attr_name):
                    field = getattr(self.parent.setup_tab, attr_name)
                    if hasattr(field, 'text'):
                        test_name_value = field.text()
                        if test_name_value:
                            return test_name_value
        
        return default_name

    def _show_capturing_preview(self):
        """Show a placeholder preview while starting capture"""
        try:
            # Create a placeholder image
            placeholder = np.zeros((270, 480, 3), dtype=np.uint8)
            placeholder[:] = (50, 50, 50)  # Dark gray background
            
            # Add a pulsating red recording indicator
            cv2.circle(placeholder, (30, 30), 15, (0, 0, 180), -1)
            
            # Add text
            cv2.putText(placeholder, "STARTING CAPTURE...", (80, 40), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)
            
            # Add reference video info
            if hasattr(self.parent, 'reference_info') and self.parent.reference_info:
                ref_info = self.parent.reference_info
                ref_name = os.path.basename(ref_info.get('path', 'Unknown'))
                cv2.putText(placeholder, f"Reference: {ref_name}", (30, 80), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
                
                # Add resolution and duration
                resolution = f"{ref_info.get('width', 0)}x{ref_info.get('height', 0)}"
                duration = ref_info.get('duration', 0)
                cv2.putText(placeholder, f"Resolution: {resolution}, Duration: {duration:.1f}s", (30, 110), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
            
            # Add device info
            device = self.device_combo.currentText()
            cv2.putText(placeholder, f"Device: {device}", (30, 140), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
            
            # Add a progress bar
            cv2.rectangle(placeholder, (30, 200), (450, 220), (50, 50, 100), -1)  # Background
            cv2.rectangle(placeholder, (30, 200), (80, 220), (0, 120, 255), -1)   # Progress (10%)
            cv2.putText(placeholder, "Initializing...", (200, 215), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            # Emit the frame to the preview
            self.update_preview(placeholder)
        except Exception as e:
            logger.error(f"Error creating capturing preview: {e}")

    def handle_capture_finished(self, success, output_path):
        """Handle capture completion with better UI feedback"""
        # Update UI
        self.btn_start_capture.setEnabled(True)
        self.btn_stop_capture.setEnabled(False)
        
        if success:
            # Show success message with output path
            self.log_to_capture(f"Capture completed successfully")
            self.log_to_capture(f"Output file: {output_path}")
            
            # Update progress to 100%
            self.pb_capture_progress.setValue(100)
            
            # Enable analysis button if it exists
            if hasattr(self, 'btn_next_to_analysis'):
                self.btn_next_to_analysis.setEnabled(True)
                
            # Show a completion frame
            try:
                # Try to grab a frame from the output file for preview
                if os.path.exists(output_path):
                    cap = cv2.VideoCapture(output_path)
                    if cap.isOpened():
                        # Skip to middle frame
                        frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                        cap.set(cv2.CAP_PROP_POS_FRAMES, frames // 2)
                        
                        # Read frame
                        ret, frame = cap.read()
                        if ret:
                            # Add completion overlay
                            height, width = frame.shape[:2]
                            cv2.rectangle(frame, (0, 0), (width, 30), (0, 150, 0), -1)
                            cv2.putText(frame, "CAPTURE COMPLETE", (width//2 - 80, 20), 
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                            
                            # Update preview
                            self.update_preview(frame)
                        
                        # Clean up
                        cap.release()
            except Exception as e:
                logger.error(f"Error showing completion frame: {e}")
        else:
            # Show error message
            self.log_to_capture(f"Capture failed: {output_path}")
            
            # Reset progress
            self.pb_capture_progress.setValue(0)
            
            # Show error frame
            try:
                placeholder = np.zeros((270, 480, 3), dtype=np.uint8)
                placeholder[:] = (50, 50, 70)  # Dark blue-gray background
                
                # Add red error banner
                cv2.rectangle(placeholder, (0, 0), (480, 40), (0, 0, 150), -1)
                cv2.putText(placeholder, "CAPTURE FAILED", (150, 30), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
                
                # Add error message (truncate if too long)
                error_msg = output_path
                if len(error_msg) > 60:
                    error_msg = error_msg[:57] + "..."
                
                lines = self._wrap_text(error_msg, 60)  # Wrap text to avoid overflow
                y_pos = 80
                for line in lines:
                    cv2.putText(placeholder, line, (30, y_pos), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
                    y_pos += 25
                
                # Update preview
                self.update_preview(placeholder)
            except Exception as e:
                logger.error(f"Error showing error frame: {e}")

    def _wrap_text(self, text, max_width):
        """Helper to wrap text to multiple lines for CV2 text rendering"""
        words = text.split()
        lines = []
        current_line = ""
        
        for word in words:
            test_line = current_line + " " + word if current_line else word
            if len(test_line) <= max_width:
                current_line = test_line
            else:
                lines.append(current_line)
                current_line = word
                
        if current_line:
            lines.append(current_line)
            
        return lines

    def update_preview(self, frame):
        """Update the preview with a video frame with better error handling"""
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

                    # Update status based on capture state
                    if hasattr(self.parent, 'capture_mgr') and self.parent.capture_mgr.is_capturing:
                        self.lbl_preview_status.setText(f"Status: Capture in progress")
                    else:
                        self.lbl_preview_status.setText(f"Status: Preview active")

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

    def stop_capture(self):
        """Stop the capture process with better error handling"""
        try:
            self.log_to_capture("Stopping capture...")
            
            if hasattr(self.parent, 'capture_mgr'):
                # Show stopping message in preview
                try:
                    placeholder = np.zeros((270, 480, 3), dtype=np.uint8)
                    placeholder[:] = (70, 70, 70)  # Gray background
                    
                    # Add stopping indication
                    cv2.rectangle(placeholder, (0, 0), (480, 40), (150, 70, 0), -1)  # Orange header
                    cv2.putText(placeholder, "STOPPING CAPTURE...", (130, 30), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                    
                    # Add message
                    cv2.putText(placeholder, "Please wait while the capture is stopped", (40, 100), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
                    cv2.putText(placeholder, "and resources are released...", (100, 130), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
                    
                    # Add spinner-like effect
                    current_time = time.time()
                    angle = int(current_time * 4) % 8
                    positions = [(240, 200), (260, 180), (280, 200), (260, 220)]
                    position = positions[angle % 4]
                    cv2.circle(placeholder, position, 10, (0, 150, 255), -1)
                    
                    # Update preview
                    self.update_preview(placeholder)
                except Exception as e:
                    logger.error(f"Error showing stopping preview: {e}")
                
                # Perform actual stop
                self.parent.capture_mgr.stop_capture(cleanup_temp=True)
            else:
                self.log_to_capture("Error: Capture manager not initialized")

            # Reset progress bar to avoid stuck state
            self.pb_capture_progress.setValue(0)

            # Update UI
            self.btn_start_capture.setEnabled(True)
            self.btn_stop_capture.setEnabled(False)
            
            # Show stopped preview
            try:
                placeholder = np.zeros((270, 480, 3), dtype=np.uint8)
                placeholder[:] = (80, 80, 80)  # Gray background
                
                # Add header
                cv2.rectangle(placeholder, (0, 0), (480, 40), (120, 20, 20), -1)  # Red header
                cv2.putText(placeholder, "CAPTURE STOPPED", (150, 30), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                
                # Add message
                cv2.putText(placeholder, "Capture was stopped by user", (120, 120), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 1)
                cv2.putText(placeholder, "Click Start Capture to begin a new capture", (70, 180), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
                
                # Update preview
                self.update_preview(placeholder)
            except Exception as e:
                logger.error(f"Error showing stopped preview: {e}")
            
        except Exception as e:
            logger.error(f"Error stopping capture: {e}")
            self.log_to_capture(f"Error stopping capture: {e}")
            
            # Make sure UI is reset
            self.btn_start_capture.setEnabled(True)
            self.btn_stop_capture.setEnabled(False)




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
        if hasattr(self.parent, 'options_manager') and self.parent.options_manager:
            try:
                # Get selected device for check
                selected_device = self.device_combo.currentText()
                if selected_device:
                    # Try to use test_device_connection method if available
                    if hasattr(self.parent.options_manager, 'test_device_connection'):
                        available, message = self.parent.options_manager.test_device_connection(selected_device)
                    else:
                        # If method not available, assume device is available
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
        """Start the bookend capture process with improved error handling and UI feedback"""
        if not self.parent.reference_info:
            QMessageBox.warning(self, "Warning", "Please select a reference video first")
            return

        # Get device and validate
        device_name = self.device_combo.currentData()
        if not device_name:
            QMessageBox.warning(self, "Warning", "Please select a capture device")
            return

        # Update UI for capture in progress
        self.btn_start_capture.setEnabled(False)
        self.btn_stop_capture.setEnabled(True)
        self.pb_capture_progress.setValue(0)

        # Clear logs and show start message
        self.txt_capture_log.clear()
        self.log_to_capture("Starting bookend capture process...")

        # Get output directory using app's methods
        output_dir = self._get_output_directory()
        
        # Get test name - use a timestamp if not available
        test_name = self._get_test_name()

        self.log_to_capture(f"Using test name: {test_name}")
        self.log_to_capture(f"Output directory: {output_dir}")

        # Set output information in capture manager
        if hasattr(self.parent, 'capture_mgr'):
            # Save selected device to options_manager before starting capture
            if hasattr(self.parent, 'options_manager') and self.parent.options_manager:
                self.parent.options_manager.update_setting("capture", "default_device", device_name)
            
            # Set capture settings        
            self.parent.capture_mgr.set_output_directory(output_dir)
            self.parent.capture_mgr.set_test_name(test_name)

            # Connect signals if not already connected
            self._ensure_signals_connected()

            # Start bookend capture
            self.log_to_capture("Starting bookend frame capture...")
            
            # Show capturing status in preview
            self._show_capturing_preview()
            
            # Start the actual capture
            success = self.parent.capture_mgr.start_bookend_capture(device_name)
            
            if not success:
                self.log_to_capture("Error: Failed to start capture")
                self.btn_start_capture.setEnabled(True)
                self.btn_stop_capture.setEnabled(False)
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


    def _show_reference_preview(self):
        """Show the reference video preview in the capture tab"""
        try:
            # Check if we have a reference video
            if hasattr(self.parent, 'reference_info') and self.parent.reference_info:
                reference_path = self.parent.reference_info.get('path')
                if reference_path and os.path.exists(reference_path):
                    # Use the same preview loading code from SetupTab
                    import cv2

                    # Open the video file
                    cap = cv2.VideoCapture(reference_path)
                    if not cap.isOpened():
                        logger.error(f"Could not open reference video: {reference_path}")
                        return

                    # Get the middle frame for preview
                    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                    if total_frames > 10:
                        # Seek to middle frame
                        cap.set(cv2.CAP_PROP_POS_FRAMES, total_frames // 2)

                    # Read the frame
                    ret, frame = cap.read()
                    if not ret:
                        logger.error("Could not read reference video frame")
                        cap.release()
                        return

                    # Convert frame to RGB format (OpenCV uses BGR)
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                    # Calculate scaled dimensions to fit the preview area
                    h, w, ch = frame_rgb.shape
                    preview_w = self.lbl_preview.width()
                    preview_h = self.lbl_preview.height()

                    # Calculate aspect ratio-preserving dimensions
                    if w/h > preview_w/preview_h:  # Width-limited
                        new_w = preview_w
                        new_h = int(h * (preview_w / w))
                    else:  # Height-limited
                        new_h = preview_h
                        new_w = int(w * (preview_h / h))

                    # Resize the frame
                    resized = cv2.resize(frame_rgb, (new_w, new_h))

                    # Convert to QImage and QPixmap
                    from PyQt5.QtGui import QImage, QPixmap
                    bytes_per_line = ch * new_w
                    q_img = QImage(resized.data, new_w, new_h, bytes_per_line, QImage.Format_RGB888)
                    pixmap = QPixmap.fromImage(q_img)

                    # Set the pixmap to the QLabel
                    self.lbl_preview.setPixmap(pixmap)
                    self.lbl_preview.setAlignment(Qt.AlignCenter)

                    # Update status text
                    ref_name = os.path.basename(reference_path)
                    self.lbl_preview_status.setText(f"Reference preview: {ref_name}")

                    # Release the video capture
                    cap.release()
                    return

            # Fall back to text message if couldn't load reference
            self.lbl_preview.setText("Reference video preview not available")
            self.lbl_preview.setStyleSheet("background-color: #f0f0f0; color: #666; padding: 10px;")
            self.lbl_preview_status.setText("Status: No reference video loaded")

        except Exception as e:
            logger.error(f"Error showing reference preview: {e}")
            self.lbl_preview.setText("Error loading reference preview")
            self.lbl_preview_status.setText(f"Error: {str(e)}")