import sys
import os
import cv2
import numpy as np
import torch
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout,
    QFileDialog, QTextEdit, QHBoxLayout, QProgressBar, QComboBox, QCheckBox
)
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtCore import QTimer, Qt, QThread, pyqtSignal
from skimage.metrics import structural_similarity as ssim


def detect_gpu():
    if torch.cuda.is_available():
        return f"GPU Detected: {torch.cuda.get_device_name(0)}"
    return "No GPU Detected"


class AlignWorker(QThread):
    progress = pyqtSignal(int)
    result = pyqtSignal(int, str)

    def __init__(self, video1_path, video2_path, resolution=(160, 90), window=10):
        super().__init__()
        self.video1_path = video1_path
        self.video2_path = video2_path
        self.resolution = resolution
        self.window = window

    def run(self):
        cap1 = cv2.VideoCapture(self.video1_path)
        cap2 = cv2.VideoCapture(self.video2_path)

        total_frames1 = int(cap1.get(cv2.CAP_PROP_FRAME_COUNT))
        total_frames2 = int(cap2.get(cv2.CAP_PROP_FRAME_COUNT))
        min_frames = min(total_frames1, total_frames2)
        compare_range = min(50, min_frames)
        offsets = []

        for i in range(compare_range):
            self.progress.emit(int((i / compare_range) * 100))
            cap1.set(cv2.CAP_PROP_POS_FRAMES, i)
            ret1, frame1 = cap1.read()
            if not ret1:
                break

            gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
            gray1 = cv2.resize(gray1, self.resolution)

            best_offset = 0
            best_score = -1

            for offset in range(-self.window, self.window + 1):
                j = i + offset
                if j < 0 or j >= total_frames2:
                    continue

                cap2.set(cv2.CAP_PROP_POS_FRAMES, j)
                ret2, frame2 = cap2.read()
                if not ret2:
                    continue

                gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)
                gray2 = cv2.resize(gray2, self.resolution)
                score, _ = ssim(gray1, gray2, full=True)
                if score > best_score:
                    best_score = score
                    best_offset = offset

            offsets.append(best_offset)

        cap1.release()
        cap2.release()

        if offsets:
            best_offset = int(np.median(offsets))
            self.result.emit(best_offset, "Success")
        else:
            self.result.emit(0, "Failed")


class VideoComparer(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Video Frame Comparison & Alignment Tool")
        self.setGeometry(100, 100, 1000, 700)

        self.video1_path = ""
        self.video2_path = ""
        self.cap1 = None
        self.cap2 = None
        self.align_worker = None

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        btn_layout = QHBoxLayout()
        self.btn_load1 = QPushButton("Load Video 1")
        self.btn_load2 = QPushButton("Load Video 2")
        self.btn_compare = QPushButton("Run Comparison")
        self.btn_align = QPushButton("Align & Trim Videos")

        self.btn_load1.clicked.connect(self.load_video1)
        self.btn_load2.clicked.connect(self.load_video2)
        self.btn_compare.clicked.connect(self.compare_videos)
        self.btn_align.clicked.connect(self.align_and_trim_videos)

        btn_layout.addWidget(self.btn_load1)
        btn_layout.addWidget(self.btn_load2)
        btn_layout.addWidget(self.btn_compare)
        btn_layout.addWidget(self.btn_align)
        layout.addLayout(btn_layout)

        video_layout = QHBoxLayout()
        self.label_video1 = QLabel("Video 1 Preview")
        self.label_video2 = QLabel("Video 2 Preview")
        self.label_video1.setFixedSize(480, 270)
        self.label_video2.setFixedSize(480, 270)
        video_layout.addWidget(self.label_video1)
        video_layout.addWidget(self.label_video2)
        layout.addLayout(video_layout)

        res_layout = QHBoxLayout()
        res_layout.addWidget(QLabel("Alignment Resolution:"))
        self.res_combo = QComboBox()
        self.res_combo.addItems(["160x90", "320x180", "480x270"])
        res_layout.addWidget(self.res_combo)
        layout.addLayout(res_layout)

        self.gpu_checkbox = QCheckBox("Use GPU Acceleration")
        self.gpu_checkbox.setChecked(torch.cuda.is_available())
        layout.addWidget(self.gpu_checkbox)

        self.gpu_label = QLabel(detect_gpu())
        layout.addWidget(self.gpu_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.progress_bar)

        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        layout.addWidget(self.output_text)

        self.setLayout(layout)
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_previews)

    def get_resolution(self):
        text = self.res_combo.currentText()
        width, height = map(int, text.split('x'))
        return (width, height)

    def load_video1(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Video 1")
        if path:
            self.video1_path = path
            self.cap1 = cv2.VideoCapture(path)
            self.start_preview()

    def load_video2(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Video 2")
        if path:
            self.video2_path = path
            self.cap2 = cv2.VideoCapture(path)
            self.start_preview()

    def start_preview(self):
        if self.cap1 or self.cap2:
            self.timer.start(100)

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

    def compare_videos(self, window=5):
        if not self.video1_path or not self.video2_path:
            self.output_text.append("Please load both videos.")
            return

        cap1 = cv2.VideoCapture(self.video1_path)
        cap2 = cv2.VideoCapture(self.video2_path)

        total_frames1 = int(cap1.get(cv2.CAP_PROP_FRAME_COUNT))
        total_frames2 = int(cap2.get(cv2.CAP_PROP_FRAME_COUNT))
        min_frames = min(total_frames1, total_frames2)

        self.output_text.append("Starting comparison...\n")
        frame_index = 0
        lag_results = []
        resolution = self.get_resolution()

        while True:
            ret1, frame1 = cap1.read()
            if not ret1:
                break

            pos2 = int(cap2.get(cv2.CAP_PROP_POS_FRAMES))
            best_score = -1
            best_offset = 0

            for offset in range(-window, window + 1):
                compare_index = frame_index + offset
                if compare_index < 0 or compare_index >= total_frames2:
                    continue

                cap2.set(cv2.CAP_PROP_POS_FRAMES, compare_index)
                ret2, frame2 = cap2.read()
                if not ret2:
                    continue

                gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
                gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)
                gray1 = cv2.resize(gray1, resolution)
                gray2 = cv2.resize(gray2, resolution)
                score, _ = ssim(gray1, gray2, full=True)

                if score > best_score:
                    best_score = score
                    best_offset = offset

            lag_results.append(best_offset)
            self.output_text.append(f"Frame {frame_index}: Offset={best_offset}, SSIM={best_score:.4f}")
            frame_index += 1

            if frame_index >= min_frames:
                break

            cap2.set(cv2.CAP_PROP_POS_FRAMES, pos2 + 1)

        cap1.release()
        cap2.release()

        avg_offset = np.mean(lag_results) if lag_results else 0
        self.output_text.append(f"\n=== Done ===\nAverage Offset: {avg_offset:.2f} frames\n")

    def align_and_trim_videos(self):
        if not self.video1_path or not self.video2_path:
            self.output_text.append("Load both videos first.")
            return

        resolution = self.get_resolution()
        self.output_text.append("Starting alignment...")
        self.progress_bar.setValue(0)

        self.align_worker = AlignWorker(self.video1_path, self.video2_path, resolution)
        self.align_worker.progress.connect(self.progress_bar.setValue)
        self.align_worker.result.connect(self.finish_alignment)
        self.align_worker.start()

    def finish_alignment(self, best_offset, status):
        if status != "Success":
            self.output_text.append("Alignment failed.")
            return

        self.output_text.append(f"Best alignment offset: {best_offset} frames")

        cap1 = cv2.VideoCapture(self.video1_path)
        cap2 = cv2.VideoCapture(self.video2_path)

        total_frames1 = int(cap1.get(cv2.CAP_PROP_FRAME_COUNT))
        total_frames2 = int(cap2.get(cv2.CAP_PROP_FRAME_COUNT))

        start1 = max(0, best_offset)
        start2 = max(0, -best_offset)
        length = min(total_frames1 - start1, total_frames2 - start2)

        cap1.set(cv2.CAP_PROP_POS_FRAMES, start1)
        cap2.set(cv2.CAP_PROP_POS_FRAMES, start2)

        width = int(cap1.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap1.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap1.get(cv2.CAP_PROP_FPS)

        out1_path = "aligned_video1.mp4"
        out2_path = "aligned_video2.mp4"

        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out1 = cv2.VideoWriter(str(out1_path), fourcc, fps, (width, height))
        out2 = cv2.VideoWriter(str(out2_path), fourcc, fps, (width, height))

        for _ in range(length):
            ret1, frame1 = cap1.read()
            ret2, frame2 = cap2.read()
            if not (ret1 and ret2):
                break
            out1.write(frame1)
            out2.write(frame2)

        cap1.release()
        cap2.release()
        out1.release()
        out2.release()

        self.output_text.append(f"Saved aligned videos:\n- {out1_path}\n- {out2_path}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = VideoComparer()
    window.show()
    sys.exit(app.exec_())
