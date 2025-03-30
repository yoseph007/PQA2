import os
import shutil
import tempfile
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class ImprovedFileManager:
    """
    Improved file manager for VMAF testing application
    
    Features:
    - Uses a single temporary workspace for all intermediate files
    - Keeps only final results in the test folders
    - Cleans up automatically to prevent abandoned files
    """
    
    def __init__(self, base_dir="./tests/test_results"):
        """
        Initialize file manager
        
        Args:
            base_dir: Base directory for test results
        """
        self.base_dir = base_dir
        
        # Create a global temp directory in system temp folder
        self.temp_dir = tempfile.mkdtemp(prefix="vmaf_app_")
        logger.info(f"Created temporary workspace: {self.temp_dir}")
        
        # Track all files
        self.temp_files = []
        self.final_files = []
    
    def get_test_path(self, test_name, filename=None):
        """
        Get path to a file in the test directory
        
        Args:
            test_name: Name of the test
            filename: Optional filename to append
            
        Returns:
            Absolute path to test directory or file
        """
        # Sanitize test name for filesystem
        safe_test_name = test_name.replace('/', '_').replace('\\', '_')
        
        # Create test directory path
        test_dir = os.path.join(self.base_dir, safe_test_name)
        
        # Ensure directory exists
        os.makedirs(test_dir, exist_ok=True)
        
        # Return full path
        if filename:
            return os.path.join(test_dir, filename)
        return test_dir
    
    def get_temp_path(self, filename):
        """
        Get path in temporary workspace
        
        Args:
            filename: Filename or subdirectory
            
        Returns:
            Absolute path in temporary directory
        """
        path = os.path.join(self.temp_dir, filename)
        self.temp_files.append(path)
        return path
    
    def get_temp_file(self, suffix=".mp4", prefix="tmp_"):
        """
        Generate a temporary file path
        
        Args:
            suffix: File extension
            prefix: Filename prefix
            
        Returns:
            Path to temporary file
        """
        fd, path = tempfile.mkstemp(suffix=suffix, prefix=prefix, dir=self.temp_dir)
        os.close(fd)
        self.temp_files.append(path)
        return path
    
    def save_to_test_dir(self, source_path, test_name, filename=None):
        """
        Save a file to the test directory
        
        Args:
            source_path: Source file to copy
            test_name: Name of the test
            filename: Optional new filename (default: use source filename)
            
        Returns:
            Path to the saved file
        """
        if not os.path.exists(source_path):
            logger.warning(f"Cannot save non-existent file: {source_path}")
            return None
            
        if not filename:
            filename = os.path.basename(source_path)
            
        # Get destination path
        dest_path = self.get_test_path(test_name, filename)
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        
        # Copy file
        shutil.copy2(source_path, dest_path)
        self.final_files.append(dest_path)
        
        logger.info(f"Saved file to test directory: {dest_path}")
        return dest_path
    
    def create_aligned_videos(self, 
                            reference_path, 
                            captured_path, 
                            test_name,
                            ref_aligned_name="reference_aligned.mp4",
                            cap_aligned_name="captured_aligned.mp4"):
        """
        Process reference and captured videos and save aligned versions to test directory
        
        Args:
            reference_path: Path to reference video
            captured_path: Path to captured video
            test_name: Name of the test
            ref_aligned_name: Name for aligned reference file
            cap_aligned_name: Name for aligned captured file
            
        Returns:
            Tuple of (aligned_reference_path, aligned_captured_path)
        """
        # This is just a placeholder for the actual implementation
        # The real implementation would use frame_alignment.py functions
        
        # Process videos in temporary directory
        temp_ref_aligned = self.get_temp_path("temp_ref_aligned.mp4")
        temp_cap_aligned = self.get_temp_path("temp_cap_aligned.mp4")
        
        # Copy source files for demonstration (real code would transform them)
        shutil.copy2(reference_path, temp_ref_aligned)
        shutil.copy2(captured_path, temp_cap_aligned)
        
        # Save to test directory
        final_ref = self.save_to_test_dir(temp_ref_aligned, test_name, ref_aligned_name)
        final_cap = self.save_to_test_dir(temp_cap_aligned, test_name, cap_aligned_name)
        
        return final_ref, final_cap
    
    def cleanup_temp_files(self):
        """
        Clean up all temporary files
        
        Returns:
            Success status
        """
        success = True
        
        # Clear individual temp files first
        for file_path in self.temp_files:
            if os.path.exists(file_path):
                try:
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                except Exception as e:
                    logger.warning(f"Failed to remove temp file {file_path}: {e}")
                    success = False
        
        # Then try to remove temp directory
        if os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
                logger.info(f"Removed temporary workspace: {self.temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to remove temp dir {self.temp_dir}: {e}")
                success = False
                
        # Reset tracking lists
        self.temp_files = []
        
        return success
    
    def get_default_base_dir(self):
        """
        Get default base directory for test results
        
        Returns:
            Default base directory path
        """
        # Get the app's base directory
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        # Create path to test_results directory
        default_dir = os.path.join(app_dir, "tests", "test_results")
        
        # Ensure it exists
        os.makedirs(default_dir, exist_ok=True)
        
        return default_dir
    
    def __del__(self):
        """Cleanup on object destruction"""
        try:
            self.cleanup_temp_files()
        except:
            pass


    def get_output_path(self, base_dir=None, test_name=None, filename=None):
        """
        Compatibility method for CaptureManager
        
        Args:
            base_dir: Base directory (ignored, using self.base_dir instead)
            test_name: Test name
            filename: Optional filename
            
        Returns:
            Complete path to output file or directory
        """
        # Update base directory if provided (though we prefer to use self.base_dir)
        if base_dir:
            self.base_dir = base_dir
            
        # If no filename, just return the test directory path
        if not filename:
            return self.get_test_path(test_name or "default_test")
        
        # Return complete path with filename
        return self.get_test_path(test_name or "default_test", filename)