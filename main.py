#!/usr/bin/env python
"""
VMAF Test App - Main entry point
"""

import sys
import os
import logging
from PyQt5.QtWidgets import QApplication
from app.ui import MainWindow  # Changed from VMafTestApp to MainWindow
from app.capture import CaptureManager
from app.utils import FileManager

if __name__ == "__main__":
    # Add parent directory to path to ensure imports work correctly
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    # Setup basic logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    
    logger.info("Starting VMAF Test App")
    
    # Create application
    app = QApplication(sys.argv)
    
    # Create file manager for consistent path handling
    file_manager = FileManager()
    
    # Create and configure capture manager
    capture_manager = CaptureManager()
    capture_manager.path_manager = file_manager
    
    # Create main window and connect to managers
    window = MainWindow(capture_manager, file_manager)
    window.show()
    
    # Start application loop
    sys.exit(app.exec_())
