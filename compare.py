import os
import sys
import json
import shutil
import cv2
import torch
import pandas as pd
import matplotlib
# Set matplotlib to use a non-interactive backend that's thread-safe
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QFileDialog, QTextEdit, QProgressBar, QComboBox, QCheckBox, QLineEdit,
    QTabWidget, QFormLayout, QListWidget, QMessageBox, QInputDialog
)

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from skimage.metrics import structural_similarity as ssim


class VideoSyncApp(QWidget):
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Video Sync GUI")
        self.setGeometry(100, 100, 1200, 800)

        self.settings_file = "settings.json"
        self.settings = {}
        self.video1_path = None
        self.video2_path = None
        self.cap1 = None
        self.cap2 = None
        self.processing = False  # Flag to track if processing is happening

        self.tabs = QTabWidget()
        self.main_tab = QWidget()
        self.settings_tab = QWidget()
        self.files_tab = QWidget()
        self.charts_tab = QWidget()

        self.tabs.addTab(self.main_tab, "Main")
        self.tabs.addTab(self.settings_tab, "Settings")
        self.tabs.addTab(self.files_tab, "Files")
        self.tabs.addTab(self.charts_tab, "Charts")

        main_layout = QVBoxLayout()
        main_layout.addWidget(self.tabs)
        self.setLayout(main_layout)

        self.init_main_tab()
        self.init_settings_tab()
        self.init_files_tab()
        self.init_charts_tab()
        self.load_settings()
        
        # Now update all button states after everything is initialized
        self.update_button_states()



    def init_main_tab(self):
        layout = QVBoxLayout(self.main_tab)

        btn_layout = QHBoxLayout()
        self.btn_load_video1 = QPushButton("Load Video 1")
        self.btn_load_video2 = QPushButton("Load Video 2")
        self.btn_load_video1.clicked.connect(lambda: self.load_video(1))
        self.btn_load_video2.clicked.connect(lambda: self.load_video(2))
        btn_layout.addWidget(self.btn_load_video1)
        btn_layout.addWidget(self.btn_load_video2)
        layout.addLayout(btn_layout)

        video_display_layout = QHBoxLayout()
        self.label_video1 = QLabel("Video 1 Preview")
        self.label_video2 = QLabel("Video 2 Preview")
        for label in [self.label_video1, self.label_video2]:
            label.setFixedSize(480, 270)
            label.setStyleSheet("background-color: black;")
        video_display_layout.addWidget(self.label_video1)
        video_display_layout.addWidget(self.label_video2)
        layout.addLayout(video_display_layout)

        action_layout = QHBoxLayout()
        self.btn_compare = QPushButton("Compare Videos")
        self.btn_align_trim = QPushButton("Align & Trim")
        self.btn_compare.clicked.connect(self.compare_videos)
        self.btn_align_trim.clicked.connect(self.align_and_trim_videos)
        action_layout.addWidget(self.btn_compare)
        action_layout.addWidget(self.btn_align_trim)
        layout.addLayout(action_layout)

        chart_layout = QHBoxLayout()
        self.btn_open_comparison_chart = QPushButton("Open SSIM Chart")
        self.btn_open_alignment_chart = QPushButton("Open Alignment Chart")
        self.btn_open_comparison_chart.clicked.connect(lambda: self.open_chart("comparison_chart.png"))
        self.btn_open_alignment_chart.clicked.connect(lambda: self.open_chart("alignment_chart.png"))
        chart_layout.addWidget(self.btn_open_comparison_chart)
        chart_layout.addWidget(self.btn_open_alignment_chart)
        layout.addLayout(chart_layout)

        thumbnail_layout = QHBoxLayout()
        self.thumbnail_comparison = QLabel("Comparison Chart Preview")
        self.thumbnail_alignment = QLabel("Alignment Chart Preview")
        for thumb in [self.thumbnail_comparison, self.thumbnail_alignment]:
            thumb.setFixedSize(200, 120)
            thumb.setStyleSheet("border: 1px solid gray;")
        thumbnail_layout.addWidget(self.thumbnail_comparison)
        thumbnail_layout.addWidget(self.thumbnail_alignment)
        layout.addLayout(thumbnail_layout)

        chart_manage_layout = QHBoxLayout()
        self.btn_export_charts = QPushButton("Export Charts to PDF")
        self.btn_export_chart_data = QPushButton("Export Chart Data (CSV/Excel)")
        self.btn_clear_charts = QPushButton("Clear Chart Images")
        self.btn_export_charts.clicked.connect(self.export_charts_to_pdf)
        self.btn_open_output_folder = QPushButton("Open Output Folder")
        self.btn_open_output_folder.clicked.connect(self.open_output_folder)
        self.btn_export_chart_data.clicked.connect(self.export_charts_to_csv_excel)
        self.btn_clear_charts.clicked.connect(self.clear_chart_images)
        chart_manage_layout.addWidget(self.btn_export_charts)
        chart_manage_layout.addWidget(self.btn_export_chart_data)
        self.btn_generate_report = QPushButton("Generate PDF Report")
        self.btn_generate_report.clicked.connect(self.generate_pdf_report)
        chart_manage_layout.addWidget(self.btn_generate_report)
        chart_manage_layout.addWidget(self.btn_clear_charts)
        layout.addLayout(chart_manage_layout)

        self.progress_bar = QProgressBar()
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.output_text)

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_previews)

        #self.update_thumbnails()
        
        # Initialize button states
        self.update_button_states()

    def init_settings_tab(self):
        layout = QVBoxLayout(self.settings_tab)
        
        form_layout = QFormLayout()
        self.sample_rate_combo = QComboBox()
        self.sample_rate_combo.addItems(["5", "10", "20", "30", "60"])
        
        self.comparison_frames_edit = QLineEdit("100")
        self.alignment_range_edit = QLineEdit("10")
        
        self.save_settings_btn = QPushButton("Save Settings")
        self.save_settings_btn.clicked.connect(self.save_settings)
        
        form_layout.addRow("Sample Rate (frames):", self.sample_rate_combo)
        form_layout.addRow("Comparison Frames:", self.comparison_frames_edit)
        form_layout.addRow("Alignment Range:", self.alignment_range_edit)
        
        layout.addLayout(form_layout)
        layout.addWidget(self.save_settings_btn)
        self.settings_tab.setLayout(layout)

    def init_files_tab(self):
        layout = QVBoxLayout(self.files_tab)
        
        self.files_list = QListWidget()
        self.btn_refresh_files = QPushButton("Refresh Files")
        self.btn_refresh_files.clicked.connect(self.refresh_file_list)
        
        self.btn_delete_selected = QPushButton("Delete Selected")
        self.btn_delete_selected.clicked.connect(self.delete_selected_files)
        
        file_actions = QHBoxLayout()
        file_actions.addWidget(self.btn_refresh_files)
        file_actions.addWidget(self.btn_delete_selected)
        
        layout.addWidget(QLabel("Generated Files:"))
        layout.addWidget(self.files_list)
        layout.addLayout(file_actions)
        
        self.btn_generate_report_files_tab = QPushButton("Generate PDF Report")
        self.btn_generate_report_files_tab.clicked.connect(self.generate_pdf_report)
        layout.addWidget(self.btn_generate_report_files_tab)
        
        self.files_tab.setLayout(layout)
        self.refresh_file_list()

    def init_charts_tab(self):
        layout = QVBoxLayout(self.charts_tab)
        
        chart_preview_layout = QHBoxLayout()
        self.chart_preview_ssim = QLabel("SSIM Chart")
        self.chart_preview_align = QLabel("Alignment Chart")
        
        for preview in [self.chart_preview_ssim, self.chart_preview_align]:
            preview.setFixedSize(400, 300)
            preview.setStyleSheet("border: 1px solid gray;")
            preview.setAlignment(Qt.AlignCenter)
        
        chart_preview_layout.addWidget(self.chart_preview_ssim)
        chart_preview_layout.addWidget(self.chart_preview_align)
        
        self.btn_generate_report_charts_tab = QPushButton("Generate PDF Report")
        self.btn_generate_report_charts_tab.clicked.connect(self.generate_pdf_report)
        
        layout.addLayout(chart_preview_layout)
        layout.addWidget(self.btn_generate_report_charts_tab)
        
        self.charts_tab.setLayout(layout)
        self.update_chart_previews()

    def update_chart_previews(self):
        def load_image(label, path):
            if os.path.exists(path):
                pixmap = QPixmap(path).scaled(400, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                label.setPixmap(pixmap)
        
        load_image(self.chart_preview_ssim, "comparison_chart.png")
        load_image(self.chart_preview_align, "alignment_chart.png")

    def refresh_file_list(self):
        self.files_list.clear()
        files = [f for f in os.listdir() if f.endswith(('.mp4', '.png', '.pdf', '.csv', '.xlsx'))]
        for file in files:
            self.files_list.addItem(file)
        
        # Update button states based on available files
        self.update_button_states()

    def delete_selected_files(self):
        selected_items = self.files_list.selectedItems()
        if not selected_items:
            return
            
        confirm = QMessageBox.question(
            self, "Confirm Delete", 
            f"Delete {len(selected_items)} selected file(s)?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if confirm == QMessageBox.Yes:
            for item in selected_items:
                try:
                    os.remove(item.text())
                except Exception as e:
                    self.output_text.append(f"Error deleting {item.text()}: {e}")
            
            self.refresh_file_list()
            self.update_thumbnails()
            self.update_chart_previews()

    def load_settings(self):
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r') as f:
                    self.settings = json.load(f)
                    # Apply loaded settings to UI
                    if 'sample_rate' in self.settings:
                        index = self.sample_rate_combo.findText(str(self.settings['sample_rate']))
                        if index >= 0:
                            self.sample_rate_combo.setCurrentIndex(index)
                    if 'comparison_frames' in self.settings:
                        self.comparison_frames_edit.setText(str(self.settings['comparison_frames']))
                    if 'alignment_range' in self.settings:
                        self.alignment_range_edit.setText(str(self.settings['alignment_range']))
        except Exception as e:
            self.output_text.append(f"Error loading settings: {e}")

    def save_settings(self):
        try:
            self.settings = {
                'sample_rate': int(self.sample_rate_combo.currentText()),
                'comparison_frames': int(self.comparison_frames_edit.text()),
                'alignment_range': int(self.alignment_range_edit.text())
            }
            
            with open(self.settings_file, 'w') as f:
                json.dump(self.settings, f)
                
            self.output_text.append("Settings saved successfully")
        except Exception as e:
            self.output_text.append(f"Error saving settings: {e}")

    def clear_chart_images(self):
        try:
            files_to_remove = ["comparison_chart.png", "alignment_chart.png"]
            for file in files_to_remove:
                if os.path.exists(file):
                    os.remove(file)
            self.update_thumbnails()
            self.update_chart_previews()
            self.output_text.append("Chart images cleared.")
        except Exception as e:
            self.output_text.append(f"Error clearing charts: {e}")

    def export_charts_to_pdf(self):
        self.generate_pdf_report()

    def export_charts_to_csv_excel(self):
        try:
            chart_data = {
                "Chart Type": ["Comparison SSIM", "Alignment Offset vs SSIM"],
                "Chart File": ["comparison_chart.png", "alignment_chart.png"]
            }
            df = pd.DataFrame(chart_data)
            df.to_csv("chart_data.csv", index=False)
            
            try:
                # Try to export to Excel if openpyxl is installed
                df.to_excel("chart_data.xlsx", index=False)
                self.output_text.append("Chart data exported to chart_data.csv and chart_data.xlsx")
            except ImportError:
                # If openpyxl is not installed, just export to CSV
                self.output_text.append("Chart data exported to chart_data.csv only (install openpyxl for Excel support)")
                
            self.refresh_file_list()
        except Exception as e:
            self.output_text.append(f"Error exporting chart data: {e}")

    def generate_pdf_report(self):
        pdf_path = QFileDialog.getSaveFileName(self, "Save PDF Report", "sync_report.pdf", "PDF Files (*.pdf)")[0]
        if not pdf_path:
            return

        try:
            c = canvas.Canvas(pdf_path, pagesize=A4)
            c.setFont("Helvetica-Bold", 16)
            c.drawString(50, 800, "Video Comparison Report")
            c.setFont("Helvetica", 12)

            c.drawString(50, 780, f"Video 1: {os.path.basename(self.video1_path) if self.video1_path else 'Not Loaded'}")
            c.drawString(50, 765, f"Video 2: {os.path.basename(self.video2_path) if self.video2_path else 'Not Loaded'}")

            if os.path.exists("comparison_chart.png"):
                c.drawString(50, 740, "SSIM Comparison Chart")
                c.drawImage("comparison_chart.png", 50, 500, width=500, preserveAspectRatio=True)

            if os.path.exists("alignment_chart.png"):
                c.drawString(50, 480, "Alignment Offset Chart")
                c.drawImage("alignment_chart.png", 50, 240, width=500, preserveAspectRatio=True)

            c.drawString(50, 220, f"Report generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            c.save()

            self.output_text.append(f"PDF report saved as {pdf_path}")
            QMessageBox.information(self, "Report Saved", f"PDF report saved to: {pdf_path}")
            
            try:
                if sys.platform == 'win32':
                    os.startfile(pdf_path)
                elif sys.platform == 'darwin':  # macOS
                    os.system(f'open "{pdf_path}"')
                else:  # Linux
                    os.system(f'xdg-open "{pdf_path}"')
            except Exception as e:
                self.output_text.append(f"Could not open PDF: {e}")
                
            self.refresh_file_list()
        except Exception as e:
            self.output_text.append(f"Error generating PDF report: {e}")
            QMessageBox.critical(self, "Error", f"Failed to generate PDF report: {e}")

    # Signal for plot data passing
    create_plot_signal = pyqtSignal(list, str, str, str, str)

    def create_matplotlib_plot(self, data_list, title, xlabel, ylabel, filename):
        # This method runs in the main thread and is safe for matplotlib
        plt.figure(figsize=(10, 4))
        if isinstance(data_list[0], tuple):  # For alignment chart
            x_values = [x for x, _ in data_list]
            y_values = [y for _, y in data_list]
            plt.plot(x_values, y_values, marker='o')
        else:  # For comparison chart
            plt.plot(data_list, label='SSIM')
        
        plt.title(title)
        plt.xlabel(xlabel)
        plt.ylabel(ylabel)
        plt.grid(True)
        plt.tight_layout()
        plt.savefig(filename)
        plt.close()
        
    def compare_videos(self):
        if not self.video1_path or not self.video2_path:
            self.output_text.append("Please load both videos first.")
            return
            
        # Disable buttons during processing
        self.disable_buttons()

        # Connect plot signal to plot creation method without using lambda
        self.create_plot_signal.connect(self.create_matplotlib_plot)

        class ComparisonThread(QThread):
            update_progress = pyqtSignal(int)
            update_text = pyqtSignal(str)
            finished_signal = pyqtSignal()
            send_plot_data = pyqtSignal(list, str, str, str, str)
            
            def __init__(self, parent):
                super().__init__()
                self.parent = parent
                
            def run(self):
                cap1 = cv2.VideoCapture(self.parent.video1_path)
                cap2 = cv2.VideoCapture(self.parent.video2_path)
                total_frames = int(min(cap1.get(cv2.CAP_PROP_FRAME_COUNT), cap2.get(cv2.CAP_PROP_FRAME_COUNT)))
                
                comparison_frames = 100
                if 'comparison_frames' in self.parent.settings:
                    comparison_frames = self.parent.settings['comparison_frames']

                self.update_text.emit("Starting comparison...")
                scores = []

                for i in range(min(comparison_frames, total_frames)):
                    progress = int((i / min(comparison_frames, total_frames)) * 100)
                    self.update_progress.emit(progress)
                    
                    cap1.set(cv2.CAP_PROP_POS_FRAMES, i)
                    cap2.set(cv2.CAP_PROP_POS_FRAMES, i)
                    ret1, f1 = cap1.read()
                    ret2, f2 = cap2.read()
                    if not (ret1 and ret2):
                        continue
                    g1 = cv2.cvtColor(f1, cv2.COLOR_BGR2GRAY)
                    g2 = cv2.cvtColor(f2, cv2.COLOR_BGR2GRAY)
                    g1 = cv2.resize(g1, (160, 90))
                    g2 = cv2.resize(g2, (160, 90))
                    score, _ = ssim(g1, g2, full=True)
                    scores.append(score)
                    self.update_text.emit(f"Frame {i}: SSIM={score:.4f}")

                cap1.release()
                cap2.release()

                avg = sum(scores)/len(scores) if scores else 0
                self.update_text.emit(f"Average SSIM: {avg:.4f}")

                # Instead of creating plot in the thread, send the data to main thread
                self.send_plot_data.emit(
                    scores, 
                    'Frame SSIM Comparison', 
                    'Frame', 
                    'SSIM',
                    "comparison_chart.png"
                )
                
                self.update_text.emit("SSIM chart saved as comparison_chart.png")
                
                # Make sure to set progress to 100% when complete
                self.update_progress.emit(100)
                self.finished_signal.emit()
        
        self.thread = ComparisonThread(self)
        self.thread.update_progress.connect(self.progress_bar.setValue)
        self.thread.update_text.connect(self.output_text.append)
        # Connect thread signal to our main thread plot method directly
        self.thread.send_plot_data.connect(self.create_matplotlib_plot)
        self.thread.finished_signal.connect(lambda: self.update_thumbnails())
        self.thread.finished_signal.connect(lambda: self.update_chart_previews())
        self.thread.finished_signal.connect(lambda: self.refresh_file_list())
        self.thread.finished_signal.connect(lambda: self.enable_buttons())
        
        self.progress_bar.setValue(0)
        self.thread.start()

    def align_and_trim_videos(self):
        if not self.video1_path or not self.video2_path:
            self.output_text.append("Please load both videos first.")
            return
            
        # Disable buttons during processing
        self.disable_buttons()

        # Connect plot signal to plot creation method without using lambda
        self.create_plot_signal.connect(self.create_matplotlib_plot)

        class AlignmentThread(QThread):
            update_progress = pyqtSignal(int)
            update_text = pyqtSignal(str)
            finished_signal = pyqtSignal()
            send_plot_data = pyqtSignal(list, str, str, str, str)
            
            def __init__(self, parent):
                super().__init__()
                self.parent = parent
                
            def run(self):
                cap1 = cv2.VideoCapture(self.parent.video1_path)
                cap2 = cv2.VideoCapture(self.parent.video2_path)
                total_frames1 = int(cap1.get(cv2.CAP_PROP_FRAME_COUNT))
                total_frames2 = int(cap2.get(cv2.CAP_PROP_FRAME_COUNT))
                
                alignment_range = 10
                if 'alignment_range' in self.parent.settings:
                    alignment_range = self.parent.settings['alignment_range']

                self.update_text.emit("Aligning videos...")
                best_offset = 0
                best_score = -1
                alignment_scores = []

                total_checks = alignment_range * 2 + 1
                progress_counter = 0

                for offset in range(-alignment_range, alignment_range + 1):
                    progress_counter += 1
                    progress = int((progress_counter / total_checks) * 100)
                    self.update_progress.emit(progress)
                    
                    scores = []
                    for i in range(30):
                        f1_idx = i
                        f2_idx = i + offset
                        if f1_idx < 0 or f2_idx < 0 or f1_idx >= total_frames1 or f2_idx >= total_frames2:
                            continue
                        cap1.set(cv2.CAP_PROP_POS_FRAMES, f1_idx)
                        cap2.set(cv2.CAP_PROP_POS_FRAMES, f2_idx)
                        ret1, f1 = cap1.read()
                        ret2, f2 = cap2.read()
                        if not (ret1 and ret2):
                            continue
                        g1 = cv2.cvtColor(f1, cv2.COLOR_BGR2GRAY)
                        g2 = cv2.cvtColor(f2, cv2.COLOR_BGR2GRAY)
                        g1 = cv2.resize(g1, (160, 90))
                        g2 = cv2.resize(g2, (160, 90))
                        score, _ = ssim(g1, g2, full=True)
                        scores.append(score)
                    avg = sum(scores)/len(scores) if scores else 0
                    alignment_scores.append((offset, avg))
                    if avg > best_score:
                        best_score = avg
                        best_offset = offset
                    
                    self.update_text.emit(f"Offset {offset}: SSIM={avg:.4f}")

                self.update_text.emit(f"Best offset: {best_offset} frames")

                # Create aligned videos
                self.update_text.emit("Creating aligned videos...")
                
                start1 = max(0, best_offset) if best_offset < 0 else 0
                start2 = max(0, -best_offset) if best_offset > 0 else 0
                trim_len = min(total_frames1 - start1, total_frames2 - start2)

                cap1.set(cv2.CAP_PROP_POS_FRAMES, start1)
                cap2.set(cv2.CAP_PROP_POS_FRAMES, start2)
                fps = cap1.get(cv2.CAP_PROP_FPS)
                width = int(cap1.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap1.get(cv2.CAP_PROP_FRAME_HEIGHT))

                fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # or 'XVID'
                out1 = cv2.VideoWriter("aligned_video1.mp4", fourcc, fps, (width, height))
                out2 = cv2.VideoWriter("aligned_video2.mp4", fourcc, fps, (width, height))

                for i in range(trim_len):
                    if i % 100 == 0:
                        progress = int((i / trim_len) * 100)
                        self.update_progress.emit(progress)
                        
                    r1, frame1 = cap1.read()
                    r2, frame2 = cap2.read()
                    if not (r1 and r2):
                        break
                    out1.write(frame1)
                    out2.write(frame2)

                cap1.release()
                cap2.release()
                out1.release()
                out2.release()

                self.update_text.emit("Aligned and trimmed videos saved as aligned_video1.mp4 and aligned_video2.mp4")

                # Send plot data to main thread for chart creation
                self.send_plot_data.emit(
                    alignment_scores,
                    "Alignment Offset vs SSIM",
                    "Offset",
                    "Average SSIM",
                    "alignment_chart.png"
                )
                
                self.update_text.emit("Alignment chart saved as alignment_chart.png")
                
                # Make sure to set progress to 100% when complete
                self.update_progress.emit(100)
                self.finished_signal.emit()

        self.thread = AlignmentThread(self)
        self.thread.update_progress.connect(self.progress_bar.setValue)
        self.thread.update_text.connect(self.output_text.append)
        # Connect thread signal to our main thread plot method directly
        self.thread.send_plot_data.connect(self.create_matplotlib_plot)
        self.thread.finished_signal.connect(lambda: self.update_thumbnails())
        self.thread.finished_signal.connect(lambda: self.update_chart_previews())
        self.thread.finished_signal.connect(lambda: self.refresh_file_list())
        self.thread.finished_signal.connect(lambda: self.enable_buttons())
        
        self.progress_bar.setValue(0)
        self.thread.start()

    def load_video(self, video_number):
        path, _ = QFileDialog.getOpenFileName(self, f"Select Video {video_number}", "", "Video Files (*.mp4 *.avi *.mkv *.mov)")
        if path:
            if video_number == 1:
                self.video1_path = path
                self.cap1 = cv2.VideoCapture(path)
                self.output_text.append(f"Video 1 loaded: {os.path.basename(path)}")
            else:
                self.video2_path = path
                self.cap2 = cv2.VideoCapture(path)
                self.output_text.append(f"Video 2 loaded: {os.path.basename(path)}")
            self.timer.start(100)
            
            # Update button states based on loaded videos
            self.update_button_states()

    def update_previews(self):
        if self.cap1:
            ret1, frame1 = self.cap1.read()
            if ret1:
                self.display_frame(self.label_video1, frame1)
            else:
                self.cap1.set(cv2.CAP_PROP_POS_FRAMES, 0)

        if self.cap2:
            ret2, frame2 = self.cap2.read()
            if ret2:
                self.display_frame(self.label_video2, frame2)
            else:
                self.cap2.set(cv2.CAP_PROP_POS_FRAMES, 0)

    def display_frame(self, label, frame):
        frame = cv2.resize(frame, (480, 270))
        rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
        label.setPixmap(QPixmap.fromImage(qt_image))

    def open_chart(self, chart_file):
            if os.path.exists(chart_file):
                try:
                    if sys.platform == 'win32':
                        os.startfile(chart_file)
                    elif sys.platform == 'darwin':  # macOS
                        os.system(f'open "{chart_file}"')
                    else:  # Linux
                        os.system(f'xdg-open "{chart_file}"')
                except Exception as e:
                    self.output_text.append(f"Could not open chart: {e}")
            else:
                self.output_text.append(f"Chart not found: {chart_file}")

    def open_output_folder(self):
        try:
            output_dir = os.getcwd()
            if sys.platform == 'win32':
                os.startfile(output_dir)
            elif sys.platform == 'darwin':  # macOS
                os.system(f'open "{output_dir}"')
            else:  # Linux
                os.system(f'xdg-open "{output_dir}"')
        except Exception as e:
            self.output_text.append(f"Could not open output folder: {e}")

    def update_thumbnails(self):
        def load_image(label, path):
            if os.path.exists(path):
                pixmap = QPixmap(path).scaled(200, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                label.setPixmap(pixmap)
            else:
                label.setText(f"No {path} found")
                
        load_image(self.thumbnail_comparison, "comparison_chart.png")
        load_image(self.thumbnail_alignment, "alignment_chart.png")
    
    
    def update_button_states(self):
        """Update button states based on current app state"""
        # Skip if currently processing
        if self.processing:
            return
            
        # Check if both videos are loaded
        both_videos_loaded = bool(self.video1_path and self.video2_path)
        
        # Main action buttons
        self.btn_compare.setEnabled(both_videos_loaded)
        self.btn_align_trim.setEnabled(both_videos_loaded)
        
        # Enable/disable chart buttons based on file existence
        self.btn_open_comparison_chart.setEnabled(os.path.exists("comparison_chart.png"))
        self.btn_open_alignment_chart.setEnabled(os.path.exists("alignment_chart.png"))
        
        # Export button states
        charts_exist = os.path.exists("comparison_chart.png") or os.path.exists("alignment_chart.png")
        self.btn_export_charts.setEnabled(charts_exist)
        self.btn_export_chart_data.setEnabled(charts_exist)
        self.btn_clear_charts.setEnabled(charts_exist)
        self.btn_generate_report.setEnabled(both_videos_loaded or charts_exist)
        
        # Tab-specific buttons - only enable if they exist
        if hasattr(self, 'btn_generate_report_files_tab'):
            self.btn_generate_report_files_tab.setEnabled(True)
        if hasattr(self, 'btn_generate_report_charts_tab'):
            self.btn_generate_report_charts_tab.setEnabled(True)
        if hasattr(self, 'btn_refresh_files'):
            self.btn_refresh_files.setEnabled(True)
        if hasattr(self, 'btn_delete_selected'):
            self.btn_delete_selected.setEnabled(True)     

     
        
    def disable_buttons(self):
        """Disable buttons during processing"""
        self.processing = True
        
        # Main action buttons
        self.btn_align_trim.setEnabled(False)
        self.btn_compare.setEnabled(False)
        
        # Allow loading videos even during processing
        # self.btn_load_video1.setEnabled(False)
        # self.btn_load_video2.setEnabled(False)
        
        # Chart buttons
        self.btn_open_comparison_chart.setEnabled(False)
        self.btn_open_alignment_chart.setEnabled(False)
        
        # Export/management buttons
        self.btn_export_charts.setEnabled(False)
        self.btn_export_chart_data.setEnabled(False)
        self.btn_clear_charts.setEnabled(False)
        self.btn_generate_report.setEnabled(False)
        self.btn_open_output_folder.setEnabled(False)
        
        # Tab-specific buttons
        self.btn_generate_report_files_tab.setEnabled(False)
        self.btn_generate_report_charts_tab.setEnabled(False)
        self.btn_refresh_files.setEnabled(False)
        self.btn_delete_selected.setEnabled(False)
        
    def enable_buttons(self):
        """Re-enable buttons after processing is complete"""
        self.processing = False
        self.update_button_states()
        self.btn_open_output_folder.setEnabled(True)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = VideoSyncApp()
    window.show()
    sys.exit(app.exec_())