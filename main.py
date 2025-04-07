
import sys
import logging
import os
from app.ui.main_window import MainWindow
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt



# Safe log directory for all environments (user profile)
log_dir = os.path.join(os.getenv('APPDATA'), 'ChromaPQA', 'logs')
os.makedirs(log_dir, exist_ok=True)

log_file = os.path.join(log_dir, 'vmaf_app.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_file, mode='a', encoding='utf-8')
    ]
)

logger = logging.getLogger("main")



if __name__ == "__main__":
    try:
        # Create logs directory if it doesn't exist
        os.makedirs('logs', exist_ok=True)

        # Log platform information
        import platform
        platform_info = platform.platform()
        logger.info(f"Running on {platform_info}")

        # Configure font paths on Windows
        if platform.system() == 'Windows':
            logger.info("Running on Windows, configuring font paths")
            os.environ["QT_QPA_FONTDIR"] = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "Fonts")

        # Create Qt application
        app = QApplication(sys.argv)

        # Set application name and organization
        app.setApplicationName("VMAF Test Application")
        app.setOrganizationName("Quality Testing")

        # Create required manager objects
        from app.capture import CaptureManager
        from app.utils import FileManager
        from app.options_manager import OptionsManager
        
        # Initialize managers
        capture_manager = CaptureManager()
        file_manager = FileManager()
        options_manager = OptionsManager()
        
        # Connect managers
        capture_manager.path_manager = file_manager
        capture_manager.options_manager = options_manager

        # Configure for headless environments like Replit
        if 'REPLIT_ENVIRONMENT' in os.environ or 'REPL_ID' in os.environ:
            logger.info("Running in Replit environment, setting QT_QPA_PLATFORM")
            os.environ["QT_QPA_PLATFORM"] = "vnc"  # Use VNC for Replit
            os.environ["QT_DEBUG_PLUGINS"] = "1"   # Enable debug for platform plugins

        # Create and show the main window
        window = MainWindow(capture_manager, file_manager, options_manager)
        window.show()

        # Run the application event loop
        sys.exit(app.exec_())

    except Exception as e:
        logger.error(f"Application error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
