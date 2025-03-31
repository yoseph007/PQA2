# test_vmaf.py
import sys
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QPushButton, 
                            QProgressBar, QLabel, QFileDialog, QTextEdit)
from analysis import VMAFAnalyzer, VMAFAnalysisThread

class VMAFTestWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.analyzer = VMAFAnalyzer()
        self.init_ui()
        self.setup_connections()
        
    def init_ui(self):
        self.setWindowTitle("VMAF Test Module")
        self.setGeometry(300, 300, 400, 300)
        
        layout = QVBoxLayout()
        
        self.btn_ref = QPushButton("Select Reference Video")
        self.btn_dist = QPushButton("Select Distorted Video")
        self.btn_run = QPushButton("Run VMAF Analysis")
        self.progress = QProgressBar()
        self.result_label = QLabel("VMAF Score: --")
        self.log = QTextEdit()
        
        layout.addWidget(self.btn_ref)
        layout.addWidget(self.btn_dist)
        layout.addWidget(self.btn_run)
        layout.addWidget(self.progress)
        layout.addWidget(self.result_label)
        layout.addWidget(self.log)
        
        self.setLayout(layout)
        
    def setup_connections(self):
        self.btn_ref.clicked.connect(lambda: self.select_file("reference"))
        self.btn_dist.clicked.connect(lambda: self.select_file("distorted"))
        self.btn_run.clicked.connect(self.start_analysis)
        
    def select_file(self, file_type):
        path, _ = QFileDialog.getOpenFileName(self, f"Select {file_type.capitalize()} Video")
        if path:
            if file_type == "reference":
                self.ref_path = path
                self.btn_ref.setText(f"Reference: {path.split('/')[-1]}")
            else:
                self.dist_path = path
                self.btn_dist.setText(f"Distorted: {path.split('/')[-1]}")
                
    def start_analysis(self):
        if not hasattr(self, 'ref_path') or not hasattr(self, 'dist_path'):
            self.log.append("Error: Please select both videos first")
            return
            
        self.thread = VMAFAnalysisThread(
            reference_path=self.ref_path,
            distorted_path=self.dist_path
        )
        
        # Connect signals
        self.thread.analysis_progress.connect(self.progress.setValue)
        self.thread.analysis_complete.connect(self.show_results)
        self.thread.error_occurred.connect(self.log.append)
        self.thread.status_update.connect(self.log.append)
        
        self.thread.start()
        self.log.append("Starting analysis...")
        
    def show_results(self, results):
        self.result_label.setText(f"VMAF Score: {results['vmaf_score']:.2f}")
        self.log.append("\nAnalysis Complete!")
        self.log.append(f"JSON Report: {results['json_path']}")
        self.log.append(f"PSNR Log: {results['psnr_log']}")
        self.log.append(f"SSIM Log: {results['ssim_log']}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = VMAFTestWindow()
    window.show()
    sys.exit(app.exec_())