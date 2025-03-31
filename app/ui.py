#Import necessary libraries
import os
import logging
import sys
from PyQt5.QtWidgets import (QMainWindow, QMessageBox, QApplication, QWidget, 
                           QVBoxLayout, QHBoxLayout, QTabWidget, QPushButton,
                           QLabel, QProgressBar, QFileDialog, QTextEdit)
from PyQt5.QtCore import Qt, pyqtSignal, QThread

from app.improved_file_manager import ImprovedFileManager
from app.capture import CaptureManager
from app.analysis import VMAFAnalyzer, VMAFAnalysisThread


class CaptureManager: # Example class, replace with your actual class
    def __init__(self):
        pass

    def stop_capture(self, cleanup_temp=True):
        pass


class YourClass: # Replace with your actual class name
    def __init__(self):
        # ... other initialization code ...
        base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests", "test_results")
        os.makedirs(base_dir, exist_ok=True)

        # Create default_test folder for temporary files
        temp_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "default_test")
        os.makedirs(temp_dir, exist_ok=True)

        self.file_manager = ImprovedFileManager(base_dir=base_dir, temp_dir=temp_dir)
        logger = logging.getLogger(__name__) # Assuming logger is defined elsewhere
        logger.info(f"Using test results directory: {base_dir}")
        logger.info(f"Using temporary directory: {temp_dir}")
        self._stopping_capture = False #Added to handle stop button logic
        # ... rest of the initialization code ...


    def handle_capture_finished(self, success, result):
        """Handle capture completion"""
        self.btn_start_capture.setEnabled(True)
        self.btn_stop_capture.setEnabled(False)

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

            # Enable analysis tab and button
            self.btn_next_to_analysis.setEnabled(True)
            self.btn_align_videos.setEnabled(True)

            # Don't show success message on stop - only show on successful completion
            if not hasattr(self, '_stopping_capture') or not self._stopping_capture:
                QMessageBox.information(self, "Capture Complete", 
                                    f"Capture completed successfully!\n\nSaved to: {display_path}")
        else:
            self.log_to_capture(f"Capture failed: {result}")
            QMessageBox.critical(self, "Capture Failed", f"Capture failed: {result}")

        # Reset stopping flag
        self._stopping_capture = False

    def stop_capture(self):
        """Stop the capture process"""
        self.log_to_capture("Stopping capture...")
        self._stopping_capture = True
        self.capture_manager.stop_capture(cleanup_temp=True)

        # Reset progress bar to avoid stuck state
        self.pb_capture_progress.setValue(0)

    def log_to_capture(self, message):
        #Implementation for logging
        pass

    # ... other methods ...

# Main application class
class VMafTestApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VMAF Test Application")
        self.setGeometry(100, 100, 1000, 700)
        
        # Create file manager
        base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests", "test_results")
        os.makedirs(base_dir, exist_ok=True)

        # Create default_test folder for temporary files
        temp_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "default_test")
        os.makedirs(temp_dir, exist_ok=True)

        self.file_manager = ImprovedFileManager(base_dir=base_dir, temp_dir=temp_dir)
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"Using test results directory: {base_dir}")
        self.logger.info(f"Using temporary directory: {temp_dir}")
        
        # Setup UI
        self.setup_ui()
        
        # Initialize capture manager
        self.capture_manager = CaptureManager()
        self._stopping_capture = False
        
    def setup_ui(self):
        # Main widget and layout
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        
        # Tabs
        self.tabs = QTabWidget()
        
        # Create tabs
        self.setup_capture_tab()
        self.setup_analysis_tab()
        self.setup_results_tab()
        
        # Add tabs to widget
        main_layout.addWidget(self.tabs)
        
        # Set central widget
        self.setCentralWidget(main_widget)
        
    def setup_capture_tab(self):
        capture_tab = QWidget()
        layout = QVBoxLayout(capture_tab)
        
        # Capture controls
        capture_controls = QHBoxLayout()
        self.btn_start_capture = QPushButton("Start Capture")
        self.btn_stop_capture = QPushButton("Stop Capture")
        self.btn_stop_capture.setEnabled(False)
        
        capture_controls.addWidget(self.btn_start_capture)
        capture_controls.addWidget(self.btn_stop_capture)
        
        # Progress bar
        self.pb_capture_progress = QProgressBar()
        
        # Log area
        self.capture_log = QTextEdit()
        self.capture_log.setReadOnly(True)
        
        # Add to layout
        layout.addLayout(capture_controls)
        layout.addWidget(self.pb_capture_progress)
        layout.addWidget(QLabel("Capture Log:"))
        layout.addWidget(self.capture_log)
        
        # Navigation button
        self.btn_next_to_analysis = QPushButton("Next: Analysis")
        self.btn_next_to_analysis.setEnabled(False)
        layout.addWidget(self.btn_next_to_analysis)
        
        # Add to tabs
        self.tabs.addTab(capture_tab, "Capture")
        
        # Connect signals
        self.btn_start_capture.clicked.connect(self.start_capture)
        self.btn_stop_capture.clicked.connect(self.stop_capture)
        self.btn_next_to_analysis.clicked.connect(lambda: self.tabs.setCurrentIndex(1))
        
    def setup_analysis_tab(self):
        analysis_tab = QWidget()
        layout = QVBoxLayout(analysis_tab)
        
        # Analysis summary
        self.lbl_analysis_summary = QLabel("No videos selected for analysis")
        layout.addWidget(self.lbl_analysis_summary)
        
        # Analysis controls
        self.btn_align_videos = QPushButton("Align Videos")
        self.btn_align_videos.setEnabled(False)
        self.btn_run_vmaf = QPushButton("Run VMAF Analysis")
        self.btn_run_vmaf.setEnabled(False)
        
        analysis_controls = QHBoxLayout()
        analysis_controls.addWidget(self.btn_align_videos)
        analysis_controls.addWidget(self.btn_run_vmaf)
        layout.addLayout(analysis_controls)
        
        # Progress bar
        self.pb_analysis_progress = QProgressBar()
        layout.addWidget(self.pb_analysis_progress)
        
        # Analysis log
        self.analysis_log = QTextEdit()
        self.analysis_log.setReadOnly(True)
        layout.addWidget(QLabel("Analysis Log:"))
        layout.addWidget(self.analysis_log)
        
        # Navigation buttons
        nav_buttons = QHBoxLayout()
        self.btn_back_to_capture = QPushButton("Back: Capture")
        self.btn_next_to_results = QPushButton("Next: Results")
        self.btn_next_to_results.setEnabled(False)
        
        nav_buttons.addWidget(self.btn_back_to_capture)
        nav_buttons.addWidget(self.btn_next_to_results)
        layout.addLayout(nav_buttons)
        
        # Add to tabs
        self.tabs.addTab(analysis_tab, "Analysis")
        
        # Connect signals
        self.btn_back_to_capture.clicked.connect(lambda: self.tabs.setCurrentIndex(0))
        self.btn_next_to_results.clicked.connect(lambda: self.tabs.setCurrentIndex(2))
        
    def setup_results_tab(self):
        results_tab = QWidget()
        layout = QVBoxLayout(results_tab)
        
        # Results display
        self.lbl_results_summary = QLabel("No analysis results available")
        layout.addWidget(self.lbl_results_summary)
        
        # Results text display
        self.results_details = QTextEdit()
        self.results_details.setReadOnly(True)
        layout.addWidget(QLabel("Results Details:"))
        layout.addWidget(self.results_details)
        
        # Export buttons
        export_buttons = QHBoxLayout()
        self.btn_export_pdf = QPushButton("Export PDF Certificate")
        self.btn_export_csv = QPushButton("Export CSV Data")
        self.btn_export_pdf.setEnabled(False)
        self.btn_export_csv.setEnabled(False)
        
        export_buttons.addWidget(self.btn_export_pdf)
        export_buttons.addWidget(self.btn_export_csv)
        layout.addLayout(export_buttons)
        
        # Navigation button
        self.btn_back_to_analysis = QPushButton("Back: Analysis")
        layout.addWidget(self.btn_back_to_analysis)
        
        # Add to tabs
        self.tabs.addTab(results_tab, "Results")
        
        # Connect signals
        self.btn_back_to_analysis.clicked.connect(lambda: self.tabs.setCurrentIndex(1))
        
    def start_capture(self):
        self.log_to_capture("Starting capture...")
        self.btn_start_capture.setEnabled(False)
        self.btn_stop_capture.setEnabled(True)
        # Initialize capture (placeholder)
        
    def stop_capture(self):
        self.log_to_capture("Stopping capture...")
        self._stopping_capture = True
        if hasattr(self, 'capture_manager'):
            self.capture_manager.stop_capture(cleanup_temp=True)
        
        # Reset progress bar to avoid stuck state
        self.pb_capture_progress.setValue(0)
        
    def log_to_capture(self, message):
        self.capture_log.append(message)
        self.logger.info(message)
        
    def handle_capture_finished(self, success, result):
        """Handle capture completion"""
        self.btn_start_capture.setEnabled(True)
        self.btn_stop_capture.setEnabled(False)

        if success:
            # Normalize the path for consistent display
            display_path = os.path.normpath(result)

            self.log_to_capture(f"Capture completed: {display_path}")
            self.capture_path = result

            # Update analysis tab
            capture_name = os.path.basename(self.capture_path)
            if hasattr(self, 'reference_info') and self.reference_info.get('path'):
                ref_name = os.path.basename(self.reference_info['path'])
                analysis_summary = (f"Reference: {ref_name}\n" +
                                  f"Captured: {capture_name}\n" +
                                  f"Ready for alignment and VMAF analysis")
                self.lbl_analysis_summary.setText(analysis_summary)
                self.btn_align_videos.setEnabled(True)

            # Enable analysis tab and button
            self.btn_next_to_analysis.setEnabled(True)

            # Don't show success message on stop - only show on successful completion
            if not hasattr(self, '_stopping_capture') or not self._stopping_capture:
                QMessageBox.information(self, "Capture Complete", 
                                      f"Capture completed successfully!\n\nSaved to: {display_path}")
        else:
            self.log_to_capture(f"Capture failed: {result}")
            QMessageBox.critical(self, "Capture Failed", f"Capture failed: {result}")

        # Reset stopping flag
        self._stopping_capture = False

# Example usage
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = VMafTestApp()
    window.show()
    sys.exit(app.exec_())