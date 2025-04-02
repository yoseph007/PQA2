import sys
import logging
import os
from PyQt5.QtWidgets import QApplication
from app.capture import CaptureManager
from app.utils import FileManager
from app.ui import MainWindow

def setup_logging():
    """Setup logging configuration with both file and console handlers"""
    log_dir = os.path.dirname(os.path.abspath(__file__))
    log_file = os.path.join(log_dir, 'vmaf_app.log')
    
    # Create logs directory if it doesn't exist
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file)
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
        options_manager = OptionsManager()
        
        # Create and configure capture manager
        capture_manager = CaptureManager()
        capture_manager.path_manager = file_manager
        capture_manager.options_manager = options_manager
        
        # Create main window and connect to managers
        window = MainWindow(capture_manager, file_manager, options_manager)
        window.headless_mode = headless  # Pass headless mode flag to window
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
