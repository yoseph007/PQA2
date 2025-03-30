import sys
import os
import subprocess
import logging
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QPushButton, QLabel, QComboBox, 
                            QProgressBar, QFileDialog, QMessageBox, QSpinBox,
                            QGroupBox, QTextEdit)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('test_app.log')
    ]
)
logger = logging.getLogger(__name__)

class CaptureThread(QThread):
    progress_updated = pyqtSignal(str)
    process_finished = pyqtSignal(bool, str)
    
    def __init__(self, device_name, output_path, duration=10):
        super().__init__()
        self.device_name = device_name
        self.output_path = output_path
        self.duration = duration
        self.process = None
        
    def run(self):
        try:
            # Build command
            cmd = [
                "ffmpeg",
                "-y",  # Overwrite output
                "-f", "decklink",
                "-i", self.device_name,  # Exactly as entered
                "-c:v", "libx264",
                "-preset", "fast", 
                "-crf", "18",
                "-t", str(self.duration)
            ]
            
            # Add output path
            cmd.append(self.output_path)
            
            # Log the command
            cmd_str = " ".join(cmd)
            logger.info(f"Running FFmpeg command: {cmd_str}")
            self.progress_updated.emit(f"Running: {cmd_str}")
            
            # Run FFmpeg
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1
            )
            
            # Monitor output
            for line in self.process.stderr:
                self.progress_updated.emit(line.strip())
                
            # Wait for process to finish
            self.process.wait()
            
            # Check result
            if self.process.returncode == 0:
                self.process_finished.emit(True, "Capture completed successfully")
            else:
                self.process_finished.emit(False, f"FFmpeg failed with code {self.process.returncode}")
                
        except Exception as e:
            logger.error(f"Capture error: {str(e)}")
            self.process_finished.emit(False, f"Error: {str(e)}")
            
    def stop(self):
        if self.process:
            try:
                self.process.terminate()
            except:
                pass

class SimpleTestApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.capture_thread = None
        
        self.setup_ui()
        
    def setup_ui(self):
        self.setWindowTitle("Intensity Shuttle Test")
        self.setGeometry(100, 100, 800, 600)
        
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        
        # Device group
        device_group = QGroupBox("Device Settings")
        device_layout = QHBoxLayout()
        
        device_layout.addWidget(QLabel("Device Name:"))
        self.device_name = QComboBox()
        self.device_name.setEditable(True)
        self.device_name.addItem("Intensity Shuttle")
        device_layout.addWidget(self.device_name)
        
        device_group.setLayout(device_layout)
        layout.addWidget(device_group)
        
        # Capture options
        capture_group = QGroupBox("Capture Options")
        capture_layout = QVBoxLayout()
        
        duration_layout = QHBoxLayout()
        duration_layout.addWidget(QLabel("Duration (seconds):"))
        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(1, 60)
        self.duration_spin.setValue(10)
        duration_layout.addWidget(self.duration_spin)
        duration_layout.addStretch()
        
        capture_layout.addLayout(duration_layout)
        
        output_layout = QHBoxLayout()
        self.output_path = QLabel("No output file selected")
        output_layout.addWidget(self.output_path)
        self.btn_browse = QPushButton("Browse...")
        self.btn_browse.clicked.connect(self.browse_output)
        output_layout.addWidget(self.btn_browse)
        
        capture_layout.addLayout(output_layout)
        
        # Buttons
        button_layout = QHBoxLayout()
        self.btn_test = QPushButton("Run Command Line Test")
        self.btn_test.clicked.connect(self.run_command_test)
        self.btn_capture = QPushButton("Start Capture")
        self.btn_capture.clicked.connect(self.start_capture)
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.clicked.connect(self.stop_capture)
        self.btn_stop.setEnabled(False)
        
        button_layout.addWidget(self.btn_test)
        button_layout.addWidget(self.btn_capture)
        button_layout.addWidget(self.btn_stop)
        
        capture_layout.addLayout(button_layout)
        capture_group.setLayout(capture_layout)
        layout.addWidget(capture_group)
        
        # Log display
        log_group = QGroupBox("Output Log")
        log_layout = QVBoxLayout()
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        log_layout.addWidget(self.log_display)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)
        
        # Status bar
        self.statusBar().showMessage("Ready")
        
    def browse_output(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Capture", "", "MP4 Files (*.mp4)"
        )
        
        if file_path:
            self.output_path.setText(file_path)
            
    def append_log(self, text):
        self.log_display.append(text)
        self.log_display.ensureCursorVisible()
        
    def run_command_test(self):
        """Run a command-line test without starting capture"""
        device = self.device_name.currentText()
        
        # Generate a test command for the user to try
        command = f'ffmpeg -f decklink -i "{device}" -c:v libx264 -preset fast -crf 18 -t 5 test_output.mp4'
        
        self.append_log("Try running this command in Command Prompt to verify your device:")
        self.append_log(command)
        
        # Show in a message box so they can copy it
        QMessageBox.information(self, "Test Command", 
                              "Copy and run this command in Command Prompt to test your device:\n\n" + command)
        
    def start_capture(self):
        device = self.device_name.currentText()
        output = self.output_path.text()
        duration = self.duration_spin.value()
        
        if output == "No output file selected":
            QMessageBox.warning(self, "Warning", "Please select an output file")
            return
            
        # Clear log
        self.log_display.clear()
        
        # Start capture
        self.append_log(f"Starting capture from {device} for {duration} seconds...")
        
        # Create capture thread
        self.capture_thread = CaptureThread(device, output, duration)
        self.capture_thread.progress_updated.connect(self.append_log)
        self.capture_thread.process_finished.connect(self.on_capture_finished)
        
        # Update UI
        self.btn_capture.setEnabled(False)
        self.btn_test.setEnabled(False)
        self.btn_stop.setEnabled(True)
        
        # Start thread
        self.capture_thread.start()
        
    def stop_capture(self):
        if self.capture_thread:
            self.append_log("Stopping capture...")
            self.capture_thread.stop()
            
    def on_capture_finished(self, success, message):
        self.btn_capture.setEnabled(True)
        self.btn_test.setEnabled(True)
        self.btn_stop.setEnabled(False)
        
        if success:
            self.append_log(f"SUCCESS: {message}")
            self.statusBar().showMessage("Capture completed")
            QMessageBox.information(self, "Success", message)
        else:
            self.append_log(f"ERROR: {message}")
            self.statusBar().showMessage("Capture failed")
            QMessageBox.critical(self, "Error", message)
        
    def closeEvent(self, event):
        if self.capture_thread and self.capture_thread.isRunning():
            self.capture_thread.stop()
        event.accept()

def main():
    app = QApplication(sys.argv)
    window = SimpleTestApp()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()