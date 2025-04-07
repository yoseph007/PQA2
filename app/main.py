import logging
import os
import sys

from PyQt5.QtWidgets import QApplication

from app.capture import CaptureManager
from app.ui import MainWindow
from app.utils import FileManager


def setup_logging():
    """Setup logging configuration with both file and console handlers"""

    # Use user-local AppData directory for logging
    log_dir = os.path.join(os.getenv('APPDATA'), 'ChromaPQA', 'logs')
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, 'vmaf_app.log')

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding='utf-8')
        ]
    )
    return logging.getLogger(__name__)

def main():
    """Main application entry point"""
    logger = setup_logging()
    logger.info("Starting VMAF Test App")
    
    try:
        # Check if running in headless environment (like Replit)
        headless = False
        if 'REPLIT_ENVIRONMENT' in os.environ or not os.environ.get('DISPLAY'):
            logger.info("Running in Replit environment, set QT_QPA_PLATFORM to offscreen")
            os.environ["QT_QPA_PLATFORM"] = "vnc"  # Use VNC instead of offscreen for preview
            os.environ["QT_DEBUG_PLUGINS"] = "1"    # Enable debug for platform plugins
            headless = True
        
        # Initialize application
        app = QApplication(sys.argv)
        
        # Create file manager for consistent path handling
        file_manager = FileManager()
        
        # Create and configure options manager
        from app.options_manager import OptionsManager
        options_manager = OptionsManager()
        
        # Create and configure capture manager
        capture_manager = CaptureManager()
        capture_manager.path_manager = file_manager
        capture_manager.options_manager = options_manager
        
        # Create main window and connect to managers
        window = MainWindow(capture_manager, file_manager, options_manager)
        window.headless_mode = headless  # Pass headless mode flag to window
        
        # Apply dark theme by default for better appearance
        try:
            import qdarkstyle
            app.setStyleSheet(qdarkstyle.load_stylesheet_pyqt5())
        except ImportError:
            logger.warning("QDarkStyle not installed, using default theme")
            
        window.show()
        
        # Start application loop
        return app.exec_()
        
    except Exception as e:
        logger.critical(f"Application failed: {str(e)}")
        import traceback
        logger.critical(traceback.format_exc())
        return 1

if __name__ == "__main__":
    sys.exit(main())
