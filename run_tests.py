
#!/usr/bin/env python3
"""
VMAF Test App - Test Runner

This script runs a comprehensive suite of tests to verify
that the VMAF Test application is ready for production deployment.
"""

import os
import sys
import logging
import argparse
import unittest
import json
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join('logs', 'test_run.log'), mode='a')
    ]
)

logger = logging.getLogger("test_runner")

def run_tests(modules=None, verbose=False):
    """Run the specified test modules or all tests"""
    # Ensure app/tests is in the path
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    # Create test directory if it doesn't exist
    os.makedirs('tests', exist_ok=True)
    os.makedirs('logs', exist_ok=True)
    
    logger.info("Starting VMAF App test suite")
    
    if modules:
        test_modules = modules
    else:
        # Auto-discover test modules
        import importlib
        test_dir = os.path.join(os.path.dirname(__file__), 'tests')
        test_modules = []
        
        for file in os.listdir(test_dir):
            if file.startswith('test_') and file.endswith('.py'):
                module_name = f"tests.{file[:-3]}"
                try:
                    importlib.import_module(module_name)
                    test_modules.append(module_name)
                except ImportError as e:
                    logger.error(f"Could not import test module {module_name}: {e}")
    
    # Run tests
    suite = unittest.TestSuite()
    
    if test_modules:
        for module_name in test_modules:
            try:
                logger.info(f"Loading tests from {module_name}")
                if verbose:
                    print(f"Loading tests from {module_name}")
                suite.addTest(unittest.defaultTestLoader.loadTestsFromName(module_name))
            except Exception as e:
                logger.error(f"Error loading tests from {module_name}: {e}")
                if verbose:
                    print(f"Error loading tests from {module_name}: {e}")
    else:
        # If no modules specified and auto-discovery found nothing, discover all tests
        logger.info("No test modules specified, discovering all tests")
        if verbose:
            print("No test modules specified, discovering all tests")
        suite.addTest(unittest.defaultTestLoader.discover('tests'))
    
    # Run the tests
    runner = unittest.TextTestRunner(verbosity=2 if verbose else 1)
    result = runner.run(suite)
    
    # Log the results
    logger.info(f"Tests complete: {result.testsRun} tests run")
    logger.info(f"Passed: {result.testsRun - len(result.failures) - len(result.errors)}")
    logger.info(f"Failed: {len(result.failures)}")
    logger.info(f"Errors: {len(result.errors)}")
    
    # Write test report
    report = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'tests_run': result.testsRun,
        'passed': result.testsRun - len(result.failures) - len(result.errors),
        'failures': len(result.failures),
        'errors': len(result.errors),
        'failure_details': [str(f[0]) for f in result.failures],
        'error_details': [str(e[0]) for e in result.errors]
    }
    
    report_path = os.path.join('logs', f'test_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    # Print summary
    if verbose:
        print("\nTest Summary:")
        print(f"- Tests Run: {result.testsRun}")
        print(f"- Passed: {result.testsRun - len(result.failures) - len(result.errors)}")
        print(f"- Failed: {len(result.failures)}")
        print(f"- Errors: {len(result.errors)}")
        print(f"- Test report written to: {report_path}")
    
    return len(result.failures) == 0 and len(result.errors) == 0

def validate_app_installation():
    """Check if the app is correctly installed with all dependencies"""
    try:
        # Check core PyQt5 dependencies
        import PyQt5
        from PyQt5 import QtWidgets, QtCore, QtGui
        
        # Check charting dependencies
        from PyQt5 import QtChart
        
        # Check reporting dependencies
        import reportlab
        import matplotlib
        import numpy
        import pandas
        
        # All dependencies are installed
        return True
    except ImportError as e:
        logger.error(f"Missing dependency: {e}")
        print(f"Missing dependency: {e}")
        print("Please install all required dependencies with: pip install -r requirements.txt")
        return False

def main():
    """Main entry point for test runner"""
    parser = argparse.ArgumentParser(description='VMAF Test App Test Runner')
    parser.add_argument('--modules', type=str, nargs='+', help='Specific test modules to run')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose output')
    
    args = parser.parse_args()
    
    # First check if all dependencies are installed
    if not validate_app_installation():
        return 1
    
    # Run the tests
    success = run_tests(args.modules, args.verbose)
    
    return 0 if success else 1

if __name__ == '__main__':
    sys.exit(main())
