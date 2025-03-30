import sys
import logging
import os
from PyQt5.QtWidgets import QApplication
from app.capture import CaptureManager
from app.ui import MainWindow

def setup_logging():
    """Setup logging configuration with both file and console handlers"""
    log_dir = os.path.dirname(os.path.abspath(__file__))
    log_file = os.path.join(log_dir, 'vmaf_app.log')
    
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
    logger = setup_logging()
    logger.info("Starting VMAF Test App")
    
    try:
        # Initialize application
        app = QApplication(sys.argv)
        
        # Create and configure capture manager
        capture_manager = CaptureManager()
        
        # Create main window without passing capture_manager directly
        window = MainWindow()
        
        # Set capture_manager after window creation and connect signals
        window.capture_mgr = capture_manager
        window.connect_signals()
        
        window.show()
        
        # Start application loop
        return app.exec_()
        
    except Exception as e:
        logger.critical(f"Application failed: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())