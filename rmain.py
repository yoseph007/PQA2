#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
VMAF Test App - Main entry point

This file serves as the entry point for the VMAF Test App, which allows video
capture, alignment, and VMAF quality analysis using white bookend frames.
"""

import sys
import os
import logging
from app.main import main

if __name__ == "__main__":
    # Add parent directory to path to ensure imports work correctly
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    # Setup basic logging for the root main.py
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    
    logger.info("Starting VMAF Test App from root main.py")
    
    # Call the main function from app.main
    try:
        sys.exit(main())
    except Exception as e:
        logger.critical(f"Unhandled exception: {str(e)}")
        import traceback
        logger.critical(traceback.format_exc())
        sys.exit(1)
