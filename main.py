import os
import sys
import logging
import argparse
from PyQt5.QtWidgets import QApplication

# Import managers
from app.capture import CaptureManager
from app.utils import FileManager
from app.options_manager import OptionsManager

# Import the main window from new modular UI structure
from app.ui.main_window import MainWindow

def setup_logging():
    """Set up logging configuration"""
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    logging.basicConfig(level=logging.INFO, format=log_format)

    # Create logs directory if it doesn't exist
    if not os.path.exists("logs"):
        os.makedirs("logs", exist_ok=True)

    # Add file handler
    file_handler = logging.FileHandler("logs/app.log")
    file_handler.setFormatter(logging.Formatter(log_format))

    # Get root logger and add file handler
    root_logger = logging.getLogger()
    root_logger.addHandler(file_handler)

    # Configure library loggers to reduce verbosity
    logging.getLogger("matplotlib").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)

    return logging.getLogger(__name__)

def main():
    """Main entry point for the VMAF Test Application"""
    # Set up logging
    logger = setup_logging()
    logger.info("Starting VMAF Test App")

    # Check platform and configure font paths for Windows
    if sys.platform == "win32":
        logger.info("Running on Windows, configuring font paths")
        # Configure font paths if needed

    # Parse command line arguments
    parser = argparse.ArgumentParser(description="VMAF Test App")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode")
    args = parser.parse_args()

    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName("VMAF Test App")

    # Create managers
    options_manager = OptionsManager()
    file_manager = FileManager()
    
    # Initialize capture manager with proper parameters
    capture_manager = CaptureManager()
    # Set options_manager and file_manager after initialization
    capture_manager.options_manager = options_manager
    capture_manager.path_manager = file_manager

    # Create and show main window
    window = MainWindow(capture_manager, file_manager, options_manager)

    # Set headless mode if requested
    if args.headless:
        window.headless_mode = True
        logger.info("Running in headless mode")
    else:
        window.show()

    # Run application event loop
    return app.exec_()

if __name__ == "__main__":
    sys.exit(main())