import logging
import os
import platform
import re
import subprocess

from PyQt5.QtCore import Qt 
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
                             QFormLayout, QGridLayout, QGroupBox, QHBoxLayout,
                             QLabel, QLineEdit, QMessageBox, QPushButton,
                             QSlider, QSpinBox, QTabWidget, QVBoxLayout,
                             QWidget, QApplication)

logger = logging.getLogger(__name__)

class OptionsTab(QWidget):
    """Options tab for configuring application settings"""

    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        
        # Store direct reference to options_manager from parent
        if hasattr(parent, 'options_manager'):
            self.options_manager = parent.options_manager
        else:
            self.options_manager = None
            logger.warning("Parent does not have options_manager")       
        
        self._setup_ui()
        
        
    def _setup_ui(self):
        """Set up the Options tab UI"""
        layout = QVBoxLayout(self)

        # Create tabbed interface for different settings categories
        options_tabs = QTabWidget()

        # Create tabs for different settings categories
        general_tab = self._setup_general_tab()
        capture_tab = self._setup_capture_tab()
        analysis_tab = self._setup_analysis_tab()
        advanced_tab = self._setup_advanced_tab()

        # Add tabs to options tabwidget
        options_tabs.addTab(general_tab, "General")
        options_tabs.addTab(capture_tab, "Capture")
        options_tabs.addTab(analysis_tab, "Analysis")
        options_tabs.addTab(advanced_tab, "Advanced")

        layout.addWidget(options_tabs)

        # Save/Reset buttons
        button_layout = QHBoxLayout()
        self.btn_save_settings = QPushButton("Save Settings")
        self.btn_save_settings.clicked.connect(self.save_settings)
        self.btn_reset_settings = QPushButton("Reset to Defaults")
        self.btn_reset_settings.clicked.connect(self.reset_settings)
        button_layout.addWidget(self.btn_save_settings)
        button_layout.addWidget(self.btn_reset_settings)
        layout.addLayout(button_layout)
        
        # Load current settings into UI elements
        self.load_settings()
        
    def _setup_general_tab(self):
        """Set up the General tab UI"""
        general_tab = QWidget()
        general_layout = QVBoxLayout(general_tab)

        # Directories group
        directories_group = QGroupBox("Directories")
        directories_layout = QVBoxLayout()

        # Reference videos directory
        ref_dir_layout = QHBoxLayout()
        ref_dir_layout.addWidget(QLabel("Reference Videos Directory:"))
        self.txt_ref_dir = QLineEdit()
        self.txt_ref_dir.setReadOnly(True)
        ref_dir_layout.addWidget(self.txt_ref_dir)
        self.btn_browse_ref_dir = QPushButton("Browse...")
        self.btn_browse_ref_dir.clicked.connect(self.browse_ref_directory)
        ref_dir_layout.addWidget(self.btn_browse_ref_dir)
        directories_layout.addLayout(ref_dir_layout)

        # Output directory
        output_dir_layout = QHBoxLayout()
        output_dir_layout.addWidget(QLabel("Output Directory:"))
        self.txt_output_dir = QLineEdit()
        self.txt_output_dir.setReadOnly(True)
        output_dir_layout.addWidget(self.txt_output_dir)
        self.btn_browse_output_dir = QPushButton("Browse...")
        self.btn_browse_output_dir.clicked.connect(self.browse_output_directory)
        output_dir_layout.addWidget(self.btn_browse_output_dir)
        directories_layout.addLayout(output_dir_layout)

        # VMAF models directory
        vmaf_dir_layout = QHBoxLayout()
        vmaf_dir_layout.addWidget(QLabel("VMAF Models Directory:"))
        self.txt_vmaf_dir = QLineEdit()
        self.txt_vmaf_dir.setReadOnly(True)
        vmaf_dir_layout.addWidget(self.txt_vmaf_dir)
        self.btn_browse_vmaf_dir = QPushButton("Browse...")
        self.btn_browse_vmaf_dir.clicked.connect(self.browse_vmaf_directory)
        vmaf_dir_layout.addWidget(self.btn_browse_vmaf_dir)
        directories_layout.addLayout(vmaf_dir_layout)

        directories_group.setLayout(directories_layout)
        general_layout.addWidget(directories_group)

        # FFmpeg settings group
        ffmpeg_group = QGroupBox("FFmpeg Configuration")
        ffmpeg_layout = QVBoxLayout()

        # FFmpeg path
        ffmpeg_path_layout = QHBoxLayout()
        ffmpeg_path_layout.addWidget(QLabel("FFmpeg Path:"))
        self.txt_ffmpeg_path = QLineEdit()
        self.txt_ffmpeg_path.setReadOnly(True)
        ffmpeg_path_layout.addWidget(self.txt_ffmpeg_path)
        self.btn_browse_ffmpeg = QPushButton("Browse...")
        self.btn_browse_ffmpeg.clicked.connect(self.browse_ffmpeg_path)
        ffmpeg_path_layout.addWidget(self.btn_browse_ffmpeg)
        ffmpeg_layout.addLayout(ffmpeg_path_layout)

        # Default encoder settings
        encoder_form = QFormLayout()

        self.combo_default_encoder = QComboBox()
        self.combo_default_encoder.addItems(["libx264", "libx265", "nvenc_h264", "nvenc_hevc"])
        encoder_form.addRow("Default Encoder:", self.combo_default_encoder)

        self.spin_default_crf = QSpinBox()
        self.spin_default_crf.setRange(0, 51)
        self.spin_default_crf.setValue(23)
        encoder_form.addRow("Default CRF Value:", self.spin_default_crf)

        self.spin_default_preset = QComboBox()
        self.spin_default_preset.addItems(["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"])
        self.spin_default_preset.setCurrentText("medium")
        encoder_form.addRow("Default Preset:", self.spin_default_preset)

        ffmpeg_layout.addLayout(encoder_form)
        ffmpeg_group.setLayout(ffmpeg_layout)
        general_layout.addWidget(ffmpeg_group)
        
        return general_tab
    
    def _setup_capture_tab(self):
        """Set up the capture settings tab UI"""
        capture_tab = QWidget()
        capture_layout = QVBoxLayout(capture_tab)

        # Capture device group
        device_group = QGroupBox("Blackmagic Capture Device")
        device_layout = QVBoxLayout()
        
        # Device selection with auto-detect
        device_selection_layout = QHBoxLayout()
        device_selection_layout.addWidget(QLabel("DeckLink Device:"))
        self.combo_capture_device = QComboBox()
        device_selection_layout.addWidget(self.combo_capture_device)
        self.btn_refresh_devices = QPushButton("Refresh Devices")
        self.btn_refresh_devices.clicked.connect(self._populate_device_list)
        device_selection_layout.addWidget(self.btn_refresh_devices)
        device_layout.addLayout(device_selection_layout)

        # Format detection
        format_detect_layout = QHBoxLayout()
        self.btn_detect_formats = QPushButton("Detect Device Formats")
        self.btn_detect_formats.clicked.connect(self.detect_device_formats)
        self.btn_detect_formats.setToolTip("Query available formats from the selected device")
        format_detect_layout.addWidget(self.btn_detect_formats)
        format_detect_layout.addStretch()
        device_layout.addLayout(format_detect_layout)
        
        # Status message for format detection
        self.lbl_format_status = QLabel("No formats detected yet")
        self.lbl_format_status.setStyleSheet("color: gray; font-style: italic;")
        device_layout.addWidget(self.lbl_format_status)
        
        # Format selection group
        format_group = QGroupBox("Capture Format")
        format_layout = QVBoxLayout()
        
        # Format code selection
        format_code_layout = QHBoxLayout()
        format_code_layout.addWidget(QLabel("Format Code:"))
        self.combo_format_code = QComboBox()
        self.combo_format_code.setToolTip("Select a format code for the capture device")
        self.combo_format_code.currentIndexChanged.connect(self._update_format_details)
        format_code_layout.addWidget(self.combo_format_code)
        format_layout.addLayout(format_code_layout)
        
        # Format details
        self.lbl_format_details = QLabel("Resolution: -- x --  |  Frame Rate: -- fps")
        self.lbl_format_details.setStyleSheet("font-weight: bold;")
        format_layout.addWidget(self.lbl_format_details)
        
        # Input connection options
        connection_group = QGroupBox("Input Connection")
        connection_layout = QVBoxLayout()
        
        # Connection type selection
        self.combo_video_input = QComboBox()
        self.combo_video_input.addItems(["hdmi", "sdi", "component", "composite", "s-video"])
        self.combo_video_input.setCurrentText("hdmi")
        self.combo_video_input.setToolTip("Select the type of video input connection")
        connection_layout.addWidget(QLabel("Video Input:"))
        connection_layout.addWidget(self.combo_video_input)
        
        # Audio input selection
        self.combo_audio_input = QComboBox()
        self.combo_audio_input.addItems(["embedded", "analog", "aesebu"])
        self.combo_audio_input.setCurrentText("embedded")
        self.combo_audio_input.setToolTip("Select the type of audio input connection")
        connection_layout.addWidget(QLabel("Audio Input:"))
        connection_layout.addWidget(self.combo_audio_input)
        
        connection_group.setLayout(connection_layout)
        format_layout.addWidget(connection_group)
        
        # Pixel format options
        format_layout.addWidget(QLabel("Pixel Format:"))
        self.combo_pixel_format = QComboBox()
        pixel_formats = [
            "uyvy422 - Packed YUV 4:2:2 (DeckLink default)",
            "yuv422p - Planar YUV 4:2:2",
            "yuv420p - Planar YUV 4:2:0",
            "rgb24 - Packed RGB",
            "bgra - 32-bit BGRA"
        ]
        self.combo_pixel_format.addItems(pixel_formats)
        self.combo_pixel_format.setToolTip("Select pixel format for the capture")
        format_layout.addWidget(self.combo_pixel_format)
        
        # Encoding parameters for capture
        encoding_group = QGroupBox("Capture Encoding")
        encoding_layout = QFormLayout()
        
        self.combo_capture_encoder = QComboBox()
        self.combo_capture_encoder.addItems(["libx264", "libx265", "h264_nvenc", "hevc_nvenc"])
        self.combo_capture_encoder.setCurrentText("libx264")
        encoding_layout.addRow("Encoder:", self.combo_capture_encoder)
        
        self.spin_capture_crf = QSpinBox()
        self.spin_capture_crf.setRange(0, 51)
        self.spin_capture_crf.setValue(18)  # Higher quality default for captures
        self.spin_capture_crf.setToolTip("CRF value (0-51): Lower values mean higher quality")
        encoding_layout.addRow("Quality (CRF):", self.spin_capture_crf)
        
        self.combo_capture_preset = QComboBox()
        self.combo_capture_preset.addItems(["ultrafast", "superfast", "veryfast", "faster", "fast", "medium"])
        self.combo_capture_preset.setCurrentText("fast")
        encoding_layout.addRow("Preset:", self.combo_capture_preset)
        
        encoding_group.setLayout(encoding_layout)
        format_layout.addWidget(encoding_group)
        
        # Advanced options
        advanced_group = QGroupBox("Advanced Options")
        advanced_layout = QFormLayout()
        
        self.chk_disable_audio = QCheckBox()
        self.chk_disable_audio.setChecked(False)
        advanced_layout.addRow("Disable Audio:", self.chk_disable_audio)
        
        self.chk_low_latency = QCheckBox()
        self.chk_low_latency.setChecked(True)
        self.chk_low_latency.setToolTip("Optimize for lower latency during capture")
        advanced_layout.addRow("Low Latency Mode:", self.chk_low_latency)
        
        self.chk_force_format = QCheckBox()
        self.chk_force_format.setChecked(False)
        self.chk_force_format.setToolTip("Force format even if device reports it's not supported")
        advanced_layout.addRow("Force Format:", self.chk_force_format)
        
        advanced_group.setLayout(advanced_layout)
        format_layout.addWidget(advanced_group)
        
        format_group.setLayout(format_layout)
        device_layout.addWidget(format_group)
        device_group.setLayout(device_layout)
        capture_layout.addWidget(device_group)
        
        # Bookend settings group with advanced parameters
        bookend_group = QGroupBox("Bookend Detection Settings")
        bookend_layout = QFormLayout()
        
        # Add helper info icon and label
        bookend_help_label = QLabel("These settings control how white bookend frames are detected and processed for alignment:")
        bookend_help_label.setStyleSheet("font-style: italic; color: #666;")
        bookend_layout.addRow(bookend_help_label)

        # Bookend duration with tooltip
        self.spin_bookend_duration = QDoubleSpinBox()
        self.spin_bookend_duration.setRange(0.1, 5.0)
        self.spin_bookend_duration.setValue(0.5)
        self.spin_bookend_duration.setDecimals(2)
        self.spin_bookend_duration.setToolTip("Duration of white bookend sections in seconds. For fast-moving content, shorter values (0.2-0.3s) may work better.")
        bookend_label = QLabel("Bookend Duration (seconds):")
        bookend_label.setToolTip("Duration of white bookend sections in seconds. For fast-moving content, shorter values (0.2-0.3s) may work better.")
        bookend_layout.addRow(bookend_label, self.spin_bookend_duration)

        # Min loops with tooltip 
        self.spin_min_loops = QSpinBox()
        self.spin_min_loops.setRange(1, 10)
        self.spin_min_loops.setValue(3)
        self.spin_min_loops.setToolTip("Minimum number of content loops to capture. Higher values produce more reliable results but take longer.")
        min_loops_label = QLabel("Minimum Loops:")
        min_loops_label.setToolTip("Minimum number of content loops to capture. Higher values produce more reliable results but take longer.")
        bookend_layout.addRow(min_loops_label, self.spin_min_loops)

        # White threshold with tooltip
        self.spin_bookend_threshold = QSpinBox()
        self.spin_bookend_threshold.setRange(100, 255)
        self.spin_bookend_threshold.setValue(230)
        self.spin_bookend_threshold.setToolTip("Brightness threshold (0-255) for detecting white frames. Lower values (200-220) may help with dim displays.")
        threshold_label = QLabel("Brightness Threshold:")
        threshold_label.setToolTip("Brightness threshold (0-255) for detecting white frames. Lower values (200-220) may help with dim displays.")
        bookend_layout.addRow(threshold_label, self.spin_bookend_threshold)

        # Add frame sampling controls with tooltip
        self.frame_sampling_slider = QSlider(Qt.Horizontal)
        self.frame_sampling_slider.setRange(1, 30)
        self.frame_sampling_slider.setValue(5)  # Default value
        self.frame_sampling_slider.setTickPosition(QSlider.TicksBelow)
        self.frame_sampling_slider.setTickInterval(1)
        self.frame_sampling_slider.setToolTip("How many frames to sample per second during bookend detection. Higher values provide more precise detection but use more CPU.")
        
        sampling_layout = QHBoxLayout()
        sampling_label = QLabel("Frame Sampling Rate:")
        sampling_label.setToolTip("How many frames to sample per second during bookend detection. Higher values provide more precise detection but use more CPU.")
        sampling_layout.addWidget(sampling_label)
        sampling_layout.addWidget(self.frame_sampling_slider)
        
        self.frame_sampling_label = QLabel("5 frames")
        sampling_layout.addWidget(self.frame_sampling_label)
        self.frame_sampling_slider.valueChanged.connect(self._update_frame_sampling_label)
        bookend_layout.addRow(sampling_layout)
        
        bookend_group.setLayout(bookend_layout)
        capture_layout.addWidget(bookend_group)
        
        # Add help text
        help_text = QLabel(
            "Note: After changing capture settings, click 'Save Settings' to apply them. "
            "For best results, ensure your device input matches the selected format."
        )
        help_text.setWordWrap(True)
        help_text.setStyleSheet("font-style: italic; color: #666;")
        capture_layout.addWidget(help_text)
        
        # Populate device list on initialization
        self._populate_device_list()
        
        return capture_tab
    
    def _populate_device_list(self):
        """Refresh and populate the device dropdown with available DeckLink devices"""
        if not hasattr(self, 'combo_capture_device'):
            logger.warning("Device combo box not initialized")
            return

        self.combo_capture_device.clear()
        
        try:
            if hasattr(self.parent, 'options_manager') and self.parent.options_manager:
                devices = self.parent.options_manager.get_decklink_devices()
                if not devices:
                    # Fallback for when no devices are detected
                    devices = ["Intensity Shuttle"]
                    
                for device in devices:
                    self.combo_capture_device.addItem(device)
                    
                # Set current device from settings if available
                current_device = self.parent.options_manager.get_setting("capture", "default_device")
                if current_device:
                    index = self.combo_capture_device.findText(current_device)
                    if index >= 0:
                        self.combo_capture_device.setCurrentIndex(index)
                        
                logger.info(f"Populated device list with {len(devices)} devices")
            else:
                # Fallback if options manager not available
                self.combo_capture_device.addItem("Intensity Shuttle")
                logger.warning("Options manager not available, using default device")
        except Exception as e:
            logger.error(f"Error populating device list: {e}")
            # Add default device as fallback
            self.combo_capture_device.addItem("Intensity Shuttle")

    def detect_device_formats(self):
        """Detect available formats for the selected device using FFmpeg"""
        device = self.combo_capture_device.currentText()
        if not device:
            QMessageBox.warning(self, "Warning", "Please select a DeckLink device first.")
            return
            
        # Update status
        self.lbl_format_status.setText("Detecting formats... Please wait.")
        self.lbl_format_status.setStyleSheet("color: blue;")
        QApplication.processEvents()  # Ensure UI updates
        
        try:
            import subprocess
            import re
            
            # Run FFmpeg command to list formats
            cmd = ["ffmpeg", "-hide_banner", "-f", "decklink", "-list_formats", "1", "-i", device]
            logger.info(f"Detecting formats using command: {' '.join(cmd)}")
            
            try:
                # Setup subprocess to capture output
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    universal_newlines=True
                )
                
                stdout, stderr = process.communicate(timeout=10)
                output = stdout + stderr
                
                # Parse the output to extract formats
                formats = []
                # Look for the "Supported formats" section
                format_section = re.search(r'Supported formats for \'[^\']+\':(.*?)(?=\n\n|\Z)', output, re.DOTALL)
                if format_section:
                    section_text = format_section.group(1)
                    
                    # Extract format information
                    format_pattern = r'(\w+)\s+([^\n]+)'
                    for line in section_text.split('\n'):
                        line = line.strip()
                        if not line or 'format_code' in line or 'description' in line:
                            continue
                            
                        match = re.search(format_pattern, line)
                        if match:
                            format_code = match.group(1)
                            description = match.group(2)
                            
                            # Extract resolution
                            res_match = re.search(r'(\d+)x(\d+)', description)
                            width, height = res_match.groups() if res_match else ('0', '0')
                            
                            # Extract frame rate - handle fractional format: 30000/1001
                            fps_match = re.search(r'(\d+)/(\d+)', description)
                            fps = 0
                            if fps_match:
                                num = int(fps_match.group(1))
                                den = int(fps_match.group(2))
                                fps = num / den
                            
                            # Format fps nicely
                            if abs(fps - 23.976) < 0.01:
                                fps_str = "23.976"
                            elif abs(fps - 29.97) < 0.01:
                                fps_str = "29.97"
                            elif abs(fps - 59.94) < 0.01:
                                fps_str = "59.94"
                            else:
                                fps_str = str(int(fps)) if fps == int(fps) else f"{fps:.3f}"
                            
                            # Check if interlaced
                            is_interlaced = "interlaced" in description.lower()
                            scan_type = "i" if is_interlaced else "p"
                            
                            # Create format object
                            format_obj = {
                                'code': format_code,
                                'width': int(width),
                                'height': int(height),
                                'resolution': f"{width}x{height}",
                                'fps': fps,
                                'fps_str': fps_str,
                                'scan_type': scan_type,
                                'description': description,
                                'display': f"{format_code} - {width}x{height} @ {fps_str}{scan_type}"
                            }
                            formats.append(format_obj)
                
                # Update the UI with detected formats
                self.combo_format_code.clear()
                
                if formats:
                    # Sort formats by resolution and then by frame rate
                    formats.sort(key=lambda x: (x['height'], x['width'], x['fps']))
                    
                    for fmt in formats:
                        self.combo_format_code.addItem(fmt['display'], fmt)
                    
                    # Select format from settings if available
                    current_format = self.parent.options_manager.get_setting("capture", "format_code")
                    if current_format:
                        for i in range(self.combo_format_code.count()):
                            item_data = self.combo_format_code.itemData(i)
                            if item_data and item_data['code'] == current_format:
                                self.combo_format_code.setCurrentIndex(i)
                                break
                    
                    # Update status message
                    self.lbl_format_status.setText(f"Detected {len(formats)} formats")
                    self.lbl_format_status.setStyleSheet("color: green;")
                    
                    # Update format details based on selection
                    self._update_format_details()
                    
                    logger.info(f"Successfully detected {len(formats)} formats")
                    QMessageBox.information(self, "Format Detection", f"Successfully detected {len(formats)} formats.")
                else:
                    # Handle no formats detected - manually add formats from the FFmpeg output
                    logger.warning("No formats detected using regex - manually adding formats from sample output")
                    self.lbl_format_status.setText("Adding standard formats for Intensity Shuttle")
                    self.lbl_format_status.setStyleSheet("color: orange;")
                    
                    # Add formats from the ffmpeg output you provided
                    manual_formats = [
                        {'code': 'ntsc', 'width': 720, 'height': 486, 'fps': 29.97, 'scan_type': 'i', 
                        'description': '720x486 at 30000/1001 fps (interlaced, lower field first)'},
                        {'code': 'nt23', 'width': 720, 'height': 486, 'fps': 23.976, 'scan_type': 'p',
                        'description': '720x486 at 24000/1001 fps'},
                        {'code': 'pal', 'width': 720, 'height': 576, 'fps': 25, 'scan_type': 'i',
                        'description': '720x576 at 25000/1000 fps (interlaced, upper field first)'},
                        {'code': 'ntsp', 'width': 720, 'height': 486, 'fps': 59.94, 'scan_type': 'p',
                        'description': '720x486 at 60000/1001 fps'},
                        {'code': 'palp', 'width': 720, 'height': 576, 'fps': 50, 'scan_type': 'p',
                        'description': '720x576 at 50000/1000 fps'},
                        {'code': '23ps', 'width': 1920, 'height': 1080, 'fps': 23.976, 'scan_type': 'p',
                        'description': '1920x1080 at 24000/1001 fps'},
                        {'code': '24ps', 'width': 1920, 'height': 1080, 'fps': 24, 'scan_type': 'p',
                        'description': '1920x1080 at 24000/1000 fps'},
                        {'code': 'Hp25', 'width': 1920, 'height': 1080, 'fps': 25, 'scan_type': 'p',
                        'description': '1920x1080 at 25000/1000 fps'},
                        {'code': 'Hp29', 'width': 1920, 'height': 1080, 'fps': 29.97, 'scan_type': 'p',
                        'description': '1920x1080 at 30000/1001 fps'},
                        {'code': 'Hp30', 'width': 1920, 'height': 1080, 'fps': 30, 'scan_type': 'p',
                        'description': '1920x1080 at 30000/1000 fps'},
                        {'code': 'Hi50', 'width': 1920, 'height': 1080, 'fps': 25, 'scan_type': 'i',
                        'description': '1920x1080 at 25000/1000 fps (interlaced, upper field first)'},
                        {'code': 'Hi59', 'width': 1920, 'height': 1080, 'fps': 29.97, 'scan_type': 'i',
                        'description': '1920x1080 at 30000/1001 fps (interlaced, upper field first)'},
                        {'code': 'Hi60', 'width': 1920, 'height': 1080, 'fps': 30, 'scan_type': 'i',
                        'description': '1920x1080 at 30000/1000 fps (interlaced, upper field first)'},
                        {'code': 'hp50', 'width': 1280, 'height': 720, 'fps': 50, 'scan_type': 'p',
                        'description': '1280x720 at 50000/1000 fps'},
                        {'code': 'hp59', 'width': 1280, 'height': 720, 'fps': 59.94, 'scan_type': 'p',
                        'description': '1280x720 at 60000/1001 fps'},
                        {'code': 'hp60', 'width': 1280, 'height': 720, 'fps': 60, 'scan_type': 'p',
                        'description': '1280x720 at 60000/1000 fps'}
                    ]
                    
                    # Add fps_str field to each format
                    for fmt in manual_formats:
                        if abs(fmt['fps'] - 23.976) < 0.01:
                            fmt['fps_str'] = "23.976"
                        elif abs(fmt['fps'] - 29.97) < 0.01:
                            fmt['fps_str'] = "29.97"
                        elif abs(fmt['fps'] - 59.94) < 0.01:
                            fmt['fps_str'] = "59.94"
                        else:
                            fmt['fps_str'] = str(int(fmt['fps'])) if fmt['fps'] == int(fmt['fps']) else f"{fmt['fps']:.3f}"
                        
                        fmt['resolution'] = f"{fmt['width']}x{fmt['height']}"
                        fmt['display'] = f"{fmt['code']} - {fmt['width']}x{fmt['height']} @ {fmt['fps_str']}{fmt['scan_type']}"
                        self.combo_format_code.addItem(fmt['display'], fmt)
                    
                    # Select a reasonable default format (1080p at 29.97fps)
                    for i in range(self.combo_format_code.count()):
                        item_data = self.combo_format_code.itemData(i)
                        if item_data and item_data['code'] == 'Hp29':
                            self.combo_format_code.setCurrentIndex(i)
                            break
                    
                    QMessageBox.information(self, "Format Detection", 
                                        "Added standard formats for Intensity Shuttle device.")
                    
            except subprocess.TimeoutExpired:
                process.kill()
                logger.error("Timeout while detecting formats")
                self.lbl_format_status.setText("Error: Detection timed out")
                self.lbl_format_status.setStyleSheet("color: red;")
                QMessageBox.critical(self, "Error", "Timeout while detecting formats.")
                
            except Exception as proc_error:
                logger.error(f"Process error during format detection: {proc_error}")
                self.lbl_format_status.setText("Error during detection")
                self.lbl_format_status.setStyleSheet("color: red;")
                QMessageBox.critical(self, "Error", f"Error during format detection: {proc_error}")
                
        except Exception as e:
            logger.error(f"Error detecting formats: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.lbl_format_status.setText("Detection failed")
            self.lbl_format_status.setStyleSheet("color: red;")
            QMessageBox.critical(self, "Error", f"Failed to detect formats: {e}")

    def _update_format_details(self):
        """Update the format details label based on the selected format"""
        if self.combo_format_code.count() == 0:
            return
            
        # Get the selected format data
        index = self.combo_format_code.currentIndex()
        format_data = self.combo_format_code.itemData(index)
        
        if format_data:
            # Format the details string
            scan_type = "Interlaced" if format_data['scan_type'] == 'i' else "Progressive"
            details = (f"Resolution: {format_data['resolution']}  |  "
                    f"Frame Rate: {format_data['fps_str']} fps  |  "
                    f"Scan: {scan_type}")
            self.lbl_format_details.setText(details)
            
            # If we have options manager, update capture settings
            if hasattr(self.parent, 'options_manager') and self.parent.options_manager:
                # Store the complete format data in a way that can be used by the capture module
                capture_settings = {
                    "default_device": self.combo_capture_device.currentText(),
                    "format_code": format_data['code'],
                    "resolution": format_data['resolution'],
                    "width": format_data['width'],
                    "height": format_data['height'],
                    "frame_rate": format_data['fps'],
                    "scan_type": format_data['scan_type'],
                    "is_interlaced": (format_data['scan_type'] == 'i'),
                    "description": format_data.get('description', '')
                }
                
                # Update only these specific capture settings (don't overwrite others)
                self.parent.options_manager.update_setting("capture", "default_device", capture_settings["default_device"])
                self.parent.options_manager.update_setting("capture", "format_code", capture_settings["format_code"])
                self.parent.options_manager.update_setting("capture", "resolution", capture_settings["resolution"])
                self.parent.options_manager.update_setting("capture", "width", capture_settings["width"])
                self.parent.options_manager.update_setting("capture", "height", capture_settings["height"])
                self.parent.options_manager.update_setting("capture", "frame_rate", capture_settings["frame_rate"])
                self.parent.options_manager.update_setting("capture", "scan_type", capture_settings["scan_type"])
                self.parent.options_manager.update_setting("capture", "is_interlaced", capture_settings["is_interlaced"])

    def load_capture_settings(self):
        """Load capture-specific settings from options manager"""
        if not hasattr(self.parent, 'options_manager') or not self.parent.options_manager:
            logger.warning("Options manager not available, cannot load capture settings")
            return
            
        try:
            # Get capture settings
            capture_settings = self.parent.options_manager.get_setting("capture")
            
            # Set device selection
            if 'default_device' in capture_settings:
                index = self.combo_capture_device.findText(capture_settings['default_device'])
                if index >= 0:
                    self.combo_capture_device.setCurrentIndex(index)
            
            # Set pixel format
            if 'pixel_format' in capture_settings:
                pixel_format = capture_settings['pixel_format']
                for i in range(self.combo_pixel_format.count()):
                    if self.combo_pixel_format.itemText(i).startswith(pixel_format):
                        self.combo_pixel_format.setCurrentIndex(i)
                        break
            
            # Set video and audio inputs
            if 'video_input' in capture_settings:
                index = self.combo_video_input.findText(capture_settings['video_input'])
                if index >= 0:
                    self.combo_video_input.setCurrentIndex(index)
                    
            if 'audio_input' in capture_settings:
                index = self.combo_audio_input.findText(capture_settings['audio_input'])
                if index >= 0:
                    self.combo_audio_input.setCurrentIndex(index)
            
            # Set encoder settings
            if 'encoder' in capture_settings:
                index = self.combo_capture_encoder.findText(capture_settings['encoder'])
                if index >= 0:
                    self.combo_capture_encoder.setCurrentIndex(index)
                    
            if 'crf' in capture_settings:
                self.spin_capture_crf.setValue(capture_settings['crf'])
                
            if 'preset' in capture_settings:
                index = self.combo_capture_preset.findText(capture_settings['preset'])
                if index >= 0:
                    self.combo_capture_preset.setCurrentIndex(index)
            
            # Set advanced options
            if 'disable_audio' in capture_settings:
                self.chk_disable_audio.setChecked(capture_settings['disable_audio'])
                
            if 'low_latency' in capture_settings:
                self.chk_low_latency.setChecked(capture_settings['low_latency'])
                
            if 'force_format' in capture_settings:
                self.chk_force_format.setChecked(capture_settings['force_format'])
            
            # Load format code
            if 'format_code' in capture_settings:
                format_code = capture_settings['format_code']
                # We need to detect formats to populate the format_code dropdown
                # Just attempt to detect formats automatically
                if self.combo_format_code.count() == 0:
                    logger.info("Attempting to auto-detect formats on settings load")
                    self.detect_device_formats()
                
                # Try to select the format from settings
                for i in range(self.combo_format_code.count()):
                    item_data = self.combo_format_code.itemData(i)
                    if item_data and item_data['code'] == format_code:
                        self.combo_format_code.setCurrentIndex(i)
                        break
            
            logger.info("Capture settings loaded successfully")
        except Exception as e:
            logger.error(f"Error loading capture settings: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def save_capture_settings(self):
        """Save capture-specific settings to options manager"""
        if not hasattr(self.parent, 'options_manager') or not self.parent.options_manager:
            logger.warning("Options manager not available, cannot save capture settings")
            return False
            
        try:
            # Get current format selection data
            format_data = None
            if self.combo_format_code.count() > 0:
                index = self.combo_format_code.currentIndex()
                format_data = self.combo_format_code.itemData(index)
            
            # Build capture settings dictionary
            capture_settings = {
                "default_device": self.combo_capture_device.currentText(),
                "pixel_format": self.combo_pixel_format.currentText().split(' - ')[0],
                "video_input": self.combo_video_input.currentText(),
                "audio_input": self.combo_audio_input.currentText(),
                "encoder": self.combo_capture_encoder.currentText(),
                "crf": self.spin_capture_crf.value(),
                "preset": self.combo_capture_preset.currentText(),
                "disable_audio": self.chk_disable_audio.isChecked(),
                "low_latency": self.chk_low_latency.isChecked(),
                "force_format": self.chk_force_format.isChecked()
            }
            
            # Add format details if available
            if format_data:
                capture_settings.update({
                    "format_code": format_data['code'],
                    "resolution": format_data['resolution'],
                    "width": format_data['width'],
                    "height": format_data['height'],
                    "frame_rate": format_data['fps'],
                    "scan_type": format_data['scan_type'],
                    "is_interlaced": (format_data['scan_type'] == 'i')
                })
            
            # Update capture settings
            self.parent.options_manager.update_category("capture", capture_settings)
            logger.info("Capture settings saved successfully")
            return True
        except Exception as e:
            logger.error(f"Error saving capture settings: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
        
    def save_settings(self):
        """Save current settings to options manager"""
        if hasattr(self.parent, 'options_manager') and self.parent.options_manager:
            try:
                # First save capture-specific settings
                if hasattr(self, 'save_capture_settings'):
                    self.save_capture_settings()
                
                # Create settings dictionary for other tabs
                settings = {
                    # Paths
                    'paths': {
                        'reference_video_dir': self.txt_ref_dir.text(),
                        'default_output_dir': self.txt_output_dir.text(),
                        'models_dir': self.txt_vmaf_dir.text(),
                        'ffmpeg_path': self.txt_ffmpeg_path.text(),
                    },

                    # Encoder settings
                    'encoder': {
                        'default_encoder': self.combo_default_encoder.currentText(),
                        'default_crf': self.spin_default_crf.value(),
                        'default_preset': self.spin_default_preset.currentText(),
                    },

                    # Bookend settings - preserve existing settings, only update sliders
                    'bookend': {
                        'bookend_duration': self.spin_bookend_duration.value(),
                        'min_loops': self.spin_min_loops.value(),
                        'white_threshold': self.spin_bookend_threshold.value(),
                        'frame_sampling_rate': self.frame_sampling_slider.value()
                    },

                    # Analysis settings with advanced VMAF options
                    'vmaf': {
                        'default_model': self.combo_default_vmaf_model.currentText(),
                        'save_json': self.check_save_json.isChecked(),
                        'save_plots': self.check_save_plots.isChecked(),
                        'threads': self.spin_vmaf_threads.value(),
                        'tester_name': self.txt_tester_name.text(),
                        'test_location': self.txt_test_location.text(),
                        'pool_method': self.combo_pool_method.currentText(),
                        'feature_subsample': self.spin_feature_subsample.value(),
                        'enable_motion_score': self.check_motion_score.isChecked(),
                        'enable_temporal_features': self.check_temporal_features.isChecked(),
                        'psnr_enabled': self.check_psnr_enabled.isChecked(),
                        'ssim_enabled': self.check_ssim_enabled.isChecked(),
                    },

                    # Analysis general settings
                    'analysis': {
                        'use_temp_files': self.check_use_temp_files.isChecked(),
                        'auto_alignment': self.check_auto_alignment.isChecked(),
                        'alignment_method': self.combo_alignment_method.currentText(),
                    },

                    # Debug settings
                    'debug': {
                        'log_level': self.combo_log_level.currentText(),
                        'save_logs': self.check_save_logs.isChecked(),
                        'show_commands': self.check_show_commands.isChecked(),
                    }
                }

                # Update settings
                self.parent.options_manager.update_settings(settings)
                QMessageBox.information(self, "Settings Saved", "Settings have been saved successfully.")
                logger.info("Settings saved successfully")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save settings: {e}")
                logger.error(f"Error saving settings: {e}")
                # Print traceback for debugging
                import traceback
                logger.error(traceback.format_exc())

    def _setup_analysis_tab(self):
        """Set up the Analysis tab UI"""
        analysis_tab = QWidget()
        analysis_layout = QVBoxLayout(analysis_tab)

        # VMAF analysis settings
        vmaf_group = QGroupBox("VMAF Analysis Settings")
        vmaf_layout = QFormLayout()

        # Tester information
        self.txt_tester_name = QLineEdit()
        vmaf_layout.addRow("Tester Name:", self.txt_tester_name)

        self.txt_test_location = QLineEdit()
        vmaf_layout.addRow("Test Location:", self.txt_test_location)

        # VMAF options with tooltips
        self.check_use_temp_files = QCheckBox()
        self.check_use_temp_files.setChecked(True)
        self.check_use_temp_files.setToolTip("Use temporary files during processing to save disk space")
        vmaf_layout.addRow("Use Temporary Files:", self.check_use_temp_files)

        self.check_save_json = QCheckBox()
        self.check_save_json.setChecked(True)
        self.check_save_json.setToolTip("Save detailed VMAF results in JSON format for later analysis")
        vmaf_layout.addRow("Save JSON Results:", self.check_save_json)

        self.check_save_plots = QCheckBox()
        self.check_save_plots.setChecked(True)
        self.check_save_plots.setToolTip("Generate graphs showing quality over time")
        vmaf_layout.addRow("Generate Plots:", self.check_save_plots)

        self.check_auto_alignment = QCheckBox()
        self.check_auto_alignment.setChecked(True)
        self.check_auto_alignment.setToolTip("Automatically align reference and distorted videos before analysis")
        vmaf_layout.addRow("Auto-Align Videos:", self.check_auto_alignment)

        self.combo_alignment_method = QComboBox()
        self.combo_alignment_method.addItems(["SSIM", "Bookend Detection", "Combined"])
        self.combo_alignment_method.setToolTip("Choose method for aligning videos. Bookend Detection works best with white frames at start/end.")
        alignment_label = QLabel("Alignment Method:")
        alignment_label.setToolTip("Choose method for aligning videos. Bookend Detection works best with white frames at start/end.")
        vmaf_layout.addRow(alignment_label, self.combo_alignment_method)

        # Number of threads for VMAF with tooltip
        self.spin_vmaf_threads = QSpinBox()
        self.spin_vmaf_threads.setRange(0, 32)
        self.spin_vmaf_threads.setValue(4)
        self.spin_vmaf_threads.setToolTip("Number of CPU threads for VMAF calculation. 0 = Auto (use all available cores)")
        threads_label = QLabel("VMAF Threads:")
        threads_label.setToolTip("Number of CPU threads for VMAF calculation. 0 = Auto (use all available cores)")
        vmaf_layout.addRow(threads_label, self.spin_vmaf_threads)

        # Add VMAF model selection with tooltip
        self.combo_default_vmaf_model = QComboBox()
        self._populate_vmaf_models()
        self.combo_default_vmaf_model.setToolTip("Choose VMAF model. vmaf_v0.6.1 is standard. Use vmaf_4k for UHD content.")
        model_label = QLabel("Default VMAF Model:")
        model_label.setToolTip("Choose VMAF model. vmaf_v0.6.1 is standard. Use vmaf_4k for UHD content.")
        vmaf_layout.addRow(model_label, self.combo_default_vmaf_model)

        # Add advanced VMAF analysis options
        vmaf_advanced_group = QGroupBox("Advanced VMAF Options")
        advanced_vmaf_layout = QFormLayout()
        
        # Add helper info
        advanced_help_label = QLabel("These settings control fine-tuning parameters for VMAF analysis:")
        advanced_help_label.setStyleSheet("font-style: italic; color: #666;")
        advanced_vmaf_layout.addRow(advanced_help_label)
        
        # Pooling method with tooltip
        self.combo_pool_method = QComboBox()
        self.combo_pool_method.addItems(["mean", "min", "harmonic_mean"])
        self.combo_pool_method.setToolTip("How frame scores are combined: 'mean' is standard, 'harmonic_mean' emphasizes drops, 'min' shows worst case")
        pool_label = QLabel("Pooling Method:")
        pool_label.setToolTip("How frame scores are combined: 'mean' is standard, 'harmonic_mean' emphasizes drops, 'min' shows worst case")
        advanced_vmaf_layout.addRow(pool_label, self.combo_pool_method)
        
        # Feature subsample for fast-moving content with tooltip
        self.spin_feature_subsample = QSpinBox()
        self.spin_feature_subsample.setRange(1, 10)
        self.spin_feature_subsample.setValue(1)
        self.spin_feature_subsample.setToolTip("Analyze every Nth frame. Higher values speed up processing but reduce accuracy. Use 1 for full precision.")
        subsample_label = QLabel("Feature Subsample Rate:")
        subsample_label.setToolTip("Analyze every Nth frame. Higher values speed up processing but reduce accuracy. Use 1 for full precision.")
        advanced_vmaf_layout.addRow(subsample_label, self.spin_feature_subsample)
        
        # Motion score option with tooltip
        self.check_motion_score = QCheckBox()
        self.check_motion_score.setChecked(False)
        self.check_motion_score.setToolTip("Measure and report motion intensity scores. Useful for analyzing fast-moving content.")
        motion_score_label = QLabel("Enable Motion Score:")
        motion_score_label.setToolTip("Measure and report motion intensity scores. Useful for analyzing fast-moving content.")
        advanced_vmaf_layout.addRow(motion_score_label, self.check_motion_score)
        
        # Temporal feature analysis with tooltip
        self.check_temporal_features = QCheckBox()
        self.check_temporal_features.setChecked(False)
        self.check_temporal_features.setToolTip("Enable additional temporal features for more accurate analysis of motion. Uses more CPU.")
        temporal_label = QLabel("Enable Temporal Features:")
        temporal_label.setToolTip("Enable additional temporal features for more accurate analysis of motion. Uses more CPU.")
        advanced_vmaf_layout.addRow(temporal_label, self.check_temporal_features)
        
        # Add PSNR/SSIM options with tooltips
        self.check_psnr_enabled = QCheckBox()
        self.check_psnr_enabled.setChecked(True)
        self.check_psnr_enabled.setToolTip("Calculate PSNR (Peak Signal-to-Noise Ratio) metric in addition to VMAF")
        psnr_label = QLabel("Enable PSNR:")
        psnr_label.setToolTip("Calculate PSNR (Peak Signal-to-Noise Ratio) metric in addition to VMAF")
        advanced_vmaf_layout.addRow(psnr_label, self.check_psnr_enabled)
        
        self.check_ssim_enabled = QCheckBox()
        self.check_ssim_enabled.setChecked(True)
        self.check_ssim_enabled.setToolTip("Calculate SSIM (Structural Similarity) metric in addition to VMAF")
        ssim_label = QLabel("Enable SSIM:")
        ssim_label.setToolTip("Calculate SSIM (Structural Similarity) metric in addition to VMAF")
        advanced_vmaf_layout.addRow(ssim_label, self.check_ssim_enabled)
        
        vmaf_advanced_group.setLayout(advanced_vmaf_layout)

        vmaf_group.setLayout(vmaf_layout)
        analysis_layout.addWidget(vmaf_group)
        analysis_layout.addWidget(vmaf_advanced_group)
        
        return analysis_tab












    def _update_frame_sampling_label(self):
        """Updates the label displaying the current frame sampling rate."""
        if hasattr(self, 'frame_sampling_label') and hasattr(self, 'frame_sampling_slider'):
            self.frame_sampling_label.setText(f"{self.frame_sampling_slider.value()} frames")















    def _populate_vmaf_models(self):
            """Populate VMAF models dropdown in options tab"""
            try:
                # Clear existing items
                self.combo_default_vmaf_model.clear()

                # Use get_project_paths to find models directory
                try:
                    from app.utils import get_project_paths
                    paths = get_project_paths()
                    models_dir = paths['models']
                except:
                    # Fallback if utils module can't be imported
                    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    models_dir = os.path.join(script_dir, "models")

                # Use custom directory if specified
                custom_dir = self.txt_vmaf_dir.text() if hasattr(self, 'txt_vmaf_dir') else ""
                if custom_dir and os.path.exists(custom_dir):
                    models_dir = custom_dir

                # Log the models directory for debugging
                logger.info(f"Looking for VMAF models in: {models_dir}")

                # Scan for model files
                if os.path.exists(models_dir):
                    model_files = []
                    for file in os.listdir(models_dir):
                        if file.endswith('.json'):
                            model_name = os.path.splitext(file)[0]
                            model_files.append(model_name)

                    # Sort models alphabetically
                    model_files.sort()

                    # Add to dropdown
                    for model in model_files:
                        self.combo_default_vmaf_model.addItem(model, model)

                    if not model_files:
                        # Add defaults if no models found
                        logger.warning(f"No VMAF model files found in {models_dir}, using defaults")
                        self.combo_default_vmaf_model.addItems(["vmaf_v0.6.1", "vmaf_4k_v0.6.1", "vmaf_b_v0.6.3"])
                else:
                    # Add defaults if directory doesn't exist
                    logger.warning(f"Models directory doesn't exist: {models_dir}, using defaults")
                    self.combo_default_vmaf_model.addItems(["vmaf_v0.6.1", "vmaf_4k_v0.6.1", "vmaf_b_v0.6.3"])

                logger.info(f"Populated VMAF model dropdown with {self.combo_default_vmaf_model.count()} models")

            except Exception as e:
                logger.error(f"Error populating VMAF models in options: {e}")
                import traceback
                logger.error(traceback.format_exc())
                # Add defaults as fallback
                self.combo_default_vmaf_model.clear()
                self.combo_default_vmaf_model.addItems(["vmaf_v0.6.1", "vmaf_4k_v0.6.1", "vmaf_b_v0.6.3"])









    def _populate_vmaf_models(self):
            """Populate VMAF models dropdown in options tab"""
            try:
                # Clear existing items
                self.combo_default_vmaf_model.clear()

                # Use get_project_paths to find models directory
                try:
                    from app.utils import get_project_paths
                    paths = get_project_paths()
                    models_dir = paths['models']
                except:
                    # Fallback if utils module can't be imported
                    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    models_dir = os.path.join(script_dir, "models")

                # Use custom directory if specified
                custom_dir = self.txt_vmaf_dir.text() if hasattr(self, 'txt_vmaf_dir') else ""
                if custom_dir and os.path.exists(custom_dir):
                    models_dir = custom_dir

                # Log the models directory for debugging
                logger.info(f"Looking for VMAF models in: {models_dir}")

                # Scan for model files
                if os.path.exists(models_dir):
                    model_files = []
                    for file in os.listdir(models_dir):
                        if file.endswith('.json'):
                            model_name = os.path.splitext(file)[0]
                            model_files.append(model_name)

                    # Sort models alphabetically
                    model_files.sort()

                    # Add to dropdown
                    for model in model_files:
                        self.combo_default_vmaf_model.addItem(model, model)

                    if not model_files:
                        # Add defaults if no models found
                        logger.warning(f"No VMAF model files found in {models_dir}, using defaults")
                        self.combo_default_vmaf_model.addItems(["vmaf_v0.6.1", "vmaf_4k_v0.6.1", "vmaf_b_v0.6.3"])
                else:
                    # Add defaults if directory doesn't exist
                    logger.warning(f"Models directory doesn't exist: {models_dir}, using defaults")
                    self.combo_default_vmaf_model.addItems(["vmaf_v0.6.1", "vmaf_4k_v0.6.1", "vmaf_b_v0.6.3"])

                logger.info(f"Populated VMAF model dropdown with {self.combo_default_vmaf_model.count()} models")

            except Exception as e:
                logger.error(f"Error populating VMAF models in options: {e}")
                import traceback
                logger.error(traceback.format_exc())
                # Add defaults as fallback
                self.combo_default_vmaf_model.clear()
                self.combo_default_vmaf_model.addItems(["vmaf_v0.6.1", "vmaf_4k_v0.6.1", "vmaf_b_v0.6.3"])









    # Add these methods to the OptionsTab class

    def browse_ref_directory(self):
        """Browse for reference videos directory"""
        directory = QFileDialog.getExistingDirectory(
            self, 
            "Select Reference Videos Directory",
            self.txt_ref_dir.text() or os.path.expanduser("~")
        )

        if directory:
            self.txt_ref_dir.setText(directory)

    def browse_output_directory(self):
        """Browse for output directory"""
        directory = QFileDialog.getExistingDirectory(
            self, 
            "Select Output Directory",
            self.txt_output_dir.text() or os.path.expanduser("~")
        )

        if directory:
            self.txt_output_dir.setText(directory)

    def browse_vmaf_directory(self):
        """Browse for VMAF models directory"""
        directory = QFileDialog.getExistingDirectory(
            self, 
            "Select VMAF Models Directory",
            self.txt_vmaf_dir.text() or os.path.expanduser("~")
        )

        if directory:
            self.txt_vmaf_dir.setText(directory)
            # Update VMAF models dropdown after changing directory
            self._populate_vmaf_models()

    def browse_ffmpeg_path(self):
        """Browse for FFmpeg executable"""
        file_filter = "Executable Files (*.exe);;All Files (*.*)" if os.name == "nt" else "All Files (*.*)"
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select FFmpeg Executable",
            self.txt_ffmpeg_path.text() or os.path.expanduser("~"),
            file_filter
        )

        if file_path:
            self.txt_ffmpeg_path.setText(file_path)






















    def _setup_general_tab(self):
        """Set up the General tab UI"""
        general_tab = QWidget()
        general_layout = QVBoxLayout(general_tab)

        # Directories group
        directories_group = QGroupBox("Directories")
        directories_layout = QVBoxLayout()

        # Reference videos directory
        ref_dir_layout = QHBoxLayout()
        ref_dir_layout.addWidget(QLabel("Reference Videos Directory:"))
        self.txt_ref_dir = QLineEdit()
        self.txt_ref_dir.setReadOnly(True)
        ref_dir_layout.addWidget(self.txt_ref_dir)
        self.btn_browse_ref_dir = QPushButton("Browse...")
        self.btn_browse_ref_dir.clicked.connect(self.browse_ref_directory)
        ref_dir_layout.addWidget(self.btn_browse_ref_dir)
        directories_layout.addLayout(ref_dir_layout)

        # Output directory
        output_dir_layout = QHBoxLayout()
        output_dir_layout.addWidget(QLabel("Output Directory:"))
        self.txt_output_dir = QLineEdit()
        self.txt_output_dir.setReadOnly(True)
        output_dir_layout.addWidget(self.txt_output_dir)
        self.btn_browse_output_dir = QPushButton("Browse...")
        self.btn_browse_output_dir.clicked.connect(self.browse_output_directory)
        output_dir_layout.addWidget(self.btn_browse_output_dir)
        directories_layout.addLayout(output_dir_layout)

        # VMAF models directory
        vmaf_dir_layout = QHBoxLayout()
        vmaf_dir_layout.addWidget(QLabel("VMAF Models Directory:"))
        self.txt_vmaf_dir = QLineEdit()
        self.txt_vmaf_dir.setReadOnly(True)
        vmaf_dir_layout.addWidget(self.txt_vmaf_dir)
        self.btn_browse_vmaf_dir = QPushButton("Browse...")
        self.btn_browse_vmaf_dir.clicked.connect(self.browse_vmaf_directory)
        vmaf_dir_layout.addWidget(self.btn_browse_vmaf_dir)
        directories_layout.addLayout(vmaf_dir_layout)

        directories_group.setLayout(directories_layout)
        general_layout.addWidget(directories_group)

        # FFmpeg settings group
        ffmpeg_group = QGroupBox("FFmpeg Configuration")
        ffmpeg_layout = QVBoxLayout()

        # FFmpeg path
        ffmpeg_path_layout = QHBoxLayout()
        ffmpeg_path_layout.addWidget(QLabel("FFmpeg Path:"))
        self.txt_ffmpeg_path = QLineEdit()
        self.txt_ffmpeg_path.setReadOnly(True)
        ffmpeg_path_layout.addWidget(self.txt_ffmpeg_path)
        self.btn_browse_ffmpeg = QPushButton("Browse...")
        self.btn_browse_ffmpeg.clicked.connect(self.browse_ffmpeg_path)
        ffmpeg_path_layout.addWidget(self.btn_browse_ffmpeg)
        ffmpeg_layout.addLayout(ffmpeg_path_layout)

        # Default encoder settings
        encoder_form = QFormLayout()

        self.combo_default_encoder = QComboBox()
        self.combo_default_encoder.addItems(["libx264", "libx265", "nvenc_h264", "nvenc_hevc"])
        encoder_form.addRow("Default Encoder:", self.combo_default_encoder)

        self.spin_default_crf = QSpinBox()
        self.spin_default_crf.setRange(0, 51)
        self.spin_default_crf.setValue(23)
        encoder_form.addRow("Default CRF Value:", self.spin_default_crf)

        self.spin_default_preset = QComboBox()
        self.spin_default_preset.addItems(["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"])
        self.spin_default_preset.setCurrentText("medium")
        encoder_form.addRow("Default Preset:", self.spin_default_preset)

        ffmpeg_layout.addLayout(encoder_form)
        ffmpeg_group.setLayout(ffmpeg_layout)
        general_layout.addWidget(ffmpeg_group)
        
        return general_tab








    def reset_settings(self):
        """Reset settings to defaults"""
        confirm = QMessageBox.question(
            self, 
            "Reset Settings", 
            "Are you sure you want to reset all settings to defaults?",
            QMessageBox.Yes | QMessageBox.No
        )

        if confirm == QMessageBox.Yes and hasattr(self.parent, 'options_manager'):
            self.parent.options_manager.reset_to_defaults()
            self.load_settings()
            QMessageBox.information(self, "Settings Reset", "Settings have been reset to defaults.")
            logger.info("Settings reset to defaults")








    def _load_advanced_settings(self, settings):
            """Load settings for the advanced tab"""
            try:
                # Populate debug settings
                debug = settings.get('debug', {})
                self.combo_log_level.setCurrentText(debug.get('log_level', 'INFO'))
                self.check_save_logs.setChecked(debug.get('save_logs', True))
                self.check_show_commands.setChecked(debug.get('show_commands', True))
            except Exception as e:
                logger.error(f"Error loading advanced settings: {e}")










    def _setup_advanced_tab(self):
        """Set up the Advanced tab UI"""
        advanced_tab = QWidget()
        advanced_layout = QVBoxLayout(advanced_tab)

        # Debugging options
        debug_group = QGroupBox("Debugging")
        debug_layout = QFormLayout()

        self.combo_log_level = QComboBox()
        self.combo_log_level.addItems(["INFO", "DEBUG", "WARNING", "ERROR", "CRITICAL"])
        debug_layout.addRow("Log Level:", self.combo_log_level)

        self.check_save_logs = QCheckBox()
        self.check_save_logs.setChecked(True)
        debug_layout.addRow("Save Logs:", self.check_save_logs)

        self.check_show_commands = QCheckBox()
        self.check_show_commands.setChecked(True)
        debug_layout.addRow("Show FFmpeg Commands:", self.check_show_commands)

        debug_group.setLayout(debug_layout)
        advanced_layout.addWidget(debug_group)
        
        return advanced_tab

    def load_settings(self):
        """Load settings from options manager"""
        try:
            if not hasattr(self, 'options_manager') or not self.options_manager:
                logger.warning("Options manager not available, cannot load settings")

                # Try to get from parent as fallback
                if hasattr(self.parent, 'options_manager') and self.parent.options_manager:
                    self.options_manager = self.parent.options_manager
                else:
                    logger.warning("Options manager not available, cannot load settings")
                    return

            # Load frame sampling rate
            settings = self.options_manager.get_settings()
            
            # Load settings for general tab components
            self._load_general_settings(settings)
            
            # Load capture-specific settings
            if hasattr(self, 'load_capture_settings'):
                self.load_capture_settings()
            
            # Load analysis tab settings
            self._load_analysis_settings(settings)
            
            # Load advanced tab settings
            self._load_advanced_settings(settings)
            
            logger.info("Settings loaded successfully")
        except Exception as e:
            logger.error(f"Error loading settings: {e}")
            # Print traceback for debugging
            import traceback
            logger.error(traceback.format_exc())
            
    def _load_general_settings(self, settings):
        """Load settings for the general tab"""
        try:
            # Load bookend slider
            bookend_settings = settings.get('bookend', {})
            frame_sampling_rate = bookend_settings.get('frame_sampling_rate', 5)
            self.frame_sampling_slider.setValue(frame_sampling_rate)
            self._update_frame_sampling_label()

            # Populate directories
            paths = settings.get('paths', {})
            self.txt_ref_dir.setText(paths.get('reference_video_dir', ''))
            self.txt_output_dir.setText(paths.get('default_output_dir', ''))
            self.txt_vmaf_dir.setText(paths.get('models_dir', ''))
            self.txt_ffmpeg_path.setText(paths.get('ffmpeg_path', ''))

            # Populate encoder settings
            encoder = settings.get('encoder', {})
            self.combo_default_encoder.setCurrentText(encoder.get('default_encoder', 'libx264'))
            self.spin_default_crf.setValue(int(encoder.get('default_crf', 23)))
            self.spin_default_preset.setCurrentText(encoder.get('default_preset', 'medium'))
            
            # Populate bookend settings
            self.spin_bookend_duration.setValue(float(bookend_settings.get('bookend_duration', 0.5)))
            self.spin_min_loops.setValue(int(bookend_settings.get('min_loops', 3)))
            self.spin_bookend_threshold.setValue(int(bookend_settings.get('white_threshold', 230)))
        except Exception as e:
            logger.error(f"Error loading general settings: {e}")
            
    def _load_analysis_settings(self, settings):
        """Load settings for the analysis tab"""
        #try:
        # Populate analysis settings
        vmaf = settings.get('vmaf', {})
        self.check_use_temp_files.setChecked(settings.get('use_temp_files', True))
        self.check_save_json.setChecked(vmaf.get('save_json', True))
        self.check_save_plots.setChecked(vmaf.get('save_plots', True))
        self.check_auto_alignment.setChecked(settings.get('auto_alignment', True))
        self.combo_alignment_method.setCurrentText(settings.get('alignment_method', 'Bookend Detection'))

        # Load tester information
        if hasattr(self, 'txt_tester_name'):
            self.txt_tester_name.setText(vmaf.get('tester_name', ''))
            self.txt_test_location.setText(vmaf.get('test_location', ''))

        # Load thread count
        if hasattr(self, 'spin_vmaf_threads'):
            self.spin_vmaf_threads.setValue(vmaf.get('threads', 4))

        # Populate VMAF models and set default
        self._populate_vmaf_models()
        default_model = vmaf.get('default_model', 'vmaf_v0.6.1')
        index = self.combo_default_vmaf_model.findText(default_model)
        if index >= 0:
            self.combo_default_vmaf_model.setCurrentIndex(index)
            
        # Load advanced VMAF settings if they exist
        if hasattr(self, 'combo_pool_method'):
            self.combo_pool_method.setCurrentText(vmaf.get('pool_method', 'mean'))
        if hasattr(self, 'spin_feature_subsample'):
            self.spin_feature_subsample.setValue(vmaf.get('feature_subsample', 1))
        if hasattr(self, 'check_motion_score'):
            self.check_motion_score.setChecked(vmaf.get('enable_motion_score', False))
        if hasattr(self, 'check_temporal_features'):
            self.check_temporal_features.setChecked(vmaf.get('enable_temporal_features', False))
        if hasattr(self, 'check_psnr_enabled'):
            self.check_psnr_enabled.setChecked(vmaf.get('psnr_enabled', True))
        if hasattr(self, 'check_ssim_enabled'):
            self.check_ssim_enabled.setChecked(vmaf.get('ssim_enabled', True))
        