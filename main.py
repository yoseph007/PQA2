
import sys
import logging
import os
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QCoreApplication
from app.capture import CaptureManager
from app.utils import FileManager
from app.ui import MainWindow
from app.options_manager import OptionsManager

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
        # Configure environment for Qt
        if 'REPL_ID' in os.environ:
            # Running in Replit environment
            os.environ['QT_QPA_PLATFORM'] = 'minimal'  # Use minimal platform in Replit
            os.environ['QT_DEBUG_PLUGINS'] = '1'  # Help debug plugin issues
            os.environ['QT_LOGGING_RULES'] = 'qt.qpa.*=true'  # More verbose QPA logging
            logger.info("Running in Replit environment, set QT_QPA_PLATFORM to minimal")
        else:
            # Running in other environments (Windows, macOS, etc.)
            # Handle font issues on Windows
            if sys.platform == 'win32':
                # Fix font directory issues on Windows
                logger.info("Running on Windows, configuring font paths")
                os.environ['QT_QPA_FONTDIR'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fonts')
                os.makedirs(os.environ['QT_QPA_FONTDIR'], exist_ok=True)
            
            # Standard configuration for local environment
            os.environ['QT_QPA_PLATFORM'] = 'offscreen' if 'PYTEST_CURRENT_TEST' in os.environ else ''
        
        # Use software rendering for better compatibility
        os.environ['QT_QUICK_BACKEND'] = 'software'
        
        # Initialize application
        app = QApplication(sys.argv)
        
        # Create file manager for consistent path handling
        file_manager = FileManager()
        
        # Create options manager for settings
        options_manager = OptionsManager()
        
        # Create and configure capture manager
        capture_manager = CaptureManager()
        capture_manager.path_manager = file_manager
        # Ensure options_manager is set properly
        capture_manager.options_manager = options_manager
        
        # Create main window and connect to managers
        window = MainWindow(capture_manager, file_manager, options_manager)
        
        # Set headless mode flag if running in Replit
        if 'REPL_ID' in os.environ:
            window.headless_mode = True
            logger.info("Setting headless mode for Replit environment")
            
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
