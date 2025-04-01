import sys
import os
import logging
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                           QPushButton, QLabel, QComboBox, QProgressBar, QFileDialog,
                           QGroupBox, QMessageBox, QTabWidget, QSpinBox, QCheckBox,
                           QStatusBar, QSplitter, QTextEdit, QListWidget, QListWidgetItem,
                           QStyle, QStackedWidget, QFormLayout)  # Added QStackedWidget and QFormLayout
from PyQt5.QtCore import Qt, pyqtSlot, QSize, QTimer
from PyQt5.QtGui import QPixmap, QImage
import cv2

# Import application modules with proper relative imports
from .reference_analyzer import ReferenceAnalyzer, ReferenceAnalysisThread
from .capture import CaptureManager, CaptureState
from .alignment import VideoAligner, AlignmentThread
from .analysis import VMAFAnalyzer, VMAFAnalysisThread
from .improved_file_manager import ImprovedFileManager
from .frame_alignment import align_videos_frame_perfect, get_video_info
from .improved_vmaf_analyzer import ImprovedVMAFAnalyzer, ImprovedVMAFAnalysisThread
from .improved_file_manager import ImprovedFileManager

logger = logging.getLogger(__name__)

class VMafTestApp(QMainWindow):
    """Main application window for VMAF Test App"""
    def __init__(self):
        super().__init__()
        
        # Set up logger
        self._setup_logging()
        
        # Create improved file manager with tests/test_results as base dir
        base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests", "test_results")
        os.makedirs(base_dir, exist_ok=True)
        self.file_manager = ImprovedFileManager(base_dir=base_dir)
        logger.info(f"Using test results directory: {base_dir}")
        
        # Initialize managers
        self.reference_analyzer = ReferenceAnalyzer()
        self.capture_manager = CaptureManager()
        self.video_aligner = VideoAligner()
        self.vmaf_analyzer = VMAFAnalyzer()
        
        # Share file manager with capture manager 
        self.capture_manager.path_manager = self.file_manager
        
        # Set up UI
        self._setup_ui()
        self._connect_signals()
        
        # State variables
        self.reference_info = None
        self.capture_path = None
        self.aligned_paths = None
        self.vmaf_results = None
        
        logger.info("VMAF Test App initialized")
        
    def _setup_logging(self):
        """Configure logging"""
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        logging.basicConfig(
            level=logging.INFO,
            format=log_format,
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler('vmaf_app.log')
            ]
        )
        
    def _setup_ui(self):
        """Set up the application UI"""
        self.setWindowTitle("VMAF Test App")
        self.setGeometry(100, 100, 1000, 800)
        
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
        
        self.tabs.addTab(self.setup_tab, "Setup")
        self.tabs.addTab(self.capture_tab, "Capture")
        self.tabs.addTab(self.analysis_tab, "Analysis")
        self.tabs.addTab(self.results_tab, "Results")
        
        # Set up each tab
        self._setup_setup_tab()
        self._setup_capture_tab()
        self._setup_analysis_tab()
        self._setup_results_tab()
        
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
        """Set up the Capture tab with fixed log window heights"""
        layout = QVBoxLayout(self.capture_tab)
        
        # Summary of setup
        self.lbl_capture_summary = QLabel("No reference video selected")
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
        device_select_layout.addWidget(QLabel("Device:"))
        self.device_combo = QComboBox()
        self.device_combo.addItem("Intensity Shuttle", "Intensity Shuttle")
        device_select_layout.addWidget(self.device_combo)
        self.btn_refresh_devices = QPushButton("Refresh")
        self.btn_refresh_devices.clicked.connect(self.refresh_devices)
        device_select_layout.addWidget(self.btn_refresh_devices)
        device_layout.addLayout(device_select_layout)
        
        # Add to group
        device_group.setLayout(device_layout)
        left_layout.addWidget(device_group)
        
        # Capture method selection
        method_group = QGroupBox("Capture Method")
        method_layout = QVBoxLayout()
        
        method_select_layout = QHBoxLayout()
        method_select_layout.addWidget(QLabel("Method:"))
        self.capture_method_combo = QComboBox()
        self.capture_method_combo.addItem("Trigger Detection", "trigger")
        self.capture_method_combo.addItem("White Bookend Frames", "bookend")
        self.capture_method_combo.currentIndexChanged.connect(self.on_capture_method_changed)
        method_select_layout.addWidget(self.capture_method_combo)
        method_layout.addLayout(method_select_layout)
        
        # Stacked widget to show different settings based on capture method
        self.capture_settings_stack = QStackedWidget()
        
        # 1. Trigger detection settings
        trigger_widget = QWidget()
        trigger_layout = QVBoxLayout(trigger_widget)
        
        self.cb_use_trigger = QCheckBox("Wait for 'STARTING' trigger frame")
        self.cb_use_trigger.setChecked(True)
        trigger_layout.addWidget(self.cb_use_trigger)
        
        trigger_settings = QHBoxLayout()
        trigger_settings.addWidget(QLabel("Threshold:"))
        self.sb_trigger_threshold = QSpinBox()
        self.sb_trigger_threshold.setRange(50, 95)
        self.sb_trigger_threshold.setValue(85)
        self.sb_trigger_threshold.setSuffix("%")
        trigger_settings.addWidget(self.sb_trigger_threshold)
        
        trigger_settings.addWidget(QLabel("Consecutive frames:"))
        self.sb_trigger_frames = QSpinBox()
        self.sb_trigger_frames.setRange(1, 10)
        self.sb_trigger_frames.setValue(2)  # Changed default to 2
        trigger_settings.addWidget(self.sb_trigger_frames)
        
        trigger_layout.addLayout(trigger_settings)
        self.capture_settings_stack.addWidget(trigger_widget)
        
        # 2. Bookend method settings
        bookend_widget = QWidget()
        bookend_layout = QVBoxLayout(bookend_widget)
        
        bookend_info = QLabel(
            "This method captures a looped video with white bookend frames.\n"
            "The player should loop the video with 0.5s white frames at the end.\n"
            "Capture will continue until at least two white frame sections are detected."
        )
        bookend_info.setWordWrap(True)
        bookend_layout.addWidget(bookend_info)
        
        bookend_settings = QHBoxLayout()
        bookend_settings.addWidget(QLabel("White threshold:"))
        self.sb_bookend_threshold = QSpinBox()
        self.sb_bookend_threshold.setRange(200, 250)
        self.sb_bookend_threshold.setValue(230)
        bookend_settings.addWidget(self.sb_bookend_threshold)
        
        bookend_settings.addStretch()
        bookend_layout.addLayout(bookend_settings)
        
        self.capture_settings_stack.addWidget(bookend_widget)
        
        # Add the stacked widget to the method layout
        method_layout.addWidget(self.capture_settings_stack)
        
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
        
        # Preview at the top
        preview_group = QGroupBox("Video Preview")
        preview_layout = QVBoxLayout()
        
        self.lbl_preview = QLabel("No video feed")
        self.lbl_preview.setAlignment(Qt.AlignCenter)
        self.lbl_preview.setMinimumSize(480, 270)
        self.lbl_preview.setStyleSheet("background-color: #e0e0e0; color: black;")  # Light grey background
        preview_layout.addWidget(self.lbl_preview)
        
        preview_group.setLayout(preview_layout)
        right_layout.addWidget(preview_group)
        
        # Capture log at the bottom with fixed height
        log_group = QGroupBox("Capture Log")
        log_layout = QVBoxLayout()
        self.txt_capture_log = QTextEdit()
        self.txt_capture_log.setReadOnly(True)
        self.txt_capture_log.setLineWrapMode(QTextEdit.WidgetWidth)  # Enable line wrapping
        self.txt_capture_log.setMinimumHeight(150)
        self.txt_capture_log.setMaximumHeight(200)  # Fix height to prevent stretching
        log_layout.addWidget(self.txt_capture_log)
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

    def start_capture(self):
        """Start the capture process with better progress monitoring"""
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
        self.log_to_capture("Starting capture process...")
        
        # Get output directory and test name
        output_dir = self.lbl_output_dir.text()
        if output_dir == "Default output directory":
            output_dir = self.file_manager.get_default_base_dir()
        
        # Add timestamp prefix to test name to prevent overwriting
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_test_name = self.txt_test_name.currentText()
        test_name = f"{timestamp}_{base_test_name}"
        
        self.log_to_capture(f"Using test name with timestamp: {test_name}")
        
        # Update file manager base directory
        self.file_manager.base_dir = output_dir
        
        # Set output information in capture manager
        self.capture_manager.set_output_directory(output_dir)
        self.capture_manager.set_test_name(test_name)
        
        # Set reference info
        self.capture_manager.set_reference_video(self.reference_info)
        
        # Get the selected capture method
        method = self.capture_method_combo.currentData()
        
        if method == "trigger":
            # Use trigger-based capture
            if self.cb_use_trigger.isChecked():
                self.log_to_capture("Waiting for trigger frame...")
                
                # Get trigger settings from UI
                threshold = self.sb_trigger_threshold.value() / 100.0  # Convert percentage to decimal
                consecutive_frames = self.sb_trigger_frames.value()
                
                # Start trigger detection with settings
                self.capture_manager.start_trigger_detection(
                    device_name,
                    threshold=threshold,
                    consecutive_frames=consecutive_frames
                )
            else:
                self.log_to_capture("Starting direct capture...")
                
                # Start capture directly
                self.capture_manager.start_capture(device_name)
        else:
            # Use bookend-based capture
            self.log_to_capture("Starting bookend frame capture mode...")
            
            # Get settings from UI if needed
            # bookend_threshold = self.sb_bookend_threshold.value()
            
            # Start bookend capture
            self.capture_manager.start_bookend_capture(device_name)

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
        
        # Alignment method selection
        alignment_layout = QHBoxLayout()
        alignment_layout.addWidget(QLabel("Alignment Method:"))
        self.combo_alignment_method = QComboBox()
        self.combo_alignment_method.addItem("Content-based", "content")
        self.combo_alignment_method.addItem("White Bookend", "bookend")
        alignment_layout.addWidget(self.combo_alignment_method)
        settings_row.addLayout(alignment_layout)
        
        settings_row.addSpacing(10)
        
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
        self.btn_run_combined_analysis = QPushButton("Run Video Alignment and VMAF Analysis")
        self.btn_run_combined_analysis.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.btn_run_combined_analysis.setEnabled(False)
        self.btn_run_combined_analysis.clicked.connect(self.run_combined_analysis)
        actions_row.addWidget(self.btn_run_combined_analysis)
        
        # Or run them separately
        actions_row.addWidget(QLabel("or"))
        
        # Individual buttons
        self.btn_align_videos = QPushButton("1. Align Videos")
        self.btn_align_videos.clicked.connect(self.align_videos)
        self.btn_align_videos.setEnabled(False)
        actions_row.addWidget(self.btn_align_videos)
        
        self.btn_run_vmaf = QPushButton("2. Run VMAF Analysis")
        self.btn_run_vmaf.clicked.connect(self.run_vmaf_analysis)
        self.btn_run_vmaf.setEnabled(False)
        actions_row.addWidget(self.btn_run_vmaf)
        
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
        self.btn_align_videos.setEnabled(False)
        self.btn_run_vmaf.setEnabled(False)
        
        # Start the alignment process
        self.align_videos_for_combined_workflow()

    def align_videos_for_combined_workflow(self):
        """Start video alignment as part of the combined workflow using selected method"""
        # Get selected alignment method
        alignment_method = self.combo_alignment_method.currentData()
        
        self.log_to_analysis(f"Starting video alignment using {alignment_method} method...")
        
        if alignment_method == "bookend":
            # Import BookendAlignmentThread
            from .bookend_alignment import BookendAlignmentThread
            
            # Create bookend alignment thread
            self.alignment_thread = BookendAlignmentThread(
                self.reference_info['path'],
                self.capture_path
            )
            
            # Log bookend method usage
            self.log_to_analysis("Using white bookend frame alignment method")
        else:
            # Default to content-based alignment
            self.alignment_thread = AlignmentThread(
                self.reference_info['path'],
                self.capture_path
            )
            
            # Log content method usage
            self.log_to_analysis("Using content-based alignment method")
        
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
            f"Aligned with offset: {offset_frames} frames ({offset_seconds:.3f}s), conf: {confidence:.2f}"
        )
        self.log_to_analysis(f"Alignment complete! Offset: {offset_frames} frames")
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
            self.btn_align_videos.setEnabled(True)
            self.btn_run_vmaf.setEnabled(True)
            
            # Show error to user
            QMessageBox.critical(self, "VMAF Error", error_msg)
        
    def start_vmaf_for_combined_workflow(self):
        """Start VMAF analysis as part of combined workflow"""
        # Reset VMAF progress
        self.pb_vmaf_progress.setValue(0)
        
        # Create analysis thread using previously stored settings
        # Make sure proper imports are at the top of this file
        from .analysis import VMAFAnalysisThread
        
        self.vmaf_thread = VMAFAnalysisThread(
            self.aligned_paths['reference'],
            self.aligned_paths['captured'],
            self.selected_model,
            self.selected_duration
        )
        
        # Connect signals
        self.vmaf_thread.analysis_progress.connect(self.handle_vmaf_progress)
        self.vmaf_thread.status_update.connect(self.log_to_analysis)
        self.vmaf_thread.error_occurred.connect(self.handle_vmaf_error)
        self.vmaf_thread.analysis_complete.connect(self.handle_vmaf_complete)
        
        # Start analysis
        self.vmaf_thread.start()

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
 
    def update_capture_progress(self, progress):
        """Handle capture progress updates with proper scale"""
        if isinstance(progress, int):
            # Ensure progress is between 0-100
            scaled_progress = min(100, max(0, progress))
            self.pb_capture_progress.setValue(scaled_progress)
        else:
            # Just in case we receive non-int progress
            self.pb_capture_progress.setValue(0)

    def _connect_signals(self):
        """Connect signals to handlers with improved progress tracking"""
        # Capture manager signals
        self.capture_manager.status_update.connect(self.update_capture_status)
        self.capture_manager.progress_update.connect(self.update_capture_progress)
        self.capture_manager.state_changed.connect(self.handle_capture_state_change)
        self.capture_manager.capture_started.connect(self.handle_capture_started)
        self.capture_manager.capture_finished.connect(self.handle_capture_finished)
        self.capture_manager.trigger_frame_available.connect(self.update_preview)
       
    def browse_reference(self):
        """Browse for reference video file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Reference Video", "", "Video Files (*.mp4 *.mov *.avi *.mkv)"
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
        has_trigger = info.get('has_trigger', False)
        
        details = (f"Duration: {duration:.2f}s ({total_frames} frames), " + 
                f"Resolution: {width}x{height}, {frame_rate:.2f} fps")
                
        if has_trigger:
            details += "\nTrigger frame detected at beginning"
            
        self.lbl_reference_details.setText(details)
        
        # Update setup status
        self.lbl_setup_status.setText("Reference video loaded successfully")
        
        # Enable next buttons
        self.btn_next_to_capture.setEnabled(True)
        
        # Update capture tab
        self.lbl_capture_summary.setText(f"Reference: {os.path.basename(info['path'])}\n{details}")
        
        # Populate the duration combo box with 1-second increments
        # up to the reference video duration
        self.combo_duration.clear()
        self.combo_duration.addItem("Full Video", "full")
        
        # Add 1-second increments
        max_seconds = int(duration)
        for i in range(1, max_seconds + 1):
            self.combo_duration.addItem(f"{i} seconds", i)
        
        self.log_to_setup("Reference video analysis complete")

    def handle_reference_error(self, error_msg):
        """Handle error in reference video analysis"""
        self.log_to_setup(f"Error: {error_msg}")
        QMessageBox.critical(self, "Reference Analysis Error", error_msg)
        
    def add_trigger_to_reference(self):
        """Add white 'STARTING' trigger frame to reference video"""
        if not self.reference_info:
            return
            
        # TODO: Implement trigger frame addition
        QMessageBox.information(self, "Not Implemented", 
                              "Adding trigger frames is not yet implemented")

    def browse_output_dir(self):
        """Browse for output directory (always uses test_results)"""
        # Always use the default test_results directory
        default_dir = self.file_manager.get_default_base_dir()
        
        # Show the browser but only for visual confirmation
        directory = QFileDialog.getExistingDirectory(
            self, "Select Output Directory", default_dir
        )
        
        # Always use test_results regardless of selection
        self.lbl_output_dir.setText(default_dir)
        self.lbl_output_dir.setToolTip(default_dir)
        
        # Update file manager base directory (even though it should already be set)
        self.file_manager.base_dir = default_dir
        
        # Update capture manager
        self.capture_manager.set_output_directory(default_dir)
        
        # Show message about standard directory
        self.log_to_setup(f"Using standard output directory: {default_dir}")
        logger.info(f"Output directory set/confirmed: {default_dir}")
       
    def refresh_devices(self):
        """Refresh list of capture devices"""
        self.device_combo.clear()
        self.device_combo.addItem("Detecting devices...")
        
        # For now, just hardcode the Intensity Shuttle
        # In a full implementation, this would scan for connected devices
        QTimer.singleShot(500, self._populate_dummy_devices)
        
    def _populate_dummy_devices(self):
        """Populate device dropdown with dummy devices"""
        self.device_combo.clear()
        self.device_combo.addItem("Intensity Shuttle", "Intensity Shuttle")
 

    def start_capture(self):
        """Start the capture process"""
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
        self.log_to_capture("Starting capture process...")
        
        # Get output directory and test name
        output_dir = self.lbl_output_dir.text()
        if output_dir == "Default output directory":
            output_dir = self.file_manager.get_default_base_dir()
        
        # Add timestamp prefix to test name to prevent overwriting
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_test_name = self.txt_test_name.currentText()
        test_name = f"{timestamp}_{base_test_name}"
        
        self.log_to_capture(f"Using test name with timestamp: {test_name}")
        
        # Update file manager base directory
        self.file_manager.base_dir = output_dir
        
        # Set output information in capture manager
        self.capture_manager.set_output_directory(output_dir)
        self.capture_manager.set_test_name(test_name)
        
        # Set reference info
        self.capture_manager.set_reference_video(self.reference_info)
        
        # Check if we should use trigger detection
        if self.cb_use_trigger.isChecked():
            self.log_to_capture("Waiting for trigger frame...")
            
            # Get trigger settings from UI
            threshold = self.sb_trigger_threshold.value() / 100.0  # Convert percentage to decimal
            consecutive_frames = self.sb_trigger_frames.value()
            
            # Start trigger detection with settings
            self.capture_manager.start_trigger_detection(
                device_name,
                threshold=threshold,
                consecutive_frames=consecutive_frames
            )
        else:
            self.log_to_capture("Starting direct capture...")
            
            # Start capture directly
            self.capture_manager.start_capture(device_name)
 
    def stop_capture(self):
        """Stop the capture process"""
        self.log_to_capture("Stopping capture...")
        self.capture_manager.stop_capture(cleanup_temp=True)
        
        # Reset progress bar to avoid stuck state
        self.pb_capture_progress.setValue(0)
     
    def update_capture_status(self, status_text):
        """Update capture status label"""
        self.lbl_capture_status.setText(status_text)
        self.log_to_capture(status_text)
        
    def handle_capture_state_change(self, state):
        """Handle changes in capture state"""
        state_text = f"Capture state: {state.name}"
        self.log_to_capture(state_text)
        
    def handle_capture_started(self):
        """Handle capture start"""
        self.btn_start_capture.setEnabled(False)
        self.btn_stop_capture.setEnabled(True)
  
    def handle_capture_finished(self, success, result):
        """Handle capture completion with better button management"""
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
                            

    def on_capture_method_changed(self, index):
        """Handle change in capture method selection"""
        method = self.capture_method_combo.currentData()
        self.capture_settings_stack.setCurrentIndex(index)
        
        if hasattr(self, 'capture_manager'):
            self.capture_manager.set_capture_method(method)
            
        self.log_to_capture(f"Capture method changed to: {method}")
        
    def handle_capture_finished(self, success, result):
        """Handle capture completion with better button management"""
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
            self.btn_align_videos.setEnabled(True)
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
        
    def align_videos(self):
        """Start video alignment process using selected method"""
        if not self.reference_info or not self.capture_path:
            self.log_to_analysis("Missing reference or captured video")
            return
            
        # Get selected alignment method
        alignment_method = self.combo_alignment_method.currentData()
        
        self.log_to_analysis(f"Starting video alignment using {alignment_method} method...")
        self.pb_alignment_progress.setValue(0)
        self.lbl_alignment_status.setText("Aligning videos...")
        
        if alignment_method == "bookend":
            # Import BookendAlignmentThread
            from .bookend_alignment import BookendAlignmentThread
            
            # Create bookend alignment thread
            self.alignment_thread = BookendAlignmentThread(
                self.reference_info['path'],
                self.capture_path
            )
            
            # Log bookend method usage
            self.log_to_analysis("Using white bookend frame alignment method")
        else:
            # Default to content-based alignment
            self.alignment_thread = AlignmentThread(
                self.reference_info['path'],
                self.capture_path
            )
            
            # Log content method usage
            self.log_to_analysis("Using content-based alignment method")
        
        # Connect signals
        self.alignment_thread.alignment_progress.connect(self.pb_alignment_progress.setValue)
        self.alignment_thread.status_update.connect(self.log_to_analysis)
        self.alignment_thread.error_occurred.connect(self.handle_alignment_error)
        self.alignment_thread.alignment_complete.connect(self.handle_alignment_complete)
        
        # Start alignment
        self.alignment_thread.start()
        
    def handle_alignment_complete(self, results):
        """Handle completion of video alignment"""
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
            f"Aligned with offset: {offset_frames} frames ({offset_seconds:.3f}s), conf: {confidence:.2f}"
        )
        self.log_to_analysis(f"Alignment complete! Offset: {offset_frames} frames")
        self.log_to_analysis(f"Aligned reference: {os.path.basename(aligned_reference)}")
        self.log_to_analysis(f"Aligned captured: {os.path.basename(aligned_captured)}")
        
        # Enable VMAF analysis
        self.btn_run_vmaf.setEnabled(True)
        
    def handle_alignment_error(self, error_msg):
        """Handle error in video alignment"""
        self.lbl_alignment_status.setText(f"Alignment failed")
        self.log_to_analysis(f"Error: {error_msg}")
        QMessageBox.critical(self, "Alignment Error", error_msg)

    def run_vmaf_analysis(self):
        """Start VMAF analysis"""
        if not self.aligned_paths:
            self.log_to_analysis("No aligned videos available")
            return
            
        # Get VMAF model and duration settings
        model = self.combo_vmaf_model.currentData()
        duration_option = self.combo_duration.currentData()
        
        # Convert duration option to seconds
        if duration_option == "full":
            duration = None
        else:
            duration = float(duration_option)
            
        self.log_to_analysis(f"Starting VMAF analysis with model: {model}")
        self.log_to_analysis(f"Duration: {duration if duration else 'Full video'}")
        
        # Reset progress
        self.pb_vmaf_progress.setValue(0)
        self.lbl_vmaf_status.setText("Running VMAF analysis...")
        
        # Disable buttons during analysis
        self.btn_run_combined_analysis.setEnabled(False)
        self.btn_align_videos.setEnabled(False)
        self.btn_run_vmaf.setEnabled(False)
        
        # Create analysis thread
        self.vmaf_thread = VMAFAnalysisThread(
            self.aligned_paths['reference'],
            self.aligned_paths['captured'],
            model,
            duration
        )
        
        # Connect signals
        self.vmaf_thread.analysis_progress.connect(self.handle_vmaf_progress)
        self.vmaf_thread.status_update.connect(self.log_to_analysis)
        self.vmaf_thread.error_occurred.connect(self.handle_vmaf_error)
        self.vmaf_thread.analysis_complete.connect(self.handle_vmaf_complete)
        
        # Start analysis
        self.vmaf_thread.start()

    def handle_vmaf_progress(self, progress):
        """Handle VMAF progress updates, ensuring proper range"""
        if isinstance(progress, int):
            # Ensure progress is between 0-100
            scaled_progress = min(100, max(0, progress))
            self.pb_vmaf_progress.setValue(scaled_progress)
        else:
            # Just in case we receive non-int progress
            self.pb_vmaf_progress.setValue(0)

    def handle_vmaf_complete(self, results):
        """Handle completion of VMAF analysis"""
        self.vmaf_results = results
        
        vmaf_score = results.get('vmaf_score')
        psnr = results.get('psnr')
        ssim = results.get('ssim')
        
        # Re-enable buttons
        self.btn_run_combined_analysis.setEnabled(True)
        self.btn_align_videos.setEnabled(True)
        self.btn_run_vmaf.setEnabled(True)
        
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
            item = QListWidgetItem(f"Aligned Reference: {os.path.basename(ref_path)}")
            item.setData(Qt.UserRole, ref_path)
            self.list_result_files.addItem(item)
            
        dist_path = results.get('distorted_path')
        if dist_path and os.path.exists(dist_path):
            item = QListWidgetItem(f"Aligned Captured: {os.path.basename(dist_path)}")
            item.setData(Qt.UserRole, dist_path)
            self.list_result_files.addItem(item)
            
    def handle_vmaf_error(self, error_msg):
        """Handle error in VMAF analysis"""
        self.lbl_vmaf_status.setText(f"VMAF analysis failed")
        self.log_to_analysis(f"Error: {error_msg}")
        QMessageBox.critical(self, "VMAF Analysis Error", error_msg)
        
        # Re-enable buttons after error
        self.btn_run_combined_analysis.setEnabled(True)
        self.btn_align_videos.setEnabled(True)
        self.btn_run_vmaf.setEnabled(self.aligned_paths is not None)

    def handle_vmaf_complete(self, results):
        """Handle completion of VMAF analysis"""
        self.vmaf_results = results
        
        vmaf_score = results.get('vmaf_score')
        psnr = results.get('psnr')
        ssim = results.get('ssim')
        
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
            item = QListWidgetItem(f"Aligned Reference: {os.path.basename(ref_path)}")
            item.setData(Qt.UserRole, ref_path)
            self.list_result_files.addItem(item)
            
        dist_path = results.get('distorted_path')
        if dist_path and os.path.exists(dist_path):
            item = QListWidgetItem(f"Aligned Captured: {os.path.basename(dist_path)}")
            item.setData(Qt.UserRole, dist_path)
            self.list_result_files.addItem(item)

    def handle_vmaf_error(self, error_msg):
        """Handle error in VMAF analysis"""
        self.lbl_vmaf_status.setText(f"VMAF analysis failed")
        self.log_to_analysis(f"Error: {error_msg}")
        QMessageBox.critical(self, "VMAF Analysis Error", error_msg)
        
    def export_pdf_certificate(self):
        """Export VMAF results as PDF certificate"""
        if not self.vmaf_results:
            QMessageBox.warning(self, "No Results", "No VMAF analysis results available to export")
            return
            
        try:
            # Get test name
            test_name = self.txt_test_name.currentText()
            
            # Get paths of videos
            reference_path = self.reference_info['path'] if self.reference_info else "Unknown"
            captured_path = self.capture_path or "Unknown"
            
            # Get aligned paths if available
            if self.aligned_paths:
                reference_path = self.aligned_paths.get('reference', reference_path)
                captured_path = self.aligned_paths.get('captured', captured_path)
                
            # Create file dialog for saving
            output_dir = os.path.dirname(self.vmaf_results.get('json_path', os.getcwd()))
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_filename = f"vmaf_certificate_{test_name}_{timestamp}.pdf"
            
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Save PDF Certificate", 
                os.path.join(output_dir, default_filename),
                "PDF Files (*.pdf)"
            )
            
            if not file_path:
                return  # User cancelled
                
            # Create PDF generator and generate certificate
            from .pdf_generator import PDFCertificateGenerator
            generator = PDFCertificateGenerator()
            
            self.statusBar().showMessage("Generating PDF certificate...")
            output_path = generator.generate_certificate(
                test_name,
                reference_path,
                captured_path,
                self.vmaf_results,
                file_path
            )
            
            if output_path:
                self.statusBar().showMessage(f"PDF certificate saved to: {output_path}")
                QMessageBox.information(self, "Export Complete", 
                                       f"PDF certificate saved to:\n{output_path}")
                
                # Add to results list
                item = QListWidgetItem(f"PDF Certificate: {os.path.basename(output_path)}")
                item.setData(Qt.UserRole, output_path)
                self.list_result_files.addItem(item)
            else:
                QMessageBox.warning(self, "Export Failed", "Failed to generate PDF certificate")
        except Exception as e:
            error_msg = f"Error generating PDF: {str(e)}"
            self.statusBar().showMessage(error_msg)
            QMessageBox.critical(self, "Export Error", error_msg)
            
    def export_csv_data(self):
        """Export VMAF results as CSV data"""
        if not self.vmaf_results:
            QMessageBox.warning(self, "No Results", "No VMAF analysis results available to export")
            return
            
        try:
            # Get test name
            test_name = self.txt_test_name.currentText()
            
            # Create file dialog for saving
            output_dir = os.path.dirname(self.vmaf_results.get('json_path', os.getcwd()))
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_filename = f"vmaf_data_{test_name}_{timestamp}.csv"
            
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Save CSV Data", 
                os.path.join(output_dir, default_filename),
                "CSV Files (*.csv)"
            )
            
            if not file_path:
                return  # User cancelled
                
            # Create PDF generator and use its CSV export method
            from .pdf_generator import PDFCertificateGenerator
            generator = PDFCertificateGenerator()
            
            self.statusBar().showMessage("Exporting data to CSV...")
            output_path = generator.export_csv(self.vmaf_results, file_path)
            
            if output_path:
                self.statusBar().showMessage(f"CSV data saved to: {output_path}")
                QMessageBox.information(self, "Export Complete", 
                                       f"CSV data saved to:\n{output_path}")
                
                # Add to results list
                item = QListWidgetItem(f"CSV Data: {os.path.basename(output_path)}")
                item.setData(Qt.UserRole, output_path)
                self.list_result_files.addItem(item)
            else:
                QMessageBox.warning(self, "Export Failed", "Failed to export CSV data")
        except Exception as e:
            error_msg = f"Error exporting CSV: {str(e)}"
            self.statusBar().showMessage(error_msg)
            QMessageBox.critical(self, "Export Error", error_msg)
        
    def open_result_file(self, item):
        """Open selected result file"""
        file_path = item.data(Qt.UserRole)
        if file_path and os.path.exists(file_path):
            # Use system default application to open the file
            import subprocess
            import platform
            
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
        self.reference_info = None
        self.capture_path = None
        self.aligned_paths = None
        self.vmaf_results = None
        
        # Reset UI
        self.lbl_reference_path.setText("No reference video selected")
        self.lbl_reference_details.setText("Reference details: None")
        self.lbl_capture_summary.setText("No reference video selected")
        self.lbl_analysis_summary.setText("No videos ready for analysis")
        self.lbl_results_summary.setText("No VMAF analysis results yet")
        
        # Disable buttons
        self.btn_next_to_capture.setEnabled(False)
        self.btn_next_to_analysis.setEnabled(False)
        self.btn_next_to_results.setEnabled(False)
        self.btn_align_videos.setEnabled(False)
        self.btn_run_vmaf.setEnabled(False)
        self.btn_export_pdf.setEnabled(False)
        self.btn_export_csv.setEnabled(False)
        
        # Clear logs and progress
        self.txt_capture_log.clear()
        self.txt_analysis_log.clear()
        self.pb_capture_progress.setValue(0)
        self.pb_alignment_progress.setValue(0)
        self.pb_vmaf_progress.setValue(0)
        
        # Go to setup tab
        self.tabs.setCurrentIndex(0)
        
        # Increment test number
        test_name = self.txt_test_name.currentText()
        if test_name.startswith("Test_") and test_name[5:].isdigit():
            next_num = int(test_name[5:]) + 1
            self.txt_test_name.setCurrentText(f"Test_{next_num:02d}")

    # Add this to the UI class to properly wait for threads before closing
    def closeEvent(self, event):
        """Handle application close event"""
        # Wait for any running threads to finish
        if hasattr(self, 'alignment_thread') and self.alignment_thread and self.alignment_thread.isRunning():
            logger.info("Waiting for alignment thread to finish...")
            self.alignment_thread.wait(2000)  # Wait up to 2 seconds
            
        if hasattr(self, 'vmaf_thread') and self.vmaf_thread and self.vmaf_thread.isRunning():
            logger.info("Waiting for VMAF thread to finish...")
            self.vmaf_thread.wait(2000)  # Wait up to 2 seconds
            
        # Clean up temporary files
        if hasattr(self, 'file_manager'):
            logger.info("Cleaning up temporary files")
            self.file_manager.cleanup_temp_files()
        
        # Call parent close event
        super().closeEvent(event)
  

    # ---------- Helper methods ----------
        
    def log_to_setup(self, message):
        """Add message to setup status"""
        self.lbl_setup_status.setText(message)
        self.statusBar().showMessage(message)
        
    def log_to_capture(self, message):
        """Add message to capture log"""
        self.txt_capture_log.append(message)
        self.txt_capture_log.verticalScrollBar().setValue(
            self.txt_capture_log.verticalScrollBar().maximum()
        )
        self.statusBar().showMessage(message)
        
    def log_to_analysis(self, message):
        """Add message to analysis log"""
        self.txt_analysis_log.append(message)
        self.txt_analysis_log.verticalScrollBar().setValue(
            self.txt_analysis_log.verticalScrollBar().maximum()
        )
        self.statusBar().showMessage(message)







def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    window = VMafTestApp()
    window.show()
    sys.exit(app.exec_())