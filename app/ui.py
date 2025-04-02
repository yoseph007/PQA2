import os
import logging
from datetime import datetime
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                           QPushButton, QLabel, QComboBox, QProgressBar, QFileDialog,
                           QGroupBox, QMessageBox, QTabWidget, QSplitter, QTextEdit,
                           QListWidget, QListWidgetItem, QStyle, QFormLayout, QCheckBox,
                           QSizePolicy, QFrame, QScrollArea, QSpinBox, QDoubleSpinBox,
                           QSlider, QLineEdit)
from PyQt5.QtCore import Qt, pyqtSlot, QTimer, QSize
from PyQt5.QtGui import QPixmap, QImage, QPainter, QColor, QFont, QPen
import cv2
import subprocess
import platform
import numpy as np
import time

# Import application modules
from .reference_analyzer import ReferenceAnalysisThread
from .capture import CaptureManager, CaptureState
from .bookend_alignment import BookendAlignmentThread
from .vmaf_analyzer import VMAFAnalysisThread
from .utils import FileManager, timestamp_string
from .options_manager import OptionsManager

logger = logging.getLogger(__name__)

class MainWindow(QMainWindow):
    """Main application window for VMAF Test App"""
    def __init__(self, capture_mgr=None, file_manager=None, options_manager=None):
        super().__init__()

        # Initialize managers
        self.capture_mgr = capture_mgr or CaptureManager()
        self.file_manager = file_manager or FileManager()
        self.options_manager = options_manager or OptionsManager()
        
        # Set up UI
        self._setup_ui()
        self._connect_signals()

        # State variables
        self.reference_info = None
        self.capture_path = None
        self.aligned_paths = None
        self.vmaf_results = None

        logger.info("VMAF Test App initialized")

    def _setup_ui(self):
        """Set up the application UI"""
        self.setWindowTitle("VMAF Test App")
        self.setGeometry(100, 100, 1200, 800)
        self.setFixedSize(1200, 800)  # Set fixed size to prevent resizing

        # Central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Create tabs
        self.tabs = QTabWidget()
        self.setup_tab = QWidget()
        self.capture_tab = QWidget()
        self.analysis_tab = QWidget()
        self.results_tab = QWidget()
        self.options_tab = QWidget()  # New options tab

        self.tabs.addTab(self.setup_tab, "Setup")
        self.tabs.addTab(self.capture_tab, "Capture")
        self.tabs.addTab(self.analysis_tab, "Analysis")
        self.tabs.addTab(self.results_tab, "Results")
        self.tabs.addTab(self.options_tab, "Options")  # Add options tab

        # Set up each tab
        self._setup_setup_tab()
        self._setup_capture_tab()
        self._setup_analysis_tab()
        self._setup_results_tab()
        self._setup_options_tab()  # Set up options tab

        # Add tabs to main layout
        main_layout.addWidget(self.tabs)

        # Status bar
        self.statusBar().showMessage("Ready")

    def _setup_setup_tab(self):
        """Set up the Setup tab"""
        layout = QVBoxLayout(self.setup_tab)

        # Reference video group
        reference_group = QGroupBox("Reference Video")
        reference_layout = QVBoxLayout()

        # Reference file selection
        ref_file_layout = QHBoxLayout()
        self.lbl_reference_path = QLabel("No reference video selected")
        self.btn_browse_reference = QPushButton("Browse...")
        self.btn_browse_reference.clicked.connect(self.browse_reference)
        ref_file_layout.addWidget(self.lbl_reference_path)
        ref_file_layout.addWidget(self.btn_browse_reference)
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
        self.btn_next_to_capture.clicked.connect(lambda: self.tabs.setCurrentIndex(1))
        nav_layout.addWidget(self.btn_next_to_capture)
        layout.addLayout(nav_layout)

        # Add stretch to push everything up
        layout.addStretch()

    def _setup_capture_tab(self):
        """Set up the Capture tab with enhanced layout and robust log handling"""
        layout = QVBoxLayout(self.capture_tab)

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

        self.pb_capture_progress = QProgressBar()
        self.pb_capture_progress.setTextVisible(True)
        self.pb_capture_progress.setAlignment(Qt.AlignCenter)
        capture_layout.addWidget(self.pb_capture_progress)

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

        # Add widgets to splitter
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([350, 650])

        # Add splitter to layout
        layout.addWidget(splitter)

        # Navigation buttons
        nav_layout = QHBoxLayout()
        self.btn_prev_to_setup = QPushButton("Back: Setup")
        self.btn_prev_to_setup.clicked.connect(lambda: self.tabs.setCurrentIndex(0))
        nav_layout.addWidget(self.btn_prev_to_setup)

        nav_layout.addStretch()

        self.btn_next_to_analysis = QPushButton("Next: Analysis")
        self.btn_next_to_analysis.setEnabled(False)
        self.btn_next_to_analysis.clicked.connect(lambda: self.tabs.setCurrentIndex(2))
        nav_layout.addWidget(self.btn_next_to_analysis)

        layout.addLayout(nav_layout)

    def _setup_analysis_tab(self):
        """Set up the Analysis tab with improved layout and combined workflow"""
        layout = QVBoxLayout(self.analysis_tab)

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
        self.combo_vmaf_model.addItem("vmaf_v0.6.1", "vmaf_v0.6.1")
        self.combo_vmaf_model.addItem("vmaf_4k_v0.6.1", "vmaf_4k_v0.6.1")
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

        # Log section with fixed height
        log_group = QGroupBox("Analysis Log")
        log_layout = QVBoxLayout()
        self.txt_analysis_log = QTextEdit()
        self.txt_analysis_log.setReadOnly(True)
        self.txt_analysis_log.setLineWrapMode(QTextEdit.WidgetWidth)
        self.txt_analysis_log.setMinimumHeight(150)
        self.txt_analysis_log.setMaximumHeight(200)  # Fix height to prevent stretching
        self.txt_analysis_log.setFixedWidth(800)  # Fixed width to avoid UI stretching with long messages
        log_layout.addWidget(self.txt_analysis_log)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)

        # Navigation buttons
        nav_layout = QHBoxLayout()
        self.btn_prev_to_capture = QPushButton("Back: Capture")
        self.btn_prev_to_capture.clicked.connect(lambda: self.tabs.setCurrentIndex(1))
        nav_layout.addWidget(self.btn_prev_to_capture)

        nav_layout.addStretch()

        self.btn_next_to_results = QPushButton("Next: Results")
        self.btn_next_to_results.setEnabled(False)
        self.btn_next_to_results.clicked.connect(lambda: self.tabs.setCurrentIndex(3))
        nav_layout.addWidget(self.btn_next_to_results)

        layout.addLayout(nav_layout)

    def _setup_results_tab(self):
        """Set up the Results tab"""
        layout = QVBoxLayout(self.results_tab)

        # Results summary
        self.lbl_results_summary = QLabel("No VMAF analysis results yet")
        layout.addWidget(self.lbl_results_summary)

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
        layout.addWidget(score_group)

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
        layout.addWidget(export_group)

        # Results files
        files_group = QGroupBox("Result Files")
        files_layout = QVBoxLayout()

        self.list_result_files = QListWidget()
        self.list_result_files.itemDoubleClicked.connect(self.open_result_file)
        files_layout.addWidget(self.list_result_files)

        files_group.setLayout(files_layout)
        layout.addWidget(files_group)

        # Navigation buttons
        nav_layout = QHBoxLayout()
        self.btn_prev_to_analysis = QPushButton("Back: Analysis")
        self.btn_prev_to_analysis.clicked.connect(lambda: self.tabs.setCurrentIndex(2))
        nav_layout.addWidget(self.btn_prev_to_analysis)

        nav_layout.addStretch()

        self.btn_new_test = QPushButton("Start New Test")
        self.btn_new_test.clicked.connect(self.start_new_test)
        nav_layout.addWidget(self.btn_new_test)

        layout.addLayout(nav_layout)

    def _connect_signals(self):
        """Connect signals to handlers"""
        # Connect signals only if capture_mgr exists
        if hasattr(self, 'capture_mgr') and self.capture_mgr:
            self.capture_mgr.status_update.connect(self.update_capture_status)
            self.capture_mgr.progress_update.connect(self.update_capture_progress) 
            self.capture_mgr.state_changed.connect(self.handle_capture_state_change)
            self.capture_mgr.capture_started.connect(self.handle_capture_started)
            self.capture_mgr.capture_finished.connect(self.handle_capture_finished)
            self.capture_mgr.frame_available.connect(self.update_preview)
            
        # Connect options manager signals
        if hasattr(self, 'options_manager') and self.options_manager:
            self.options_manager.settings_updated.connect(self.handle_settings_updated)
            
    def handle_settings_updated(self, settings):
        """Handle when settings are updated"""
        logger.info("Settings updated, applying changes to UI")
        
        # Update device status indicator in capture tab if device settings changed
        if hasattr(self, 'device_status_indicator'):
            self._populate_devices_and_check_status()

    def browse_reference(self):
        """Browse for reference video file"""
        # Use the tests/test_data folder for reference videos if it exists
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        reference_folder = os.path.join(script_dir, "tests", "test_data")
        
        # If folder doesn't exist, use home directory
        if not os.path.exists(reference_folder):
            reference_folder = os.path.expanduser("~")
        
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Reference Video", reference_folder, "Video Files (*.mp4 *.mov *.avi *.mkv)"
        )        
        if file_path:
            self.lbl_reference_path.setText(os.path.basename(file_path))
            self.lbl_reference_path.setToolTip(file_path)

            # Analyze the reference video
            self.analyze_reference(file_path)

    def analyze_reference(self, file_path):
        """Analyze reference video to extract metadata"""
        self.log_to_setup(f"Analyzing reference video: {os.path.basename(file_path)}")

        # Create analysis thread
        self.reference_thread = ReferenceAnalysisThread(file_path)
        self.reference_thread.progress_update.connect(self.log_to_setup)
        self.reference_thread.error_occurred.connect(self.handle_reference_error)
        self.reference_thread.analysis_complete.connect(self.handle_reference_analyzed)

        # Start analysis
        self.reference_thread.start()

    def handle_reference_analyzed(self, info):
        """Handle completion of reference video analysis"""
        self.reference_info = info

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
        self.lbl_capture_summary.setText(f"Reference: {os.path.basename(info['path'])}\n{details}")

        # Share reference info with capture manager
        if hasattr(self, 'capture_mgr') and self.capture_mgr:
            self.capture_mgr.set_reference_video(info)

        # Populate the duration combo box with 1-second increments
        # up to the reference video duration
        self.combo_duration.clear()
        self.combo_duration.addItem("Full Video", "full")

        # Add duration options based on reference video length
        max_seconds = int(duration)
        if max_seconds <= 60:  # For shorter videos, add every second
            for i in range(1, max_seconds + 1):
                self.combo_duration.addItem(f"{i} seconds", i)
        else:  # For longer videos, add more reasonable options
            durations = [1, 2, 5, 10, 15, 30, 60]
            durations.extend([d for d in [90, 120, 180, 240, 300] if d < max_seconds])
            for d in durations:
                self.combo_duration.addItem(f"{d} seconds", d)

        self.log_to_setup("Reference video analysis complete")

    def handle_reference_error(self, error_msg):
        """Handle error in reference video analysis"""
        self.log_to_setup(f"Error: {error_msg}")
        QMessageBox.critical(self, "Reference Analysis Error", error_msg)

    def browse_output_dir(self):
        """Browse for output directory"""
        # Use standard test_results directory as base
        default_dir = self.file_manager.get_default_base_dir() if hasattr(self, 'file_manager') else None
        
        if not default_dir:
            script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
            
            if hasattr(self, 'file_manager'):
                self.file_manager.base_dir = directory
                
            if hasattr(self, 'capture_mgr'):
                self.capture_mgr.set_output_directory(directory)

            self.log_to_setup(f"Output directory set to: {directory}")

    def refresh_devices(self):
        """Refresh list of capture devices and update status indicator"""
        self.device_combo.clear()
        self.device_combo.addItem("Detecting devices...")
        self.device_status_indicator.setStyleSheet("background-color: #808080; border-radius: 8px;")  # Grey while checking
        self.device_status_indicator.setToolTip("Checking device status...")

        # Use options manager to get devices
        QTimer.singleShot(500, self._populate_devices_and_check_status)

    def _populate_devices_and_check_status(self):
        """Populate device dropdown with devices and check their status"""
        # Get devices from options manager
        if hasattr(self, 'options_manager'):
            devices = self.options_manager.get_decklink_devices()
        else:
            # Fallback to hardcoded device
            devices = ["Intensity Shuttle"]
            
        # Update dropdown
        self.device_combo.clear()
        for device in devices:
            self.device_combo.addItem(device, device)
        
        # Set current device from settings
        if hasattr(self, 'options_manager'):
            current_device = self.options_manager.get_setting("capture", "default_device")
            index = self.device_combo.findText(current_device)
            if index >= 0:
                self.device_combo.setCurrentIndex(index)
        
        # Check if device is available
        if hasattr(self, 'capture_mgr'):
            try:
                # Use first device for check
                if devices:
                    available, _ = self.capture_mgr._test_device_availability(devices[0])
                    if available:
                        # Green for connected device
                        self.device_status_indicator.setStyleSheet("background-color: #00AA00; border-radius: 8px;")
                        self.device_status_indicator.setToolTip("Capture card status: connected")
                    else:
                        # Red for unavailable device
                        self.device_status_indicator.setStyleSheet("background-color: #AA0000; border-radius: 8px;")
                        self.device_status_indicator.setToolTip("Capture card status: not connected")
                else:
                    # Grey for no devices
                    self.device_status_indicator.setStyleSheet("background-color: #808080; border-radius: 8px;")
                    self.device_status_indicator.setToolTip("No capture devices found")
            except:
                # Grey for unknown status
                self.device_status_indicator.setStyleSheet("background-color: #808080; border-radius: 8px;")
                self.device_status_indicator.setToolTip("Capture card status: unknown")
        else:
            # Grey for initialization not complete
            self.device_status_indicator.setStyleSheet("background-color: #808080; border-radius: 8px;")
            self.device_status_indicator.setToolTip("Capture card status: not initialized")
        
        # Update the options tab indicator if it exists
        if hasattr(self, 'options_device_indicator'):
            self.options_device_indicator.setStyleSheet(self.device_status_indicator.styleSheet())
            self.options_device_indicator.setToolTip(self.device_status_indicator.toolTip())

    def start_capture(self):
        """Start the bookend capture process"""
        if not self.reference_info:
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
        output_dir = self.lbl_output_dir.text()
        if output_dir == "Default output directory":
            if hasattr(self, 'file_manager'):
                output_dir = self.file_manager.get_default_base_dir()
            else:
                script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                output_dir = os.path.join(script_dir, "tests", "test_results")
                os.makedirs(output_dir, exist_ok=True)

        # Add timestamp prefix to test name to prevent overwriting
        base_test_name = self.txt_test_name.currentText()
        test_name = f"{base_test_name}"

        self.log_to_capture(f"Using test name: {test_name}")

        # Set output information in capture manager
        if hasattr(self, 'capture_mgr'):
            self.capture_mgr.set_output_directory(output_dir)
            self.capture_mgr.set_test_name(test_name)
            
            # Start bookend capture
            self.log_to_capture("Starting bookend frame capture...")
            self.capture_mgr.start_bookend_capture(device_name)
        else:
            self.log_to_capture("Error: Capture manager not initialized")
            self.btn_start_capture.setEnabled(True)
            self.btn_stop_capture.setEnabled(False)

    def stop_capture(self):
        """Stop the capture process"""
        self.log_to_capture("Stopping capture...")
        if hasattr(self, 'capture_mgr'):
            self.capture_mgr.stop_capture(cleanup_temp=True)
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

    def handle_capture_finished(self, success, result):
        """Handle capture completion"""
        self.btn_start_capture.setEnabled(True)
        self.btn_stop_capture.setEnabled(False)

        # Reset progress bar to avoid stuck state
        self.pb_capture_progress.setValue(0)

        if success:
            # Normalize the path for consistent display
            display_path = os.path.normpath(result)

            self.log_to_capture(f"Capture completed: {display_path}")
            self.capture_path = result

            # Update analysis tab
            capture_name = os.path.basename(self.capture_path)
            ref_name = os.path.basename(self.reference_info['path'])

            analysis_summary = (f"Reference: {ref_name}\n" +
                            f"Captured: {capture_name}\n" +
                            f"Ready for alignment and VMAF analysis")

            self.lbl_analysis_summary.setText(analysis_summary)

            # Enable analysis tab and buttons
            self.btn_next_to_analysis.setEnabled(True)
            self.btn_run_combined_analysis.setEnabled(True)

            # Show success message with normalized path
            QMessageBox.information(self, "Capture Complete", 
                                  f"Capture completed successfully!\n\nSaved to: {display_path}")

            # Switch to analysis tab
            self.tabs.setCurrentIndex(2)

        else:
            self.log_to_capture(f"Capture failed: {result}")
            QMessageBox.critical(self, "Capture Failed", f"Capture failed: {result}")

    def update_preview(self, frame):
        """Update the preview with a video frame"""
        try:
            # Check if frame is valid
            if frame is None or frame.size == 0:
                logger.warning("Received empty frame for preview")
                self._show_placeholder_image("No valid video frame received")
                return
                
            # Convert OpenCV frame to QImage
            height, width, channel = frame.shape
            bytes_per_line = 3 * width

            # Convert BGR to RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Create QImage and QPixmap
            q_img = QImage(rgb_frame.data, width, height, bytes_per_line, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(q_img)

            # Scale pixmap to fit label while maintaining aspect ratio
            scaled_pixmap = pixmap.scaled(
                self.lbl_preview.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )

            # Update label
            self.lbl_preview.setPixmap(scaled_pixmap)
            
        except Exception as e:
            logger.error(f"Error updating preview: {str(e)}")
            self._show_placeholder_image(f"Preview error: {str(e)}")
            
    def _show_placeholder_image(self, message="No video feed"):
        """Show a placeholder image with text when no video is available"""
        try:
            # Create a blank image
            placeholder = np.zeros((270, 480, 3), dtype=np.uint8)
            placeholder[:] = (224, 224, 224)  # Light gray background
            
            # Add text
            font = cv2.FONT_HERSHEY_SIMPLEX
            text_size = cv2.getTextSize(message, font, 0.7, 2)[0]
            text_x = (placeholder.shape[1] - text_size[0]) // 2
            text_y = (placeholder.shape[0] + text_size[1]) // 2
            cv2.putText(placeholder, message, (text_x, text_y), font, 0.7, (0, 0, 0), 2)
            
            # Convert to QImage and display
            rgb_image = cv2.cvtColor(placeholder, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb_image.shape
            bytes_per_line = ch * w
            q_img = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
            self.lbl_preview.setPixmap(QPixmap.fromImage(q_img))
            
        except Exception as e:
            logger.error(f"Error creating placeholder: {str(e)}")
            # Fallback to text-only label
            self.lbl_preview.setText(message)
            self.lbl_preview.setStyleSheet("background-color: #e0e0e0; color: black;")

    def run_combined_analysis(self):
        """Run video alignment and VMAF analysis in sequence"""
        if not self.reference_info or not self.capture_path:
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

        # Start the alignment process
        self.align_videos_for_combined_workflow()

    def align_videos_for_combined_workflow(self):
        """Start video alignment as part of the combined workflow using bookend method"""
        self.log_to_analysis("Starting video alignment using bookend method...")

        # Create bookend alignment thread
        self.alignment_thread = BookendAlignmentThread(
            self.reference_info['path'],
            self.capture_path
        )

        # Connect signals
        self.alignment_thread.alignment_progress.connect(self.pb_alignment_progress.setValue)
        self.alignment_thread.status_update.connect(self.log_to_analysis)
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
        self.aligned_paths = {
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

        # Get test name and output directory
        test_name = self.txt_test_name.currentText()
        output_dir = self.lbl_output_dir.text()
        if output_dir == "Default output directory" and hasattr(self, 'file_manager'):
            output_dir = self.file_manager.get_default_base_dir()

        # Create analysis thread
        self.vmaf_thread = VMAFAnalysisThread(
            self.aligned_paths['reference'],
            self.aligned_paths['captured'],
            self.selected_model,
            self.selected_duration
        )

        # Set output directory and test name if available
        if output_dir and output_dir != "Default output directory":
            self.vmaf_thread.set_output_directory(output_dir)
        if test_name:
            self.vmaf_thread.set_test_name(test_name)

        # Connect signals
        self.vmaf_thread.analysis_progress.connect(self.pb_vmaf_progress.setValue)
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
        self.vmaf_results = results

        vmaf_score = results.get('vmaf_score')
        psnr = results.get('psnr')
        ssim = results.get('ssim')

        # Re-enable analysis button
        self.btn_run_combined_analysis.setEnabled(True)

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

        # Update results tab header with test name
        test_name = self.txt_test_name.currentText()
        self.lbl_results_summary.setText(f"VMAF Analysis Results for {test_name}")

        # Update metrics display
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

        # Add result files to list
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

    def _setup_options_tab(self):
        """Set up the Options tab with all configurable settings"""
        layout = QVBoxLayout(self.options_tab)
        
        # Create a scrollable area for many options
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(10)
        
        # Load current settings
        settings = self.options_manager.settings
        
        # Create section groupboxes
        bookend_group = self._create_bookend_options_group(settings)
        vmaf_group = self._create_vmaf_options_group(settings)
        capture_group = self._create_capture_options_group(settings)
        paths_group = self._create_paths_options_group(settings)
        
        # Add sections to layout
        scroll_layout.addWidget(bookend_group)
        scroll_layout.addWidget(vmaf_group)
        scroll_layout.addWidget(capture_group)
        scroll_layout.addWidget(paths_group)
        
        # Add spacer at the end to push everything up
        scroll_layout.addStretch()
        
        # Add content to scroll area
        scroll_area.setWidget(scroll_content)
        layout.addWidget(scroll_area)
        
        # Add save/reset buttons at the bottom
        button_layout = QHBoxLayout()
        self.btn_save_options = QPushButton("Save Options")
        self.btn_save_options.clicked.connect(self.save_all_options)
        self.btn_reset_options = QPushButton("Reset to Defaults")
        self.btn_reset_options.clicked.connect(self.reset_options_to_defaults)
        
        button_layout.addStretch()
        button_layout.addWidget(self.btn_reset_options)
        button_layout.addWidget(self.btn_save_options)
        layout.addLayout(button_layout)
    
    def _create_bookend_options_group(self, settings):
        """Create the bookend options group"""
        bookend_group = QGroupBox("Bookend Capture Settings")
        bookend_layout = QFormLayout()
        
        # Get current bookend settings
        bookend_settings = settings.get("bookend", self.options_manager.default_settings["bookend"])
        
        # Min loops spinner
        self.spinbox_min_loops = QSpinBox()
        self.spinbox_min_loops.setRange(1, 10)
        self.spinbox_min_loops.setValue(bookend_settings.get("min_loops", 3))
        self.spinbox_min_loops.setToolTip("Minimum number of video loops to capture")
        bookend_layout.addRow("Minimum Loops:", self.spinbox_min_loops)
        
        # Max capture time spinner (seconds)
        self.spinbox_max_capture = QSpinBox()
        self.spinbox_max_capture.setRange(10, 600)
        self.spinbox_max_capture.setSuffix(" seconds")
        self.spinbox_max_capture.setValue(bookend_settings.get("max_capture_time", 120))
        self.spinbox_max_capture.setToolTip("Maximum capture duration in seconds")
        bookend_layout.addRow("Maximum Capture Time:", self.spinbox_max_capture)
        
        # Bookend duration spinner (seconds)
        self.spinbox_bookend_duration = QDoubleSpinBox()
        self.spinbox_bookend_duration.setRange(0.1, 5.0)
        self.spinbox_bookend_duration.setSingleStep(0.1)
        self.spinbox_bookend_duration.setSuffix(" seconds")
        self.spinbox_bookend_duration.setValue(bookend_settings.get("bookend_duration", 0.5))
        self.spinbox_bookend_duration.setToolTip("Duration of white bookend frames in seconds")
        bookend_layout.addRow("Bookend Duration:", self.spinbox_bookend_duration)
        
        # White threshold slider (0-255)
        self.slider_white_threshold = QSlider(Qt.Horizontal)
        self.slider_white_threshold.setRange(200, 255)
        self.slider_white_threshold.setValue(bookend_settings.get("white_threshold", 240))
        self.lbl_white_threshold = QLabel(str(self.slider_white_threshold.value()))
        self.slider_white_threshold.valueChanged.connect(lambda v: self.lbl_white_threshold.setText(str(v)))
        self.slider_white_threshold.setToolTip("Brightness threshold for detecting white frames (0-255)")
        
        threshold_layout = QHBoxLayout()
        threshold_layout.addWidget(self.slider_white_threshold)
        threshold_layout.addWidget(self.lbl_white_threshold)
        bookend_layout.addRow("White Threshold:", threshold_layout)
        
        bookend_group.setLayout(bookend_layout)
        return bookend_group
    
    def _create_vmaf_options_group(self, settings):
        """Create the VMAF options group"""
        vmaf_group = QGroupBox("VMAF Analysis Settings")
        vmaf_layout = QFormLayout()
        
        # Get current VMAF settings
        vmaf_settings = settings.get("vmaf", self.options_manager.default_settings["vmaf"])
        
        # Default VMAF model selection
        self.combo_default_vmaf_model = QComboBox()
        available_models = vmaf_settings.get("available_models", ["vmaf_v0.6.1", "vmaf_4k_v0.6.1"])
        for model in available_models:
            self.combo_default_vmaf_model.addItem(model)
        
        # Set current model
        current_model = vmaf_settings.get("default_model", "vmaf_v0.6.1")
        index = self.combo_default_vmaf_model.findText(current_model)
        if index >= 0:
            self.combo_default_vmaf_model.setCurrentIndex(index)
        
        self.combo_default_vmaf_model.setToolTip("Default VMAF model to use for analysis")
        vmaf_layout.addRow("Default VMAF Model:", self.combo_default_vmaf_model)
        
        # Subsample (analyze every Nth frame)
        self.spinbox_subsample = QSpinBox()
        self.spinbox_subsample.setRange(1, 10)
        self.spinbox_subsample.setValue(vmaf_settings.get("subsample", 1))
        self.spinbox_subsample.setToolTip("Analyze every Nth frame (1 = all frames)")
        vmaf_layout.addRow("Subsample Rate:", self.spinbox_subsample)
        
        # Threads
        self.spinbox_threads = QSpinBox()
        self.spinbox_threads.setRange(0, 16)
        self.spinbox_threads.setValue(vmaf_settings.get("threads", 0))
        self.spinbox_threads.setToolTip("Number of threads for VMAF analysis (0 = auto)")
        self.spinbox_threads.setSpecialValueText("Auto")
        vmaf_layout.addRow("Threads:", self.spinbox_threads)
        
        # Output format
        self.combo_output_format = QComboBox()
        self.combo_output_format.addItems(["json", "xml", "csv"])
        current_format = vmaf_settings.get("output_format", "json")
        index = self.combo_output_format.findText(current_format)
        if index >= 0:
            self.combo_output_format.setCurrentIndex(index)
        self.combo_output_format.setToolTip("Output format for VMAF results")
        vmaf_layout.addRow("Output Format:", self.combo_output_format)
        
        # Custom model path
        self.txt_custom_model = QLineEdit()
        self.txt_custom_model.setText(vmaf_settings.get("custom_model_path", ""))
        self.txt_custom_model.setToolTip("Path to custom VMAF model (leave empty to use built-in models)")
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self.browse_custom_model)
        
        custom_model_layout = QHBoxLayout()
        custom_model_layout.addWidget(self.txt_custom_model)
        custom_model_layout.addWidget(browse_button)
        vmaf_layout.addRow("Custom Model Path:", custom_model_layout)
        
        vmaf_group.setLayout(vmaf_layout)
        return vmaf_group
    
    def _create_capture_options_group(self, settings):
        """Create the capture options group"""
        capture_group = QGroupBox("Capture Card Settings")
        capture_layout = QFormLayout()
        
        # Get current capture settings
        capture_settings = settings.get("capture", self.options_manager.default_settings["capture"])
        
        # Default device selection
        self.combo_default_device = QComboBox()
        device_layout = QHBoxLayout()
        device_layout.addWidget(self.combo_default_device)
        
        # Status indicator for device
        self.options_device_indicator = QLabel()
        self.options_device_indicator.setFixedSize(16, 16)
        self.options_device_indicator.setStyleSheet("background-color: #808080; border-radius: 8px;")  # Grey by default
        device_layout.addWidget(self.options_device_indicator)
        
        # Refresh button
        self.btn_refresh_options_devices = QPushButton("Refresh Devices")
        self.btn_refresh_options_devices.clicked.connect(self.refresh_capture_devices)
        device_layout.addWidget(self.btn_refresh_options_devices)
        
        capture_layout.addRow("Default Capture Device:", device_layout)
        
        # Resolution selection
        self.combo_resolution = QComboBox()
        available_resolutions = capture_settings.get("available_resolutions", ["1080p", "720p", "576p", "480p"])
        self.combo_resolution.addItems(available_resolutions)
        current_resolution = capture_settings.get("resolution", "1080p")
        index = self.combo_resolution.findText(current_resolution)
        if index >= 0:
            self.combo_resolution.setCurrentIndex(index)
        self.combo_resolution.setToolTip("Default capture resolution")
        capture_layout.addRow("Default Resolution:", self.combo_resolution)
        
        # Frame rate selection
        self.combo_frame_rate = QComboBox()
        available_rates = capture_settings.get("available_frame_rates", [23.98, 24, 25, 29.97, 30, 50, 59.94, 60])
        for rate in available_rates:
            self.combo_frame_rate.addItem(str(rate))
        current_rate = str(capture_settings.get("frame_rate", 30))
        index = self.combo_frame_rate.findText(current_rate)
        if index >= 0:
            self.combo_frame_rate.setCurrentIndex(index)
        self.combo_frame_rate.setToolTip("Default capture frame rate")
        capture_layout.addRow("Default Frame Rate:", self.combo_frame_rate)
        
        # Pixel format selection
        self.combo_pixel_format = QComboBox()
        self.combo_pixel_format.addItems(["uyvy422", "yuyv422", "nv12", "rgb24"])
        current_format = capture_settings.get("pixel_format", "uyvy422")
        index = self.combo_pixel_format.findText(current_format)
        if index >= 0:
            self.combo_pixel_format.setCurrentIndex(index)
        self.combo_pixel_format.setToolTip("Pixel format for capture")
        capture_layout.addRow("Pixel Format:", self.combo_pixel_format)
        
        # Auto detect formats button
        self.btn_detect_formats = QPushButton("Auto-Detect Formats")
        self.btn_detect_formats.clicked.connect(self.detect_device_formats)
        capture_layout.addRow("", self.btn_detect_formats)
        
        capture_group.setLayout(capture_layout)
        
        # Populate devices on initialization
        self.refresh_capture_devices()
        
        return capture_group
    
    def _create_paths_options_group(self, settings):
        """Create the paths options group"""
        paths_group = QGroupBox("File Paths Settings")
        paths_layout = QFormLayout()
        
        # Get current paths settings
        paths_settings = settings.get("paths", self.options_manager.default_settings["paths"])
        
        # Default output directory
        self.txt_default_output = QLineEdit()
        self.txt_default_output.setText(paths_settings.get("default_output_dir", ""))
        output_browse = QPushButton("Browse...")
        output_browse.clicked.connect(self.browse_default_output)
        
        output_layout = QHBoxLayout()
        output_layout.addWidget(self.txt_default_output)
        output_layout.addWidget(output_browse)
        paths_layout.addRow("Default Output Directory:", output_layout)
        
        # Reference video directory
        self.txt_reference_dir = QLineEdit()
        self.txt_reference_dir.setText(paths_settings.get("reference_video_dir", ""))
        ref_browse = QPushButton("Browse...")
        ref_browse.clicked.connect(self.browse_reference_dir)
        
        ref_layout = QHBoxLayout()
        ref_layout.addWidget(self.txt_reference_dir)
        ref_layout.addWidget(ref_browse)
        paths_layout.addRow("Reference Videos Directory:", ref_layout)
        
        # Results directory
        self.txt_results_dir = QLineEdit()
        self.txt_results_dir.setText(paths_settings.get("results_dir", ""))
        results_browse = QPushButton("Browse...")
        results_browse.clicked.connect(self.browse_results_dir)
        
        results_layout = QHBoxLayout()
        results_layout.addWidget(self.txt_results_dir)
        results_layout.addWidget(results_browse)
        paths_layout.addRow("Results Directory:", results_layout)
        
        # Temporary files directory
        self.txt_temp_dir = QLineEdit()
        self.txt_temp_dir.setText(paths_settings.get("temp_dir", ""))
        self.txt_temp_dir.setPlaceholderText("Leave empty to use system temp directory")
        temp_browse = QPushButton("Browse...")
        temp_browse.clicked.connect(self.browse_temp_dir)
        
        temp_layout = QHBoxLayout()
        temp_layout.addWidget(self.txt_temp_dir)
        temp_layout.addWidget(temp_browse)
        paths_layout.addRow("Temporary Files Directory:", temp_layout)
        
        paths_group.setLayout(paths_layout)
        return paths_group
    
    def refresh_capture_devices(self):
        """Refresh the list of capture devices and update the dropdown"""
        self.combo_default_device.clear()
        self.combo_default_device.addItem("Detecting devices...")
        self.options_device_indicator.setStyleSheet("background-color: #808080; border-radius: 8px;")  # Grey while checking
        
        # Run in timer to avoid blocking UI
        QTimer.singleShot(100, self._populate_capture_devices)
    
    def _populate_capture_devices(self):
        """Populate the device dropdown with detected devices"""
        # Get devices from options manager
        devices = self.options_manager.get_decklink_devices()
        
        # Update dropdown
        self.combo_default_device.clear()
        for device in devices:
            self.combo_default_device.addItem(device, device)
        
        # Set current device from settings
        current_device = self.options_manager.get_setting("capture", "default_device")
        index = self.combo_default_device.findText(current_device)
        if index >= 0:
            self.combo_default_device.setCurrentIndex(index)
        
        # Check if main device is available
        if hasattr(self, 'capture_mgr'):
            try:
                # Use first device for check
                if devices:
                    available, _ = self.capture_mgr._test_device_availability(devices[0])
                    if available:
                        # Green for connected device
                        self.options_device_indicator.setStyleSheet("background-color: #00AA00; border-radius: 8px;")
                        self.options_device_indicator.setToolTip("Capture card status: connected")
                    else:
                        # Red for unavailable device
                        self.options_device_indicator.setStyleSheet("background-color: #AA0000; border-radius: 8px;")
                        self.options_device_indicator.setToolTip("Capture card status: not connected")
                else:
                    # Grey for no devices
                    self.options_device_indicator.setStyleSheet("background-color: #808080; border-radius: 8px;")
                    self.options_device_indicator.setToolTip("No capture devices found")
            except:
                # Grey for error
                self.options_device_indicator.setStyleSheet("background-color: #808080; border-radius: 8px;")
                self.options_device_indicator.setToolTip("Error checking device status")
        
        # Also update the device status in the capture tab if it exists
        if hasattr(self, 'device_status_indicator'):
            self.device_status_indicator.setStyleSheet(self.options_device_indicator.styleSheet())
            self.device_status_indicator.setToolTip(self.options_device_indicator.toolTip())
    
    def detect_device_formats(self):
        """Auto-detect formats supported by the selected device"""
        device = self.combo_default_device.currentData()
        if not device:
            return
        
        # Disable button during detection
        self.btn_detect_formats.setEnabled(False)
        self.btn_detect_formats.setText("Detecting...")
        
        # Run in timer to avoid blocking UI
        QTimer.singleShot(100, lambda: self._perform_format_detection(device))
    
    def _perform_format_detection(self, device):
        """Perform the actual format detection"""
        try:
            # Get formats from options manager
            format_info = self.options_manager.get_decklink_formats(device)
            
            # Update UI with detected options
            if format_info["resolutions"]:
                self.combo_resolution.clear()
                for res in format_info["resolutions"]:
                    self.combo_resolution.addItem(res)
            else:
                # If no resolutions detected, fall back to defaults
                default_resolutions = ["1920x1080", "1280x720", "720x576", "720x480"]
                self.combo_resolution.clear()
                for res in default_resolutions:
                    self.combo_resolution.addItem(res)
                format_info["resolutions"] = default_resolutions
            
            if format_info["frame_rates"]:
                self.combo_frame_rate.clear()
                for rate in format_info["frame_rates"]:
                    self.combo_frame_rate.addItem(str(rate))
            else:
                # If no frame rates detected, fall back to defaults
                default_rates = [23.98, 24, 25, 29.97, 30, 50, 59.94, 60]
                self.combo_frame_rate.clear()
                for rate in default_rates:
                    self.combo_frame_rate.addItem(str(rate))
                format_info["frame_rates"] = default_rates
            
            # Update settings
            new_capture_settings = self.options_manager.get_setting("capture")
            new_capture_settings["available_resolutions"] = format_info["resolutions"]
            new_capture_settings["available_frame_rates"] = format_info["frame_rates"]
            self.options_manager.update_category("capture", new_capture_settings)
            
            # Show success message with number of formats
            num_formats = len(format_info['formats']) if format_info['formats'] else 0
            if num_formats > 0:
                QMessageBox.information(self, "Format Detection Complete", 
                                      f"Detected {num_formats} formats for {device}")
            else:
                QMessageBox.information(self, "Format Detection Complete", 
                                      f"Using default formats for {device}")
        except Exception as e:
            logger.error(f"Error detecting formats: {str(e)}")
            QMessageBox.warning(self, "Format Detection Error", 
                               f"Could not detect formats: {str(e)}")
            
            # Even on error, ensure we have default values
            default_resolutions = ["1920x1080", "1280x720", "720x576", "720x480"]
            default_rates = [23.98, 24, 25, 29.97, 30, 50, 59.94, 60]
            
            # Update UI with defaults
            self.combo_resolution.clear()
            for res in default_resolutions:
                self.combo_resolution.addItem(res)
                
            self.combo_frame_rate.clear()
            for rate in default_rates:
                self.combo_frame_rate.addItem(str(rate))
            
            # Update settings with defaults
            new_capture_settings = self.options_manager.get_setting("capture")
            new_capture_settings["available_resolutions"] = default_resolutions
            new_capture_settings["available_frame_rates"] = default_rates
            self.options_manager.update_category("capture", new_capture_settings)
        finally:
            # Re-enable button
            self.btn_detect_formats.setEnabled(True)
            self.btn_detect_formats.setText("Auto-Detect Formats")
    
    def browse_custom_model(self):
        """Browse for custom VMAF model file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Custom VMAF Model", "", "VMAF Models (*.json)"
        )
        if file_path:
            self.txt_custom_model.setText(file_path)
    
    def browse_default_output(self):
        """Browse for default output directory"""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Default Output Directory", self.txt_default_output.text()
        )
        if directory:
            self.txt_default_output.setText(directory)
    
    def browse_reference_dir(self):
        """Browse for reference videos directory"""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Reference Videos Directory", self.txt_reference_dir.text()
        )
        if directory:
            self.txt_reference_dir.setText(directory)
    
    def browse_results_dir(self):
        """Browse for results directory"""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Results Directory", self.txt_results_dir.text()
        )
        if directory:
            self.txt_results_dir.setText(directory)
            
    def browse_temp_dir(self):
        """Browse for temporary files directory"""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Temporary Files Directory", self.txt_temp_dir.text()
        )
        if directory:
            self.txt_temp_dir.setText(directory)
    
    def save_all_options(self):
        """Save all options from the UI to settings"""
        try:
            # Bookend settings
            bookend_settings = self.options_manager.get_setting("bookend")
            bookend_settings["min_loops"] = self.spinbox_min_loops.value()
            bookend_settings["max_capture_time"] = self.spinbox_max_capture.value()
            bookend_settings["bookend_duration"] = self.spinbox_bookend_duration.value()
            bookend_settings["white_threshold"] = self.slider_white_threshold.value()
            self.options_manager.update_category("bookend", bookend_settings)
            
            # VMAF settings
            vmaf_settings = self.options_manager.get_setting("vmaf")
            vmaf_settings["default_model"] = self.combo_default_vmaf_model.currentText()
            vmaf_settings["subsample"] = self.spinbox_subsample.value()
            vmaf_settings["threads"] = self.spinbox_threads.value()
            vmaf_settings["output_format"] = self.combo_output_format.currentText()
            vmaf_settings["custom_model_path"] = self.txt_custom_model.text()
            self.options_manager.update_category("vmaf", vmaf_settings)
            
            # Capture settings
            capture_settings = self.options_manager.get_setting("capture")
            capture_settings["default_device"] = self.combo_default_device.currentText()
            capture_settings["resolution"] = self.combo_resolution.currentText()
            capture_settings["frame_rate"] = float(self.combo_frame_rate.currentText())
            capture_settings["pixel_format"] = self.combo_pixel_format.currentText()
            self.options_manager.update_category("capture", capture_settings)
            
            # Paths settings
            paths_settings = self.options_manager.get_setting("paths")
            paths_settings["default_output_dir"] = self.txt_default_output.text()
            paths_settings["reference_video_dir"] = self.txt_reference_dir.text()
            paths_settings["results_dir"] = self.txt_results_dir.text()
            paths_settings["temp_dir"] = self.txt_temp_dir.text()
            self.options_manager.update_category("paths", paths_settings)
            
            # Apply settings to other components
            self._apply_settings_to_components()
            
            # Show confirmation
            QMessageBox.information(self, "Settings Saved", "All options have been saved successfully")
            
        except Exception as e:
            logger.error(f"Error saving options: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to save options: {str(e)}")
    
    def reset_options_to_defaults(self):
        """Reset all options to default values"""
        if QMessageBox.question(self, "Confirm Reset", 
                              "Are you sure you want to reset all options to defaults?",
                              QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            # Reset to defaults
            self.options_manager.reset_to_defaults()
            
            # Reload UI with defaults
            self._reload_options_from_settings()
            
            # Apply settings to other components
            self._apply_settings_to_components()
            
            QMessageBox.information(self, "Reset Complete", "All options have been reset to defaults")
    
    def _reload_options_from_settings(self):
        """Reload all UI elements with current settings"""
        # Get current settings
        settings = self.options_manager.settings
        
        # Bookend settings
        bookend_settings = settings.get("bookend", {})
        self.spinbox_min_loops.setValue(bookend_settings.get("min_loops", 3))
        self.spinbox_max_capture.setValue(bookend_settings.get("max_capture_time", 120))
        self.spinbox_bookend_duration.setValue(bookend_settings.get("bookend_duration", 0.5))
        self.slider_white_threshold.setValue(bookend_settings.get("white_threshold", 240))
        
        # VMAF settings
        vmaf_settings = settings.get("vmaf", {})
        index = self.combo_default_vmaf_model.findText(vmaf_settings.get("default_model", "vmaf_v0.6.1"))
        if index >= 0:
            self.combo_default_vmaf_model.setCurrentIndex(index)
        self.spinbox_subsample.setValue(vmaf_settings.get("subsample", 1))
        self.spinbox_threads.setValue(vmaf_settings.get("threads", 0))
        index = self.combo_output_format.findText(vmaf_settings.get("output_format", "json"))
        if index >= 0:
            self.combo_output_format.setCurrentIndex(index)
        self.txt_custom_model.setText(vmaf_settings.get("custom_model_path", ""))
        
        # Capture settings - refresh devices to update
        self.refresh_capture_devices()
        
        # Paths settings
        paths_settings = settings.get("paths", {})
        self.txt_default_output.setText(paths_settings.get("default_output_dir", ""))
        self.txt_reference_dir.setText(paths_settings.get("reference_video_dir", ""))
        self.txt_results_dir.setText(paths_settings.get("results_dir", ""))
    
    def _apply_settings_to_components(self):
        """Apply current settings to other components of the application"""
        # Update capture manager if it exists
        if hasattr(self, 'capture_mgr') and self.capture_mgr:
            # Apply device and output directory settings
            device = self.options_manager.get_setting("capture", "default_device")
            if device and self.device_combo:
                index = self.device_combo.findText(device) 
                if index >= 0:
                    self.device_combo.setCurrentIndex(index)
            
            # Apply output directory settings
            output_dir = self.options_manager.get_setting("paths", "default_output_dir")
            if output_dir and os.path.exists(output_dir):
                self.capture_mgr.set_output_directory(output_dir)
                if hasattr(self, 'lbl_output_dir'):
                    self.lbl_output_dir.setText(output_dir)
                    self.lbl_output_dir.setToolTip(output_dir)
        
        # Update VMAF model in analysis tab if it exists
        vmaf_model = self.options_manager.get_setting("vmaf", "default_model")
        if vmaf_model and hasattr(self, 'combo_vmaf_model'):
            index = self.combo_vmaf_model.findText(vmaf_model)
            if index >= 0:
                self.combo_vmaf_model.setCurrentIndex(index)

            item = QListWidgetItem(f"Captured: {os.path.basename(dist_path)}")
            item.setData(Qt.UserRole, dist_path)
            self.list_result_files.addItem(item)
            
        # Add aligned videos
        if self.aligned_paths:
            for key, path in self.aligned_paths.items():
                if path and os.path.exists(path):
                    item = QListWidgetItem(f"Aligned {key.title()}: {os.path.basename(path)}")
                    item.setData(Qt.UserRole, path)
                    self.list_result_files.addItem(item)

        # Show message with VMAF score
        if vmaf_score is not None:
            QMessageBox.information(self, "Analysis Complete", 
                                f"VMAF analysis complete!\n\nVMAF Score: {vmaf_score:.2f}")
        else:
            QMessageBox.information(self, "Analysis Complete", 
                                "VMAF analysis complete!")

        # Switch to results tab
        self.tabs.setCurrentIndex(3)

    def handle_vmaf_error(self, error_msg):
        """Handle error in VMAF analysis"""
        self.lbl_vmaf_status.setText(f"VMAF analysis failed")
        self.log_to_analysis(f"Error: {error_msg}")
        QMessageBox.critical(self, "VMAF Analysis Error", error_msg)
        
        # Re-enable analysis button
        self.btn_run_combined_analysis.setEnabled(True)

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

    def start_new_test(self):
        """Reset application for a new test"""
        # Reset state variables
        self.ensure_threads_finished()
        self.capture_path = None
        self.aligned_paths = None
        self.vmaf_results = None

        # Clear logs
        self.txt_capture_log.clear()
        self.txt_analysis_log.clear()
        
        # Reset progress bars
        self.pb_capture_progress.setValue(0)
        self.pb_alignment_progress.setValue(0)
        self.pb_vmaf_progress.setValue(0)

        # Reset status
        self.lbl_capture_status.setText("Ready to capture")
        self.lbl_alignment_status.setText("Not aligned")
        self.lbl_vmaf_status.setText("Not analyzed")
        
        # Disable buttons
        self.btn_next_to_analysis.setEnabled(False)
        self.btn_next_to_results.setEnabled(False)
        self.btn_run_combined_analysis.setEnabled(False)
        self.btn_export_pdf.setEnabled(False)
        self.btn_export_csv.setEnabled(False)
        
        # Reset results
        self.lbl_vmaf_score.setText("VMAF Score: --")
        self.lbl_psnr_score.setText("PSNR: --")
        self.lbl_ssim_score.setText("SSIM: --")
        self.list_result_files.clear()
        
        # Update summaries
        if self.reference_info:
            capture_text = f"Reference: {os.path.basename(self.reference_info['path'])}\nNo capture yet"
            self.lbl_capture_summary.setText(capture_text)
            self.lbl_analysis_summary.setText("No captured video yet for analysis")
        else:
            self.lbl_capture_summary.setText("No reference video selected")
            self.lbl_analysis_summary.setText("No videos ready for analysis")
        
        self.lbl_results_summary.setText("No VMAF analysis results yet")

        # Increment test number
        test_name = self.txt_test_name.currentText()
        if test_name.startswith("Test_") and len(test_name) > 5 and test_name[5:].isdigit():
            next_num = int(test_name[5:]) + 1
            self.txt_test_name.setCurrentText(f"Test_{next_num:02d}")

        # Go back to capture tab
        self.tabs.setCurrentIndex(1)

    # Helper methods for logging to the UI
    def log_to_setup(self, message):
        """Add message to setup status"""
        self.lbl_setup_status.setText(message)
        self.statusBar().showMessage(message)

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
        self.statusBar().showMessage(message)
        
        # If error message, flash status bar to draw attention
        if "error" in message.lower():
            current_style = self.statusBar().styleSheet()
            self.statusBar().setStyleSheet("background-color: #FFCDD2;")  # Light red
            # Reset style after 2 seconds
            QTimer.singleShot(2000, lambda: self.statusBar().setStyleSheet(current_style))

    def log_to_analysis(self, message):
        """Add message to analysis log"""
        self.txt_analysis_log.append(message)
        self.txt_analysis_log.verticalScrollBar().setValue(
            self.txt_analysis_log.verticalScrollBar().maximum()
        )
        self.statusBar().showMessage(message)
 
    def closeEvent(self, event):
        """Handle application close event"""
        logger.info("Application closing - cleaning up resources")
        
        # Stop any active capture process first
        if hasattr(self, 'capture_mgr') and self.capture_mgr and self.capture_mgr.is_capturing:
            logger.info("Stopping active capture process before closing")
            self.capture_mgr.stop_capture(cleanup_temp=True)
        
        # Ensure all threads are properly terminated
        self.ensure_threads_finished()
        
        # Clean up temporary files if file manager exists
        if hasattr(self, 'file_manager') and self.file_manager:
            logger.info("Cleaning up temporary files")
            self.file_manager.cleanup_temp_files()
        
        # Call parent close event
        logger.info("Cleanup complete, proceeding with application close")
        super().closeEvent(event)
  
    def ensure_threads_finished(self):
        """Ensure all running threads are properly terminated before proceeding"""
        # Check for vmaf_thread specifically since that's causing the issue
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
                
                # If it's still running, we're in trouble but we've tried our best
                if self.vmaf_thread.isRunning():
                    logger.error("VMAF thread couldn't be terminated - possible resource leak")
        
        # Do the same for other threads
        for thread_attr, thread_name in [
            ('alignment_thread', 'Alignment'), 
            ('reference_thread', 'Reference analysis')
        ]:
            if hasattr(self, thread_attr) and getattr(self, thread_attr) and getattr(self, thread_attr).isRunning():
                logger.info(f"{thread_name} thread is still running - attempting clean shutdown")
                thread = getattr(self, thread_attr)
                thread.quit()
                if not thread.wait(3000):
                    logger.warning(f"{thread_name} thread didn't respond to quit - forcing termination")
                    thread.terminate()
                    thread.wait(1000)
 
 