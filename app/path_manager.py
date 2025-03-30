import os
import shutil
import tempfile
import logging

logger = logging.getLogger(__name__)

class PathManager:
    """
    Manages all file paths and temporary files in the application
    to ensure consistent path handling and proper cleanup
    """
    
    def __init__(self):
        self.temp_files = []
        self.temp_dirs = []
        
    def get_test_dir(self, base_dir, test_name):
        """
        Get unique test directory path without nesting
        """
        # Clean test name to avoid path issues
        safe_test_name = test_name.replace('/', '_').replace('\\', '_')
        
        # Create a clean path without multiple nested directories
        test_dir = os.path.join(base_dir, safe_test_name)
        
        # Ensure it exists
        os.makedirs(test_dir, exist_ok=True)
        
        return test_dir
        
    def get_output_path(self, base_dir, test_name, filename):
        """
        Generate standardized output path
        """
        test_dir = self.get_test_dir(base_dir, test_name)
        output_path = os.path.join(test_dir, filename)
        return os.path.normpath(output_path)
    
    def create_temp_file(self, suffix=None, prefix=None):
        """Create a temporary file and track it for cleanup"""
        fd, path = tempfile.mkstemp(suffix=suffix, prefix=prefix)
        os.close(fd)
        self.temp_files.append(path)
        logger.debug(f"Created temp file: {path}")
        return path
    
    def create_temp_dir(self):
        """Create a temporary directory and track it for cleanup"""
        path = tempfile.mkdtemp()
        self.temp_dirs.append(path)
        logger.debug(f"Created temp dir: {path}")
        return path
    
    def ffmpeg_path(self, path):
        """Convert path to FFmpeg-friendly format (forward slashes)"""
        if path is None:
            return None
        return path.replace('\\', '/')
        
    def cleanup(self):
        """Clean up all temporary files and directories"""
        # Clean temp files
        for file_path in self.temp_files:
            try:
                if os.path.exists(file_path):
                    os.unlink(file_path)
                    logger.debug(f"Cleaned temp file: {file_path}")
            except Exception as e:
                logger.warning(f"Failed to clean temp file {file_path}: {e}")
        
        # Clean temp dirs
        for dir_path in self.temp_dirs:
            try:
                if os.path.exists(dir_path):
                    shutil.rmtree(dir_path)
                    logger.debug(f"Cleaned temp dir: {dir_path}")
            except Exception as e:
                logger.warning(f"Failed to clean temp dir {dir_path}: {e}")
                
        # Reset tracking lists
        self.temp_files = []
        self.temp_dirs = []