
import logging
import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
    QLabel, QPushButton, QComboBox, QCheckBox,
    QSpinBox, QDoubleSpinBox, QTabWidget, QLineEdit,
    QFormLayout, QFileDialog, QMessageBox
)
from PyQt5.QtCore import Qt, pyqtSignal

logger = logging.getLogger(__name__)

class OptionsTab(QWidget):
    """Options tab for configuring application settings"""
    
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self._setup_ui()
        
    def _setup_ui(self):
        """Set up the Options tab UI"""
        layout = QVBoxLayout(self)

        # Create tabbed interface for different settings categories
        options_tabs = QTabWidget()
        
        # General settings tab
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
        
        # Theme settings
        theme_group = QGroupBox("Theme")
        theme_layout = QHBoxLayout()
        theme_layout.addWidget(QLabel("Application Theme:"))
        self.combo_theme = QComboBox()
        self.combo_theme.addItems(["System", "Light", "Dark", "Blue", "High Contrast"])
        self.combo_theme.currentTextChanged.connect(self.theme_changed)
        theme_layout.addWidget(self.combo_theme)
        theme_group.setLayout(theme_layout)
        general_layout.addWidget(theme_group)
        
        # Capture tab settings
        capture_tab = QWidget()
        capture_layout = QVBoxLayout(capture_tab)
        
        # Capture device group
        device_group = QGroupBox("Capture Device Settings")
        device_layout = QVBoxLayout()
        
        # Auto-detect formats button
        auto_detect_layout = QHBoxLayout()
        self.combo_device_for_formats = QComboBox()
        auto_detect_layout.addWidget(QLabel("Device:"))
        auto_detect_layout.addWidget(self.combo_device_for_formats)
        self.btn_auto_detect_formats = QPushButton("Auto-Detect Formats")
        self.btn_auto_detect_formats.clicked.connect(self.auto_detect_formats)
        auto_detect_layout.addWidget(self.btn_auto_detect_formats)
        device_layout.addLayout(auto_detect_layout)
        
        # Populate device list after creating the combo box
        self._populate_device_list()
        
        # Format settings
        format_settings = QFormLayout()
        
        self.combo_capture_api = QComboBox()
        self.combo_capture_api.addItems(["dshow", "decklink", "v4l2"])
        format_settings.addRow("Capture API:", self.combo_capture_api)
        
        self.combo_pixel_format = QComboBox()
        self.combo_pixel_format.addItems(["uyvy422", "yuyv422", "rgb24", "bgr24"])
        format_settings.addRow("Pixel Format:", self.combo_pixel_format)
        
        self.combo_default_resolution = QComboBox()
        self.combo_default_resolution.addItems([
            "1920x1080", "1280x720", "720x576", "720x486", "3840x2160"
        ])
        format_settings.addRow("Default Resolution:", self.combo_default_resolution)
        
        self.combo_default_fps = QComboBox()
        self.combo_default_fps.addItems([
            "23.976", "24", "25", "29.97", "30", "50", "59.94", "60"
        ])
        format_settings.addRow("Default Frame Rate:", self.combo_default_fps)
        
        device_layout.addLayout(format_settings)
        device_group.setLayout(device_layout)
        capture_layout.addWidget(device_group)
        
        # Bookend settings group
        bookend_group = QGroupBox("Bookend Detection Settings")
        bookend_layout = QFormLayout()
        
        self.spin_bookend_duration = QDoubleSpinBox()
        self.spin_bookend_duration.setRange(0.1, 5.0)
        self.spin_bookend_duration.setValue(0.5)
        self.spin_bookend_duration.setDecimals(2)
        bookend_layout.addRow("Bookend Duration (seconds):", self.spin_bookend_duration)
        
        self.spin_min_loops = QSpinBox()
        self.spin_min_loops.setRange(1, 10)
        self.spin_min_loops.setValue(3)
        bookend_layout.addRow("Minimum Loops:", self.spin_min_loops)
        
        self.spin_max_loops = QSpinBox()
        self.spin_max_loops.setRange(2, 20)
        self.spin_max_loops.setValue(5)
        bookend_layout.addRow("Maximum Loops:", self.spin_max_loops)
        
        self.spin_bookend_threshold = QSpinBox()
        self.spin_bookend_threshold.setRange(100, 255)
        self.spin_bookend_threshold.setValue(230)
        bookend_layout.addRow("Brightness Threshold:", self.spin_bookend_threshold)
        
        bookend_group.setLayout(bookend_layout)
        capture_layout.addWidget(bookend_group)
        
        # Analysis tab settings
        analysis_tab = QWidget()
        analysis_layout = QVBoxLayout(analysis_tab)
        
        # VMAF analysis settings
        vmaf_group = QGroupBox("VMAF Analysis Settings")
        vmaf_layout = QFormLayout()
        
        self.check_use_temp_files = QCheckBox()
        self.check_use_temp_files.setChecked(True)
        vmaf_layout.addRow("Use Temporary Files:", self.check_use_temp_files)
        
        self.check_save_json = QCheckBox()
        self.check_save_json.setChecked(True)
        vmaf_layout.addRow("Save JSON Results:", self.check_save_json)
        
        self.check_save_plots = QCheckBox()
        self.check_save_plots.setChecked(True)
        vmaf_layout.addRow("Generate Plots:", self.check_save_plots)
        
        self.check_auto_alignment = QCheckBox()
        self.check_auto_alignment.setChecked(True)
        vmaf_layout.addRow("Auto-Align Videos:", self.check_auto_alignment)
        
        self.combo_alignment_method = QComboBox()
        self.combo_alignment_method.addItems(["SSIM", "Bookend Detection", "Combined"])
        vmaf_layout.addRow("Alignment Method:", self.combo_alignment_method)
        
        # Add default VMAF model selection
        self.combo_default_vmaf_model = QComboBox()
        self._populate_vmaf_models()
        vmaf_layout.addRow("Default VMAF Model:", self.combo_default_vmaf_model)
        
        vmaf_group.setLayout(vmaf_layout)
        analysis_layout.addWidget(vmaf_group)
        
        # Advanced tab
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
        
        # Theme and Branding tab
        theme_tab = QWidget()
        theme_layout = QVBoxLayout(theme_tab)
        
        # UI Theme settings
        ui_theme_group = QGroupBox("UI Theme")
        ui_theme_layout = QFormLayout()
        
        self.combo_theme_selection = QComboBox()
        self.combo_theme_selection.addItems(["System", "Light", "Dark", "Custom"])
        ui_theme_layout.addRow("Theme:", self.combo_theme_selection)
        
        # Custom theme colors
        self.color_bg = QLineEdit("#2D2D30")
        ui_theme_layout.addRow("Background Color:", self.color_bg)
        self.btn_pick_bg = QPushButton("...")
        self.btn_pick_bg.setMaximumWidth(30)
        self.btn_pick_bg.clicked.connect(lambda: self.pick_color(self.color_bg))
        ui_theme_layout.addWidget(self.btn_pick_bg)
        
        self.color_text = QLineEdit("#FFFFFF")
        ui_theme_layout.addRow("Text Color:", self.color_text)
        self.btn_pick_text = QPushButton("...")
        self.btn_pick_text.setMaximumWidth(30)
        self.btn_pick_text.clicked.connect(lambda: self.pick_color(self.color_text))
        ui_theme_layout.addWidget(self.btn_pick_text)
        
        self.color_accent = QLineEdit("#007ACC")
        ui_theme_layout.addRow("Accent Color:", self.color_accent)
        self.btn_pick_accent = QPushButton("...")
        self.btn_pick_accent.setMaximumWidth(30)
        self.btn_pick_accent.clicked.connect(lambda: self.pick_color(self.color_accent))
        ui_theme_layout.addWidget(self.btn_pick_accent)
        
        ui_theme_group.setLayout(ui_theme_layout)
        theme_layout.addWidget(ui_theme_group)
        
        # White-label branding settings
        branding_group = QGroupBox("White-Label Branding")
        branding_layout = QFormLayout()
        
        self.check_enable_white_label = QCheckBox()
        branding_layout.addRow("Enable White-Label:", self.check_enable_white_label)
        
        self.txt_app_name = QLineEdit("VMAF Test App")
        branding_layout.addRow("Application Name:", self.txt_app_name)
        
        self.txt_company_name = QLineEdit("Chroma")
        branding_layout.addRow("Company Name:", self.txt_company_name)
        
        self.txt_footer_text = QLineEdit("© 2025 Chroma")
        branding_layout.addRow("Footer Text:", self.txt_footer_text)
        
        self.color_primary = QLineEdit("#4CAF50")
        branding_layout.addRow("Primary Brand Color:", self.color_primary)
        self.btn_pick_primary = QPushButton("...")
        self.btn_pick_primary.setMaximumWidth(30)
        self.btn_pick_primary.clicked.connect(lambda: self.pick_color(self.color_primary))
        branding_layout.addWidget(self.btn_pick_primary)
        
        # Logo selection
        logo_layout = QHBoxLayout()
        logo_layout.addWidget(QLabel("Logo:"))
        self.txt_logo_path = QLineEdit()
        self.txt_logo_path.setReadOnly(True)
        logo_layout.addWidget(self.txt_logo_path)
        self.btn_browse_logo = QPushButton("Browse...")
        self.btn_browse_logo.clicked.connect(self.browse_logo)
        logo_layout.addWidget(self.btn_browse_logo)
        branding_layout.addRow(logo_layout)
        
        branding_group.setLayout(branding_layout)
        theme_layout.addWidget(branding_group)
        
        # Add tabs to options tabwidget
        options_tabs.addTab(general_tab, "General")
        options_tabs.addTab(capture_tab, "Capture")
        options_tabs.addTab(analysis_tab, "Analysis")
        options_tabs.addTab(theme_tab, "Theme & Branding")
        options_tabs.addTab(advanced_tab, "Advanced")
        
        layout.addWidget(options_tabs)
        
        # Save/Reset buttons
        button_layout = QHBoxLayout()
        self.btn_save_settings = QPushButton("Save Settings")
        self.btn_save_settings.clicked.connect(self.save_settings)
        self.btn_reset_settings = QPushButton("Reset to Defaults")
        self.btn_reset_settings.clicked.connect(self.reset_settings)
        button_layout.addStretch()
        button_layout.addWidget(self.btn_reset_settings)
        button_layout.addWidget(self.btn_save_settings)
        layout.addLayout(button_layout)
        
        # Load current settings
        self.load_settings()
    
    def load_settings(self):
        """Load current settings from options manager"""
        if hasattr(self.parent, 'options_manager') and self.parent.options_manager:
            try:
                settings = self.parent.options_manager.get_settings()
                
                # Populate directories
                paths = settings.get('paths', {})
                self.txt_ref_dir.setText(paths.get('reference_video_dir', ''))
                self.txt_output_dir.setText(paths.get('default_output_dir', ''))
                self.txt_vmaf_dir.setText(paths.get('models_dir', ''))
                self.txt_ffmpeg_path.setText(paths.get('ffmpeg_path', ''))
                
                # Populate capture settings
                capture = settings.get('capture', {})
                self.combo_capture_api.setCurrentText(capture.get('capture_api', 'dshow'))
                self.combo_pixel_format.setCurrentText(capture.get('pixel_format', 'uyvy422'))
                self.combo_default_resolution.setCurrentText(capture.get('resolution', '1920x1080'))
                self.combo_default_fps.setCurrentText(str(capture.get('frame_rate', '29.97')))
                
                # Populate bookend settings
                bookend = settings.get('bookend', {})
                self.spin_bookend_duration.setValue(float(bookend.get('bookend_duration', 0.5)))
                self.spin_min_loops.setValue(int(bookend.get('min_loops', 3)))
                self.spin_max_loops.setValue(int(bookend.get('max_loops', 5)))
                self.spin_bookend_threshold.setValue(int(bookend.get('white_threshold', 230)))
                
                # Populate encoder settings
                encoder = settings.get('encoder', {})
                self.combo_default_encoder.setCurrentText(encoder.get('default_encoder', 'libx264'))
                self.spin_default_crf.setValue(int(encoder.get('default_crf', 23)))
                self.spin_default_preset.setCurrentText(encoder.get('default_preset', 'medium'))
                
                # Populate analysis settings
                vmaf = settings.get('vmaf', {})
                self.check_use_temp_files.setChecked(settings.get('use_temp_files', True))
                self.check_save_json.setChecked(vmaf.get('save_json', True))
                self.check_save_plots.setChecked(vmaf.get('save_plots', True))
                self.check_auto_alignment.setChecked(settings.get('auto_alignment', True))
                self.combo_alignment_method.setCurrentText(settings.get('alignment_method', 'Bookend Detection'))
                
                # Populate VMAF models and set default
                self._populate_vmaf_models()
                default_model = vmaf.get('default_model', 'vmaf_v0.6.1')
                index = self.combo_default_vmaf_model.findText(default_model)
                if index >= 0:
                    self.combo_default_vmaf_model.setCurrentIndex(index)
                
                # Populate debug settings
                debug = settings.get('debug', {})
                self.combo_log_level.setCurrentText(debug.get('log_level', 'INFO'))
                self.check_save_logs.setChecked(debug.get('save_logs', True))
                self.check_show_commands.setChecked(debug.get('show_commands', True))
                
                # Populate theme settings
                theme = settings.get('theme', {})
                if isinstance(theme, dict):
                    self.combo_theme.setCurrentText(theme.get('selected_theme', 'System'))
                    
                    # Load custom theme settings if they exist
                    if hasattr(self, 'combo_theme_selection'):
                        self.combo_theme_selection.setCurrentText(theme.get('selected_theme', 'System'))
                        self.color_bg.setText(theme.get('bg_color', '#2D2D30'))
                        self.color_text.setText(theme.get('text_color', '#FFFFFF'))
                        self.color_accent.setText(theme.get('accent_color', '#007ACC'))
                        self.txt_logo_path.setText(theme.get('logo_path', ''))
                else:
                    # If theme is a string (legacy format)
                    self.combo_theme.setCurrentText(theme if theme else 'System')
                    if hasattr(self, 'combo_theme_selection'):
                        self.combo_theme_selection.setCurrentText(theme if theme else 'System')
                
                # Populate branding settings
                branding = settings.get('branding', {})
                if hasattr(self, 'check_enable_white_label'):
                    self.check_enable_white_label.setChecked(branding.get('enable_white_label', False))
                    self.txt_app_name.setText(branding.get('app_name', 'VMAF Test App'))
                    self.txt_company_name.setText(branding.get('company_name', 'Chroma'))
                    self.txt_footer_text.setText(branding.get('footer_text', '© 2025 Chroma'))
                    self.color_primary.setText(branding.get('primary_color', '#4CAF50'))
                
                # Populate device dropdown
                if hasattr(self, 'combo_device_for_formats'):
                    devices = self.parent.options_manager.get_decklink_devices()
                    self.combo_device_for_formats.clear()
                    for device in devices:
                        self.combo_device_for_formats.addItem(device)
                
                logger.info("Settings loaded successfully")
            except Exception as e:
                logger.error(f"Error loading settings: {e}")
                # Print traceback for debugging
                import traceback
                logger.error(traceback.format_exc())
    
    def save_settings(self):
        """Save current settings to options manager"""
        if hasattr(self.parent, 'options_manager') and self.parent.options_manager:
            try:
                # Create settings in a structured format
                settings = {
                    # Paths
                    'paths': {
                        'reference_video_dir': self.txt_ref_dir.text(),
                        'default_output_dir': self.txt_output_dir.text(),
                        'models_dir': self.txt_vmaf_dir.text(),
                        'ffmpeg_path': self.txt_ffmpeg_path.text(),
                    },
                    
                    # Capture settings
                    'capture': {
                        'capture_api': self.combo_capture_api.currentText(),
                        'pixel_format': self.combo_pixel_format.currentText(),
                        'resolution': self.combo_default_resolution.currentText(),
                        'frame_rate': self.combo_default_fps.currentText(),
                    },
                    
                    # Bookend settings
                    'bookend': {
                        'bookend_duration': self.spin_bookend_duration.value(),
                        'min_loops': self.spin_min_loops.value(),
                        'max_loops': self.spin_max_loops.value(),
                        'white_threshold': self.spin_bookend_threshold.value(),
                    },
                    
                    # Encoder settings
                    'encoder': {
                        'default_encoder': self.combo_default_encoder.currentText(),
                        'default_crf': self.spin_default_crf.value(),
                        'default_preset': self.spin_default_preset.currentText(),
                    },
                    
                    # Analysis settings
                    'vmaf': {
                        'default_model': self.combo_default_vmaf_model.currentText(),
                        'save_json': self.check_save_json.isChecked(),
                        'save_plots': self.check_save_plots.isChecked(),
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
                
                # Add theme settings if they exist
                if hasattr(self, 'combo_theme_selection'):
                    settings['theme'] = {
                        'selected_theme': self.combo_theme_selection.currentText(),
                        'bg_color': self.color_bg.text(),
                        'text_color': self.color_text.text(),
                        'accent_color': self.color_accent.text(),
                        'logo_path': self.txt_logo_path.text()
                    }
                else:
                    settings['theme'] = {
                        'selected_theme': self.combo_theme.currentText()
                    }
                
                # Add branding settings if they exist
                if hasattr(self, 'check_enable_white_label'):
                    settings['branding'] = {
                        'enable_white_label': self.check_enable_white_label.isChecked(),
                        'app_name': self.txt_app_name.text(),
                        'company_name': self.txt_company_name.text(),
                        'footer_text': self.txt_footer_text.text(),
                        'primary_color': self.color_primary.text()
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
    
    def _populate_vmaf_models(self):
        """Populate VMAF models dropdown in options tab"""
        try:
            # Clear existing items
            self.combo_default_vmaf_model.clear()
            
            # Find models directory
            root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            models_dir = os.path.join(root_dir, "models")
            
            # Use custom directory if specified
            custom_dir = self.txt_vmaf_dir.text()
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
    
    def theme_changed(self, theme_name):
        """Handle theme selection change"""
        if hasattr(self.parent, 'theme_manager'):
            self.parent.theme_manager.set_theme(theme_name)
            
    def pick_color(self, text_field):
        """Open a color picker dialog and set the selected color"""
        try:
            from PyQt5.QtWidgets import QColorDialog
            from PyQt5.QtGui import QColor
            
            current_color = text_field.text()
            color = QColorDialog.getColor(QColor(current_color), self, "Select Color")
            
            if color.isValid():
                text_field.setText(color.name())
        except Exception as e:
            logger.error(f"Error picking color: {e}")
            
    def browse_logo(self):
        """Browse for logo file"""
        file_filter = "Images (*.png *.jpg *.jpeg *.gif *.bmp);;All Files (*.*)"
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Logo Image",
            self.txt_logo_path.text() or os.path.expanduser("~"),
            file_filter
        )
        
        if file_path:
            self.txt_logo_path.setText(file_path)
    
    def _populate_device_list(self):
        """Populate the device dropdown with available devices"""
        if not hasattr(self, 'combo_device_for_formats'):
            logger.warning("Device formats combo box not initialized yet")
            return
            
        if hasattr(self.parent, 'options_manager') and self.parent.options_manager:
            try:
                devices = self.parent.options_manager.get_decklink_devices()
                self.combo_device_for_formats.clear()
                for device in devices:
                    self.combo_device_for_formats.addItem(device)
                logger.info(f"Populated device dropdown with {len(devices)} devices")
            except Exception as e:
                logger.error(f"Error populating device list: {e}")
    
    def auto_detect_formats(self):
        """Auto-detect formats for the selected device"""
        device = self.combo_device_for_formats.currentText()
        if not device:
            QMessageBox.warning(self, "Warning", "Please select a device first.")
            return
        
        try:
            if hasattr(self.parent, 'options_manager'):
                # Show a message box indicating detection is in progress
                QMessageBox.information(self, "Auto-Detect", 
                                       "Detecting formats for the selected device.\nThis may take a few moments.")
                
                # Get formats for the device
                formats = self.parent.options_manager.get_device_formats(device)
                
                if formats:
                    # Get unique resolutions and frame rates
                    resolutions = set()
                    frame_rates = set()
                    pixel_formats = set()
                    
                    for fmt in formats:
                        if 'resolution' in fmt:
                            resolutions.add(fmt['resolution'])
                        if 'fps' in fmt:
                            frame_rates.add(fmt['fps'])
                        if 'pixel_format' in fmt:
                            pixel_formats.add(fmt['pixel_format'])
                    
                    # Update the resolution dropdown with detailed information
                    self.combo_default_resolution.clear()
                    for res in sorted(resolutions, key=lambda x: int(x.split('x')[0]) if 'x' in x else 0, reverse=True):
                        display_text = res
                        # Look for formats with this resolution to get more details
                        details = []
                        for fmt in formats:
                            if fmt.get('resolution') == res:
                                # Add details like color format, frame rate if available
                                if 'pixel_format' in fmt:
                                    if fmt['pixel_format'] not in details:
                                        details.append(fmt['pixel_format'])
                        
                        # Add details to display text if available
                        if details:
                            display_text = f"{res} ({', '.join(details)})"
                            
                        self.combo_default_resolution.addItem(display_text, res)
                    
                    # Update the frame rate dropdown with more details
                    self.combo_default_fps.clear()
                    for fps in sorted(frame_rates, key=float):
                        display_text = str(fps)
                        
                        # Check for common frame rates and add standard names
                        if abs(float(fps) - 23.98) < 0.01:
                            display_text = f"{fps} (23.98 - Film)"
                        elif abs(float(fps) - 24.0) < 0.01:
                            display_text = f"{fps} (24p - Cinema)"
                        elif abs(float(fps) - 25.0) < 0.01:
                            display_text = f"{fps} (25p - PAL)"
                        elif abs(float(fps) - 29.97) < 0.01:
                            display_text = f"{fps} (29.97 - NTSC)"
                        elif abs(float(fps) - 30.0) < 0.01:
                            display_text = f"{fps} (30p)"
                        elif abs(float(fps) - 50.0) < 0.01:
                            display_text = f"{fps} (50p - PAL HD)"
                        elif abs(float(fps) - 59.94) < 0.01:
                            display_text = f"{fps} (59.94 - NTSC HD)"
                        elif abs(float(fps) - 60.0) < 0.01:
                            display_text = f"{fps} (60p)"
                            
                        self.combo_default_fps.addItem(display_text, str(fps))
                    
                    # Update the pixel format dropdown
                    self.combo_pixel_format.clear()
                    for pix_fmt in sorted(pixel_formats):
                        self.combo_pixel_format.addItem(pix_fmt)
                    
                    QMessageBox.information(
                        self, 
                        "Auto-Detect Complete", 
                        f"Found {len(formats)} formats with {len(resolutions)} resolutions and {len(frame_rates)} frame rates."
                    )
                else:
                    QMessageBox.warning(
                        self,
                        "No Formats Found",
                        "No formats were detected for the selected device."
                    )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error detecting formats: {e}")
            logger.error(f"Error auto-detecting formats: {e}")
