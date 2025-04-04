import os
import sys
import cv2
import time
import json
import shutil
import logging
import platform
import subprocess
import numpy as np
from datetime import datetime
from pathlib import Path
from enum import Enum, auto

# PyQt5 imports
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFileDialog, QComboBox, QProgressBar, QGroupBox,
    QFormLayout, QLineEdit, QSpinBox, QDoubleSpinBox, QCheckBox, QTextEdit,
    QMessageBox, QSplitter, QFrame, QRadioButton, QButtonGroup,QListWidget,QTableWidget,QHeaderView,QListWidgetItem
)
from PyQt5.QtCore import (
    Qt, QThread, QObject, pyqtSignal, pyqtSlot, QRunnable, QThreadPool, 
    QMutex, QTimer, QSize, QDir
)
from PyQt5.QtGui import QImage, QPixmap, QIcon, QFont, QTextCursor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger('video_quality_app')

# Define signal states in the application
class AppState(Enum):
    IDLE = auto()
    CAPTURING = auto()
    PROCESSING = auto()
    ANALYZING = auto()
    COMPLETED = auto()
    ERROR = auto()

# Worker thread for video capture
class CaptureWorker(QObject):
    """Worker for capturing video in a separate thread"""
    progress = pyqtSignal(int)
    frame_ready = pyqtSignal(object)
    capture_complete = pyqtSignal(str)
    error = pyqtSignal(str)
    log = pyqtSignal(str)

    def __init__(self, device_id, output_path, duration, fps=30, resolution=(1920, 1080), raw_format=False):
        super().__init__()
        self.device_id = device_id
        self.output_path = output_path
        self.duration = duration
        self.fps = fps
        self.resolution = resolution
        self.raw_format = raw_format
        self.running = True
        self.capture = None

    @pyqtSlot()
    def capture_video(self):
        """Captures video from the specified device"""
        try:
            self.log.emit(f"Initializing capture from device {self.device_id}")
            
            # Initialize capture
            if isinstance(self.device_id, int):
                self.capture = cv2.VideoCapture(self.device_id)
            else:
                # For DeckLink/Blackmagic, use specific options
                self.capture = cv2.VideoCapture(self.device_id)
                
            # Configure capture settings
            width, height = self.resolution
            self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            self.capture.set(cv2.CAP_PROP_FPS, self.fps)
            
            if not self.capture.isOpened():
                self.error.emit(f"Failed to open capture device {self.device_id}")
                return
                
            # Set up video writer
            fourcc = cv2.VideoWriter_fourcc(*'XVID')  # Default codec
            
            if self.raw_format:
                # Use lossless format if requested
                if platform.system() == 'Windows':
                    fourcc = cv2.VideoWriter_fourcc(*'HFYU')  # HuffYUV (lossless)
                else:
                    fourcc = cv2.VideoWriter_fourcc(*'FFV1')  # FFmpeg lossless
            
            out_video = cv2.VideoWriter(
                self.output_path, 
                fourcc, 
                self.fps, 
                (width, height)
            )
            
            if not out_video.isOpened():
                self.error.emit(f"Failed to create output video file: {self.output_path}")
                return
            
            # Determine frame count for progress calculation
            total_frames = int(self.duration * self.fps)
            frame_count = 0
            start_time = time.time()
            
            self.log.emit(f"Starting capture of {total_frames} frames at {self.fps} FPS")
            self.log.emit(f"Output video: {self.output_path}")
            
            # Main capture loop
            while self.running and frame_count < total_frames:
                ret, frame = self.capture.read()
                
                if not ret:
                    self.error.emit("Failed to read frame from capture device")
                    break
                
                # Write frame to video
                out_video.write(frame)
                
                # Update progress (every 5 frames to reduce overhead)
                if frame_count % 5 == 0:
                    progress_percent = min(100, int((frame_count / total_frames) * 100))
                    self.progress.emit(progress_percent)
                    
                    # Emit frame for preview (reduced frequency for performance)
                    if frame_count % 15 == 0:
                        self.frame_ready.emit(frame.copy())
                
                frame_count += 1
                
                # If we're ahead of the expected time, add a small delay
                elapsed = time.time() - start_time
                expected_time = frame_count / self.fps
                if expected_time > elapsed:
                    time.sleep(expected_time - elapsed)
            
            # Cleanup
            self.log.emit(f"Capture completed: {frame_count} frames captured")
            out_video.release()
            
            # Mark as complete
            self.progress.emit(100)
            self.capture_complete.emit(self.output_path)
            
        except Exception as e:
            self.error.emit(f"Capture error: {str(e)}")
        finally:
            if self.capture:
                self.capture.release()
    
    def stop(self):
        """Stops the capture process"""
        self.running = False


# Worker thread for processing video frames with OpenCV
class ProcessingWorker(QObject):
    """Worker for processing video frames with OpenCV"""
    progress = pyqtSignal(int)
    frame_processed = pyqtSignal(object)
    processing_complete = pyqtSignal(str)
    error = pyqtSignal(str)
    log = pyqtSignal(str)

    def __init__(self, input_path, output_path, processing_options=None):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.processing_options = processing_options or {}
        self.running = True

    @pyqtSlot()
    def process_video(self):
        """Processes video with OpenCV"""
        try:
            self.log.emit(f"Starting video processing: {self.input_path}")
            
            # Open input video
            cap = cv2.VideoCapture(self.input_path)
            if not cap.isOpened():
                self.error.emit(f"Failed to open input video: {self.input_path}")
                return
            
            # Get video properties
            fps = cap.get(cv2.CAP_PROP_FPS)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            # Set up video writer
            fourcc = cv2.VideoWriter_fourcc(*'XVID')
            out_video = cv2.VideoWriter(
                self.output_path, 
                fourcc, 
                fps, 
                (width, height)
            )
            
            if not out_video.isOpened():
                self.error.emit(f"Failed to create output video: {self.output_path}")
                return
            
            # Extract processing options
            resize = self.processing_options.get('resize', None)
            denoise = self.processing_options.get('denoise', False)
            sharpen = self.processing_options.get('sharpen', False)
            histogram_eq = self.processing_options.get('histogram_eq', False)
            
            # Process frames
            frame_count = 0
            
            while self.running:
                ret, frame = cap.read()
                
                if not ret:
                    break
                
                # Apply processing operations
                processed_frame = frame.copy()
                
                # Resize if requested
                if resize:
                    processed_frame = cv2.resize(
                        processed_frame,
                        resize,
                        interpolation=cv2.INTER_AREA
                    )
                
                # Apply denoise if requested
                if denoise:
                    processed_frame = cv2.fastNlMeansDenoisingColored(
                        processed_frame,
                        None,
                        10,
                        10,
                        7,
                        21
                    )
                
                # Apply sharpening if requested
                if sharpen:
                    kernel = np.array([
                        [-1, -1, -1],
                        [-1, 9, -1],
                        [-1, -1, -1]
                    ])
                    processed_frame = cv2.filter2D(processed_frame, -1, kernel)
                
                # Apply histogram equalization if requested
                if histogram_eq:
                    # Convert to YUV color space
                    yuv = cv2.cvtColor(processed_frame, cv2.COLOR_BGR2YUV)
                    # Equalize the Y channel
                    yuv[:,:,0] = cv2.equalizeHist(yuv[:,:,0])
                    # Convert back to BGR
                    processed_frame = cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR)
                
                # Write processed frame
                out_video.write(processed_frame)
                
                # Update progress every 10 frames
                frame_count += 1
                if frame_count % 10 == 0:
                    progress = min(100, int((frame_count / total_frames) * 100))
                    self.progress.emit(progress)
                    
                    # Send frame for display (reduced frequency)
                    if frame_count % 30 == 0:
                        self.frame_processed.emit(processed_frame.copy())
            
            # Cleanup
            cap.release()
            out_video.release()
            
            self.progress.emit(100)
            self.processing_complete.emit(self.output_path)
            self.log.emit(f"Processing completed: {self.output_path}")
            
        except Exception as e:
            self.error.emit(f"Processing error: {str(e)}")


# Worker thread for quality analysis with FFmpeg
class AnalysisWorker(QObject):
    """Worker for running video quality analysis using FFmpeg"""
    progress = pyqtSignal(int)
    analysis_complete = pyqtSignal(dict)
    error = pyqtSignal(str)
    log = pyqtSignal(str)

    def __init__(self, reference_path, distorted_path, output_dir, metrics=None, vmaf_model=None):
        super().__init__()
        self.reference_path = reference_path
        self.distorted_path = distorted_path
        self.output_dir = output_dir
        self.metrics = metrics or ['vmaf', 'psnr', 'ssim']
        self.vmaf_model = vmaf_model
        self.running = True

    @pyqtSlot()
    def analyze_quality(self):
        """Runs quality analysis using FFmpeg"""
        try:
            self.log.emit(f"Starting quality analysis")
            self.log.emit(f"Reference: {self.reference_path}")
            self.log.emit(f"Distorted: {self.distorted_path}")
            
            # Create output directory
            os.makedirs(self.output_dir, exist_ok=True)
            
            # Prepare result dictionary
            results = {
                'reference_path': self.reference_path,
                'distorted_path': self.distorted_path,
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            # Run alignment first if needed
            if 'vmaf' in self.metrics:
                self.log.emit("Running VMAF analysis...")
                
                # Determine JSON output path
                json_path = os.path.join(self.output_dir, "vmaf.json")
                results['json_path'] = json_path
                
                # Build FFmpeg command
                ffmpeg_cmd = [
                    "ffmpeg",
                    "-i", self.distorted_path,
                    "-i", self.reference_path,
                    "-lavfi", 
                ]
                
                # Create filtergraph based on requested metrics
                filter_graph = ""
                
                # Main VMAF filter
                vmaf_filter = f"libvmaf=log_fmt=json:log_path={json_path}:psnr=1:ssim=1"
                
                # Add model if specified
                if self.vmaf_model:
                    vmaf_filter += f":model_path={self.vmaf_model}"
                
                filter_graph = vmaf_filter
                
                ffmpeg_cmd.extend([filter_graph, "-f", "null", "-"])
                
                # Execute ffmpeg command
                self.log.emit(f"Executing: {' '.join(ffmpeg_cmd)}")
                
                # Start process
                process = subprocess.Popen(
                    ffmpeg_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                    text=True
                )
                
                # Process output to track progress
                for line in iter(process.stderr.readline, ""):
                    if not self.running:
                        process.terminate()
                        self.error.emit("Analysis cancelled")
                        return
                    
                    # Try to parse progress information
                    if "frame=" in line:
                        try:
                            # Extract frame number
                            frame_part = line.split("frame=")[1].split()[0].strip()
                            frame_num = int(frame_part)
                            
                            # Estimate total frames
                            cap = cv2.VideoCapture(self.distorted_path)
                            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                            cap.release()
                            
                            # Calculate progress
                            progress = min(100, int((frame_num / total_frames) * 100))
                            self.progress.emit(progress)
                        except:
                            pass
                    
                    self.log.emit(line.strip())
                
                # Wait for process to complete
                process.wait()
                
                if process.returncode != 0:
                    self.error.emit(f"FFmpeg VMAF analysis failed with return code {process.returncode}")
                    return
                
                # Parse JSON results
                if os.path.exists(json_path):
                    with open(json_path, 'r') as f:
                        vmaf_data = json.load(f)
                    
                    # Extract scores
                    if "pooled_metrics" in vmaf_data:
                        pooled = vmaf_data["pooled_metrics"]
                        
                        if "vmaf" in pooled:
                            results['vmaf_score'] = pooled["vmaf"]["mean"]
                        
                        if "psnr_y" in pooled:
                            results['psnr'] = pooled["psnr_y"]["mean"]
                        elif "psnr" in pooled:
                            results['psnr'] = pooled["psnr"]["mean"]
                        
                        if "ssim_y" in pooled:
                            results['ssim'] = pooled["ssim_y"]["mean"]
                        elif "ssim" in pooled:
                            results['ssim'] = pooled["ssim"]["mean"]
                    
                    # Store raw results
                    results['raw_results'] = vmaf_data
                else:
                    self.error.emit(f"VMAF JSON output file not found: {json_path}")
                    return
            
            # Run individual metrics if requested
            if 'psnr' in self.metrics and 'psnr' not in results:
                self.log.emit("Running standalone PSNR analysis...")
                # Implementation for standalone PSNR would go here
            
            if 'ssim' in self.metrics and 'ssim' not in results:
                self.log.emit("Running standalone SSIM analysis...")
                # Implementation for standalone SSIM would go here
            
            # Complete analysis
            self.progress.emit(100)
            self.analysis_complete.emit(results)
            self.log.emit("Quality analysis completed successfully")
            
        except Exception as e:
            self.error.emit(f"Analysis error: {str(e)}")
    
    def stop(self):
        """Stops the analysis process"""
        self.running = False


# Main application window
class MainWindow(QMainWindow):
    """Main application window for video quality assessment"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Video Quality Assessment")
        self.setMinimumSize(1024, 768)
        
        # Initialize UI state
        self.app_state = AppState.IDLE
        self.threadpool = QThreadPool()
        
        # Set up path variables
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.output_dir = os.path.join(self.base_dir, "output")
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Initialize empty paths
        self.reference_path = None
        self.capture_path = None
        self.processed_path = None
        
        # Analysis results
        self.analysis_results = None
        
        # Set up UI components
        self.setup_ui()
        
        # Initialize options
        self.load_config()
        
        # Connect signals
        self.connect_signals()

    def setup_ui(self):
        """Sets up the main UI structure"""
        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QVBoxLayout(central_widget)
        
        # Create tab widget
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        
        # Add tabs
        self.setup_tab = SetupTab(self)
        self.capture_tab = CaptureTab(self)
        self.processing_tab = ProcessingTab(self)
        self.analysis_tab = AnalysisTab(self)
        self.results_tab = ResultsTab(self)
        
        self.tabs.addTab(self.setup_tab, "Setup")
        self.tabs.addTab(self.capture_tab, "Capture")
        self.tabs.addTab(self.processing_tab, "Processing")
        self.tabs.addTab(self.analysis_tab, "Analysis")
        self.tabs.addTab(self.results_tab, "Results")
        
        # Status bar
        self.status_label = QLabel("Ready")
        self.statusBar().addWidget(self.status_label)

    def connect_signals(self):
        """Connects signals between tabs and UI components"""
        # Setup tab signals
        self.setup_tab.reference_selected.connect(self.on_reference_selected)
        
        # Capture tab signals
        self.capture_tab.capture_started.connect(self.on_capture_started)
        self.capture_tab.capture_completed.connect(self.on_capture_completed)
        
        # Processing tab signals
        self.processing_tab.processing_started.connect(self.on_processing_started)
        self.processing_tab.processing_completed.connect(self.on_processing_completed)
        
        # Analysis tab signals
        self.analysis_tab.analysis_started.connect(self.on_analysis_started)
        self.analysis_tab.analysis_completed.connect(self.on_analysis_completed)
        
        # Tab navigation buttons
        self.setup_tab.btn_next_to_capture.clicked.connect(lambda: self.tabs.setCurrentIndex(1))
        self.capture_tab.btn_prev_to_setup.clicked.connect(lambda: self.tabs.setCurrentIndex(0))
        self.capture_tab.btn_next_to_processing.clicked.connect(lambda: self.tabs.setCurrentIndex(2))
        self.processing_tab.btn_prev_to_capture.clicked.connect(lambda: self.tabs.setCurrentIndex(1))
        self.processing_tab.btn_next_to_analysis.clicked.connect(lambda: self.tabs.setCurrentIndex(3))
        self.analysis_tab.btn_prev_to_processing.clicked.connect(lambda: self.tabs.setCurrentIndex(2))
        self.analysis_tab.btn_next_to_results.clicked.connect(lambda: self.tabs.setCurrentIndex(4))
        self.results_tab.btn_prev_to_analysis.clicked.connect(lambda: self.tabs.setCurrentIndex(3))
        self.results_tab.btn_new_test.clicked.connect(self.start_new_test)

    def load_config(self):
        """Loads configuration settings"""
        # Default configuration
        self.config = {
            "capture": {
                "device_id": 0,
                "duration": 10,
                "fps": 30,
                "resolution": (1920, 1080),
                "raw_format": False
            },
            "processing": {
                "resize": None,
                "denoise": False,
                "sharpen": False,
                "histogram_eq": False
            },
            "analysis": {
                "metrics": ["vmaf", "psnr", "ssim"],
                "vmaf_model": None
            }
        }
        
        # Try to load from config file
        config_path = os.path.join(self.base_dir, "config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    loaded_config = json.load(f)
                
                # Update config
                self.config.update(loaded_config)
                logger.info("Configuration loaded from file")
            except Exception as e:
                logger.error(f"Error loading configuration: {str(e)}")

    def save_config(self):
        """Saves configuration settings"""
        config_path = os.path.join(self.base_dir, "config.json")
        try:
            with open(config_path, 'w') as f:
                json.dump(self.config, f, indent=4)
            logger.info("Configuration saved to file")
        except Exception as e:
            logger.error(f"Error saving configuration: {str(e)}")

    def on_reference_selected(self, file_path):
        """Handles reference video selection"""
        self.reference_path = file_path
        self.status_label.setText(f"Reference video selected: {os.path.basename(file_path)}")
        logger.info(f"Reference video set to: {file_path}")
        
        # Update capture tab
        self.capture_tab.update_reference_info(file_path)
        
        # Enable capture tab
        self.tabs.setTabEnabled(1, True)
        
        # Update analysis tab
        self.analysis_tab.update_reference_info(file_path)

    def on_capture_started(self):
        """Handles capture start event"""
        self.app_state = AppState.CAPTURING
        self.status_label.setText("Capturing video...")
        
        # Disable other tabs during capture
        for i in range(self.tabs.count()):
            if i != 1:  # Don't disable capture tab
                self.tabs.setTabEnabled(i, False)

    def on_capture_completed(self, file_path):
        """Handles capture completion event"""
        self.app_state = AppState.IDLE
        self.capture_path = file_path
        self.status_label.setText(f"Capture completed: {os.path.basename(file_path)}")
        
        # Re-enable tabs
        for i in range(self.tabs.count()):
            self.tabs.setTabEnabled(i, True)
        
        # Update processing tab
        self.processing_tab.update_input_video(file_path)
        
        # Update analysis tab
        self.analysis_tab.update_distorted_info(file_path)

    def on_processing_started(self):
        """Handles processing start event"""
        self.app_state = AppState.PROCESSING
        self.status_label.setText("Processing video...")
        
        # Disable other tabs during processing
        for i in range(self.tabs.count()):
            if i != 2:  # Don't disable processing tab
                self.tabs.setTabEnabled(i, False)

    def on_processing_completed(self, file_path):
        """Handles processing completion event"""
        self.app_state = AppState.IDLE
        self.processed_path = file_path
        self.status_label.setText(f"Processing completed: {os.path.basename(file_path)}")
        
        # Re-enable tabs
        for i in range(self.tabs.count()):
            self.tabs.setTabEnabled(i, True)
        
        # Update analysis tab with processed video
        self.analysis_tab.update_distorted_info(file_path)

    def on_analysis_started(self):
        """Handles analysis start event"""
        self.app_state = AppState.ANALYZING
        self.status_label.setText("Analyzing video quality...")
        
        # Disable other tabs during analysis
        for i in range(self.tabs.count()):
            if i != 3:  # Don't disable analysis tab
                self.tabs.setTabEnabled(i, False)

    def on_analysis_completed(self, results):
        """Handles analysis completion event"""
        self.app_state = AppState.COMPLETED
        self.analysis_results = results
        
        # Extract main score for status display
        vmaf_score = results.get('vmaf_score', 'N/A')
        score_text = f"{vmaf_score:.2f}" if isinstance(vmaf_score, (int, float)) else vmaf_score
        
        self.status_label.setText(f"Analysis completed, VMAF score: {score_text}")
        
        # Re-enable tabs
        for i in range(self.tabs.count()):
            self.tabs.setTabEnabled(i, True)
        
        # Update results tab
        self.results_tab.update_results(results)
        
        # Switch to results tab
        self.tabs.setCurrentIndex(4)

    def start_new_test(self):
        """Resets the application state for a new test"""
        # Reset state
        self.app_state = AppState.IDLE
        self.capture_path = None
        self.processed_path = None
        self.analysis_results = None
        
        # Reset tabs
        self.capture_tab.reset()
        self.processing_tab.reset()
        self.analysis_tab.reset()
        self.results_tab.reset()
        
        # Go back to setup tab
        self.tabs.setCurrentIndex(0)
        
        self.status_label.setText("Ready for new test")
        logger.info("Application reset for new test")

    def closeEvent(self, event):
        """Handle application close event"""
        # Ensure threads are stopped
        if self.app_state in [AppState.CAPTURING, AppState.PROCESSING, AppState.ANALYZING]:
            reply = QMessageBox.question(
                self, 
                "Confirm Exit",
                "Tasks are still running. Are you sure you want to quit?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                # Stop running threads
                if hasattr(self.capture_tab, 'capture_thread'):
                    self.capture_tab.stop_capture()
                
                if hasattr(self.processing_tab, 'processing_thread'):
                    self.processing_tab.stop_processing()
                
                if hasattr(self.analysis_tab, 'analysis_thread'):
                    self.analysis_tab.stop_analysis()
                
                # Save config
                self.save_config()
                event.accept()
            else:
                event.ignore()
        else:
            # Save config
            self.save_config()
            event.accept()


# Setup Tab
class SetupTab(QWidget):
    """Setup tab for application configuration and reference video selection"""
    reference_selected = pyqtSignal(str)
    
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.setup_ui()
    
    def setup_ui(self):
        """Sets up the UI for the setup tab"""
        layout = QVBoxLayout(self)
        
        # Test metadata group
        test_meta_group = QGroupBox("Test Information")
        test_meta_layout = QFormLayout()
        
        self.txt_test_name = QLineEdit("Test_01")
        test_meta_layout.addRow("Test Name:", self.txt_test_name)
        
        self.txt_tester_name = QLineEdit()
        test_meta_layout.addRow("Tester Name:", self.txt_tester_name)
        
        self.txt_test_location = QLineEdit()
        test_meta_layout.addRow("Test Location:", self.txt_test_location)
        
        self.txt_test_description = QTextEdit()
        self.txt_test_description.setMaximumHeight(100)
        test_meta_layout.addRow("Description:", self.txt_test_description)
        
        test_meta_group.setLayout(test_meta_layout)
        layout.addWidget(test_meta_group)
        
        # Reference video selection
        ref_group = QGroupBox("Reference Video")
        ref_layout = QVBoxLayout()
        
        ref_help_label = QLabel("Select a reference video file to compare against captured video")
        ref_layout.addWidget(ref_help_label)
        
        ref_select_layout = QHBoxLayout()
        self.lbl_reference_path = QLineEdit()
        self.lbl_reference_path.setReadOnly(True)
        self.lbl_reference_path.setPlaceholderText("No reference video selected")
        
        self.btn_select_reference = QPushButton("Browse...")
        self.btn_select_reference.clicked.connect(self.select_reference_video)
        
        ref_select_layout.addWidget(self.lbl_reference_path)
        ref_select_layout.addWidget(self.btn_select_reference)
        ref_layout.addLayout(ref_select_layout)
        
        # Reference video info
        self.reference_info = QLabel("No reference video selected")
        ref_layout.addWidget(self.reference_info)
        
        ref_group.setLayout(ref_layout)
        layout.addWidget(ref_group)
        
        # Device configuration
        device_group = QGroupBox("Capture Device Settings")
        device_layout = QFormLayout()
        
        # Device selection
        self.cmb_device = QComboBox()
        self.populate_devices()
        device_layout.addRow("Capture Device:", self.cmb_device)
        
        # Capture settings
        self.cmb_resolution = QComboBox()
        for res in ["1920x1080", "1280x720", "720x576", "720x480"]:
            self.cmb_resolution.addItem(res)
        device_layout.addRow("Resolution:", self.cmb_resolution)
        
        self.spin_fps = QSpinBox()
        self.spin_fps.setRange(15, 60)
        self.spin_fps.setValue(30)
        device_layout.addRow("Frame Rate:", self.spin_fps)
        
        self.check_raw_format = QCheckBox("Use lossless format")
        device_layout.addRow("", self.check_raw_format)
        
        device_group.setLayout(device_layout)
        layout.addWidget(device_group)
        
        # Navigation buttons
        nav_layout = QHBoxLayout()
        nav_layout.addStretch()
        
        self.btn_next_to_capture = QPushButton("Next: Capture")
        self.btn_next_to_capture.setEnabled(False)
        nav_layout.addWidget(self.btn_next_to_capture)
        
        layout.addLayout(nav_layout)
        layout.addStretch()
    
    def populate_devices(self):
        """Populates device dropdown with available capture devices"""
        self.cmb_device.clear()
        
        # Add default devices
        self.cmb_device.addItem("Default Camera (0)", 0)
        
        # Look for DeckLink devices using BlackMagic SDK or similar
        # This is a placeholder - actual implementation depends on SDK
        try:
            # Placeholder for BlackMagic SDK enumeration
            # In a real implementation, use the SDK to list devices
            self.cmb_device.addItem("DeckLink Mini Recorder", "DeckLink Mini Recorder")
            self.cmb_device.addItem("DeckLink SDI 4K", "DeckLink SDI 4K")
            self.cmb_device.addItem("Intensity Shuttle", "Intensity Shuttle")
        except Exception as e:
            logger.warning(f"Failed to enumerate DeckLink devices: {str(e)}")
    
    def select_reference_video(self):
        """Opens file dialog to select reference video"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Reference Video",
            "",
            "Video Files (*.mp4 *.avi *.mov *.mkv)"
        )
        
        if file_path:
            self.lbl_reference_path.setText(file_path)
            
            # Get video info
            try:
                cap = cv2.VideoCapture(file_path)
                if cap.isOpened():
                    # Get video properties
                    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    fps = cap.get(cv2.CAP_PROP_FPS)
                    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                    duration = frame_count / fps if fps > 0 else 0
                    
                    # Format info text
                    info_text = (
                        f"<b>File:</b> {os.path.basename(file_path)}<br>"
                        f"<b>Resolution:</b> {width}x{height}<br>"
                        f"<b>Frame Rate:</b> {fps:.2f} FPS<br>"
                        f"<b>Duration:</b> {duration:.2f} seconds ({frame_count} frames)"
                    )
                    
                    self.reference_info.setText(info_text)
                    
                    # Enable next button
                    self.btn_next_to_capture.setEnabled(True)
                    
                    # Set recommended capture settings
                    idx = self.cmb_resolution.findText(f"{width}x{height}")
                    if idx >= 0:
                        self.cmb_resolution.setCurrentIndex(idx)
                    
                    self.spin_fps.setValue(min(max(int(fps), self.spin_fps.minimum()), self.spin_fps.maximum()))
                    
                    # Signal reference selection
                    self.reference_selected.emit(file_path)
                    
                    cap.release()
                else:
                    QMessageBox.warning(
                        self,
                        "Error",
                        f"Could not open video file: {file_path}"
                    )
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Error",
                    f"Error processing video file: {str(e)}"
                )


# Capture Tab
class CaptureTab(QWidget):
    """Capture tab for recording from Blackmagic hardware"""
    capture_started = pyqtSignal()
    capture_completed = pyqtSignal(str)
    
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.capture_thread = None
        self.worker = None
        self.preview_timer = None
        self.capture_running = False
        self.setup_ui()
    
    def setup_ui(self):
        """Sets up the UI for the capture tab"""
        layout = QVBoxLayout(self)
        
        # Reference and capture summary
        summary_group = QGroupBox("Test Summary")
        summary_layout = QVBoxLayout()
        
        self.lbl_capture_summary = QLabel("No reference video selected")
        summary_layout.addWidget(self.lbl_capture_summary)
        
        summary_group.setLayout(summary_layout)
        layout.addWidget(summary_group)
        
        # Preview and controls
        content_layout = QHBoxLayout()
        
        # Live preview
        preview_group = QGroupBox("Live Preview")
        preview_layout = QVBoxLayout()
        
        self.preview_label = QLabel()
        self.preview_label.setMinimumSize(480, 270)
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setText("No preview available")
        preview_layout.addWidget(self.preview_label)
        
        preview_group.setLayout(preview_layout)
        content_layout.addWidget(preview_group)
        
        # Capture controls
        controls_group = QGroupBox("Capture Controls")
        controls_layout = QVBoxLayout()
        
        # Duration control
        duration_layout = QHBoxLayout()
        duration_layout.addWidget(QLabel("Capture Duration:"))
        self.spin_duration = QSpinBox()
        self.spin_duration.setRange(1, 300)
        self.spin_duration.setValue(10)
        self.spin_duration.setSuffix(" seconds")
        duration_layout.addWidget(self.spin_duration)
        controls_layout.addLayout(duration_layout)
        
        # Status and buttons
        self.lbl_capture_status = QLabel("Ready to capture")
        controls_layout.addWidget(self.lbl_capture_status)
        
        self.pb_capture_progress = QProgressBar()
        self.pb_capture_progress.setRange(0, 100)
        self.pb_capture_progress.setValue(0)
        controls_layout.addWidget(self.pb_capture_progress)
        
        btn_layout = QVBoxLayout()
        self.btn_start_capture = QPushButton("Start Capture")
        self.btn_start_capture.clicked.connect(self.start_capture)
        btn_layout.addWidget(self.btn_start_capture)
        
        self.btn_stop_capture = QPushButton("Stop Capture")
        self.btn_stop_capture.clicked.connect(self.stop_capture)
        self.btn_stop_capture.setEnabled(False)
        btn_layout.addWidget(self.btn_stop_capture)
        
        controls_layout.addLayout(btn_layout)
        
        controls_group.setLayout(controls_layout)
        content_layout.addWidget(controls_group)
        
        layout.addLayout(content_layout)
        
        # Capture log
        log_group = QGroupBox("Capture Log")
        log_layout = QVBoxLayout()
        
        self.txt_capture_log = QTextEdit()
        self.txt_capture_log.setReadOnly(True)
        log_layout.addWidget(self.txt_capture_log)
        
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)
        
        # Navigation buttons
        nav_layout = QHBoxLayout()
        
        self.btn_prev_to_setup = QPushButton("Back: Setup")
        nav_layout.addWidget(self.btn_prev_to_setup)
        
        nav_layout.addStretch()
        
        self.btn_next_to_processing = QPushButton("Next: Processing")
        self.btn_next_to_processing.setEnabled(False)
        nav_layout.addWidget(self.btn_next_to_processing)
        
        layout.addLayout(nav_layout)
    
    def update_reference_info(self, file_path):
        """Updates UI with reference video information"""
        if file_path and os.path.exists(file_path):
            try:
                cap = cv2.VideoCapture(file_path)
                if cap.isOpened():
                    # Get video properties
                    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    fps = cap.get(cv2.CAP_PROP_FPS)
                    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                    duration = frame_count / fps if fps > 0 else 0
                    
                    # Update summary
                    summary_text = (
                        f"<b>Reference:</b> {os.path.basename(file_path)}<br>"
                        f"<b>Resolution:</b> {width}x{height}<br>"
                        f"<b>Duration:</b> {duration:.2f} seconds<br>"
                        f"<b>No capture yet</b>"
                    )
                    
                    self.lbl_capture_summary.setText(summary_text)
                    
                    # Update spin duration to match reference
                    self.spin_duration.setValue(min(int(duration), self.spin_duration.maximum()))
                    
                    # Enable start capture button
                    self.btn_start_capture.setEnabled(True)
                    
                    cap.release()
            except Exception as e:
                self.log(f"Error reading reference video: {str(e)}")







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
        output_dir = None
        
        # Check for output directory field in setup_tab
        if hasattr(self.parent, 'setup_tab'):
            setup_tab = self.parent.setup_tab
            # Try to get output directory - handle different possible field names
            for attr_name in ['output_directory', 'output_dir', 'txt_output_dir', 'le_output_dir']:
                if hasattr(setup_tab, attr_name):
                    field = getattr(setup_tab, attr_name)
                    if hasattr(field, 'text'):
                        output_dir = field.text()
                        break
        
        # If we couldn't find the output directory, use default
        if not output_dir or output_dir == "Default output directory":
            if hasattr(self.parent, 'file_manager'):
                output_dir = self.parent.file_manager.get_default_base_dir()
            else:
                script_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
                output_dir = os.path.join(script_dir, "tests", "test_results")
                os.makedirs(output_dir, exist_ok=True)

        # Get test name using same approach
        test_name = None
        if hasattr(self.parent, 'setup_tab'):
            setup_tab = self.parent.setup_tab
            for attr_name in ['test_name', 'txt_test_name', 'le_test_name']:
                if hasattr(setup_tab, attr_name):
                    field = getattr(setup_tab, attr_name)
                    if hasattr(field, 'text'):
                        test_name = field.text()
                        break
        
        # Use default test name if not found
        if not test_name:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            test_name = f"test_{timestamp}"

        self.log_to_capture(f"Using test name: {test_name}")
        self.log_to_capture(f"Output directory: {output_dir}")

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
        """Stops the current capture process"""
        if not self.capture_running:
            return
        
        self.log("Stopping capture...")
        
        if self.worker:
            self.worker.stop()
        
        # Wait for thread to finish
        if self.capture_thread and self.capture_thread.isRunning():
            self.capture_thread.quit()
            self.capture_thread.wait(3000)  # Wait up to 3 seconds
            
            if self.capture_thread.isRunning():
                self.capture_thread.terminate()
        
        # Update UI
        self.capture_running = False
        self.btn_start_capture.setEnabled(True)
        self.btn_stop_capture.setEnabled(False)
        self.lbl_capture_status.setText("Capture stopped by user")
    
    def update_progress(self, progress):
        """Updates the progress bar"""
        self.pb_capture_progress.setValue(progress)
    
    def update_preview(self, frame):
        """Updates the preview image with a captured frame"""
        if frame is not None:
            # Convert OpenCV frame to QImage
            height, width, channels = frame.shape
            bytes_per_line = channels * width
            
            # Convert BGR to RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Create QImage
            q_img = QImage(rgb_frame.data, width, height, bytes_per_line, QImage.Format_RGB888)
            
            # Scale for preview (maintain aspect ratio)
            preview_size = self.preview_label.size()
            pixmap = QPixmap.fromImage(q_img)
            pixmap = pixmap.scaled(
                preview_size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            
            # Update preview
            self.preview_label.setPixmap(pixmap)
    
    def on_capture_complete(self, file_path):
        """Handles capture completion"""
        self.capture_running = False
        
        # Check if file exists
        if not os.path.exists(file_path):
            self.log(f"Error: Capture file not found at {file_path}")
            return
        
        self.log(f"Capture completed successfully")
        self.log(f"Saved to: {file_path}")
        
        # Update UI
        self.lbl_capture_status.setText("Capture completed")
        self.btn_start_capture.setEnabled(True)
        self.btn_stop_capture.setEnabled(False)
        
        # Update summary
        basename = os.path.basename(file_path)
        ref_basename = os.path.basename(self.parent.reference_path)
        self.lbl_capture_summary.setText(
            f"<b>Reference:</b> {ref_basename}<br>"
            f"<b>Captured:</b> {basename}"
        )
        
        # Enable next button
        self.btn_next_to_processing.setEnabled(True)
        
        # Signal completion
        self.capture_completed.emit(file_path)
        
        # Clean up thread
        if self.capture_thread:
            self.capture_thread.quit()
            self.capture_thread.wait()
            self.capture_thread = None
            self.worker = None
    
    def on_capture_error(self, error_message):
        """Handles capture errors"""
        self.log(f"Error: {error_message}")
        
        # Update UI
        self.lbl_capture_status.setText(f"Error: {error_message}")
        self.btn_start_capture.setEnabled(True)
        self.btn_stop_capture.setEnabled(False)
        self.capture_running = False
        
        # Show error message
        QMessageBox.critical(
            self,
            "Capture Error",
            f"Capture failed: {error_message}"
        )
        
        # Clean up thread
        if self.capture_thread:
            self.capture_thread.quit()
            self.capture_thread.wait()
            self.capture_thread = None
            self.worker = None
    
    def log(self, message):
        """Adds a message to the capture log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.txt_capture_log.append(f"[{timestamp}] {message}")
        # Scroll to bottom
        cursor = self.txt_capture_log.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.txt_capture_log.setTextCursor(cursor)
    
    def reset(self):
        """Resets the capture tab"""
        # Stop capture if running
        if self.capture_running:
            self.stop_capture()
        
        # Reset UI
        self.pb_capture_progress.setValue(0)
        self.lbl_capture_status.setText("Ready to capture")
        self.preview_label.setText("No preview available")
        self.preview_label.setPixmap(QPixmap())
        self.txt_capture_log.clear()
        self.btn_next_to_processing.setEnabled(False)
        
        # Reset summary based on reference
        if self.parent.reference_path:
            basename = os.path.basename(self.parent.reference_path)
            self.lbl_capture_summary.setText(
                f"<b>Reference:</b> {basename}<br>"
                f"<b>No capture yet</b>"
            )
        else:
            self.lbl_capture_summary.setText("No reference video selected")





# Processing Tab
class ProcessingTab(QWidget):
    """Processing tab for applying OpenCV operations to captured video"""
    processing_started = pyqtSignal()
    processing_completed = pyqtSignal(str)
    
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.processing_thread = None
        self.worker = None
        self.processing_running = False
        self.setup_ui()
    
    def setup_ui(self):
        """Sets up the UI for the processing tab"""
        layout = QVBoxLayout(self)
        
        # Video info
        info_group = QGroupBox("Video Information")
        info_layout = QVBoxLayout()
        
        self.lbl_video_info = QLabel("No video selected for processing")
        info_layout.addWidget(self.lbl_video_info)
        
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)
        
        # Processing options and preview
        options_preview_layout = QHBoxLayout()
        
        # Processing options
        options_group = QGroupBox("Processing Options")
        options_layout = QVBoxLayout()
        
        # Resize option
        resize_layout = QHBoxLayout()
        self.check_resize = QCheckBox("Resize Video")
        self.check_resize.stateChanged.connect(self.update_resize_options)
        resize_layout.addWidget(self.check_resize)
        
        self.cmb_resize = QComboBox()
        for res in ["1920x1080", "1280x720", "720x576", "720x480", "640x360"]:
            self.cmb_resize.addItem(res)
        self.cmb_resize.setEnabled(False)
        resize_layout.addWidget(self.cmb_resize)
        
        options_layout.addLayout(resize_layout)
        
        # Image enhancement options
        self.check_denoise = QCheckBox("Apply Denoising")
        options_layout.addWidget(self.check_denoise)
        
        self.check_sharpen = QCheckBox("Apply Sharpening")
        options_layout.addWidget(self.check_sharpen)
        
        self.check_hist_eq = QCheckBox("Apply Histogram Equalization")
        options_layout.addWidget(self.check_hist_eq)
        
        # Add presets dropdown
        preset_layout = QHBoxLayout()
        preset_layout.addWidget(QLabel("Presets:"))
        
        self.cmb_presets = QComboBox()
        self.cmb_presets.addItem("No Preset")
        self.cmb_presets.addItem("Low Quality Enhancement")
        self.cmb_presets.addItem("Noise Reduction")
        self.cmb_presets.addItem("Sharpen Only")
        self.cmb_presets.currentIndexChanged.connect(self.apply_preset)
        
        preset_layout.addWidget(self.cmb_presets)
        options_layout.addLayout(preset_layout)
        
        options_layout.addStretch()
        
        # Processing controls
        controls_layout = QVBoxLayout()
        
        self.lbl_processing_status = QLabel("Ready")
        controls_layout.addWidget(self.lbl_processing_status)
        
        self.pb_processing_progress = QProgressBar()
        self.pb_processing_progress.setRange(0, 100)
        self.pb_processing_progress.setValue(0)
        controls_layout.addWidget(self.pb_processing_progress)
        
        self.btn_start_processing = QPushButton("Start Processing")
        self.btn_start_processing.clicked.connect(self.start_processing)
        self.btn_start_processing.setEnabled(False)
        controls_layout.addWidget(self.btn_start_processing)
        
        self.btn_stop_processing = QPushButton("Stop Processing")
        self.btn_stop_processing.clicked.connect(self.stop_processing)
        self.btn_stop_processing.setEnabled(False)
        controls_layout.addWidget(self.btn_stop_processing)
        
        options_layout.addLayout(controls_layout)
        
        options_group.setLayout(options_layout)
        options_preview_layout.addWidget(options_group)
        
        # Frame preview
        preview_group = QGroupBox("Frame Preview")
        preview_layout = QVBoxLayout()
        
        preview_tabs = QTabWidget()
        
        # Original frame
        original_tab = QWidget()
        original_layout = QVBoxLayout(original_tab)
        
        self.lbl_original_frame = QLabel("No preview available")
        self.lbl_original_frame.setAlignment(Qt.AlignCenter)
        self.lbl_original_frame.setMinimumSize(480, 270)
        original_layout.addWidget(self.lbl_original_frame)
        
        preview_tabs.addTab(original_tab, "Original")
        
        # Processed frame
        processed_tab = QWidget()
        processed_layout = QVBoxLayout(processed_tab)
        
        self.lbl_processed_frame = QLabel("No preview available")
        self.lbl_processed_frame.setAlignment(Qt.AlignCenter)
        self.lbl_processed_frame.setMinimumSize(480, 270)
        processed_layout.addWidget(self.lbl_processed_frame)
        
        preview_tabs.addTab(processed_tab, "Processed")
        
        preview_layout.addWidget(preview_tabs)
        
        self.btn_preview = QPushButton("Generate Preview")
        self.btn_preview.clicked.connect(self.generate_preview)
        self.btn_preview.setEnabled(False)
        preview_layout.addWidget(self.btn_preview)
        
        preview_group.setLayout(preview_layout)
        options_preview_layout.addWidget(preview_group)
        
        layout.addLayout(options_preview_layout)
        
        # Processing log
        log_group = QGroupBox("Processing Log")
        log_layout = QVBoxLayout()
        
        self.txt_processing_log = QTextEdit()
        self.txt_processing_log.setReadOnly(True)
        log_layout.addWidget(self.txt_processing_log)
        
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)
        
        # Navigation buttons
        nav_layout = QHBoxLayout()
        
        self.btn_prev_to_capture = QPushButton("Back: Capture")
        nav_layout.addWidget(self.btn_prev_to_capture)
        
        nav_layout.addStretch()
        
        self.btn_next_to_analysis = QPushButton("Next: Analysis")
        self.btn_next_to_analysis.setEnabled(False)
        nav_layout.addWidget(self.btn_next_to_analysis)
        
        layout.addLayout(nav_layout)
    
    def update_input_video(self, file_path):
        """Updates the UI when an input video is selected"""
        if file_path and os.path.exists(file_path):
            try:
                # Get video info
                cap = cv2.VideoCapture(file_path)
                if cap.isOpened():
                    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    fps = cap.get(cv2.CAP_PROP_FPS)
                    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                    duration = frame_count / fps if fps > 0 else 0
                    
                    # Update info label
                    info_text = (
                        f"<b>File:</b> {os.path.basename(file_path)}<br>"
                        f"<b>Resolution:</b> {width}x{height}<br>"
                        f"<b>Frame Rate:</b> {fps:.2f} FPS<br>"
                        f"<b>Duration:</b> {duration:.2f} seconds ({frame_count} frames)"
                    )
                    
                    self.lbl_video_info.setText(info_text)
                    
                    # Extract a preview frame
                    cap.set(cv2.CAP_PROP_POS_FRAMES, min(10, frame_count - 1))
                    ret, frame = cap.read()
                    if ret:
                        self.update_original_preview(frame)
                    
                    # Enable processing buttons
                    self.btn_start_processing.setEnabled(True)
                    self.btn_preview.setEnabled(True)
                    
                    cap.release()
                    
                    self.log(f"Loaded input video: {file_path}")
                else:
                    self.log(f"Error: Could not open video file {file_path}")
            except Exception as e:
                self.log(f"Error loading video: {str(e)}")
        else:
            self.lbl_video_info.setText("No video selected for processing")
            self.btn_start_processing.setEnabled(False)
            self.btn_preview.setEnabled(False)
    
    def update_resize_options(self, state):
        """Enables or disables resize dropdown based on checkbox state"""
        self.cmb_resize.setEnabled(state == Qt.Checked)
    
    def apply_preset(self, index):
        """Applies a preset configuration of processing options"""
        if index == 0:  # No preset
            return
        
        # Reset options
        self.check_resize.setChecked(False)
        self.check_denoise.setChecked(False)
        self.check_sharpen.setChecked(False)
        self.check_hist_eq.setChecked(False)
        
        if index == 1:  # Low Quality Enhancement
            self.check_denoise.setChecked(True)
            self.check_sharpen.setChecked(True)
            self.check_hist_eq.setChecked(True)
        elif index == 2:  # Noise Reduction
            self.check_denoise.setChecked(True)
        elif index == 3:  # Sharpen Only
            self.check_sharpen.setChecked(True)
    
    def generate_preview(self):
        """Generates a preview of processing on a single frame"""
        if not self.parent.capture_path or not os.path.exists(self.parent.capture_path):
            QMessageBox.warning(
                self,
                "No Input Video",
                "Please capture a video first."
            )
            return
        
        try:
            # Load a frame from the video
            cap = cv2.VideoCapture(self.parent.capture_path)
            
            if not cap.isOpened():
                self.log("Error opening capture video")
                return
            
            # Get middle frame for preview
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            cap.set(cv2.CAP_PROP_POS_FRAMES, min(frame_count // 2, frame_count - 1))
            
            # Read frame
            ret, frame = cap.read()
            cap.release()
            
            if not ret:
                self.log("Error reading frame for preview")
                return
            
            # Store original frame for preview
            self.update_original_preview(frame)
            
            # Apply processing
            processed_frame = self.process_frame(frame)
            
            # Update processed preview
            self.update_processed_preview(processed_frame)
            
            self.log("Preview generated with current settings")
            
        except Exception as e:
            self.log(f"Error generating preview: {str(e)}")
    
    def process_frame(self, frame):
        """Applies processing operations to a single frame"""
        processed = frame.copy()
        
        # Apply resize if enabled
        if self.check_resize.isChecked():
            try:
                size_str = self.cmb_resize.currentText()
                target_width, target_height = map(int, size_str.split('x'))
                processed = cv2.resize(
                    processed,
                    (target_width, target_height),
                    interpolation=cv2.INTER_AREA
                )
            except Exception as e:
                self.log(f"Resize error: {str(e)}")
        
        # Apply denoise if enabled
        if self.check_denoise.isChecked():
            try:
                processed = cv2.fastNlMeansDenoisingColored(
                    processed,
                    None,
                    10,  # Filter strength
                    10,  # Color component filter strength
                    7,   # Template window size
                    21   # Search window size
                )
            except Exception as e:
                self.log(f"Denoising error: {str(e)}")
        
        # Apply sharpening if enabled
        if self.check_sharpen.isChecked():
            try:
                kernel = np.array([
                    [-1, -1, -1],
                    [-1, 9, -1],
                    [-1, -1, -1]
                ])
                processed = cv2.filter2D(processed, -1, kernel)
            except Exception as e:
                self.log(f"Sharpening error: {str(e)}")
        
        # Apply histogram equalization if enabled
        if self.check_hist_eq.isChecked():
            try:
                # Convert to YUV color space
                yuv = cv2.cvtColor(processed, cv2.COLOR_BGR2YUV)
                # Equalize the Y channel
                yuv[:,:,0] = cv2.equalizeHist(yuv[:,:,0])
                # Convert back to BGR
                processed = cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR)
            except Exception as e:
                self.log(f"Histogram equalization error: {str(e)}")
        
        return processed
    
    def update_original_preview(self, frame):
        """Updates the original frame preview"""
        if frame is not None:
            # Convert BGR to RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Create QImage
            height, width, channels = rgb_frame.shape
            bytes_per_line = channels * width
            q_img = QImage(rgb_frame.data, width, height, bytes_per_line, QImage.Format_RGB888)
            
            # Scale for preview
            pixmap = QPixmap.fromImage(q_img)
            pixmap = pixmap.scaled(
                self.lbl_original_frame.width(),
                self.lbl_original_frame.height(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            
            # Update label
            self.lbl_original_frame.setPixmap(pixmap)
    
    def update_processed_preview(self, frame):
        """Updates the processed frame preview"""
        if frame is not None:
            # Convert BGR to RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Create QImage
            height, width, channels = rgb_frame.shape
            bytes_per_line = channels * width
            q_img = QImage(rgb_frame.data, width, height, bytes_per_line, QImage.Format_RGB888)
            
            # Scale for preview
            pixmap = QPixmap.fromImage(q_img)
            pixmap = pixmap.scaled(
                self.lbl_processed_frame.width(),
                self.lbl_processed_frame.height(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            
            # Update label
            self.lbl_processed_frame.setPixmap(pixmap)
    
    def start_processing(self):
        """Starts video processing with selected options"""
        if self.processing_running:
            return
        
        if not self.parent.capture_path or not os.path.exists(self.parent.capture_path):
            QMessageBox.warning(
                self,
                "No Input Video",
                "Please capture a video first."
            )
            return
        
        try:
            # Create output directory
            input_dir = os.path.dirname(self.parent.capture_path)
            output_path = os.path.join(input_dir, "processed.avi")
            
            # Get processing options
            processing_options = {}
            
            if self.check_resize.isChecked():
                size_str = self.cmb_resize.currentText()
                width, height = map(int, size_str.split('x'))
                processing_options['resize'] = (width, height)
            
            processing_options['denoise'] = self.check_denoise.isChecked()
            processing_options['sharpen'] = self.check_sharpen.isChecked()
            processing_options['histogram_eq'] = self.check_hist_eq.isChecked()
            
            # Log processing settings
            self.log("Starting video processing with options:")
            for key, value in processing_options.items():
                self.log(f"- {key}: {value}")
            
            # Create worker
            self.worker = ProcessingWorker(
                self.parent.capture_path,
                output_path,
                processing_options
            )
            
            self.processing_thread = QThread()
            self.worker.moveToThread(self.processing_thread)
            
            # Connect signals
            self.worker.progress.connect(self.update_progress)
            self.worker.frame_processed.connect(self.update_processed_preview)
            self.worker.processing_complete.connect(self.on_processing_complete)
            self.worker.error.connect(self.on_processing_error)
            self.worker.log.connect(self.log)
            
            self.processing_thread.started.connect(self.worker.process_video)
            
            # Start processing
            self.processing_running = True
            self.processing_thread.start()
            
            # Update UI
            self.btn_start_processing.setEnabled(False)
            self.btn_stop_processing.setEnabled(True)
            self.btn_preview.setEnabled(False)
            self.lbl_processing_status.setText("Processing...")
            self.pb_processing_progress.setValue(0)
            
            # Emit signal
            self.processing_started.emit()
            
        except Exception as e:
            self.log(f"Error starting processing: {str(e)}")
            QMessageBox.critical(
                self,
                "Processing Error",
                f"Failed to start processing: {str(e)}"
            )
    
    def stop_processing(self):
        """Stops the current processing operation"""
        if not self.processing_running:
            return
        
        self.log("Stopping processing...")
        
        # Stop thread
        if self.processing_thread and self.processing_thread.isRunning():
            self.processing_thread.quit()
            self.processing_thread.wait()
        
        # Update UI
        self.processing_running = False
        self.btn_start_processing.setEnabled(True)
        self.btn_stop_processing.setEnabled(False)
        self.btn_preview.setEnabled(True)
        self.lbl_processing_status.setText("Processing stopped by user")
    
    def update_progress(self, progress):
        """Updates the progress bar"""
        self.pb_processing_progress.setValue(progress)
    
    def on_processing_complete(self, output_path):
        """Handles processing completion"""
        self.processing_running = False
        
        # Update UI
        self.btn_start_processing.setEnabled(True)
        self.btn_stop_processing.setEnabled(False)
        self.btn_preview.setEnabled(True)
        self.lbl_processing_status.setText("Processing completed")
        self.pb_processing_progress.setValue(100)
        
        self.log(f"Processing completed: {output_path}")
        
        # Check if file exists
        if not os.path.exists(output_path):
            self.log("Error: Processed file not found")
            return
        
        # Get file info
        try:
            cap = cv2.VideoCapture(output_path)
            if cap.isOpened():
                # Extract a preview frame
                ret, frame = cap.read()
                if ret:
                    self.update_processed_preview(frame)
                cap.release()
        except Exception as e:
            self.log(f"Error getting processed video info: {str(e)}")
        
        # Enable next button
        self.btn_next_to_analysis.setEnabled(True)
        
        # Signal completion
        self.processing_completed.emit(output_path)
        
        # Clean up thread
        if self.processing_thread:
            self.processing_thread.quit()
            self.processing_thread.wait()
            self.processing_thread = None
            self.worker = None
    
    def on_processing_error(self, error_message):
        """Handles processing errors"""
        self.log(f"Error: {error_message}")
        
        # Update UI
        self.btn_start_processing.setEnabled(True)
        self.btn_stop_processing.setEnabled(False)
        self.btn_preview.setEnabled(True)
        self.lbl_processing_status.setText(f"Error: {error_message}")
        self.processing_running = False
        
        # Show error message
        QMessageBox.critical(
            self,
            "Processing Error",
            f"Processing failed: {error_message}"
        )
        
        # Clean up thread
        if self.processing_thread:
            self.processing_thread.quit()
            self.processing_thread.wait()
            self.processing_thread = None
            self.worker = None
    
    def log(self, message):
        """Adds a message to the processing log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.txt_processing_log.append(f"[{timestamp}] {message}")
        # Scroll to bottom
        cursor = self.txt_processing_log.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.txt_processing_log.setTextCursor(cursor)
    
    def reset(self):
        """Resets the processing tab"""
        # Stop processing if running
        if self.processing_running:
            self.stop_processing()
        
        # Reset UI
        self.pb_processing_progress.setValue(0)
        self.lbl_processing_status.setText("Ready")
        self.lbl_original_frame.setText("No preview available")
        self.lbl_original_frame.setPixmap(QPixmap())
        self.lbl_processed_frame.setText("No preview available")
        self.lbl_processed_frame.setPixmap(QPixmap())
        self.txt_processing_log.clear()
        self.btn_next_to_analysis.setEnabled(False)
        self.btn_start_processing.setEnabled(False)
        self.btn_preview.setEnabled(False)
        
        # Reset options
        self.cmb_presets.setCurrentIndex(0)
        self.check_resize.setChecked(False)
        self.check_denoise.setChecked(False)
        self.check_sharpen.setChecked(False)
        self.check_hist_eq.setChecked(False)
        
        # Reset video info
        self.lbl_video_info.setText("No video selected for processing")






                
# Analysis Tab
class AnalysisTab(QWidget):
    """Analysis tab for performing quality assessment"""
    analysis_started = pyqtSignal()
    analysis_completed = pyqtSignal(dict)
    
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.analysis_thread = None
        self.worker = None
        self.analysis_running = False
        self.reference_path = None
        self.distorted_path = None
        self.setup_ui()
    
    def setup_ui(self):
        """Sets up the UI for the analysis tab"""
        layout = QVBoxLayout(self)
        
        # Videos info
        info_group = QGroupBox("Videos for Analysis")
        info_layout = QVBoxLayout()
        
        self.lbl_analysis_summary = QLabel("No videos ready for analysis")
        info_layout.addWidget(self.lbl_analysis_summary)
        
        # Preview thumbnails
        thumbs_layout = QHBoxLayout()
        
        # Reference preview
        ref_frame = QFrame()
        ref_frame.setFrameShape(QFrame.StyledPanel)
        ref_layout = QVBoxLayout(ref_frame)
        
        ref_layout.addWidget(QLabel("<b>Reference:</b>"))
        
        self.lbl_ref_preview = QLabel("No preview")
        self.lbl_ref_preview.setMinimumSize(320, 180)
        self.lbl_ref_preview.setAlignment(Qt.AlignCenter)
        ref_layout.addWidget(self.lbl_ref_preview)
        
        thumbs_layout.addWidget(ref_frame)
        
        # Distorted preview
        dist_frame = QFrame()
        dist_frame.setFrameShape(QFrame.StyledPanel)
        dist_layout = QVBoxLayout(dist_frame)
        
        dist_layout.addWidget(QLabel("<b>Distorted:</b>"))
        
        self.lbl_dist_preview = QLabel("No preview")
        self.lbl_dist_preview.setMinimumSize(320, 180)
        self.lbl_dist_preview.setAlignment(Qt.AlignCenter)
        dist_layout.addWidget(self.lbl_dist_preview)
        
        thumbs_layout.addWidget(dist_frame)
        
        info_layout.addLayout(thumbs_layout)
        
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)
        
        # Analysis options and controls
        options_layout = QHBoxLayout()
        
        # Analysis options
        options_group = QGroupBox("Analysis Options")
        options_form = QFormLayout()
        
        # VMAF model selection
        self.cmb_vmaf_model = QComboBox()
        self.populate_vmaf_models()
        options_form.addRow("VMAF Model:", self.cmb_vmaf_model)
        
        # Metrics selection
        metrics_layout = QVBoxLayout()
        self.check_vmaf = QCheckBox("VMAF")
        self.check_vmaf.setChecked(True)
        metrics_layout.addWidget(self.check_vmaf)
        
        self.check_psnr = QCheckBox("PSNR")
        self.check_psnr.setChecked(True)
        metrics_layout.addWidget(self.check_psnr)
        
        self.check_ssim = QCheckBox("SSIM")
        self.check_ssim.setChecked(True)
        metrics_layout.addWidget(self.check_ssim)
        
        options_form.addRow("Metrics:", metrics_layout)
        
        options_group.setLayout(options_form)
        options_layout.addWidget(options_group)
        
        # Analysis controls
        controls_group = QGroupBox("Analysis Controls")
        controls_layout = QVBoxLayout()
        
        # Status labels
        self.lbl_alignment_status = QLabel("Not aligned")
        controls_layout.addWidget(self.lbl_alignment_status)
        
        self.pb_alignment_progress = QProgressBar()
        self.pb_alignment_progress.setRange(0, 100)
        self.pb_alignment_progress.setValue(0)
        controls_layout.addWidget(self.pb_alignment_progress)
        
        self.lbl_vmaf_status = QLabel("Not analyzed")
        controls_layout.addWidget(self.lbl_vmaf_status)
        
        self.pb_vmaf_progress = QProgressBar()
        self.pb_vmaf_progress.setRange(0, 100)
        self.pb_vmaf_progress.setValue(0)
        controls_layout.addWidget(self.pb_vmaf_progress)
        
        # Run buttons
        self.btn_run_combined_analysis = QPushButton("Run Analysis")
        self.btn_run_combined_analysis.clicked.connect(self.run_combined_analysis)
        self.btn_run_combined_analysis.setEnabled(False)
        controls_layout.addWidget(self.btn_run_combined_analysis)
        
        self.btn_stop_analysis = QPushButton("Stop Analysis")
        self.btn_stop_analysis.clicked.connect(self.stop_analysis)
        self.btn_stop_analysis.setEnabled(False)
        controls_layout.addWidget(self.btn_stop_analysis)
        
        controls_group.setLayout(controls_layout)
        options_layout.addWidget(controls_group)
        
        layout.addLayout(options_layout)
        
        # Analysis log
        log_group = QGroupBox("Analysis Log")
        log_layout = QVBoxLayout()
        
        self.txt_analysis_log = QTextEdit()
        self.txt_analysis_log.setReadOnly(True)
        log_layout.addWidget(self.txt_analysis_log)
        
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)
        
        # Navigation buttons
        nav_layout = QHBoxLayout()
        
        self.btn_prev_to_processing = QPushButton("Back: Processing")
        nav_layout.addWidget(self.btn_prev_to_processing)
        
        nav_layout.addStretch()
        
        self.btn_next_to_results = QPushButton("Next: Results")
        self.btn_next_to_results.setEnabled(False)
        nav_layout.addWidget(self.btn_next_to_results)
        
        layout.addLayout(nav_layout)
    
    def populate_vmaf_models(self):
        """Populates VMAF model dropdown with available models"""
        self.cmb_vmaf_model.clear()
        
        # Add default model
        self.cmb_vmaf_model.addItem("Default", None)
        
        # Add other models if available
        try:
            # In a real implementation, scan ffmpeg libvmaf model directory
            self.cmb_vmaf_model.addItem("vmaf_v0.6.1", "vmaf_v0.6.1.json")
            self.cmb_vmaf_model.addItem("vmaf_4K_v0.6.1", "vmaf_4k_v0.6.1.json")
            self.cmb_vmaf_model.addItem("vmaf_v0.6.1neg", "vmaf_v0.6.1neg.json")
            
            logger.info(f"Populated VMAF model dropdown with {self.cmb_vmaf_model.count()} models")
        except Exception as e:
            logger.error(f"Error populating VMAF models: {str(e)}")
    
    def update_reference_info(self, file_path):
        """Updates reference video information"""
        self.reference_path = file_path
        self.update_analysis_summary()
        
        # Load preview frame
        try:
            cap = cv2.VideoCapture(file_path)
            if cap.isOpened():
                ret, frame = cap.read()
                if ret:
                    self.update_reference_preview(frame)
                cap.release()
        except Exception as e:
            self.log(f"Error loading reference preview: {str(e)}")
    
    def update_distorted_info(self, file_path):
        """Updates distorted video information"""
        self.distorted_path = file_path
        self.update_analysis_summary()
        
        # Load preview frame
        try:
            cap = cv2.VideoCapture(file_path)
            if cap.isOpened():
                ret, frame = cap.read()
                if ret:
                    self.update_distorted_preview(frame)
                cap.release()
        except Exception as e:
            self.log(f"Error loading distorted preview: {str(e)}")
        
        # Enable analysis button if both videos are available
        if self.reference_path and self.distorted_path:
            self.btn_run_combined_analysis.setEnabled(True)
    
    def update_analysis_summary(self):
        """Updates the analysis summary with current video info"""
        if self.reference_path and self.distorted_path:
            ref_basename = os.path.basename(self.reference_path)
            dist_basename = os.path.basename(self.distorted_path)
            
            summary = (
                f"<b>Reference:</b> {ref_basename}<br>"
                f"<b>Distorted:</b> {dist_basename}<br>"
                f"<b>Ready for analysis</b>"
            )
            
            self.lbl_analysis_summary.setText(summary)
        elif self.reference_path:
            ref_basename = os.path.basename(self.reference_path)
            
            summary = (
                f"<b>Reference:</b> {ref_basename}<br>"
                f"<b>No captured/processed video yet</b>"
            )
            
            self.lbl_analysis_summary.setText(summary)
        else:
            self.lbl_analysis_summary.setText("No videos ready for analysis")
    
    def update_reference_preview(self, frame):
        """Updates the reference video preview"""
        if frame is not None:
            # Convert BGR to RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Create QImage
            height, width, channels = rgb_frame.shape
            bytes_per_line = channels * width
            q_img = QImage(rgb_frame.data, width, height, bytes_per_line, QImage.Format_RGB888)
            
            # Scale for preview
            pixmap = QPixmap.fromImage(q_img)
            pixmap = pixmap.scaled(
                self.lbl_ref_preview.width(),
                self.lbl_ref_preview.height(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            
            # Update label
            self.lbl_ref_preview.setPixmap(pixmap)
    
    def update_distorted_preview(self, frame):
        """Updates the distorted video preview"""
        if frame is not None:
            # Convert BGR to RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Create QImage
            height, width, channels = rgb_frame.shape
            bytes_per_line = channels * width
            q_img = QImage(rgb_frame.data, width, height, bytes_per_line, QImage.Format_RGB888)
            
            # Scale for preview
            pixmap = QPixmap.fromImage(q_img)
            pixmap = pixmap.scaled(
                self.lbl_dist_preview.width(),
                self.lbl_dist_preview.height(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            
            # Update label
            self.lbl_dist_preview.setPixmap(pixmap)
    
    def run_combined_analysis(self):
        """Runs the complete analysis process"""
        if self.analysis_running:
            return
        
        if not self.reference_path or not self.distorted_path:
            QMessageBox.warning(
                self,
                "Videos Required",
                "Both reference and distorted videos are required for analysis."
            )
            return
        
        try:
            # Create output directory
            test_name = self.parent.setup_tab.txt_test_name.text() or "Test"
            input_dir = os.path.dirname(self.distorted_path)
            output_dir = input_dir
            
            # Get selected metrics
            metrics = []
            if self.check_vmaf.isChecked():
                metrics.append('vmaf')
            if self.check_psnr.isChecked():
                metrics.append('psnr')
            if self.check_ssim.isChecked():
                metrics.append('ssim')
            
            if not metrics:
                QMessageBox.warning(
                    self,
                    "No Metrics Selected",
                    "Please select at least one quality metric."
                )
                return
            
            # Get selected VMAF model
            vmaf_model = self.cmb_vmaf_model.currentData()
            
            # Log analysis settings
            self.log(f"Starting quality analysis with settings:")
            self.log(f"- Reference: {os.path.basename(self.reference_path)}")
            self.log(f"- Distorted: {os.path.basename(self.distorted_path)}")
            self.log(f"- Metrics: {', '.join(metrics)}")
            self.log(f"- VMAF Model: {vmaf_model or 'Default'}")
            
            # Create worker
            self.worker = AnalysisWorker(
                self.reference_path,
                self.distorted_path,
                output_dir,
                metrics,
                vmaf_model
            )
            
            self.analysis_thread = QThread()
            self.worker.moveToThread(self.analysis_thread)
            
            # Connect signals
            self.worker.progress.connect(self.update_vmaf_progress)
            self.worker.analysis_complete.connect(self.on_analysis_complete)
            self.worker.error.connect(self.on_analysis_error)
            self.worker.log.connect(self.log)
            
            self.analysis_thread.started.connect(self.worker.analyze_quality)
            
            # Start analysis
            self.analysis_running = True
            self.analysis_thread.start()
            
            # Update UI
            self.btn_run_combined_analysis.setEnabled(False)
            self.btn_stop_analysis.setEnabled(True)
            self.lbl_vmaf_status.setText("Analyzing...")
            self.pb_vmaf_progress.setValue(0)
            
            # Emit signal
            self.analysis_started.emit()
            
        except Exception as e:
            self.log(f"Error starting analysis: {str(e)}")
            QMessageBox.critical(
                self,
                "Analysis Error",
                f"Failed to start analysis: {str(e)}"
            )
    
    def stop_analysis(self):
        """Stops the current analysis process"""
        if not self.analysis_running:
            return
        
        self.log("Stopping analysis...")
        
        if self.worker:
            self.worker.stop()
        
        # Wait for thread to finish
        if self.analysis_thread and self.analysis_thread.isRunning():
            self.analysis_thread.quit()
            self.analysis_thread.wait(3000)
            
            if self.analysis_thread.isRunning():
                self.analysis_thread.terminate()
        
        # Update UI
        self.analysis_running = False
        self.btn_run_combined_analysis.setEnabled(True)
        self.btn_stop_analysis.setEnabled(False)
        self.lbl_vmaf_status.setText("Analysis stopped by user")
    
    def update_vmaf_progress(self, progress):
        """Updates the VMAF analysis progress bar"""
        self.pb_vmaf_progress.setValue(progress)
    
    def on_analysis_complete(self, results):
        """Handles analysis completion"""
        self.analysis_running = False
        
        # Extract main scores
        vmaf_score = results.get('vmaf_score', 'N/A')
        psnr_score = results.get('psnr', 'N/A')
        ssim_score = results.get('ssim', 'N/A')
        
        vmaf_str = f"{vmaf_score:.2f}" if isinstance(vmaf_score, (int, float)) else vmaf_score
        psnr_str = f"{psnr_score:.2f} dB" if isinstance(psnr_score, (int, float)) else psnr_score
        ssim_str = f"{ssim_score:.4f}" if isinstance(ssim_score, (int, float)) else ssim_score
        
        # Log results
        self.log("Analysis completed successfully")
        self.log(f"VMAF Score: {vmaf_str}")
        self.log(f"PSNR: {psnr_str}")
        self.log(f"SSIM: {ssim_str}")
        
        # Update UI
        self.btn_run_combined_analysis.setEnabled(True)
        self.btn_stop_analysis.setEnabled(False)
        self.lbl_vmaf_status.setText(f"Analysis complete - VMAF: {vmaf_str}")
        self.pb_vmaf_progress.setValue(100)
        
        # Enable next button
        self.btn_next_to_results.setEnabled(True)
        
        # Signal completion
        self.analysis_completed.emit(results)
        
        # Clean up thread
        if self.analysis_thread:
            self.analysis_thread.quit()
            self.analysis_thread.wait()
            self.analysis_thread = None
            self.worker = None
    
    def on_analysis_error(self, error_message):
        """Handles analysis errors"""
        self.log(f"Error: {error_message}")
        
        # Update UI
        self.btn_run_combined_analysis.setEnabled(True)
        self.btn_stop_analysis.setEnabled(False)
        self.lbl_vmaf_status.setText(f"Error: {error_message}")
        self.analysis_running = False
        
        # Show error message
        QMessageBox.critical(
            self,
            "Analysis Error",
            f"Analysis failed: {error_message}"
        )
        
        # Clean up thread
        if self.analysis_thread:
            self.analysis_thread.quit()
            self.analysis_thread.wait()
            self.analysis_thread = None
            self.worker = None
    
    def log(self, message):
        """Adds a message to the analysis log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.txt_analysis_log.append(f"[{timestamp}] {message}")
        # Scroll to bottom
        cursor = self.txt_analysis_log.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.txt_analysis_log.setTextCursor(cursor)
    
    def reset(self):
        """Resets the analysis tab"""
        # Stop analysis if running
        if self.analysis_running:
            self.stop_analysis()
        
        # Reset UI
        self.pb_alignment_progress.setValue(0)
        self.pb_vmaf_progress.setValue(0)
        self.lbl_alignment_status.setText("Not aligned")
        self.lbl_vmaf_status.setText("Not analyzed")
        self.txt_analysis_log.clear()
        self.btn_next_to_results.setEnabled(False)
        self.btn_run_combined_analysis.setEnabled(False)
        
        # Reset state
        self.distorted_path = None
        
        # Reset previews
        self.lbl_ref_preview.setText("No preview")
        self.lbl_ref_preview.setPixmap(QPixmap())
        self.lbl_dist_preview.setText("No preview")
        self.lbl_dist_preview.setPixmap(QPixmap())
        
        # Reset summary
        self.lbl_analysis_summary.setText("No videos ready for analysis")              
                
                
                
                
# Results Tab
class ResultsTab(QWidget):
    """Results tab for displaying quality assessment results"""
    
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.setup_ui()
    
    def setup_ui(self):
        """Sets up the UI for the results tab"""
        layout = QVBoxLayout(self)
        
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
        score_group = QGroupBox("Quality Metrics")
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
        self.btn_export_pdf = QPushButton("Export PDF Report")
        self.btn_export_pdf.clicked.connect(self.export_pdf_report)
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
        
        # Setup history tab
        history_layout = QVBoxLayout(history_tab)
        
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
        
        # Create table for results history
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(8)
        self.results_table.setHorizontalHeaderLabels([
            "Test Name", "Date/Time", "VMAF Score", "PSNR", "SSIM", 
            "Reference", "Duration", "Actions"
        ])
        self.results_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.results_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        
        history_layout.addWidget(self.results_table)
        
        # Add results tabs to main layout
        layout.addWidget(results_tabs)
        
        # Navigation buttons at the bottom
        nav_layout = QHBoxLayout()
        self.btn_prev_to_analysis = QPushButton("Back: Analysis")
        nav_layout.addWidget(self.btn_prev_to_analysis)
        
        nav_layout.addStretch()
        
        self.btn_new_test = QPushButton("Start New Test")
        self.btn_new_test.clicked.connect(self.on_new_test)
        nav_layout.addWidget(self.btn_new_test)
        
        layout.addLayout(nav_layout)
        
        # Load results history
        self.load_results_history()
    
    def update_results(self, results):
        """Updates UI with analysis results"""
        if not results:
            return
        
        # Update test name in header
        test_name = self.parent.setup_tab.txt_test_name.text()
        self.lbl_results_summary.setText(f"VMAF Analysis Results for {test_name}")
        
        # Update metrics display
        vmaf_score = results.get('vmaf_score')
        psnr = results.get('psnr')
        ssim = results.get('ssim')
        
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
        
        # Update result files list
        self.update_result_files_list(results)
        
        # Refresh history
        self.load_results_history()
    
    def update_result_files_list(self, results):
        """Updates the list of result files"""
        self.list_result_files.clear()
        
        # Add final output files
        json_path = results.get('json_path')
        if json_path and os.path.exists(json_path):
            item = QListWidgetItem(f"VMAF Results: {os.path.basename(json_path)}")
            item.setData(Qt.UserRole, json_path)
            self.list_result_files.addItem(item)
        
        reference_path = results.get('reference_path')
        if reference_path and os.path.exists(reference_path):
            item = QListWidgetItem(f"Reference: {os.path.basename(reference_path)}")
            item.setData(Qt.UserRole, reference_path)
            self.list_result_files.addItem(item)
        
        distorted_path = results.get('distorted_path')
        if distorted_path and os.path.exists(distorted_path):
            item = QListWidgetItem(f"Distorted: {os.path.basename(distorted_path)}")
            item.setData(Qt.UserRole, distorted_path)
            self.list_result_files.addItem(item)
    
    def open_result_file(self, item):
        """Opens selected result file"""
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
                QMessageBox.warning(
                    self,
                    "Error Opening File",
                    f"Could not open file: {str(e)}"
                )
    
    def export_pdf_report(self):
        """Exports results as PDF report"""
        if not self.parent.analysis_results:
            QMessageBox.warning(self, "No Results", "No analysis results available to export.")
            return
        
        # Get output file path
        test_name = self.parent.setup_tab.txt_test_name.text()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"{test_name}_report_{timestamp}.pdf"
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save PDF Report",
            os.path.join(os.path.expanduser("~"), default_filename),
            "PDF Files (*.pdf)"
        )
        
        if not file_path:
            return
        
        try:
            # Show generating message
            QMessageBox.information(
                self,
                "Export PDF",
                "PDF report export would be implemented here.\n\n"
                "This would generate a PDF report with metrics, charts, and test metadata."
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Export Error",
                f"Failed to export PDF report: {str(e)}"
            )
    
    def export_csv_data(self):
        """Exports results as CSV data"""
        if not self.parent.analysis_results:
            QMessageBox.warning(self, "No Results", "No analysis results available to export.")
            return
        
        # Get output file path
        test_name = self.parent.setup_tab.txt_test_name.text()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"{test_name}_data_{timestamp}.csv"
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save CSV Data",
            os.path.join(os.path.expanduser("~"), default_filename),
            "CSV Files (*.csv)"
        )
        
        if not file_path:
            return
        
        try:
            # Extract data
            results = self.parent.analysis_results
            vmaf_score = results.get('vmaf_score', 'N/A')
            psnr_score = results.get('psnr', 'N/A')
            ssim_score = results.get('ssim', 'N/A')
            reference_path = results.get('reference_path', 'N/A')
            distorted_path = results.get('distorted_path', 'N/A')
            
            # Write CSV file
            with open(file_path, 'w', newline='') as csvfile:
                import csv
                writer = csv.writer(csvfile)
                
                # Write header and summary data
                writer.writerow(['Test Name', 'Date', 'VMAF Score', 'PSNR Score', 'SSIM Score'])
                writer.writerow([
                    test_name,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    vmaf_score if isinstance(vmaf_score, str) else f"{vmaf_score:.4f}",
                    psnr_score if isinstance(psnr_score, str) else f"{psnr_score:.4f}",
                    ssim_score if isinstance(ssim_score, str) else f"{ssim_score:.4f}"
                ])
                
                writer.writerow([])  # Empty row
                writer.writerow(['Reference File', reference_path])
                writer.writerow(['Distorted File', distorted_path])
                
                # Write frame data if available
                if 'raw_results' in results and 'frames' in results['raw_results']:
                    frames = results['raw_results']['frames']
                    
                    if frames:
                        writer.writerow([])  # Empty row
                        
                        # Determine which metrics are available
                        first_frame = frames[0]
                        metrics = first_frame.get('metrics', {})
                        available_metrics = list(metrics.keys())
                        
                        # Write frame data header
                        header = ['Frame Number']
                        for metric in available_metrics:
                            header.append(metric)
                        writer.writerow(header)
                        
                        # Write each frame's data
                        for frame in frames:
                            frame_num = frame.get('frameNum', 'N/A')
                            metrics = frame.get('metrics', {})
                            
                            row = [frame_num]
                            for metric in available_metrics:
                                value = metrics.get(metric, 'N/A')
                                if isinstance(value, (int, float)):
                                    value = f"{value:.4f}"
                                row.append(value)
                            
                            writer.writerow(row)
            
            QMessageBox.information(
                self,
                "Export Complete",
                f"VMAF data successfully exported to CSV:\n{file_path}"
            )
            
            # Ask if user wants to open the CSV
            reply = QMessageBox.question(
                self,
                "Open CSV",
                "Would you like to open the CSV file now?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            
            if reply == QMessageBox.Yes:
                try:
                    if platform.system() == 'Windows':
                        os.startfile(file_path)
                    elif platform.system() == 'Darwin':  # macOS
                        subprocess.run(['open', file_path], check=True)
                    else:  # Linux
                        subprocess.run(['xdg-open', file_path], check=True)
                except Exception as e:
                    QMessageBox.warning(
                        self,
                        "Open Failed",
                        f"Could not open the CSV file: {str(e)}"
                    )
                    
        except Exception as e:
            QMessageBox.critical(
                self,
                "Export Error",
                f"Failed to export CSV: {str(e)}"
            )
    
    def load_results_history(self):
        """Loads historical test results into the data grid"""
        try:
            self.results_table.setRowCount(0)
            
            # Get output directory
            output_dir = self.parent.output_dir
            if not os.path.exists(output_dir):
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
                json_files = [f for f in os.listdir(test_dir) if f.endswith("_vmaf.json") or f == "vmaf.json"]
                
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
                                # Estimate duration from frame count
                                duration = len(frames) / 30.0  # Assuming 30fps
                                
                                # Get the metrics from the first frame as fallback
                                metrics = frames[0].get("metrics", {})
                                if vmaf_score is None and "vmaf" in metrics:
                                    vmaf_score = metrics["vmaf"]
                                if psnr_score is None and ("psnr" in metrics or "psnr_y" in metrics):
                                    psnr_score = metrics.get("psnr", metrics.get("psnr_y"))
                                if ssim_score is None and ("ssim" in metrics or "ssim_y" in metrics):
                                    ssim_score = metrics.get("ssim", metrics.get("ssim_y"))
                        
                        # Figure out reference name
                        reference_name = "Unknown"
                        for f in os.listdir(test_dir):
                            if (f.lower().startswith("ref") or 
                                "reference" in f.lower() or 
                                f == os.path.basename(self.parent.reference_path or "")):
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
                        btn_view.clicked.connect(self.view_result)
                        actions_layout.addWidget(btn_view)
                        
                        btn_delete = QPushButton("Delete")
                        btn_delete.setProperty("row", row)
                        btn_delete.setProperty("dir", test_dir)
                        btn_delete.clicked.connect(self.delete_result)
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
    
    def view_result(self):
        """Views a historical test result"""
        sender = self.sender()
        row = sender.property("row")
        test_dir = sender.property("dir")
        
        try:
            # Get test details
            item = self.results_table.item(row, 0)
            test_name = item.text() if item else "Unknown"
            
            item = self.results_table.item(row, 1)
            timestamp = item.text() if item else "Unknown"
            
            # Show result dialog
            QMessageBox.information(
                self,
                "View Result",
                f"This would display detailed results for test:\n{test_name} ({timestamp})\n\n"
                "With frame-by-frame charts, thumbnails, and detailed metrics."
            )
            
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Error viewing result: {str(e)}"
            )
    
    def delete_result(self):
        """Deletes a historical test result"""
        sender = self.sender()
        row = sender.property("row")
        test_dir = sender.property("dir")
        
        try:
            # Confirm deletion
            reply = QMessageBox.question(
                self,
                "Confirm Deletion",
                f"Are you sure you want to delete this test result?\n\nThis will permanently delete all files in:\n{test_dir}",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply != QMessageBox.Yes:
                return
            
            # Delete the directory
            shutil.rmtree(test_dir)
            
            # Remove from table
            self.results_table.removeRow(row)
            
            QMessageBox.information(
                self,
                "Deleted",
                "Test result deleted successfully."
            )
            
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Error deleting result: {str(e)}"
            )
    
    def delete_selected_results(self):
        """Deletes selected results"""
        selected_rows = []
        for item in self.results_table.selectedItems():
            if item.row() not in selected_rows:
                selected_rows.append(item.row())
        
        if not selected_rows:
            QMessageBox.information(
                self,
                "No Selection",
                "Please select at least one test result to delete."
            )
            return
        
        try:
            # Confirm deletion
            reply = QMessageBox.question(
                self,
                "Confirm Deletion",
                f"Are you sure you want to delete {len(selected_rows)} selected test results?\n\nThis cannot be undone.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply != QMessageBox.Yes:
                return
            
            # Delete selected items (in reverse order to avoid index issues)
            for row in sorted(selected_rows, reverse=True):
                item = self.results_table.item(row, 0)
                if item:
                    data = item.data(Qt.UserRole)
                    if data and "test_dir" in data:
                        test_dir = data["test_dir"]
                        
                        # Delete directory
                        if os.path.exists(test_dir):
                            shutil.rmtree(test_dir)
                        
                        # Remove from table
                        self.results_table.removeRow(row)
            
            QMessageBox.information(
                self,
                "Deleted",
                f"{len(selected_rows)} test results deleted successfully."
            )
            
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Error deleting results: {str(e)}"
            )
    
    def export_selected_results(self):
        """Exports selected results"""
        selected_rows = []
        for item in self.results_table.selectedItems():
            if item.row() not in selected_rows:
                selected_rows.append(item.row())
        
        if not selected_rows:
            QMessageBox.information(
                self,
                "No Selection",
                "Please select at least one test result to export."
            )
            return
        
        # Get export format
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QRadioButton, QButtonGroup, QLabel
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Export Format")
        layout = QVBoxLayout(dialog)
        
        layout.addWidget(QLabel(f"Export {len(selected_rows)} results as:"))
        
        format_group = QButtonGroup(dialog)
        
        csv_radio = QRadioButton("CSV Data Files")
        csv_radio.setChecked(True)
        format_group.addButton(csv_radio, 1)
        layout.addWidget(csv_radio)
        
        pdf_radio = QRadioButton("PDF Reports")
        format_group.addButton(pdf_radio, 2)
        layout.addWidget(pdf_radio)
        
        combined_radio = QRadioButton("Combined CSV Summary")
        format_group.addButton(combined_radio, 3)
        layout.addWidget(combined_radio)
        
        btn_layout = QHBoxLayout()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(dialog.reject)
        btn_layout.addWidget(btn_cancel)
        
        btn_export = QPushButton("Export")
        btn_export.clicked.connect(dialog.accept)
        btn_layout.addWidget(btn_export)
        
        layout.addLayout(btn_layout)
        
        # Show dialog
        if dialog.exec_() != QDialog.Accepted:
            return
        
        export_format = format_group.checkedId()
        
        try:
            # Get output directory
            output_dir = QFileDialog.getExistingDirectory(
                self,
                "Select Export Directory",
                os.path.expanduser("~")
            )
            
            if not output_dir:
                return
            
            # Export each selected result
            for row in selected_rows:
                item = self.results_table.item(row, 0)
                if item:
                    data = item.data(Qt.UserRole)
                    if data and "test_dir" in data:
                        test_dir = data["test_dir"]
                        test_name = data.get("test_name", f"test_{row}")
                        
                        # Export based on format
                        if export_format == 1:  # CSV
                            self.export_result_csv(test_dir, test_name, output_dir)
                        elif export_format == 2:  # PDF
                            self.export_result_pdf(test_dir, test_name, output_dir)
                        # Combined CSV is handled separately
            
            if export_format == 3:  # Combined CSV
                self.export_combined_csv(selected_rows, output_dir)
            
            QMessageBox.information(
                self,
                "Export Complete",
                f"Successfully exported {len(selected_rows)} test results to:\n{output_dir}"
            )
            
        except Exception as e:
            QMessageBox.critical(
                self,
                "Export Error",
                f"Error exporting results: {str(e)}"
            )
    
    def export_result_csv(self, test_dir, test_name, output_dir):
        """Exports a test result as CSV"""
        try:
            # Find the JSON file
            json_path = None
            for f in os.listdir(test_dir):
                if f.endswith("_vmaf.json") or f == "vmaf.json":
                    json_path = os.path.join(test_dir, f)
                    break
            
            if not json_path or not os.path.exists(json_path):
                logger.error(f"Could not find JSON file in {test_dir}")
                return
            
            # Load JSON data
            with open(json_path, 'r') as f:
                data = json.load(f)
            
            # Create output file path
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(output_dir, f"{test_name}_data_{timestamp}.csv")
            
            # Extract data
            vmaf_score = None
            psnr_score = None
            ssim_score = None
            
            # Try to get from pooled metrics first
            if "pooled_metrics" in data:
                pool = data["pooled_metrics"]
                if "vmaf" in pool:
                    vmaf_score = pool["vmaf"]["mean"]
                if "psnr" in pool or "psnr_y" in pool:
                    psnr_score = pool.get("psnr", {}).get("mean", pool.get("psnr_y", {}).get("mean"))
                if "ssim" in pool or "ssim_y" in pool:
                    ssim_score = pool.get("ssim", {}).get("mean", pool.get("ssim_y", {}).get("mean"))
            
            # Find reference and distorted videos
            reference_path = "Unknown"
            distorted_path = "Unknown"
            
            for f in os.listdir(test_dir):
                if (f.lower().startswith("ref") or "reference" in f.lower()):
                    reference_path = os.path.join(test_dir, f)
                elif "captured" in f.lower() or "distorted" in f.lower():
                    distorted_path = os.path.join(test_dir, f)
            
            # Write CSV file
            with open(output_path, 'w', newline='') as csvfile:
                import csv
                writer = csv.writer(csvfile)
                
                # Write header and summary data
                writer.writerow(['Test Name', 'Date', 'VMAF Score', 'PSNR Score', 'SSIM Score'])
                writer.writerow([
                    test_name,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    vmaf_score if isinstance(vmaf_score, str) else f"{vmaf_score:.4f}" if vmaf_score is not None else "N/A",
                    psnr_score if isinstance(psnr_score, str) else f"{psnr_score:.4f}" if psnr_score is not None else "N/A",
                    ssim_score if isinstance(ssim_score, str) else f"{ssim_score:.4f}" if ssim_score is not None else "N/A"
                ])
                
                writer.writerow([])  # Empty row
                writer.writerow(['Reference File', reference_path])
                writer.writerow(['Distorted File', distorted_path])
                
                # Write frame data if available
                if "frames" in data:
                    frames = data["frames"]
                    
                    if frames:
                        writer.writerow([])  # Empty row
                        
                        # Determine which metrics are available
                        first_frame = frames[0]
                        metrics = first_frame.get('metrics', {})
                        available_metrics = sorted(list(metrics.keys()))
                        
                        # Write frame data header
                        header = ['Frame Number']
                        header.extend(available_metrics)
                        writer.writerow(header)
                        
                        # Write each frame's data
                        for frame in frames:
                            frame_num = frame.get('frameNum', 'N/A')
                            metrics = frame.get('metrics', {})
                            
                            row = [frame_num]
                            for metric in available_metrics:
                                value = metrics.get(metric, 'N/A')
                                if isinstance(value, (int, float)):
                                    value = f"{value:.4f}"
                                row.append(value)
                            
                            writer.writerow(row)
            
            logger.info(f"Exported CSV to {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Error exporting CSV: {str(e)}")
            raise
    
    def export_result_pdf(self, test_dir, test_name, output_dir):
        """Exports a test result as PDF"""
        try:
            # Create output file path
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(output_dir, f"{test_name}_report_{timestamp}.pdf")
            
            # Show placeholder message
            logger.info(f"PDF export would be implemented to {output_path}")
            
            # In a real implementation, this would:
            # 1. Load the VMAF JSON data
            # 2. Create charts and visualizations
            # 3. Generate a PDF report with test details
            # 4. Include frame thumbnails and metrics
            
            return output_path
            
        except Exception as e:
            logger.error(f"Error exporting PDF: {str(e)}")
            raise
    
    def export_combined_csv(self, selected_rows, output_dir):
        """Exports multiple test results to a single CSV file"""
        try:
            # Create output file path
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(output_dir, f"combined_results_{timestamp}.csv")
            
            # Open CSV file
            with open(output_path, 'w', newline='') as csvfile:
                import csv
                writer = csv.writer(csvfile)
                
                # Write header row
                writer.writerow([
                    'Test Name', 'Date/Time', 'VMAF Score', 'PSNR Score', 'SSIM Score',
                    'Reference', 'Duration', 'Test Directory'
                ])
                
                # Process each selected row
                for row in selected_rows:
                    try:
                        # Get row data
                        test_name = self.results_table.item(row, 0).text()
                        timestamp = self.results_table.item(row, 1).text()
                        vmaf_score = self.results_table.item(row, 2).text()
                        psnr_score = self.results_table.item(row, 3).text()
                        ssim_score = self.results_table.item(row, 4).text()
                        reference = self.results_table.item(row, 5).text()
                        duration = self.results_table.item(row, 6).text()
                        
                        # Get test directory
                        test_dir = ""
                        item = self.results_table.item(row, 0)
                        if item:
                            data = item.data(Qt.UserRole)
                            if data and "test_dir" in data:
                                test_dir = data["test_dir"]
                        
                        # Write row
                        writer.writerow([
                            test_name, timestamp, vmaf_score, psnr_score, ssim_score,
                            reference, duration, test_dir
                        ])
                    except Exception as e:
                        logger.error(f"Error processing row {row}: {str(e)}")
                        continue
            
            logger.info(f"Exported combined CSV to {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Error exporting combined CSV: {str(e)}")
            raise
    
    def on_new_test(self):
        """Handles new test button click"""
        self.parent.start_new_test()
    
    def reset(self):
        """Resets the results tab"""
        # Reset UI
        self.lbl_results_summary.setText("No VMAF analysis results yet")
        self.lbl_vmaf_score.setText("VMAF Score: --")
        self.lbl_psnr_score.setText("PSNR: --")
        self.lbl_ssim_score.setText("SSIM: --")
        self.list_result_files.clear()
        
        # Disable export buttons
        self.btn_export_pdf.setEnabled(False)
        self.btn_export_csv.setEnabled(False)
        
        # Refresh history
        self.load_results_history()


# Main application entry point
def main():
    """Main application entry point"""
    # Set up exception handler
    def exception_handler(exc_type, exc_value, exc_traceback):
        logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
    
    sys.excepthook = exception_handler
    
    app = QApplication(sys.argv)
    app.setApplicationName("Video Quality Assessment")
    
    # Set stylesheet for a more modern look
    stylesheet = """
    QMainWindow, QDialog {
        background-color: #f5f5f5;
    }
    
    QTabWidget::pane {
        border: 1px solid #cccccc;
        background-color: #ffffff;
    }
    
    QTabBar::tab {
        background-color: #e0e0e0;
        border: 1px solid #cccccc;
        border-bottom-color: #cccccc;
        padding: 6px 12px;
    }
    
    QTabBar::tab:selected {
        background-color: #ffffff;
        border-bottom-color: #ffffff;
    }
    
    QGroupBox {
        background-color: #ffffff;
        border: 1px solid #cccccc;
        border-radius: 4px;
        margin-top: 8px;
    }
    
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 5px;
        background-color: #ffffff;
    }
    
    QPushButton {
        background-color: #0078d7;
        color: white;
        border: 1px solid #0067b8;
        border-radius: 3px;
        padding: 5px 15px;
    }
    
    QPushButton:hover {
        background-color: #0067b8;
    }
    
    QPushButton:pressed {
        background-color: #005a9e;
    }
    
    QPushButton:disabled {
        background-color: #cccccc;
        border: 1px solid #bbbbbb;
        color: #888888;
    }
    
    QProgressBar {
        border: 1px solid #cccccc;
        border-radius: 3px;
        text-align: center;
        background-color: #ffffff;
    }
    
    QProgressBar::chunk {
        background-color: #0078d7;
    }
    
    QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
        border: 1px solid #cccccc;
        border-radius: 3px;
        padding: 2px 4px;
        background-color: white;
    }
    
    QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
        border: 1px solid #0078d7;
    }
    """
    
    app.setStyleSheet(stylesheet)
    
    window = MainWindow()
    window.show()
    
    return app.exec_()


if __name__ == "__main__":
    main()