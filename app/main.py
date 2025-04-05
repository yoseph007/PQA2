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
            logger.info("Running in Replit environment")
            # Try different Qt platform plugins in order of preference
            # Try 'vnc' first, then fallback to offscreen if that fails
            platform_plugins = ["vnc", "offscreen", "minimal", "webgl"]
            
            # Log platform information
            import platform
            logger.info(f"Running on {platform.platform()}")
            
            # Set debug for platform plugins
            os.environ["QT_DEBUG_PLUGINS"] = "1"
            
            # Set headless flag
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
