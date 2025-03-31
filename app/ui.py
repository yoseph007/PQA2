#Import necessary libraries
import os
import logging
from PyQt5.QtWidgets import QMessageBox

# Assuming ImprovedFileManager and other necessary classes/functions are defined elsewhere


class CaptureManager: # Example class, replace with your actual class
    def __init__(self):
        pass

    def stop_capture(self, cleanup_temp=True):
        pass


class YourClass: # Replace with your actual class name
    def __init__(self):
        # ... other initialization code ...
        base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests", "test_results")
        os.makedirs(base_dir, exist_ok=True)

        # Create default_test folder for temporary files
        temp_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "default_test")
        os.makedirs(temp_dir, exist_ok=True)

        self.file_manager = ImprovedFileManager(base_dir=base_dir, temp_dir=temp_dir)
        logger = logging.getLogger(__name__) # Assuming logger is defined elsewhere
        logger.info(f"Using test results directory: {base_dir}")
        logger.info(f"Using temporary directory: {temp_dir}")
        self._stopping_capture = False #Added to handle stop button logic
        # ... rest of the initialization code ...


    def handle_capture_finished(self, success, result):
        """Handle capture completion"""
        self.btn_start_capture.setEnabled(True)
        self.btn_stop_capture.setEnabled(False)

        if success:
            # Normalize the path for consistent display
            display_path = os.path.normpath(result)

            self.log_to_capture(f"Capture completed: {display_path}")
            self.capture_path = result

            # Update analysis tab
            capture_name = os.path.basename(self.capture_path)
            ref_name = os.path.basename(self.reference_info['path'])

            analysis_summary = (f"Reference: {ref_name}\n" +
                            f"Captured: {capture_name}\n" +
                            f"Ready for alignment and VMAF analysis")

            self.lbl_analysis_summary.setText(analysis_summary)

            # Enable analysis tab and button
            self.btn_next_to_analysis.setEnabled(True)
            self.btn_align_videos.setEnabled(True)

            # Don't show success message on stop - only show on successful completion
            if not hasattr(self, '_stopping_capture') or not self._stopping_capture:
                QMessageBox.information(self, "Capture Complete", 
                                    f"Capture completed successfully!\n\nSaved to: {display_path}")
        else:
            self.log_to_capture(f"Capture failed: {result}")
            QMessageBox.critical(self, "Capture Failed", f"Capture failed: {result}")

        # Reset stopping flag
        self._stopping_capture = False

    def stop_capture(self):
        """Stop the capture process"""
        self.log_to_capture("Stopping capture...")
        self._stopping_capture = True
        self.capture_manager.stop_capture(cleanup_temp=True)

        # Reset progress bar to avoid stuck state
        self.pb_capture_progress.setValue(0)

    def log_to_capture(self, message):
        #Implementation for logging
        pass

    # ... other methods ...

# Example usage (replace with your actual application setup)

#if __name__ == "__main__":
#    app = YourQApplication(sys.argv)
#    window = YourClass()
#    window.show()
#    sys.exit(app.exec_())