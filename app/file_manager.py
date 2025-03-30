import os
import shutil
import tempfile
import logging

logger = logging.getLogger(__name__)

class VideoFileManager:
    """
    Manage test video files and cleanup for VMAF testing
    
    This class handles temporary file creation, organization of final files,
    and cleanup of intermediate files.
    """
    
    def get_output_path(self, base_dir=None, test_name=None, filename=None):
        """
        Compatibility method for CaptureManager
        Args:
            base_dir: Optional base directory (updates self.base_output_dir if provided)
            test_name: Optional test name (updates self.test_name if provided)
            filename: Filename to use
        Returns:
            Full path to output file
        """
        # Update settings if provided
        if base_dir:
            self.base_output_dir = base_dir
        if test_name:
            self.test_name = test_name
        
        # Use the filename if provided, otherwise just return test directory
        if filename:
            return self.output_path(filename)
        return self.get_test_dir()



    def __init__(self, base_output_dir, test_name="default_test"):
        """
        Initialize the file manager
        
        Args:
            base_output_dir: Base directory for test output
            test_name: Name of the current test (used for subdirectory creation)
        """
        self.base_output_dir = base_output_dir
        self.test_name = test_name
        self.temp_dir = tempfile.mkdtemp()
        self.temp_files = []
        self.final_files = []
        
        logger.info(f"Initialized VideoFileManager with temp dir: {self.temp_dir}")
        logger.info(f"Test output will be in: {self.get_test_dir()}")
    
    def get_test_dir(self):
        """
        Get the test output directory
        
        Returns:
            Full path to the test-specific output directory
        """
        # Ensure test name is safe for file paths
        safe_test_name = self.test_name.replace('/', '_').replace('\\', '_')
        test_dir = os.path.join(self.base_output_dir, safe_test_name)
        os.makedirs(test_dir, exist_ok=True)
        return test_dir
    
    def temp_path(self, filename):
        """
        Get a path for a temporary file
        
        Args:
            filename: Base filename for the temporary file
            
        Returns:
            Full path to the temporary file
        """
        path = os.path.join(self.temp_dir, filename)
        self.temp_files.append(path)
        return path
    
    def output_path(self, filename):
        """
        Get a path in the test output directory
        
        Args:
            filename: Base filename for the output file
            
        Returns:
            Full path to the output file
        """
        path = os.path.join(self.get_test_dir(), filename)
        self.final_files.append(path)
        return path
    
    def create_temp_file(self, suffix=None, prefix=None):
        """
        Create a temporary file with random name
        
        Args:
            suffix: Optional file suffix (e.g., '.mp4')
            prefix: Optional file prefix
            
        Returns:
            Path to the created temporary file
        """
        fd, path = tempfile.mkstemp(suffix=suffix, prefix=prefix, dir=self.temp_dir)
        os.close(fd)
        self.temp_files.append(path)
        return path
    
    def create_temp_dir(self):
        """
        Create a nested temporary directory
        
        Returns:
            Path to the created temporary directory
        """
        path = tempfile.mkdtemp(dir=self.temp_dir)
        return path
    
    def move_to_final(self, temp_file, final_filename=None):
        """
        Move a temporary file to the final output directory
        
        Args:
            temp_file: Path to the temporary file
            final_filename: Optional new filename (default: use original filename)
            
        Returns:
            Path to the file in the final location
        """
        if not os.path.exists(temp_file):
            logger.warning(f"Cannot move non-existent temp file: {temp_file}")
            return None
            
        if not final_filename:
            final_filename = os.path.basename(temp_file)
            
        final_path = self.output_path(final_filename)
        
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(final_path), exist_ok=True)
            
            # Copy the file (rather than move, to avoid cross-device link issues)
            shutil.copy2(temp_file, final_path)
            logger.debug(f"Moved temporary file to final location: {final_path}")
            
            return final_path
        except Exception as e:
            logger.error(f"Failed to move {temp_file} to {final_path}: {e}")
            return None
    
    def cleanup_temp_files(self):
        """
        Clean up all temporary files
        
        Returns:
            True if cleanup was successful, False otherwise
        """
        success = True
        for file_path in self.temp_files:
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.debug(f"Removed temp file: {file_path}")
                except Exception as e:
                    logger.warning(f"Failed to remove temp file {file_path}: {e}")
                    success = False
        
        if os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
                logger.debug(f"Removed temp directory: {self.temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to remove temp dir {self.temp_dir}: {e}")
                success = False
                
        # Reset internal lists
        self.temp_files = []
                
        return success
                
    def __del__(self):
        """Cleanup on object destruction"""
        try:
            self.cleanup_temp_files()
        except:
            pass
