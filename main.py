import sys
import logging
import os
from app.ui.main_window import MainWindow
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join('logs', 'vmaf_app.log'), mode='a')
    ]
)

logger = logging.getLogger("main")

def initialize_vmaf_enhancer():
    """Initialize the VMAF enhancer to prepare for analysis"""
    try:
        from app.vmaf_enhancer import VMAFEnhancer
        # Create temporary directory
        os.makedirs('temp', exist_ok=True)
        # Initialize enhancer
        enhancer = VMAFEnhancer()
        logger.info("VMAF enhancer initialized and ready")
        return enhancer
    except Exception as e:
        logger.warning(f"Could not initialize VMAF enhancer: {str(e)}")
        return None

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

        # Initialize VMAF enhancer
        enhancer = initialize_vmaf_enhancer()

        # Create Qt application
        app = QApplication(sys.argv)

        # Set application name and organization
        app.setApplicationName("VMAF Test Application")
        app.setOrganizationName("Quality Testing")

        # Create and show the main window
        window = MainWindow()
        window.show()

        # Run the application event loop
        sys.exit(app.exec_())

    except Exception as e:
        logger.error(f"Application error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())