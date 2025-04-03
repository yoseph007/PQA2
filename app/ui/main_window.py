import os
import logging
import sys
import platform
from datetime import datetime
from PyQt5.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QSplitter
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap

# Import UI components
from .tabs.setup_tab import SetupTab
from .tabs.capture_tab import CaptureTab
from .tabs.analysis_tab import AnalysisTab
from .tabs.results_tab import ResultsTab
from .tabs.options_tab import OptionsTab
from .theme_manager import ThemeManager

logger = logging.getLogger(__name__)

class MainWindow(QMainWindow):
    """Main application window for VMAF Test App"""
    def __init__(self, capture_manager, file_manager, options_manager):
        super().__init__()

        # Store manager references
        self.capture_mgr = capture_manager
        self.file_mgr = file_manager
        self.options_manager = options_manager
        self.theme_manager = ThemeManager(self, options_manager)

        # Flag to handle headless mode
        self.headless_mode = False

        # Set up UI
        self._setup_ui()
        self._connect_signals()

        # State variables
        self.reference_info = None
        self.capture_path = None
        self.aligned_paths = None
        self.vmaf_results = None
        self.vmaf_running = False

        logger.info("VMAF Test App initialized")

    def _setup_ui(self):
        """Set up the application UI"""
        self.setWindowTitle("VMAF Test App")
        self.setGeometry(100, 100, 1200, 800)
        self.setFixedSize(1200, 800)  # Set fixed size to prevent resizing

        # Set application icon/logo
        self._set_application_logo()

        # Central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Create tabs
        self.tabs = QTabWidget()

        # Create tab widgets
        self.setup_tab = SetupTab(self)
        self.capture_tab = CaptureTab(self)
        self.analysis_tab = AnalysisTab(self)
        self.results_tab = ResultsTab(self)
        self.options_tab = OptionsTab(self)

        self.tabs.addTab(self.setup_tab, "Setup")
        self.tabs.addTab(self.capture_tab, "Capture")
        self.tabs.addTab(self.analysis_tab, "Analysis")
        self.tabs.addTab(self.results_tab, "Results")
        self.tabs.addTab(self.options_tab, "Options")

        # Add tabs to main layout
        main_layout.addWidget(self.tabs)

        # Status bar
        self.statusBar().showMessage("Ready")

        # Apply theme
        self.theme_manager.apply_current_theme()

    def _connect_signals(self):
        """Connect signals to handlers"""
        # Connect capture manager signals
        if hasattr(self, 'capture_mgr') and self.capture_mgr:
            self.capture_mgr.status_update.connect(self.capture_tab.update_capture_status)
            self.capture_mgr.progress_update.connect(self.capture_tab.update_capture_progress) 
            self.capture_mgr.state_changed.connect(self.capture_tab.handle_capture_state_change)
            self.capture_mgr.capture_started.connect(self.capture_tab.handle_capture_started)
            self.capture_mgr.capture_finished.connect(self.handle_capture_finished)
            self.capture_mgr.frame_available.connect(self.capture_tab.update_preview)

            # Connect to capture monitor frame counter if available
            if hasattr(self.capture_mgr, 'capture_monitor') and self.capture_mgr.capture_monitor:
                self.capture_mgr.capture_monitor.frame_count_updated.connect(self.capture_tab.update_frame_counter)

        # Connect options manager signals
        if hasattr(self, 'options_manager') and self.options_manager:
            self.options_manager.settings_updated.connect(self.handle_settings_updated)

        # Initialize reference video dropdown
        self.setup_tab.refresh_reference_videos()

        # Connect tab navigation signals
        self.setup_tab.btn_next_to_capture.clicked.connect(lambda: self.tabs.setCurrentIndex(1))
        self.capture_tab.btn_prev_to_setup.clicked.connect(lambda: self.tabs.setCurrentIndex(0))
        self.capture_tab.btn_next_to_analysis.clicked.connect(lambda: self.tabs.setCurrentIndex(2))
        self.analysis_tab.btn_prev_to_capture.clicked.connect(lambda: self.tabs.setCurrentIndex(1))
        self.analysis_tab.btn_next_to_results.clicked.connect(lambda: self.tabs.setCurrentIndex(3))
        self.results_tab.btn_prev_to_analysis.clicked.connect(lambda: self.tabs.setCurrentIndex(2))

    def handle_settings_updated(self, settings):
        """Handle when settings are updated"""
        logger.info("Settings updated, applying changes to UI")

        # Update device status indicator in capture tab
        self.capture_tab.populate_devices_and_check_status()

        # Apply theme if changed
        self.theme_manager.apply_current_theme()

    def handle_capture_finished(self, success, result):
        """Handle capture completion"""
        self.capture_tab.btn_start_capture.setEnabled(True)
        self.capture_tab.btn_stop_capture.setEnabled(False)

        # Reset progress bar to avoid stuck state
        self.capture_tab.pb_capture_progress.setValue(0)

        if success:
            # Normalize the path for consistent display
            display_path = os.path.normpath(result)

            self.capture_tab.log_to_capture(f"Capture completed: {display_path}")
            self.capture_path = result

            # Update analysis tab
            capture_name = os.path.basename(self.capture_path)
            ref_name = os.path.basename(self.reference_info['path'])

            analysis_summary = (f"Reference: {ref_name}\n" +
                            f"Captured: {capture_name}\n" +
                            f"Ready for alignment and VMAF analysis")

            self.analysis_tab.lbl_analysis_summary.setText(analysis_summary)

            # Enable analysis tab and buttons
            self.capture_tab.btn_next_to_analysis.setEnabled(True)
            self.analysis_tab.btn_run_combined_analysis.setEnabled(True)

            # Show success message with normalized path
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(self, "Capture Complete", 
                                  f"Capture completed successfully!\n\nSaved to: {display_path}")

            # Switch to analysis tab
            self.tabs.setCurrentIndex(2)

        else:
            self.capture_tab.log_to_capture(f"Capture failed: {result}")
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Capture Failed", f"Capture failed: {result}")

    def _set_application_logo(self):
        """Set the application logo/icon"""
        try:
            # Check if logo path is set in options
            logo_path = None
            if hasattr(self, 'options_manager') and self.options_manager:
                theme_settings = self.options_manager.get_setting("theme")

                # Handle both dictionary and string theme settings
                if isinstance(theme_settings, dict):
                    logo_path = theme_settings.get("logo_path", "")
                elif isinstance(theme_settings, str):
                    # If theme_settings is a string, it's just the theme name
                    logo_path = ""

            # If not set or doesn't exist, use default
            if not logo_path or not os.path.exists(logo_path):
                # Try multiple potential logo locations
                possible_paths = [
                    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 
                               "attached_assets", "chroma-logo.png"),
                    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 
                               "assets", "chroma-logo.png")
                ]

                for path in possible_paths:
                    if os.path.exists(path):
                        logo_path = path
                        break

            # Set the window icon if the logo exists
            if logo_path and os.path.exists(logo_path):
                from PyQt5.QtGui import QIcon
                self.setWindowIcon(QIcon(logo_path))

                # Store the logo path for future reference
                self.logo_path = logo_path
                logger.info(f"Set application logo: {logo_path}")
            else:
                logger.warning("Could not find a valid logo file")

        except Exception as e:
            logger.error(f"Error setting application logo: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())

    def closeEvent(self, event):
        """Handle application close event"""
        logger.info("Application closing - cleaning up resources")

        # Stop any active capture process first
        if hasattr(self, 'capture_mgr') and self.capture_mgr and self.capture_mgr.is_capturing:
            logger.info("Stopping active capture process before closing")
            self.capture_mgr.stop_capture(cleanup_temp=True)

        # Ensure all threads are properly terminated
        self.ensure_threads_finished()

        # Clean up temporary files if file manager exists
        if hasattr(self, 'file_manager') and self.file_manager:
            logger.info("Cleaning up temporary files")
            self.file_manager.cleanup_temp_files()

        # Call parent close event
        logger.info("Cleanup complete, proceeding with application close")
        super().closeEvent(event)

    def ensure_threads_finished(self):
        """Ensure all running threads are properly terminated before proceeding"""
        # Check each tab's threads
        for tab in [self.setup_tab, self.capture_tab, self.analysis_tab, self.results_tab]:
            if hasattr(tab, 'ensure_threads_finished'):
                tab.ensure_threads_finished()