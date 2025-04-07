import logging
import os
import platform

from PyQt5.QtCore import Qt 
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
                             QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                             QLineEdit, QMessageBox, QPushButton, QSlider,
                             QSpinBox, QTabWidget, QVBoxLayout, QWidget,
                             QApplication, QScrollArea)

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
        """Set up the Options tab UI with scrolling support"""
        # Create a scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # Create a widget to hold all content
        scroll_content = QWidget()
        scroll_area.setWidget(scroll_content)

        # Create main layout for the content
        layout = QVBoxLayout(scroll_content)

        # Set the scroll area as the main widget
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(scroll_area)

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

        # Use a form layout for better alignment and spacing
        directories_form = QFormLayout()
        directories_form.setSpacing(10)  # Increase spacing between rows
        directories_form.setLabelAlignment(Qt.AlignRight)  # Align labels to the right
        directories_form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)  # Let fields expand

        # Reference videos directory
        ref_dir_widget = QWidget()
        ref_dir_layout = QHBoxLayout(ref_dir_widget)
        ref_dir_layout.setContentsMargins(0, 0, 0, 0)
        ref_dir_layout.setSpacing(10)

        self.txt_ref_dir = QLineEdit()
        self.txt_ref_dir.setReadOnly(True)
        self.txt_ref_dir.setMinimumWidth(400)  # Set minimum width

        self.btn_browse_ref_dir = QPushButton("Browse...")
        self.btn_browse_ref_dir.clicked.connect(self.browse_ref_directory)
        self.btn_browse_ref_dir.setFixedWidth(100)  # Fixed width for button

        ref_dir_layout.addWidget(self.txt_ref_dir)
        ref_dir_layout.addWidget(self.btn_browse_ref_dir)

        # Output directory
        output_dir_widget = QWidget()
        output_dir_layout = QHBoxLayout(output_dir_widget)
        output_dir_layout.setContentsMargins(0, 0, 0, 0)
        output_dir_layout.setSpacing(10)

        self.txt_output_dir = QLineEdit()
        self.txt_output_dir.setReadOnly(True)
        self.txt_output_dir.setMinimumWidth(400)

        self.btn_browse_output_dir = QPushButton("Browse...")
        self.btn_browse_output_dir.clicked.connect(self.browse_output_directory)
        self.btn_browse_output_dir.setFixedWidth(100)

        output_dir_layout.addWidget(self.txt_output_dir)
        output_dir_layout.addWidget(self.btn_browse_output_dir)

        # VMAF models directory
        vmaf_dir_widget = QWidget()
        vmaf_dir_layout = QHBoxLayout(vmaf_dir_widget)
        vmaf_dir_layout.setContentsMargins(0, 0, 0, 0)
        vmaf_dir_layout.setSpacing(10)

        self.txt_vmaf_dir = QLineEdit()
        self.txt_vmaf_dir.setReadOnly(True)
        self.txt_vmaf_dir.setMinimumWidth(400)

        self.btn_browse_vmaf_dir = QPushButton("Browse...")
        self.btn_browse_vmaf_dir.clicked.connect(self.browse_vmaf_directory)
        self.btn_browse_vmaf_dir.setFixedWidth(100)

        vmaf_dir_layout.addWidget(self.txt_vmaf_dir)
        vmaf_dir_layout.addWidget(self.btn_browse_vmaf_dir)

        # Add to form layout
        directories_form.addRow("Reference Videos Directory:", ref_dir_widget)
        directories_form.addRow("Output Directory:", output_dir_widget)
        directories_form.addRow("VMAF Models Directory:", vmaf_dir_widget)

        # Add form to directories layout
        directories_layout.addLayout(directories_form)

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

        self.combo_default_preset = QComboBox()
        self.combo_default_preset.addItems(["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"])
        self.combo_default_preset.setCurrentText("medium")
        encoder_form.addRow("Default Preset:", self.combo_default_preset)

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

    def _setup_advanced_tab(self):
        """Set up the Advanced tab UI"""
        advanced_tab = QWidget()
        advanced_layout = QVBoxLayout(advanced_tab)
        
        # Bookend Settings group
        bookend_group = QGroupBox("Bookend Detection Settings")
        bookend_layout = QFormLayout()

        # Add helper info
        bookend_help_label = QLabel("These settings control the white frame bookend detection and alignment:")
        bookend_help_label.setStyleSheet("font-style: italic; color: #666;")
        bookend_help_label.setWordWrap(True)
        bookend_layout.addRow(bookend_help_label)

        # Loops settings with tooltips
        self.spin_min_loops = QSpinBox()
        self.spin_min_loops.setRange(1, 20)
        self.spin_min_loops.setValue(3)
        self.spin_min_loops.setToolTip("Minimum number of content loops to capture")
        min_loops_label = QLabel("Minimum Loops:")
        min_loops_label.setToolTip("Minimum number of content loops to capture")
        bookend_layout.addRow(min_loops_label, self.spin_min_loops)

        self.spin_max_loops = QSpinBox()
        self.spin_max_loops.setRange(1, 50)
        self.spin_max_loops.setValue(10)
        self.spin_max_loops.setToolTip("Maximum number of content loops to capture")
        max_loops_label = QLabel("Maximum Loops:")
        max_loops_label.setToolTip("Maximum number of content loops to capture")
        bookend_layout.addRow(max_loops_label, self.spin_max_loops)

        # Capture time settings
        self.spin_min_capture_time = QSpinBox()
        self.spin_min_capture_time.setRange(1, 300)
        self.spin_min_capture_time.setValue(5)
        self.spin_min_capture_time.setSuffix(" sec")
        self.spin_min_capture_time.setToolTip("Minimum recording time in seconds")
        min_time_label = QLabel("Minimum Capture Time:")
        min_time_label.setToolTip("Minimum recording time in seconds")
        bookend_layout.addRow(min_time_label, self.spin_min_capture_time)

        self.spin_max_capture_time = QSpinBox()
        self.spin_max_capture_time.setRange(5, 600)
        self.spin_max_capture_time.setValue(120)
        self.spin_max_capture_time.setSuffix(" sec")
        self.spin_max_capture_time.setToolTip("Maximum recording time in seconds")
        max_time_label = QLabel("Maximum Capture Time:")
        max_time_label.setToolTip("Maximum recording time in seconds")
        bookend_layout.addRow(max_time_label, self.spin_max_capture_time)

        # Bookend duration with tooltip
        self.spin_bookend_duration = QDoubleSpinBox()
        self.spin_bookend_duration.setRange(0.1, 2.0)
        self.spin_bookend_duration.setValue(0.2)
        self.spin_bookend_duration.setSingleStep(0.1)
        self.spin_bookend_duration.setDecimals(1)
        self.spin_bookend_duration.setSuffix(" sec")
        self.spin_bookend_duration.setToolTip("Duration of white bookend frames in seconds")
        bookend_duration_label = QLabel("Bookend Duration:")
        bookend_duration_label.setToolTip("Duration of white bookend frames in seconds")
        bookend_layout.addRow(bookend_duration_label, self.spin_bookend_duration)

        # White threshold setting with slider
        threshold_widget = QWidget()
        threshold_layout = QHBoxLayout(threshold_widget)
        threshold_layout.setContentsMargins(0, 0, 0, 0)

        self.slider_white_threshold = QSlider(Qt.Horizontal)
        self.slider_white_threshold.setRange(160, 250)
        self.slider_white_threshold.setValue(200)
        self.slider_white_threshold.setTickPosition(QSlider.TicksBelow)
        self.slider_white_threshold.setTickInterval(10)

        self.spin_white_threshold = QSpinBox()
        self.spin_white_threshold.setRange(160, 250)
        self.spin_white_threshold.setValue(200)
        self.spin_white_threshold.setToolTip("Brightness threshold for white frame detection (0-255)")

        # Connect slider and spinbox
        self.slider_white_threshold.valueChanged.connect(self.spin_white_threshold.setValue)
        self.spin_white_threshold.valueChanged.connect(self.slider_white_threshold.setValue)

        threshold_layout.addWidget(self.slider_white_threshold)
        threshold_layout.addWidget(self.spin_white_threshold)

        white_threshold_label = QLabel("White Threshold:")
        white_threshold_label.setToolTip("Brightness threshold for white frame detection (0-255)")
        bookend_layout.addRow(white_threshold_label, threshold_widget)

        # Frame sampling rate with tooltip
        self.spin_frame_sampling = QSpinBox()
        self.spin_frame_sampling.setRange(1, 30)
        self.spin_frame_sampling.setValue(5)
        self.spin_frame_sampling.setToolTip("Sample every Nth frame when detecting bookends. Higher values are faster but less precise.")
        sampling_label = QLabel("Frame Sampling Rate:")
        sampling_label.setToolTip("Sample every Nth frame when detecting bookends. Higher values are faster but less precise.")
        bookend_layout.addRow(sampling_label, self.spin_frame_sampling)

        # Frame offset with tooltip
        self.spin_frame_offset = QSpinBox()
        self.spin_frame_offset.setRange(-10, 10)
        self.spin_frame_offset.setValue(6)
        self.spin_frame_offset.setToolTip("Frame offset adjustment for alignment. Negative values start earlier.")
        offset_label = QLabel("Frame Offset:")
        offset_label.setToolTip("Frame offset adjustment for alignment. Negative values start earlier.")
        bookend_layout.addRow(offset_label, self.spin_frame_offset)

        # Option checkboxes for bookend settings
        self.check_adaptive_brightness = QCheckBox()
        self.check_adaptive_brightness.setChecked(True)
        self.check_adaptive_brightness.setToolTip("Auto-adjust white detection threshold based on content brightness")
        adaptive_label = QLabel("Use Adaptive Brightness:")
        adaptive_label.setToolTip("Auto-adjust white detection threshold based on content brightness")
        bookend_layout.addRow(adaptive_label, self.check_adaptive_brightness)

        self.check_motion_compensation = QCheckBox()
        self.check_motion_compensation.setChecked(False)
        self.check_motion_compensation.setToolTip("Use motion compensation when aligning distorted content (experimental)")
        motion_label = QLabel("Use Motion Compensation:")
        motion_label.setToolTip("Use motion compensation when aligning distorted content (experimental)")
        bookend_layout.addRow(motion_label, self.check_motion_compensation)

        self.check_fallback_full_video = QCheckBox()
        self.check_fallback_full_video.setChecked(True)
        self.check_fallback_full_video.setToolTip("Use full video if bookend detection fails")
        fallback_label = QLabel("Fallback to Full Video:")
        fallback_label.setToolTip("Use full video if bookend detection fails")
        bookend_layout.addRow(fallback_label, self.check_fallback_full_video)

        bookend_group.setLayout(bookend_layout)
        advanced_layout.addWidget(bookend_group)
        
        # Add the Debugging section
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

    def _populate_device_list(self):
        """Refresh and populate the device dropdown with available DeckLink devices"""
        if not hasattr(self, 'combo_capture_device'):
            logger.warning("Device combo box not initialized")
            return

        self.combo_capture_device.clear()

        try:
            if self.options_manager:
                devices = self.options_manager.get_decklink_devices()
                if not devices:
                    # Fallback for when no devices are detected
                    devices = ["Intensity Shuttle"]

                for device in devices:
                    self.combo_capture_device.addItem(device)

                # Set current device from settings if available
                current_device = self.options_manager.get_setting("capture", "default_device")
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
            # First check if options_manager has a method to get device formats
            formats = []
            formats_map = {}
            
            if hasattr(self.options_manager, 'get_decklink_formats'):
                # Use the options_manager method
                result = self.options_manager.get_decklink_formats(device)
                if result and (result.get("formats") or result.get("format_map")):
                    formats = result.get("formats", [])
                    formats_map = result.get("format_map", {})
                    logger.info(f"Obtained {len(formats)} formats from options_manager")
                    
                    # Update the UI with detected formats
                    self.combo_format_code.clear()

                    # Sort formats by resolution and then by frame rate for better presentation
                    formats.sort(key=lambda x: (x.get('height', 0), x.get('width', 0), x.get('frame_rate', 0)))

                    for fmt in formats:
                        self.combo_format_code.addItem(fmt.get('display', ''), fmt)

                    # Select format from settings if available
                    current_format = self.options_manager.get_setting("capture", "format_code")
                    if current_format:
                        for i in range(self.combo_format_code.count()):
                            item_data = self.combo_format_code.itemData(i)
                            if item_data and item_data.get('code') == current_format:
                                self.combo_format_code.setCurrentIndex(i)
                                break

                    # Update status message
                    self.lbl_format_status.setText(f"Detected {len(formats)} formats")
                    self.lbl_format_status.setStyleSheet("color: green;")

                    # Update format details based on selection
                    self._update_format_details()
                    
                    # Save the format information to options_manager
                    self._save_detected_formats(formats, formats_map)
                    
                    return
                
            # If the above didn't work, try the direct approach
            import subprocess
            import re
            
            # First try with decklink format
            try:
                # Run FFmpeg command to list formats with improved error handling
                ffmpeg_path = "ffmpeg"
                if hasattr(self.options_manager, 'get_ffmpeg_path'):
                    ffmpeg_path = self.options_manager.get_ffmpeg_path()
                
                cmd = [ffmpeg_path, "-hide_banner", "-f", "decklink", "-list_formats", "1", "-i", device]
                logger.info(f"Detecting formats using command: {' '.join(cmd)}")

                # Configure subprocess to avoid Windows error dialogs
                startupinfo = None
                creationflags = 0
                env = os.environ.copy()
                
                if platform.system() == 'Windows':
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = 0  # SW_HIDE
                    if hasattr(subprocess, 'CREATE_NO_WINDOW'):
                        creationflags = subprocess.CREATE_NO_WINDOW
                    # Add environment variables to suppress FFmpeg dialogs
                    env.update({
                        "FFMPEG_HIDE_BANNER": "1",
                        "AV_LOG_FORCE_NOCOLOR": "1"
                    })
                
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    universal_newlines=True,
                    startupinfo=startupinfo,
                    creationflags=creationflags,
                    env=env
                )

                stdout, stderr = process.communicate(timeout=10)
                output = stdout + stderr

                # Parse the output to extract formats
                formats = []
                formats_map = {}
                
                # Look for the "Supported formats" section
                format_section = re.search(r'Supported formats for \'[^\']+\':(.*?)(?=\n\n|\Z)', output, re.DOTALL)
                if format_section:
                    section_text = format_section.group(1)

                    # Extract format information - match format_code, resolution, and frame rate
                    format_pattern = r'\s+(\w+)\s+([0-9]+x[0-9]+) at ([0-9]+(?:\/[0-9]+)?)'
                    for match in re.finditer(format_pattern, section_text):
                        format_code, resolution, frame_rate_str = match.groups()
                        
                        # Parse frame rate (handle both fractional and decimal)
                        if '/' in frame_rate_str:
                            num, denom = frame_rate_str.split('/')
                            frame_rate = float(num) / float(denom)
                        else:
                            frame_rate = float(frame_rate_str)

                        # Format the rate nicely
                        nice_rate = frame_rate
                        if abs(frame_rate - 23.976) < 0.01:
                            nice_rate = 23.98
                        elif abs(frame_rate - 29.97) < 0.01:
                            nice_rate = 29.97
                        elif abs(frame_rate - 59.94) < 0.01:
                            nice_rate = 59.94

                        # Check if interlaced
                        is_interlaced = "interlaced" in section_text.lower()
                        scan_type = "i" if is_interlaced else "p"

                        # Extract resolution components
                        width, height = map(int, resolution.split('x'))

                        # Create format object
                        format_obj = {
                            'code': format_code,
                            'width': width,
                            'height': height,
                            'resolution': resolution,
                            'fps': nice_rate, 
                            'frame_rate': nice_rate,  # duplicate for compatibility
                            'fps_str': f"{nice_rate:.2f}".rstrip('0').rstrip('.'),
                            'scan_type': scan_type,
                            'is_interlaced': is_interlaced,
                            'display': f"{format_code} - {resolution} @ {nice_rate:.2f}fps ({scan_type})"
                        }
                        formats.append(format_obj)
                        
                        # Add to format map
                        if resolution not in formats_map:
                            formats_map[resolution] = []
                        if nice_rate not in formats_map[resolution]:
                            formats_map[resolution].append(nice_rate)
                
                # Update the UI with detected formats
                self.combo_format_code.clear()

                if formats:
                    # Sort formats by resolution and then by frame rate
                    formats.sort(key=lambda x: (x['height'], x['width'], x['fps']))

                    for fmt in formats:
                        self.combo_format_code.addItem(fmt['display'], fmt)

                    # Select format from settings if available
                    current_format = self.options_manager.get_setting("capture", "format_code")
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
                    
                    # Save the format information to options_manager
                    self._save_detected_formats(formats, formats_map)
                    
                    logger.info(f"Successfully detected {len(formats)} formats")
                else:
                    # Handle no formats detected - add default formats for Intensity Shuttle
                    logger.warning("No formats detected - adding standard formats for Intensity Shuttle")
                    self.lbl_format_status.setText("Adding standard formats for Intensity Shuttle")
                    self.lbl_format_status.setStyleSheet("color: orange;")

                    # Standard formats for Intensity Shuttle
                    manual_formats = [
                        {'code': 'ntsc', 'width': 720, 'height': 486, 'fps': 29.97, 'scan_type': 'i', 
                        'resolution': '720x486', 'fps_str': '29.97',
                        'display': 'ntsc - 720x486 @ 29.97 fps (i)'},
                        {'code': 'nt23', 'width': 720, 'height': 486, 'fps': 23.976, 'scan_type': 'p',
                        'resolution': '720x486', 'fps_str': '23.98',
                        'display': 'nt23 - 720x486 @ 23.98 fps (p)'},
                        {'code': 'pal', 'width': 720, 'height': 576, 'fps': 25, 'scan_type': 'i',
                        'resolution': '720x576', 'fps_str': '25',
                        'display': 'pal - 720x576 @ 25 fps (i)'},
                        {'code': 'Hp29', 'width': 1920, 'height': 1080, 'fps': 29.97, 'scan_type': 'p',
                        'resolution': '1920x1080', 'fps_str': '29.97',
                        'display': 'Hp29 - 1920x1080 @ 29.97 fps (p)'},
                        {'code': 'Hp30', 'width': 1920, 'height': 1080, 'fps': 30, 'scan_type': 'p',
                        'resolution': '1920x1080', 'fps_str': '30',
                        'display': 'Hp30 - 1920x1080 @ 30 fps (p)'},
                        {'code': 'hp59', 'width': 1280, 'height': 720, 'fps': 59.94, 'scan_type': 'p',
                        'resolution': '1280x720', 'fps_str': '59.94',
                        'display': 'hp59 - 1280x720 @ 59.94 fps (p)'}
                    ]

                    # Add to dropdown
                    for fmt in manual_formats:
                        # Add is_interlaced field
                        fmt['is_interlaced'] = (fmt['scan_type'] == 'i')
                        self.combo_format_code.addItem(fmt['display'], fmt)
                        
                        # Add to formats map
                        resolution = fmt['resolution']
                        if resolution not in formats_map:
                            formats_map[resolution] = []
                        if fmt['fps'] not in formats_map[resolution]:
                            formats_map[resolution].append(fmt['fps'])

                    # Select a reasonable default format (1080p at 29.97fps)
                    for i in range(self.combo_format_code.count()):
                        item_data = self.combo_format_code.itemData(i)
                        if item_data and item_data['code'] == 'Hp29':
                            self.combo_format_code.setCurrentIndex(i)
                            break

                    # Save the default format information
                    self._save_detected_formats(manual_formats, formats_map)
                    
                    logger.info("Added standard formats for Intensity Shuttle device.")

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



 
 
 
 
 
 
    def _save_detected_formats(self, formats, format_map):
        """Save detected formats to options_manager for future reference"""
        if not self.options_manager:
            return
            
        try:
            # Save both formats and format_map
            self.options_manager.update_setting("capture", "detected_formats", formats)
            self.options_manager.update_setting("capture", "format_map", format_map)
            
            # Also update available resolutions and frame rates
            resolutions = list(format_map.keys())
            self.options_manager.update_setting("capture", "available_resolutions", resolutions)
            
            # Collect all unique frame rates
            frame_rates = []
            for rates in format_map.values():
                for rate in rates:
                    if rate not in frame_rates:
                        frame_rates.append(rate)
            frame_rates.sort()
            
            self.options_manager.update_setting("capture", "available_frame_rates", frame_rates)
            
            logger.info(f"Saved detected formats to options_manager: {len(formats)} formats")
        except Exception as e:
            logger.error(f"Error saving detected formats: {e}")

 
 
 
 
 
 
 
 
 
 
 
    def save_settings(self):
        """Save current settings to options manager"""
        if not self.options_manager:
            logger.warning("Options manager not available, cannot save settings")
            QMessageBox.critical(self, "Error", "Settings manager not available, cannot save settings.")
            return
            
        try:
            # Save each section of settings
            self.save_general_settings()
            self.save_capture_settings()
            self.save_analysis_settings()
            self.save_advanced_settings()
            self.save_bookend_settings()
            
            QMessageBox.information(self, "Settings Saved", "Settings have been saved successfully.")
            logger.info("All settings saved successfully")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save settings: {e}")
            logger.error(f"Error saving settings: {e}")
            import traceback
            logger.error(traceback.format_exc())
 
 
    
    def save_general_settings(self):
        """Save general tab settings"""
        try:
            # Paths settings
            paths_settings = {
                'reference_video_dir': self.txt_ref_dir.text(),
                'default_output_dir': self.txt_output_dir.text(),
                'models_dir': self.txt_vmaf_dir.text(),
                'ffmpeg_path': self.txt_ffmpeg_path.text(),
            }
            self.options_manager.update_category("paths", paths_settings)
            
            # Encoder settings
            encoder_settings = {
                'default_encoder': self.combo_default_encoder.currentText(),
                'default_crf': self.spin_default_crf.value(),
                'default_preset': self.combo_default_preset.currentText(),
            }
            self.options_manager.update_category("encoder", encoder_settings)
            
            logger.info("General settings saved successfully")
            return True
        except Exception as e:
            logger.error(f"Error saving general settings: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
 
 
 
 
 
 
 
 
 
    def save_capture_settings(self):
        """Save capture-specific settings to options manager"""
        try:
            # Get current format selection data
            format_data = None
            if self.combo_format_code.count() > 0:
                index = self.combo_format_code.currentIndex()
                format_data = self.combo_format_code.itemData(index)

            # Extract pixel format from the combo box text (handles formats like "uyvy422 - Packed YUV 4:2:2")
            pixel_format = self.combo_pixel_format.currentText().split(' ')[0]

            # Build capture settings dictionary with safe defaults
            capture_settings = {
                "default_device": self.combo_capture_device.currentText(),
                "pixel_format": pixel_format,
                "video_input": self.combo_video_input.currentText(),
                "audio_input": self.combo_audio_input.currentText(),
                "encoder": self.combo_capture_encoder.currentText(),
                "crf": self.spin_capture_crf.value(),
                "preset": self.combo_capture_preset.currentText(),
                "disable_audio": self.chk_disable_audio.isChecked(),
                "low_latency": self.chk_low_latency.isChecked(),
                "force_format": self.chk_force_format.isChecked(),
                
                # Add these essential fields with defaults if not available
                "resolution": "1920x1080",
                "frame_rate": 29.97,
                "format_code": ""
            }

            # Add format details if available
            if format_data and isinstance(format_data, dict):
                # Check each key exists before adding it
                if 'code' in format_data:
                    capture_settings["format_code"] = format_data['code']
                elif 'id' in format_data:
                    # Use id as fallback if code isn't available
                    capture_settings["format_code"] = format_data['id']
                    
                # Add other format details with safe fallbacks
                resolution = format_data.get('resolution', None)
                if resolution:
                    capture_settings["resolution"] = resolution
                    
                    # Try to extract width and height if not directly available
                    if 'width' not in format_data or 'height' not in format_data:
                        try:
                            width, height = map(int, resolution.split('x'))
                            capture_settings["width"] = width
                            capture_settings["height"] = height
                        except Exception:
                            # Use default HD resolution if parsing fails
                            capture_settings["width"] = 1920
                            capture_settings["height"] = 1080
                    else:
                        capture_settings["width"] = format_data.get('width', 1920)
                        capture_settings["height"] = format_data.get('height', 1080)
                
                # Add frame rate with fallbacks
                if 'frame_rate' in format_data:
                    capture_settings["frame_rate"] = format_data['frame_rate']
                elif 'fps' in format_data:
                    capture_settings["frame_rate"] = format_data['fps']
                    
                # Add scan type with fallback
                if 'scan_type' in format_data:
                    capture_settings["scan_type"] = format_data['scan_type']
                    capture_settings["is_interlaced"] = (format_data['scan_type'] == 'i')
                else:
                    capture_settings["scan_type"] = 'p'  # Default to progressive
                    capture_settings["is_interlaced"] = False

            # Update capture settings
            self.options_manager.update_category("capture", capture_settings)
            logger.info("Capture settings saved successfully")
            return True
        except Exception as e:
            logger.error(f"Error saving capture settings: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    
    
 
 
 
    
    def save_analysis_settings(self):
        """Save analysis tab settings"""
        try:
            # Analysis general settings
            analysis_settings = {
                'use_temp_files': self.check_use_temp_files.isChecked(),
                'auto_alignment': self.check_auto_alignment.isChecked(),
                'alignment_method': self.combo_alignment_method.currentText(),
            }
            self.options_manager.update_category("analysis", analysis_settings)
            
            # VMAF specific settings
            vmaf_settings = {
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
            }
            self.options_manager.update_category("vmaf", vmaf_settings)
            
            logger.info("Analysis settings saved successfully")
            return True
        except Exception as e:
            logger.error(f"Error saving analysis settings: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def save_advanced_settings(self):
        """Save advanced tab settings"""
        try:
            # Debug settings
            debug_settings = {
                'log_level': self.combo_log_level.currentText(),
                'save_logs': self.check_save_logs.isChecked(),
                'show_commands': self.check_show_commands.isChecked()
            }
            self.options_manager.update_category("debug", debug_settings)
            
            logger.info("Advanced settings saved successfully")
            return True
        except Exception as e:
            logger.error(f"Error saving advanced settings: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def save_bookend_settings(self):
        """Save bookend-specific settings to options manager"""
        try:
            # Build bookend settings dictionary
            bookend_settings = {
                "min_loops": self.spin_min_loops.value(),
                "max_loops": self.spin_max_loops.value(),
                "min_capture_time": self.spin_min_capture_time.value(),
                "max_capture_time": self.spin_max_capture_time.value(),
                "bookend_duration": self.spin_bookend_duration.value(),
                "white_threshold": self.spin_white_threshold.value(),
                "frame_sampling_rate": self.spin_frame_sampling.value(),
                "frame_offset": self.spin_frame_offset.value(),
                "adaptive_brightness": self.check_adaptive_brightness.isChecked(),
                "motion_compensation": self.check_motion_compensation.isChecked(),
                "fallback_to_full_video": self.check_fallback_full_video.isChecked()
            }

            # Update bookend settings
            self.options_manager.update_category("bookend", bookend_settings)
            logger.info("Bookend settings saved successfully")
            return True
        except Exception as e:
            logger.error(f"Error saving bookend settings: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
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
            if self.options_manager:
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
                self.options_manager.update_setting("capture", "default_device", capture_settings["default_device"])
                self.options_manager.update_setting("capture", "format_code", capture_settings["format_code"])
                self.options_manager.update_setting("capture", "resolution", capture_settings["resolution"])
                self.options_manager.update_setting("capture", "width", capture_settings["width"])
                self.options_manager.update_setting("capture", "height", capture_settings["height"])
                self.options_manager.update_setting("capture", "frame_rate", capture_settings["frame_rate"])
                self.options_manager.update_setting("capture", "scan_type", capture_settings["scan_type"])
                self.options_manager.update_setting("capture", "is_interlaced", capture_settings["is_interlaced"])





    def _update_format_details(self):
        """Update the format details label based on the selected format"""
        if self.combo_format_code.count() == 0:
            return

        # Get the selected format data
        index = self.combo_format_code.currentIndex()
        format_data = self.combo_format_code.itemData(index)

        if format_data:
            # Format the details string
            scan_type = "Interlaced" if format_data.get('scan_type') == 'i' else "Progressive"
            details = (f"Resolution: {format_data.get('resolution')}  |  "
                    f"Frame Rate: {format_data.get('fps_str', format_data.get('fps'))} fps  |  "
                    f"Scan: {scan_type}")
            self.lbl_format_details.setText(details)

            # If we have options manager, update capture settings
            if self.options_manager:
                # Store the complete format data in a way that can be used by the capture module
                capture_settings = {
                    "default_device": self.combo_capture_device.currentText(),
                    "format_code": format_data.get('code', ''),
                    "resolution": format_data.get('resolution', '1920x1080'),
                    "width": format_data.get('width', 1920),
                    "height": format_data.get('height', 1080),
                    "frame_rate": format_data.get('fps', 29.97),
                    "scan_type": format_data.get('scan_type', 'p'),
                    "is_interlaced": (format_data.get('scan_type', 'p') == 'i')
                }

                # Update only these specific capture settings (don't overwrite others)
                self.options_manager.update_setting("capture", "default_device", capture_settings["default_device"])
                self.options_manager.update_setting("capture", "format_code", capture_settings["format_code"])
                self.options_manager.update_setting("capture", "resolution", capture_settings["resolution"])
                self.options_manager.update_setting("capture", "width", capture_settings["width"])
                self.options_manager.update_setting("capture", "height", capture_settings["height"])
                self.options_manager.update_setting("capture", "frame_rate", capture_settings["frame_rate"])
                self.options_manager.update_setting("capture", "scan_type", capture_settings["scan_type"])
                self.options_manager.update_setting("capture", "is_interlaced", capture_settings["is_interlaced"])










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

    def reset_settings(self):
        """Reset settings to defaults"""
        confirm = QMessageBox.question(
            self, 
            "Reset Settings", 
            "Are you sure you want to reset all settings to defaults?",
            QMessageBox.Yes | QMessageBox.No
        )

        if confirm == QMessageBox.Yes and self.options_manager:
            self.options_manager.reset_to_defaults()
            self.load_settings()
            QMessageBox.information(self, "Settings Reset", "Settings have been reset to defaults.")
            logger.info("Settings reset to defaults")





    def load_settings(self):
        """Load settings from options manager and populate UI elements"""
        try:
            if not self.options_manager:
                logger.warning("Options manager not available, cannot load settings")
                return

            # Get all settings
            settings = self.options_manager.get_settings()

            # Load tab-specific settings
            self._load_general_settings(settings)
            self.load_capture_settings()
            self._load_analysis_settings(settings)
            self._load_advanced_settings(settings)
            self._load_bookend_settings(settings)

            logger.info("Settings loaded successfully")
        except Exception as e:
            logger.error(f"Error loading settings: {e}")
            import traceback
            logger.error(traceback.format_exc())
















    def _load_general_settings(self, settings):
        """Load settings for the general tab"""
        try:
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
            self.combo_default_preset.setCurrentText(encoder.get('default_preset', 'medium'))
        except Exception as e:
            logger.error(f"Error loading general settings: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def _load_analysis_settings(self, settings):
        """Load settings for the analysis tab"""
        try:
            # Populate analysis settings
            vmaf = settings.get('vmaf', {})
            analysis = settings.get('analysis', {})
            
            self.check_use_temp_files.setChecked(analysis.get('use_temp_files', True))
            self.check_save_json.setChecked(vmaf.get('save_json', True))
            self.check_save_plots.setChecked(vmaf.get('save_plots', True))
            self.check_auto_alignment.setChecked(analysis.get('auto_alignment', True))
            self.combo_alignment_method.setCurrentText(analysis.get('alignment_method', 'Bookend Detection'))

            # Load tester information
            self.txt_tester_name.setText(vmaf.get('tester_name', ''))
            self.txt_test_location.setText(vmaf.get('test_location', ''))

            # Load thread count
            self.spin_vmaf_threads.setValue(vmaf.get('threads', 4))

            # Populate VMAF models and set default
            self._populate_vmaf_models()
            default_model = vmaf.get('default_model', 'vmaf_v0.6.1')
            index = self.combo_default_vmaf_model.findText(default_model)
            if index >= 0:
                self.combo_default_vmaf_model.setCurrentIndex(index)

            # Load advanced VMAF settings
            self.combo_pool_method.setCurrentText(vmaf.get('pool_method', 'mean'))
            self.spin_feature_subsample.setValue(vmaf.get('feature_subsample', 1))
            self.check_motion_score.setChecked(vmaf.get('enable_motion_score', False))
            self.check_temporal_features.setChecked(vmaf.get('enable_temporal_features', False))
            self.check_psnr_enabled.setChecked(vmaf.get('psnr_enabled', True))
            self.check_ssim_enabled.setChecked(vmaf.get('ssim_enabled', True))
            
        except Exception as e:
            logger.error(f"Error loading analysis settings: {e}")
            import traceback
            logger.error(traceback.format_exc())

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
            import traceback
            logger.error(traceback.format_exc())

    def _load_bookend_settings(self, settings):
        """Load bookend settings from options manager"""
        try:
            # Get bookend settings
            bookend = settings.get('bookend', {})
            
            # Load basic settings
            self.spin_min_loops.setValue(bookend.get('min_loops', 3))
            self.spin_max_loops.setValue(bookend.get('max_loops', 10))
            self.spin_min_capture_time.setValue(bookend.get('min_capture_time', 5))
            self.spin_max_capture_time.setValue(bookend.get('max_capture_time', 30))
            self.spin_bookend_duration.setValue(bookend.get('bookend_duration', 0.2))
            self.spin_white_threshold.setValue(bookend.get('white_threshold', 200))
            self.slider_white_threshold.setValue(bookend.get('white_threshold', 200))
            self.spin_frame_sampling.setValue(bookend.get('frame_sampling_rate', 5))
            self.spin_frame_offset.setValue(bookend.get('frame_offset', 3))
            
            # Load boolean settings
            self.check_adaptive_brightness.setChecked(bookend.get('adaptive_brightness', True))
            self.check_motion_compensation.setChecked(bookend.get('motion_compensation', False))
            self.check_fallback_full_video.setChecked(bookend.get('fallback_to_full_video', True))
            
            logger.info("Bookend settings loaded successfully")
        except Exception as e:
            logger.error(f"Error loading bookend settings: {e}")
            import traceback
            logger.error(traceback.format_exc())










    def load_capture_settings(self):
        """Load capture-specific settings from options manager"""
        if not self.options_manager:
            logger.warning("Options manager not available, cannot load capture settings")
            return

        try:
            # Get capture settings
            capture_settings = self.options_manager.get_setting("capture")

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

            # Try to detect formats automatically if empty
            if self.combo_format_code.count() == 0:
                logger.info("No formats loaded, attempting to detect formats")
                self.detect_device_formats()
            
            # If we have formats and a format_code, select it
            if 'format_code' in capture_settings and self.combo_format_code.count() > 0:
                format_code = capture_settings['format_code']
                # Try to select the format from settings
                for i in range(self.combo_format_code.count()):
                    item_data = self.combo_format_code.itemData(i)
                    if item_data and item_data.get('code') == format_code:
                        self.combo_format_code.setCurrentIndex(i)
                        break

            logger.info("Capture settings loaded successfully")
        except Exception as e:
            logger.error(f"Error loading capture settings: {e}")
            import traceback
            logger.error(traceback.format_exc())


