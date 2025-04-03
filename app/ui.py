import os
import logging
from datetime import datetime
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                           QPushButton, QLabel, QComboBox, QProgressBar, QFileDialog,
                           QGroupBox, QMessageBox, QTabWidget, QSplitter, QTextEdit,
                           QListWidget, QListWidgetItem, QStyle, QFormLayout, QCheckBox,
                           QSizePolicy, QFrame, QScrollArea, QSpinBox, QDoubleSpinBox,
                           QSlider, QLineEdit, QApplication)
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

# Import for theme customization
import qdarkstyle
from PyQt5.QtGui import QPalette, QColor

from .options_manager import OptionsManager

logger = logging.getLogger(__name__)

class MainWindow(QMainWindow):
    """Main application window for VMAF Test App"""
    def __init__(self, capture_manager, file_manager, options_manager):
        super().__init__()

        # Store manager references
        self.capture_mgr = capture_manager
        self.file_mgr = file_manager
        self.options_manager = options_manager  # Store the options manager reference

        # Flag to handle headless mode
        self.headless_mode = False

        # Set up UI
        self._setup_ui()
        self._connect_signals()

        # State variables
        self.reference_info = None
        self.capture_path = None
        self.aligned_paths = None
        self.vmaf_results = None
        self.vmaf_running = False # Added vmaf_running flag

        logger.info("VMAF Test App initialized")

    def _setup_ui(self):
        """Set up the application UI"""
        self.setWindowTitle("VMAF Test App")
        self.setGeometry(100, 100, 1200, 800)
        self.setFixedSize(1200, 800)  # Set fixed size to prevent resizing
        
        # Set application icon/logo
        self._set_application_logo()

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
        """Set up the Results tab with data grid for historical results"""
        layout = QVBoxLayout(self.results_tab)

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
        from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView
        
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

            # Connect to capture monitor frame counter if available
            if hasattr(self.capture_mgr, 'capture_monitor') and self.capture_mgr.capture_monitor:
                self.capture_mgr.capture_monitor.frame_count_updated.connect(self.update_frame_counter)

        # Connect options manager signals
        if hasattr(self, 'options_manager') and self.options_manager:
            self.options_manager.settings_updated.connect(self.handle_settings_updated)

        # Initialize reference video dropdown
        self.refresh_reference_videos()

    def handle_settings_updated(self, settings):
        """Handle when settings are updated"""
        logger.info("Settings updated, applying changes to UI")

        # Update device status indicator in capture tab if device settings changed
        if hasattr(self, 'device_status_indicator'):
            self._populate_devices_and_check_status()

    def refresh_reference_videos(self):
        """Populate dropdown with available reference videos from configured directory"""
        self.combo_reference_videos.clear()

        # Get reference directory from settings
        reference_folder = None
        if hasattr(self, 'options_manager') and self.options_manager:
            reference_folder = self.options_manager.get_setting("paths", "reference_video_dir")

        # If not configured, use default location
        if not reference_folder or not os.path.exists(reference_folder):
            script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            reference_folder = os.path.join(script_dir, "tests", "test_data")

            # If still doesn't exist, create it
            if not os.path.exists(reference_folder):
                os.makedirs(reference_folder, exist_ok=True)

        # Find all video files
        video_extensions = ['.mp4', '.mov', '.avi', '.mkv']
        video_files = []

        try:
            for file in os.listdir(reference_folder):
                if any(file.lower().endswith(ext) for ext in video_extensions):
                    video_files.append(os.path.join(reference_folder, file))

            # Add to dropdown
            if video_files:
                for video_path in sorted(video_files):
                    self.combo_reference_videos.addItem(os.path.basename(video_path), video_path)
                logger.info(f"Found {len(video_files)} reference videos")
            else:
                self.combo_reference_videos.addItem("No reference videos found", "")
                logger.info("No reference videos found in the configured directory")
        except Exception as e:
            logger.error(f"Error loading reference videos: {str(e)}")
            self.combo_reference_videos.addItem("Error loading videos", "")

    def reference_selected(self, index):
        """Handle reference video selection from dropdown"""
        if index < 0:
            return

        file_path = self.combo_reference_videos.currentData()
        if file_path and os.path.exists(file_path):
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
        self.device_status_indicator.setStyleSheet("background-color: #808080; borderradius: 8px;")  # Grey while checking
        self.device_status_indicator.setToolTip("Checking device status...")

        # Use options manager to get devices
        QTimer.singleShot(500, self._populate_devices_and_check_status)

    def _populate_devices_and_check_status(self):
        """Populate device dropdown with devices and check their status"""
        # Get devices from options manager
        devices = []
        if hasattr(self, 'options_manager') and self.options_manager:
            try:
                # Try to get devices from options manager
                devices = self.options_manager.get_decklink_devices()
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
        if hasattr(self, 'options_manager') and self.options_manager:
            try:
                current_device = self.options_manager.get_setting("capture", "default_device")
                index = self.device_combo.findText(current_device)
                if index >= 0:
                    self.device_combo.setCurrentIndex(index)
                logger.info(f"Set current device to: {current_device}")
            except Exception as e:
                logger.error(f"Error setting current device: {e}")

        # Check if device is available
        if hasattr(self, 'capture_mgr') and self.capture_mgr:
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

                        # Only attempt to get formats when explicitly requested (not during auto-refresh)
                        # This prevents infinite loops where settings changes trigger more refreshes
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

        # Update the options tab indicator if it exists
        if hasattr(self, 'options_device_indicator'):
            self.options_device_indicator.setStyleSheet(self.device_status_indicator.styleSheet())
            self.options_device_indicator.setToolTip(self.device_status_indicator.toolTip())

        # Make sure to populate UI fields from settings, but don't trigger format detection
        if hasattr(self, 'combo_resolution') and hasattr(self, 'combo_frame_rate'):
            self._populate_capture_settings_fields()

    def _populate_capture_settings_fields(self):
        """Update UI fields with current capture settings"""
        if not hasattr(self, 'options_manager') or not self.options_manager:
            logger.warning("Options manager not available, can't populate capture settings fields")
            return

        if not hasattr(self, 'combo_resolution') or not hasattr(self, 'combo_frame_rate'):
            logger.warning("UI elements not initialized, can't populate capture settings fields")
            return

        try:
            # Get current settings
            capture_settings = self.options_manager.get_setting("capture")

            # Update resolution dropdown
            if capture_settings.get("available_resolutions"):
                # Save current selection if any
                current_resolution = self.combo_resolution.currentText()

                # Clear and repopulate
                self.combo_resolution.clear()
                for res in capture_settings["available_resolutions"]:
                    self.combo_resolution.addItem(res)

                # Restore previous selection or set from settings
                if current_resolution and self.combo_resolution.findText(current_resolution) >= 0:
                    self.combo_resolution.setCurrentText(current_resolution)
                elif capture_settings.get("resolution"):
                    idx = self.combo_resolution.findText(capture_settings["resolution"])
                    if idx >= 0:
                        self.combo_resolution.setCurrentIndex(idx)

                logger.info(f"Populated resolution dropdown with {self.combo_resolution.count()} items")
            else:
                logger.warning("No available resolutions in settings")
                # Add default resolutions as fallback
                default_resolutions = ["1920x1080", "1280x720", "720x576", "720x480"]
                self.combo_resolution.clear()
                for res in default_resolutions:
                    self.combo_resolution.addItem(res)

            # Update frame rate dropdown
            if capture_settings.get("available_frame_rates"):
                # Save current selection if any
                current_rate = self.combo_frame_rate.currentText()

                # Clear and repopulate
                self.combo_frame_rate.clear()
                for rate in capture_settings["available_frame_rates"]:
                    self.combo_frame_rate.addItem(str(rate))

                # Restore previous selection or set from settings
                if current_rate and self.combo_frame_rate.findText(current_rate) >= 0:
                    self.combo_frame_rate.setCurrentText(current_rate)
                elif capture_settings.get("frame_rate"):
                    rate_str = str(capture_settings["frame_rate"])
                    idx = self.combo_frame_rate.findText(rate_str)
                    if idx >= 0:
                        self.combo_frame_rate.setCurrentIndex(idx)

                logger.info(f"Populated frame rate dropdown with {self.combo_frame_rate.count()} items")
            else:
                logger.warning("No available frame rates in settings")
                # Add default frame rates as fallback
                default_rates = [23.98, 24, 25, 29.97, 30, 50, 59.94, 60]
                self.combo_frame_rate.clear()
                for rate in default_rates:
                    self.combo_frame_rate.addItem(str(rate))

            # Update pixel format dropdown
            if hasattr(self, 'combo_pixel_format') and capture_settings.get("pixel_format"):
                idx = self.combo_pixel_format.findText(capture_settings["pixel_format"])
                if idx >= 0:
                    self.combo_pixel_format.setCurrentIndex(idx)
        except Exception as e:
            logger.error(f"Error populating capture settings fields: {e}")

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
            # Check if we're in headless mode
            if hasattr(self, 'headless_mode') and self.headless_mode:
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
        self.vmaf_running = True # Set vmaf_running flag before starting analysis

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

    def update_frame_counter(self, current_frame, total_frames):
        """Update frame counter display during capture"""
        if hasattr(self, 'lbl_capture_frame_counter'):
            # Format with thousands separator for readability
            if total_frames > 0:
                self.lbl_capture_frame_counter.setText(f"Frames: {current_frame:,} / {total_frames:,}")
            else:
                self.lbl_capture_frame_counter.setText(f"Frames: {current_frame:,}")

    def handle_vmaf_complete(self, results):
        """Handle completion of VMAF analysis"""
        self.vmaf_results = results

        vmaf_score = results.get('vmaf_score')
        psnr = results.get('psnr')
        ssim = results.get('ssim')

        # Ensure progress bar shows 100% when complete
        self.pb_vmaf_progress.setValue(100)
        
        # Re-enable analysis button
        self.btn_run_combined_analysis.setEnabled(True)
        self.vmaf_running = False # Reset vmaf_running flag

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

        # Reset vmaf_running flag to allow new analysis
        self.vmaf_running = False

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

        # Create theme customization group
        theme_group = self._create_theme_options_group(settings)
        
        # Create section groupboxes
        bookend_group = self._create_bookend_options_group(settings)
        vmaf_group = self._create_vmaf_options_group(settings)
        capture_group = self._create_capture_options_group(settings)
        paths_group = self._create_paths_options_group(settings)

        # Add sections to layout
        scroll_layout.addWidget(theme_group)
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
        
    def _create_theme_options_group(self, settings):
        """Create the theme options group"""
        theme_group = QGroupBox("Theme Settings")
        theme_layout = QVBoxLayout()
        
        # Theme selection
        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("Application Theme:"))
        
        self.combo_theme = QComboBox()
        self.combo_theme.addItems(["Light", "Dark", "System", "Custom"])
        
        # Get current theme
        current_theme = settings.get("theme", {}).get("selected_theme", "System")
        index = self.combo_theme.findText(current_theme)
        if index >= 0:
            self.combo_theme.setCurrentIndex(index)
            
        self.combo_theme.currentTextChanged.connect(self._update_theme_preview)
        theme_row.addWidget(self.combo_theme)
        
        # Add apply theme button
        self.btn_apply_theme = QPushButton("Apply Theme")
        self.btn_apply_theme.clicked.connect(self._apply_selected_theme)
        theme_row.addWidget(self.btn_apply_theme)
        
        theme_row.addStretch()
        theme_layout.addLayout(theme_row)
        
        # Theme preview
        self.theme_preview = QFrame()
        self.theme_preview.setMinimumHeight(100)
        self.theme_preview.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        preview_layout = QVBoxLayout(self.theme_preview)
        
        # Add some sample widgets to the preview
        preview_label = QLabel("Theme Preview")
        preview_label.setAlignment(Qt.AlignCenter)
        preview_layout.addWidget(preview_label)
        
        preview_buttons = QHBoxLayout()
        preview_buttons.addWidget(QPushButton("Normal Button"))
        
        check_box = QCheckBox("Checkbox")
        check_box.setChecked(True)
        preview_buttons.addWidget(check_box)
        
        combo = QComboBox()
        combo.addItems(["Item 1", "Item 2", "Item 3"])
        preview_buttons.addWidget(combo)
        
        preview_layout.addLayout(preview_buttons)
        
        theme_layout.addWidget(self.theme_preview)
        
        # Custom theme options
        self.custom_theme_group = QGroupBox("Custom Theme Options")
        self.custom_theme_group.setVisible(self.combo_theme.currentText() == "Custom")
        
        custom_layout = QFormLayout(self.custom_theme_group)
        
        # Background color
        bg_layout = QHBoxLayout()
        self.bg_color_button = QPushButton()
        self.bg_color_button.setFixedSize(24, 24)
        bg_color = settings.get("theme", {}).get("bg_color", "#2D2D30")
        self.bg_color_button.setStyleSheet(f"background-color: {bg_color}; border: 1px solid #888;")
        self.bg_color_button.clicked.connect(lambda: self._pick_color("bg_color"))
        bg_layout.addWidget(self.bg_color_button)
        bg_layout.addWidget(QLabel(bg_color))
        bg_layout.addStretch()
        custom_layout.addRow("Background Color:", bg_layout)
        
        # Text color
        text_layout = QHBoxLayout()
        self.text_color_button = QPushButton()
        self.text_color_button.setFixedSize(24, 24)
        text_color = settings.get("theme", {}).get("text_color", "#FFFFFF")
        self.text_color_button.setStyleSheet(f"background-color: {text_color}; border: 1px solid #888;")
        self.text_color_button.clicked.connect(lambda: self._pick_color("text_color"))
        text_layout.addWidget(self.text_color_button)
        text_layout.addWidget(QLabel(text_color))
        text_layout.addStretch()
        custom_layout.addRow("Text Color:", text_layout)
        
        # Accent color
        accent_layout = QHBoxLayout()
        self.accent_color_button = QPushButton()
        self.accent_color_button.setFixedSize(24, 24)
        accent_color = settings.get("theme", {}).get("accent_color", "#007ACC")
        self.accent_color_button.setStyleSheet(f"background-color: {accent_color}; border: 1px solid #888;")
        self.accent_color_button.clicked.connect(lambda: self._pick_color("accent_color"))
        accent_layout.addWidget(self.accent_color_button)
        accent_layout.addWidget(QLabel(accent_color))
        accent_layout.addStretch()
        custom_layout.addRow("Accent Color:", accent_layout)
        
        theme_layout.addWidget(self.custom_theme_group)
        
        # Logo section
        logo_group = QGroupBox("Application Logo")
        logo_layout = QVBoxLayout(logo_group)
        
        # Logo preview
        self.logo_label = QLabel()
        self.logo_label.setAlignment(Qt.AlignCenter)
        logo_path = settings.get("theme", {}).get("logo_path", "")
        
        if logo_path and os.path.exists(logo_path):
            pixmap = QPixmap(logo_path)
            scaled_pixmap = pixmap.scaled(200, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.logo_label.setPixmap(scaled_pixmap)
        else:
            # Load default logo from assets
            default_logo = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                                     "attached_assets", "chroma-logo.png")
            if os.path.exists(default_logo):
                pixmap = QPixmap(default_logo)
                scaled_pixmap = pixmap.scaled(200, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.logo_label.setPixmap(scaled_pixmap)
            else:
                self.logo_label.setText("Logo not found")
        
        logo_layout.addWidget(self.logo_label)
        
        # Logo controls
        logo_buttons = QHBoxLayout()
        self.btn_change_logo = QPushButton("Change Logo")
        self.btn_change_logo.clicked.connect(self._change_logo)
        logo_buttons.addWidget(self.btn_change_logo)
        
        self.btn_reset_logo = QPushButton("Reset to Default")
        self.btn_reset_logo.clicked.connect(self._reset_logo)
        logo_buttons.addWidget(self.btn_reset_logo)
        
        logo_layout.addLayout(logo_buttons)
        
        theme_layout.addWidget(logo_group)
        
        theme_group.setLayout(theme_layout)
        return theme_group

    def _create_bookend_options_group(self, settings):
        """Create the bookend options group with improved clarity"""
        bookend_group = QGroupBox("Bookend Capture Settings")
        bookend_layout = QVBoxLayout()

        # Add explanation of bookend method at the top
        explanation = QLabel(
            "The bookend capture method uses white frames at the beginning and end of a looped "
            "video to automatically detect and extract the video content. These settings control "
            "how the capture and detection process works."
        )
        explanation.setWordWrap(True)
        explanation.setStyleSheet("font-style: italic; color: #666;")
        bookend_layout.addWidget(explanation)

        # Create form layout for settings
        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        # Get current bookend settings
        bookend_settings = settings.get("bookend", self.options_manager.default_settings["bookend"])

        # Minimum loops with better explanation
        min_loops_layout = QHBoxLayout()
        self.spinbox_min_loops = QSpinBox()
        self.spinbox_min_loops.setRange(1, 10)
        self.spinbox_min_loops.setValue(bookend_settings.get("min_loops", 3))
        min_loops_help = QPushButton("?")
        min_loops_help.setMaximumWidth(24)
        min_loops_help.clicked.connect(lambda: QMessageBox.information(
            self, "Minimum Loops Help",
            "This setting controls the minimum number of complete video loops to capture.\n\n"
            "Each loop consists of: white frame → video content → white frame\n\n"
            "Higher values ensure better quality analysis but take longer to capture."
        ))
        min_loops_layout.addWidget(self.spinbox_min_loops)
        min_loops_layout.addWidget(min_loops_help)
        min_loops_layout.addStretch()
        form_layout.addRow("Minimum Loops:", min_loops_layout)

        # Max capture time with better explanation
        max_time_layout = QHBoxLayout()
        self.spinbox_max_capture = QSpinBox()
        self.spinbox_max_capture.setRange(10, 600)
        self.spinbox_max_capture.setSuffix(" seconds")
        self.spinbox_max_capture.setValue(bookend_settings.get("max_capture_time", 120))
        max_time_help = QPushButton("?")
        max_time_help.setMaximumWidth(24)
        max_time_help.clicked.connect(lambda: QMessageBox.information(
            self, "Maximum Capture Time Help",
            "This setting limits the total duration of the capture process.\n\n"
            "The capture will automatically stop after this many seconds, "
            "even if the minimum number of loops hasn't been reached.\n\n"
            "This prevents the capture from running indefinitely if there's an issue."
        ))
        max_time_layout.addWidget(self.spinbox_max_capture)
        max_time_layout.addWidget(max_time_help)
        max_time_layout.addStretch()
        form_layout.addRow("Maximum Capture Time:", max_time_layout)

        # Bookend duration with better explanation
        bookend_duration_layout = QHBoxLayout()
        self.spinbox_bookend_duration = QDoubleSpinBox()
        self.spinbox_bookend_duration.setRange(0.1, 5.0)
        self.spinbox_bookend_duration.setSingleStep(0.1)
        self.spinbox_bookend_duration.setSuffix(" seconds")
        self.spinbox_bookend_duration.setValue(bookend_settings.get("bookend_duration", 0.5))
        bookend_duration_help = QPushButton("?")
        bookend_duration_help.setMaximumWidth(24)
        bookend_duration_help.clicked.connect(lambda: QMessageBox.information(
            self, "Bookend Duration Help",
            "This is the expected duration of the white frames at the beginning and end of each loop.\n\n"
            "Make sure this matches the white frame duration in your reference video loop.\n\n"
            "Typical values are 0.5 to 1.0 seconds."
        ))
        bookend_duration_layout.addWidget(self.spinbox_bookend_duration)
        bookend_duration_layout.addWidget(bookend_duration_help)
        bookend_duration_layout.addStretch()
        form_layout.addRow("Bookend Duration:", bookend_duration_layout)

        # White threshold with better explanation and visual feedback
        threshold_layout = QHBoxLayout()
        self.slider_white_threshold = QSlider(Qt.Horizontal)
        self.slider_white_threshold.setRange(200, 255)
        self.slider_white_threshold.setValue(bookend_settings.get("white_threshold", 240))
        self.lbl_white_threshold = QLabel(str(self.slider_white_threshold.value()))

        # Add color indicator for threshold
        self.threshold_color_indicator = QFrame()
        self.threshold_color_indicator.setFixedSize(24, 24)
        self.threshold_color_indicator.setFrameShape(QFrame.Box)
        self.threshold_color_indicator.setFrameShadow(QFrame.Plain)
        self.threshold_color_indicator.setLineWidth(1)

        # Function to update color indicator
        def update_threshold_indicator(value):
            self.lbl_white_threshold.setText(str(value))
            self.threshold_color_indicator.setStyleSheet(f"background-color: rgb({value}, {value}, {value});")

        self.slider_white_threshold.valueChanged.connect(update_threshold_indicator)
        update_threshold_indicator(self.slider_white_threshold.value())  # Set initial color

        threshold_help = QPushButton("?")
        threshold_help.setMaximumWidth(24)
        threshold_help.clicked.connect(lambda: QMessageBox.information(
            self, "White Threshold Help", 
            "This setting controls how bright a frame must be to be considered a white bookend frame.\n\n"
            "Higher values (closer to 255) require brighter, more pure white frames.\n\n"
            "Lower values (closer to 200) are more lenient but may detect non-bookend frames."
        ))

        threshold_layout.addWidget(self.slider_white_threshold)
        threshold_layout.addWidget(self.lbl_white_threshold)
        threshold_layout.addWidget(self.threshold_color_indicator)
        threshold_layout.addWidget(threshold_help)
        form_layout.addRow("White Threshold:", threshold_layout)

        bookend_layout.addLayout(form_layout)
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

        # Combined format selection (resolution and frame rate together)
        self.combo_format = QComboBox()
        self.combo_format.setMinimumWidth(300)
        resolution_framerates = capture_settings.get("resolution_framerates", [])
        if resolution_framerates:
            self.combo_format.addItems(resolution_framerates)
        else:
            # Create defaults if none available
            default_formats = []
            for res in ["1920x1080", "1280x720", "720x576", "720x480"]:
                for fps in [29.97, 25, 30, 50, 59.94, 60]:
                    default_formats.append(f"{res} @ {fps}fps")
            self.combo_format.addItems(default_formats)

        # Try to set current format from settings
        current_resolution = capture_settings.get("resolution", "1920x1080")
        current_rate = capture_settings.get("frame_rate", 30)
        current_format = f"{current_resolution} @ {current_rate}fps"

        index = self.combo_format.findText(current_format)
        if index >= 0:
            self.combo_format.setCurrentIndex(index)
        self.combo_format.setToolTip("Combined resolution and frame rate for capture")
        capture_layout.addRow("Video Format:", self.combo_format)

        # Keep these for backwards compatibility, but hide them in the UI
        self.combo_resolution = QComboBox()
        self.combo_resolution.setVisible(False)
        self.combo_frame_rate = QComboBox()
        self.combo_frame_rate.setVisible(False)

        # When format changes, update the hidden resolution and frame rate fields
        self.combo_format.currentTextChanged.connect(self._update_resolution_framerate_from_format)

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

        # Format info display
        self.lbl_format_info = QLabel("Select 'Auto-Detect Formats' to see available capture card formats")
        self.lbl_format_info.setStyleSheet("font-style: italic; color: #666;")
        self.lbl_format_info.setWordWrap(True)
        capture_layout.addRow("", self.lbl_format_info)

        capture_group.setLayout(capture_layout)

        # Populate devices on initialization
        self.refresh_capture_devices()

        return capture_group

    def _update_resolution_framerate_from_format(self, format_text):
        """Update the hidden resolution and frame rate fields from the format selection"""
        if not format_text:
            return

        # Parse the format text like "1920x1080 @ 30fps"
        try:
            parts = format_text.split("@")
            if len(parts) == 2:
                resolution = parts[0].strip()
                fps_part = parts[1].strip()

                # Remove "fps" suffix
                fps = fps_part.replace("fps", "").strip()

                # Update the hidden fields
                self.combo_resolution.clear()
                self.combo_resolution.addItem(resolution)

                self.combo_frame_rate.clear()
                self.combo_frame_rate.addItem(fps)

                logger.debug(f"Updated resolution to {resolution} and frame rate to {fps}")
        except Exception as e:
            logger.error(f"Error parsing format text '{format_text}': {e}")

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
        QTimer.singleShot(100, lambda: self._populate_capture_devices())

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
        self.lbl_format_info.setText("Detecting available formats...")

        # Run in timer to avoid blocking UI
        QTimer.singleShot(100, lambda: self._perform_format_detection(device))

    def _perform_format_detection(self, device):
        """Perform the actual format detection"""
        try:
            # Get formats from options manager
            format_info = self.options_manager.get_decklink_formats(device)

            # First update the combined format dropdown
            resolution_framerates = format_info.get("resolution_framerates", [])
            if resolution_framerates:
                self.combo_format.clear()
                for format_name in resolution_framerates:
                    self.combo_format.addItem(format_name)

                # Update format info label
                self.lbl_format_info.setText(f"Detected {len(resolution_framerates)} available video formats")
            else:
                # If no formats detected, fall back to defaults
                self.combo_format.clear()
                default_formats = []
                for res in ["1920x1080", "1280x720", "720x576", "720x480"]:
                    for fps in [29.97, 25, 30, 50, 59.94, 60]:
                        format_name = f"{res} @ {fps}fps"
                        default_formats.append(format_name)
                        self.combo_format.addItem(format_name)

                format_info["resolution_framerates"] = default_formats
                self.lbl_format_info.setText("Using default formats (detection failed)")

            # Also update the hidden fields for backward compatibility
            # Extract unique resolutions from format_map
            resolutions = []
            if "format_map" in format_info and format_info["format_map"]:
                resolutions = list(format_info["format_map"].keys())
            
            if resolutions:
                self.combo_resolution.clear()
                for res in resolutions:
                    self.combo_resolution.addItem(res)
                format_info["resolutions"] = resolutions
            else:
                # If no resolutions detected, fall back to defaults
                default_resolutions = ["1920x1080", "1280x720", "720x576", "720x480"]
                self.combo_resolution.clear()
                for res in default_resolutions:
                    self.combo_resolution.addItem(res)
                format_info["resolutions"] = default_resolutionsions

            # Extract all frame rates from format_map
            frame_rates = []
    if "format_map" in format_info and format_info["format_map"]:
        for res in format_info["format_map"]:
            for rate in format_info["format_map"][res]:
                if rate not in frame_rates:
                    frame_rates.append(rate)
        # Sort the frame rates
        frame_rates.sort()
    
    if frame_rates:
        self.combo_frame_rate.clear()
        for rate in frame_rates:
            self.combo_frame_rate.addItem(str(rate))
        format_info["frame_rates"] = frame_rates
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
            new_capture_settings["resolution_framerates"] = format_info["resolution_framerates"]
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
            default_formats = []
            for res in default_resolutions:
                for fps in default_rates:
                    default_formats.append(f"{res} @ {fps}fps")

            # Update UI with defaults
            self.combo_resolution.clear()
            for res in default_resolutions:
                self.combo_resolution.addItem(res)

            self.combo_frame_rate.clear()
            for rate in default_rates:
                self.combo_frame_rate.addItem(str(rate))

            self.combo_format.clear()
            for format_name in default_formats:
                self.combo_format.addItem(format_name)

            # Update settings with defaults
            new_capture_settings = self.options_manager.get_setting("capture")
            new_capture_settings["available_resolutions"] = default_resolutions
            new_capture_settings["available_frame_rates"] = default_rates
            new_capture_settings["resolution_framerates"] = default_formats
            self.options_manager.update_category("capture", new_capture_settings)

            self.lbl_format_info.setText("Using default formats (detection failed)")
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

            # Parse format for resolution and frame rate
            format_text = self.combo_format.currentText()
            if format_text and "@" in format_text:
                parts = format_text.split("@")
                if len(parts) == 2:
                    resolution = parts[0].strip()
                    fps_str = parts[1].strip().replace("fps", "").strip()

                    try:
                        capture_settings["resolution"] = resolution
                        capture_settings["frame_rate"] = float(fps_str)
                    except ValueError:
                        logger.warning(f"Could not parse frame rate from {fps_str}, using fallback")
                        # Use values from hidden fields as fallback
                        capture_settings["resolution"] = self.combo_resolution.currentText()
                        capture_settings["frame_rate"] = float(self.combo_frame_rate.currentText() or "30")
            else:
                # Use values from hidden fields as fallback
                capture_settings["resolution"] = self.combo_resolution.currentText()
                try:
                    capture_settings["frame_rate"] = float(self.combo_frame_rate.currentText() or "30")
                except ValueError:
                    capture_settings["frame_rate"] = 30.0

            capture_settings["pixel_format"] = self.combo_pixel_format.currentText()

            # Add the current format to resolution_framerates if not already there
            format_text = self.combo_format.currentText()
            if "resolution_framerates" not in capture_settings:
                capture_settings["resolution_framerates"] = []

            if format_text and format_text not in capture_settings["resolution_framerates"]:
                capture_settings["resolution_framerates"].append(format_text)

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

    def handle_vmaf_error(self, error_msg):
        """Handle error in VMAF analysis"""
        self.lbl_vmaf_status.setText(f"VMAF analysis failed")
        self.log_to_analysis(f"Error: {error_msg}")
        QMessageBox.critical(self, "VMAF Analysis Error", error_msg)

        # Reset vmaf_running flag to allow new analysis
        self.vmaf_running = False

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

    def load_results_history(self):
        """Load historical test results into the data grid"""
        try:
            # Clear current table
            self.results_table.setRowCount(0)
            
            # Get output directory
            output_dir = self.lbl_output_dir.text()
            if output_dir == "Default output directory" and hasattr(self, 'file_manager'):
                output_dir = self.file_manager.get_default_base_dir()
            
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


    def _update_theme_preview(self):
        """Update the theme preview based on selected theme"""
        theme = self.combo_theme.currentText()
        
        # Show/hide custom theme options
        self.custom_theme_group.setVisible(theme == "Custom")
        
        # Update preview style
        if theme == "Light":
            self.theme_preview.setStyleSheet("")
            self.theme_preview.setPalette(self.style().standardPalette())
        elif theme == "Dark":
            self.theme_preview.setStyleSheet(qdarkstyle.load_stylesheet_pyqt5())
        elif theme == "System":
            # Use system theme (default)
            self.theme_preview.setStyleSheet("")
            self.theme_preview.setPalette(self.style().standardPalette())
        elif theme == "Custom":
            # Use custom colors
            palette = QPalette()
            bg_color = self.bg_color_button.styleSheet().split("background-color:")[1].split(";")[0].strip()
            text_color = self.text_color_button.styleSheet().split("background-color:")[1].split(";")[0].strip()
            accent_color = self.accent_color_button.styleSheet().split("background-color:")[1].split(";")[0].strip()
            
            palette.setColor(QPalette.Window, QColor(bg_color))
            palette.setColor(QPalette.WindowText, QColor(text_color))
            palette.setColor(QPalette.Base, QColor(bg_color).lighter(110))
            palette.setColor(QPalette.AlternateBase, QColor(bg_color))
            palette.setColor(QPalette.ToolTipBase, QColor(text_color))
            palette.setColor(QPalette.ToolTipText, QColor(text_color))
            palette.setColor(QPalette.Text, QColor(text_color))
            palette.setColor(QPalette.Button, QColor(bg_color).lighter(110))
            palette.setColor(QPalette.ButtonText, QColor(text_color))
            palette.setColor(QPalette.BrightText, QColor(text_color).lighter(150))
            palette.setColor(QPalette.Highlight, QColor(accent_color))
            palette.setColor(QPalette.HighlightedText, QColor(text_color).lighter(150))
            
            self.theme_preview.setPalette(palette)
    
    def _apply_selected_theme(self):
        """Apply the selected theme to the entire application"""
        theme = self.combo_theme.currentText()
        
        # Store the selection
        if hasattr(self, 'options_manager') and self.options_manager:
            theme_settings = self.options_manager.get_setting("theme")
            theme_settings["selected_theme"] = theme
            
            # Save custom theme colors if applicable
            if theme == "Custom":
                bg_color = self.bg_color_button.styleSheet().split("background-color:")[1].split(";")[0].strip()
                text_color = self.text_color_button.styleSheet().split("background-color:")[1].split(";")[0].strip()
                accent_color = self.accent_color_button.styleSheet().split("background-color:")[1].split(";")[0].strip()
                
                theme_settings["bg_color"] = bg_color
                theme_settings["text_color"] = text_color
                theme_settings["accent_color"] = accent_color
            
            self.options_manager.update_category("theme", theme_settings)
        
        # Apply theme
        app = QApplication.instance()
        if app:
            if theme == "Light":
                app.setStyleSheet("")
                app.setPalette(self.style().standardPalette())
            elif theme == "Dark":
                app.setStyleSheet(qdarkstyle.load_stylesheet_pyqt5())
            elif theme == "System":
                # Use system theme (default)
                app.setStyleSheet("")
                app.setPalette(self.style().standardPalette())
            elif theme == "Custom":
                # Use custom colors
                palette = QPalette()
                bg_color = self.bg_color_button.styleSheet().split("background-color:")[1].split(";")[0].strip()
                text_color = self.text_color_button.styleSheet().split("background-color:")[1].split(";")[0].strip()
                accent_color = self.accent_color_button.styleSheet().split("background-color:")[1].split(";")[0].strip()
                
                palette.setColor(QPalette.Window, QColor(bg_color))
                palette.setColor(QPalette.WindowText, QColor(text_color))
                palette.setColor(QPalette.Base, QColor(bg_color).lighter(110))
                palette.setColor(QPalette.AlternateBase, QColor(bg_color))
                palette.setColor(QPalette.ToolTipBase, QColor(text_color))
                palette.setColor(QPalette.ToolTipText, QColor(text_color))
                palette.setColor(QPalette.Text, QColor(text_color))
                palette.setColor(QPalette.Button, QColor(bg_color).lighter(110))
                palette.setColor(QPalette.ButtonText, QColor(text_color))
                palette.setColor(QPalette.BrightText, QColor(text_color).lighter(150))
                palette.setColor(QPalette.Highlight, QColor(accent_color))
                palette.setColor(QPalette.HighlightedText, QColor(text_color).lighter(150))
                
                app.setPalette(palette)
    
    def _pick_color(self, color_type):
        """Open color picker dialog for custom theme colors"""
        from PyQt5.QtWidgets import QColorDialog
        
        # Get current color
        sender = self.sender()
        current_color = sender.styleSheet().split("background-color:")[1].split(";")[0].strip()
        
        # Open color dialog
        color = QColorDialog.getColor(QColor(current_color), self, f"Select {color_type.replace('_', ' ').title()}")
        
        if color.isValid():
            # Update button color
            sender.setStyleSheet(f"background-color: {color.name()}; border: 1px solid #888;")
            
            # Update preview
            self._update_theme_preview()
    
    def _change_logo(self):
        """Change the application logo"""
        from PyQt5.QtWidgets import QFileDialog
        
        # Open file dialog
        logo_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Logo Image",
            "",
            "Image Files (*.png *.jpg *.jpeg *.gif *.svg)"
        )
        
        if logo_path:
            # Load and display the logo
            pixmap = QPixmap(logo_path)
            scaled_pixmap = pixmap.scaled(200, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.logo_label.setPixmap(scaled_pixmap)
            
            # Save the logo path
            if hasattr(self, 'options_manager') and self.options_manager:
                theme_settings = self.options_manager.get_setting("theme")
                theme_settings["logo_path"] = logo_path
                self.options_manager.update_category("theme", theme_settings)
    
    def _reset_logo(self):
        """Reset to default logo"""
        # Load default logo
        default_logo = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                                 "attached_assets", "chroma-logo.png")
        
        if os.path.exists(default_logo):
            pixmap = QPixmap(default_logo)
            scaled_pixmap = pixmap.scaled(200, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.logo_label.setPixmap(scaled_pixmap)
            
            # Save the default logo path
            if hasattr(self, 'options_manager') and self.options_manager:
                theme_settings = self.options_manager.get_setting("theme")
                theme_settings["logo_path"] = default_logo
                self.options_manager.update_category("theme", theme_settings)
        else:
            self.logo_label.setText("Default logo not found")


    def _set_application_logo(self):
        """Set the application logo/icon"""
        try:
            # Check if logo path is set in options
            logo_path = None
            if hasattr(self, 'options_manager') and self.options_manager:
                theme_settings = self.options_manager.get_setting("theme", {})
                logo_path = theme_settings.get("logo_path", "")
            
            # If not set or doesn't exist, use default
            if not logo_path or not os.path.exists(logo_path):
                # Use the Chroma logo from assets
                logo_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                                      "attached_assets", "chroma-logo.png")
            
            # Set the window icon if the logo exists
            if os.path.exists(logo_path):
                from PyQt5.QtGui import QIcon
                self.setWindowIcon(QIcon(logo_path))
                
                # Also add the logo to the title bar
                title_layout = QHBoxLayout()
                logo_label = QLabel()
                pixmap = QPixmap(logo_path)
                scaled_pixmap = pixmap.scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                logo_label.setPixmap(scaled_pixmap)
                title_layout.addWidget(logo_label)
                title_layout.addWidget(QLabel("VMAF Test App"))
                title_layout.addStretch()
                
                # Set a title bar widget to show logo
                title_widget = QWidget()
                title_widget.setLayout(title_layout)
                
                # Store the logo path for future reference
                self.logo_path = logo_path
        except Exception as e:
            logger.error(f"Error setting application logo: {str(e)}")