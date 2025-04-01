# test_vmaf.py
import sys
import os
import logging
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QPushButton, 
                            QProgressBar, QLabel, QFileDialog, QTextEdit,
                            QHBoxLayout, QComboBox, QCheckBox, QSpinBox, QGroupBox)
from PyQt5.QtCore import Qt, pyqtSlot
from analysis import VMAFAnalyzer, VMAFAnalysisThread
from alignment import VideoAligner, AlignmentThread

# Set up logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class LogRedirector(logging.Handler):
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget
        self.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        
    def emit(self, record):
        msg = self.format(record)
        self.text_widget.append(msg)

class VMAFTestWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.analyzer = VMAFAnalyzer()
        self.init_ui()
        self.setup_connections()
        self.setup_logging()
        
    def setup_logging(self):
        # Add log handler to redirect logs to text widget
        log_handler = LogRedirector(self.log)
        logging.getLogger().addHandler(log_handler)
        logger.info("Application started")
        
    def init_ui(self):
        self.setWindowTitle("VMAF Test Module")
        self.setGeometry(300, 300, 600, 500)
        
        main_layout = QVBoxLayout()
        
        # File selection group
        file_group = QGroupBox("Video Files")
        file_layout = QVBoxLayout()
        
        self.btn_ref = QPushButton("Select Reference Video")
        self.btn_dist = QPushButton("Select Distorted Video")
        
        file_layout.addWidget(self.btn_ref)
        file_layout.addWidget(self.btn_dist)
        file_group.setLayout(file_layout)
        main_layout.addWidget(file_group)
        
        # Analysis options group
        options_group = QGroupBox("Analysis Options")
        options_layout = QVBoxLayout()
        
        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel("VMAF Model:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(["vmaf_v0.6.1", "vmaf_4k", "vmaf_hd"])
        model_layout.addWidget(self.model_combo)
        options_layout.addLayout(model_layout)
        
        align_layout = QHBoxLayout()
        self.align_check = QCheckBox("Align Videos First")
        self.align_check.setChecked(True)
        align_layout.addWidget(self.align_check)
        options_layout.addLayout(align_layout)
        
        duration_layout = QHBoxLayout()
        duration_layout.addWidget(QLabel("Analyze Duration (seconds):"))
        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(0, 300)
        self.duration_spin.setValue(0)
        self.duration_spin.setSpecialValueText("Full")
        duration_layout.addWidget(self.duration_spin)
        options_layout.addLayout(duration_layout)
        
        options_group.setLayout(options_layout)
        main_layout.addWidget(options_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        self.btn_run = QPushButton("Run VMAF Analysis")
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setEnabled(False)
        button_layout.addWidget(self.btn_run)
        button_layout.addWidget(self.btn_stop)
        main_layout.addLayout(button_layout)
        
        # Progress
        progress_layout = QVBoxLayout()
        progress_layout.addWidget(QLabel("Progress:"))
        self.progress = QProgressBar()
        progress_layout.addWidget(self.progress)
        main_layout.addLayout(progress_layout)
        
        # Results
        results_group = QGroupBox("Results")
        results_layout = QVBoxLayout()
        self.vmaf_label = QLabel("VMAF Score: --")
        self.psnr_label = QLabel("PSNR: --")
        self.ssim_label = QLabel("SSIM: --")
        results_layout.addWidget(self.vmaf_label)
        results_layout.addWidget(self.psnr_label)
        results_layout.addWidget(self.ssim_label)
        results_group.setLayout(results_layout)
        main_layout.addWidget(results_group)
        
        # Log
        log_layout = QVBoxLayout()
        log_layout.addWidget(QLabel("Log:"))
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        log_layout.addWidget(self.log)
        main_layout.addLayout(log_layout)
        
        self.setLayout(main_layout)
        
    def setup_connections(self):
        self.btn_ref.clicked.connect(lambda: self.select_file("reference"))
        self.btn_dist.clicked.connect(lambda: self.select_file("distorted"))
        self.btn_run.clicked.connect(self.start_analysis)
        self.btn_stop.clicked.connect(self.stop_analysis)
        
    def select_file(self, file_type):
        path, _ = QFileDialog.getOpenFileName(self, f"Select {file_type.capitalize()} Video", 
                                             "", "Video Files (*.mp4 *.avi *.mkv *.mov)")
        if path:
            if file_type == "reference":
                self.ref_path = path
                self.btn_ref.setText(f"Reference: {os.path.basename(path)}")
                logger.info(f"Selected reference video: {path}")
            else:
                self.dist_path = path
                self.btn_dist.setText(f"Distorted: {os.path.basename(path)}")
                logger.info(f"Selected distorted video: {path}")
    
    def start_analysis(self):
        if not hasattr(self, 'ref_path') or not hasattr(self, 'dist_path'):
            self.log.append("Error: Please select both videos first")
            return
        
        # Update UI state
        self.btn_run.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.progress.setValue(0)
        self.vmaf_label.setText("VMAF Score: --")
        self.psnr_label.setText("PSNR: --")
        self.ssim_label.setText("SSIM: --")
        
        # Get analysis options
        self.selected_model = self.model_combo.currentText()
        self.align_videos = self.align_check.isChecked()
        self.duration = self.duration_spin.value() if self.duration_spin.value() > 0 else None
        
        logger.info(f"Starting analysis with model: {self.selected_model}, "
                   f"align: {self.align_videos}, duration: {self.duration}")
        
        if self.align_videos:
            self.log.append("Aligning videos before analysis...")
            self.start_alignment()
        else:
            self.start_vmaf_analysis(self.ref_path, self.dist_path)
    
    def start_alignment(self):
        self.alignment_thread = AlignmentThread(
            reference_path=self.ref_path,
            captured_path=self.dist_path,
            max_offset_seconds=10
        )
        
        # Connect signals
        self.alignment_thread.alignment_progress.connect(self.progress.setValue)
        self.alignment_thread.alignment_complete.connect(self.on_alignment_complete)
        self.alignment_thread.error_occurred.connect(lambda msg: logger.error(msg))
        self.alignment_thread.status_update.connect(lambda msg: logger.info(msg))
        
        # Start alignment
        self.alignment_thread.start()
        logger.info("Alignment started")
    
    @pyqtSlot(dict)
    def on_alignment_complete(self, result):
        logger.info(f"Alignment complete: {result}")
        
        if not result or 'aligned_reference' not in result or 'aligned_captured' not in result:
            logger.error("Alignment failed or produced invalid results")
            self.log.append("Error: Alignment failed. Proceeding with original videos.")
            self.start_vmaf_analysis(self.ref_path, self.dist_path)
            return
        
        # Use aligned videos for VMAF analysis
        aligned_ref = result['aligned_reference']
        aligned_dist = result['aligned_captured']
        
        # Check if files exist
        if not os.path.exists(aligned_ref) or not os.path.exists(aligned_dist):
            logger.error("Aligned video files not found")
            self.log.append("Error: Aligned videos not found. Using original videos.")
            self.start_vmaf_analysis(self.ref_path, self.dist_path)
            return
        
        logger.info(f"Using aligned videos: {aligned_ref}, {aligned_dist}")
        self.log.append(f"Alignment complete (confidence: {result.get('confidence', 0):.2f})")
        self.log.append(f"Offset: {result.get('offset_frames', 0)} frames / {result.get('offset_seconds', 0):.3f} seconds")
        
        # Start VMAF with aligned videos
        self.start_vmaf_analysis(aligned_ref, aligned_dist)
    
    def start_vmaf_analysis(self, ref_path, dist_path):
        self.log.append("Starting VMAF analysis...")
        
        self.vmaf_thread = VMAFAnalysisThread(
            reference_path=ref_path,
            distorted_path=dist_path,
            model=self.selected_model,
            duration=self.duration
        )
        
        # Connect signals
        self.vmaf_thread.analysis_progress.connect(self.progress.setValue)
        self.vmaf_thread.analysis_complete.connect(self.show_results)
        self.vmaf_thread.error_occurred.connect(lambda msg: logger.error(msg))
        self.vmaf_thread.status_update.connect(lambda msg: logger.info(msg))
        
        # Start analysis
        self.vmaf_thread.start()
    
    def stop_analysis(self):
        if hasattr(self, 'alignment_thread') and self.alignment_thread.isRunning():
            logger.info("Stopping alignment thread")
            self.alignment_thread.terminate()
            self.alignment_thread.wait()
            
        if hasattr(self, 'vmaf_thread') and self.vmaf_thread.isRunning():
            logger.info("Stopping VMAF analysis thread")
            self.vmaf_thread.terminate()
            self.vmaf_thread.wait()
            
        self.log.append("Analysis stopped by user")
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)
    
    @pyqtSlot(dict)
    def show_results(self, results):
        if not results:
            logger.error("No results received from VMAF analysis")
            self.log.append("Error: VMAF analysis failed to produce results")
            self.btn_run.setEnabled(True)
            self.btn_stop.setEnabled(False)
            return
            
        # Update results display
        vmaf_score = results.get('vmaf_score')
        psnr_score = results.get('psnr')
        ssim_score = results.get('ssim')
        
        if vmaf_score is not None:
            self.vmaf_label.setText(f"VMAF Score: {vmaf_score:.2f}")
        if psnr_score is not None:
            self.psnr_label.setText(f"PSNR: {psnr_score:.2f} dB")
        if ssim_score is not None:
            self.ssim_label.setText(f"SSIM: {ssim_score:.4f}")
        
        # Log results
        self.log.append("\n=== Analysis Complete ===")
        self.log.append(f"VMAF Score: {vmaf_score:.2f}" if vmaf_score is not None else "VMAF: Not available")
        self.log.append(f"PSNR: {psnr_score:.2f} dB" if psnr_score is not None else "PSNR: Not available")
        self.log.append(f"SSIM: {ssim_score:.4f}" if ssim_score is not None else "SSIM: Not available")
        self.log.append(f"Report files:")
        self.log.append(f"- JSON: {results.get('json_path', 'Not available')}")
        self.log.append(f"- CSV: {results.get('csv_path', 'Not available')}")
        self.log.append(f"- PSNR Log: {results.get('psnr_log', 'Not available')}")
        self.log.append(f"- SSIM Log: {results.get('ssim_log', 'Not available')}")
        
        # Re-enable run button
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = VMAFTestWindow()
    window.show()
    sys.exit(app.exec_())