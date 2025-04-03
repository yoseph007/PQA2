import os
import sys
import logging
import argparse
import platform
from PyQt5.QtWidgets import QApplication

# Set Python path to include current directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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

    # Check if running in headless environment (like Replit)
    headless = False
    # Only use headless mode in Replit environment, not on local machines
    if 'REPLIT_ENVIRONMENT' in os.environ:
        logger.info("Running in Replit environment, setting QT_QPA_PLATFORM to offscreen")
        os.environ["QT_QPA_PLATFORM"] = "offscreen"  # Use offscreen platform which is available
        os.environ["QT_DEBUG_PLUGINS"] = "1"    # Enable debug for platform plugins
        headless = True
    # For local machines on Windows, force GUI mode
    elif platform.system() == 'Windows':
        logger.info("Running on Windows local machine, forcing GUI mode")
        headless = False
    # For other systems, check for display
    elif not os.environ.get('DISPLAY'):
        logger.info("No display detected on non-Windows system, setting headless mode")
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        headless = True

    # Configure font paths to resolve Qt font loading issues
    logger.info("Configuring font paths")
    if platform.system() == 'Windows':
        # On Windows, use system fonts
        from PyQt5.QtGui import QFontDatabase
        logger.info("Running on Windows, configuring font paths")
        # Add Windows system fonts directory
        if "WINDIR" in os.environ:
            QFontDatabase.addApplicationFont(os.path.join(os.environ["WINDIR"], "Fonts", "arial.ttf"))
    else:
        # On Linux/Replit, configure a font path
        if os.path.exists("/usr/share/fonts"):
            os.environ["QT_QPA_FONTDIR"] = "/usr/share/fonts"
        # Create a fonts directory and add a font file if it doesn't exist
        fonts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
        if not os.path.exists(fonts_dir):
            os.makedirs(fonts_dir, exist_ok=True)

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

    # Apply dark theme by default for better appearance
    try:
        import qdarkstyle
        app.setStyleSheet(qdarkstyle.load_stylesheet_pyqt5())
    except ImportError:
        logger.warning("QDarkStyle not installed, using default theme")

    # Create and show main window
    logger.info("Creating main window...")
    try:
        window = MainWindow(capture_manager, file_manager, options_manager)
        
        # Set headless mode if requested or running in Replit
        if args.headless or headless:
            window.headless_mode = True
            logger.info("Running in headless mode")
        else:
            logger.info("Showing GUI window...")
            window.show()
            logger.info("Window show() called successfully")
    except Exception as e:
        logger.error(f"ERROR creating or showing window: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())

    # Run application event loop
    return app.exec_()

if __name__ == "__main__":
    sys.exit(main())