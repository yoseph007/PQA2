import os
import json
import logging
import shutil
import subprocess
import tempfile
from datetime import datetime

logger = logging.getLogger(__name__)

def get_ffmpeg_path():
    """
    Get path to ffmpeg executables
    
    Returns:
        Tuple of (ffmpeg_exe, ffprobe_exe, ffplay_exe) paths
    """
    import os
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Find the root directory of the application
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # The directory might be 'app' or we might be at the root already
    # Try to determine the actual root directory
    if os.path.basename(current_dir) == "app":
        root_dir = os.path.dirname(current_dir)  # Go up one level if we're in the app directory
    else:
        root_dir = current_dir  # We're already at the root
    
    logger.info(f"Root directory determined to be: {root_dir}")
    
    # Check if ffmpeg_bin exists at the root level
    ffmpeg_bin_dir = os.path.join(root_dir, "ffmpeg_bin")
    if not os.path.exists(ffmpeg_bin_dir):
        # If not, check adjacent to the app directory
        ffmpeg_bin_dir = os.path.join(os.path.dirname(os.path.dirname(current_dir)), "ffmpeg_bin")
        if not os.path.exists(ffmpeg_bin_dir):
            # As a last resort, just use the current directory
            ffmpeg_bin_dir = current_dir
    
    logger.info(f"Using FFmpeg bin directory: {ffmpeg_bin_dir}")
    
    ffmpeg_exe = os.path.join(ffmpeg_bin_dir, "ffmpeg.exe") 
    ffprobe_exe = os.path.join(ffmpeg_bin_dir, "ffprobe.exe")
    ffplay_exe = os.path.join(ffmpeg_bin_dir, "ffplay.exe")
    
    # Check if files exist
    if not os.path.exists(ffmpeg_exe):
        logger.warning(f"FFmpeg executable not found at {ffmpeg_exe}")
        # Try to find ffmpeg.exe in PATH
        ffmpeg_exe = "ffmpeg"
    if not os.path.exists(ffprobe_exe):
        logger.warning(f"FFprobe executable not found at {ffprobe_exe}")
        # Try to find ffprobe.exe in PATH
        ffprobe_exe = "ffprobe"
    if not os.path.exists(ffplay_exe):
        logger.warning(f"FFplay executable not found at {ffplay_exe}")
        # Try to find ffplay.exe in PATH  
        ffplay_exe = "ffplay"
    
    logger.info(f"FFmpeg path: {ffmpeg_exe}")
    logger.info(f"FFprobe path: {ffprobe_exe}")
    
    return (ffmpeg_exe, ffprobe_exe, ffplay_exe)


class FileManager:
    """
    Manages file paths and temporary files for the application
    to ensure consistent path handling and proper cleanup
    """
    
    def __init__(self, base_dir=None):
        """
        Initialize file manager
        
        Args:
            base_dir: Base directory for test results
        """
        # If no base directory provided, use default in tests/test_results
        if base_dir is None:
            script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            base_dir = os.path.join(script_dir, "tests", "test_results")
            # Ensure it exists
            os.makedirs(base_dir, exist_ok=True)

        self.base_dir = base_dir
        logger.info(f"File manager initialized with base directory: {self.base_dir}")

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

    def __del__(self):
        """Cleanup on object destruction"""
        try:
            self.cleanup_temp_files()
        except:
            pass

    def get_output_path(self, base_dir=None, test_name=None, filename=None):
        """
        Generate standardized output path for files
        
        Args:
            base_dir: Base directory for output (defaults to self.base_dir)
            test_name: Test name for subdirectory 
            filename: Optional filename to append
            
        Returns:
            Complete path to output file or directory
        """
        # Use provided base_dir or default
        output_dir = base_dir if base_dir else self.base_dir
        
        # Make safe test name with timestamp
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if test_name:
            # Clean test name to avoid path issues
            safe_test_name = test_name.replace('/', '_').replace('\\', '_')
            # Add timestamp for uniqueness
            dir_name = f"{safe_test_name}_{timestamp}"
        else:
            dir_name = f"test_{timestamp}"
        
        # Create the test directory path
        test_dir = os.path.join(output_dir, dir_name)

        # Ensure directory exists
        os.makedirs(test_dir, exist_ok=True)

        # Log the directory being used
        logger.debug(f"Using output directory: {test_dir}")

        # If no filename, just return the test directory path
        if not filename:
            return test_dir

        # Return path with filename
        return os.path.join(test_dir, filename)


def timestamp_string():
    """
    Generate timestamp string for file naming
    
    Returns:
        Formatted timestamp string
    """
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def normalize_path(path, for_ffmpeg=False):
    """
    Normalize file path to use consistent separators
    
    Args:
        path: The path to normalize
        for_ffmpeg: If True, always use forward slashes for FFmpeg commands
    
    Returns:
        Normalized path string
    """
    if path is None:
        return None
        
    # First, convert to proper OS path with normalized separators
    normalized = os.path.normpath(path)
    
    # For FFmpeg, always use forward slashes regardless of platform
    if for_ffmpeg:
        normalized = normalized.replace('\\', '/')
        
    return normalized


def get_subprocess_startupinfo():
    """
    Get a STARTUPINFO object configured to suppress Windows console windows and error dialogs
    
    Returns:
        Tuple containing (startupinfo, creationflags, env) for subprocess calls
    """
    startupinfo = None
    creationflags = 0
    env = os.environ.copy()
    
    if platform.system() == 'Windows':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0  # SW_HIDE
        
        # Use CREATE_NO_WINDOW flag if available
        if hasattr(subprocess, 'CREATE_NO_WINDOW'):
            creationflags = subprocess.CREATE_NO_WINDOW
            
        # Add environment variables to suppress FFmpeg dialogs
        env.update({
            "FFMPEG_HIDE_BANNER": "1",
            "AV_LOG_FORCE_NOCOLOR": "1"
        })
    
    return startupinfo, creationflags, env

def run_ffmpeg_without_dialogs(cmd, timeout=None, input_data=None, universal_newlines=True):
    """
    Run FFmpeg command with comprehensive error dialog suppression
    
    Args:
        cmd: Command list to execute
        timeout: Optional timeout in seconds
        input_data: Optional input data for stdin
        universal_newlines: Whether to use text mode (default: True)
        
    Returns:
        CompletedProcess object or subprocess.Popen object if input_data is provided
    """
    startupinfo, creationflags, env = get_subprocess_startupinfo()
    
    # Log the command being executed
    logging.getLogger(__name__).debug(f"Running FFmpeg command: {' '.join(cmd)}")
    
    if input_data is not None:
        # When stdin input is needed, use Popen
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=universal_newlines,
            startupinfo=startupinfo,
            creationflags=creationflags,
            env=env
        )
        stdout, stderr = process.communicate(input=input_data, timeout=timeout)
        return process
    else:
        # For simple commands, use run
        return subprocess.run(
            cmd,
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=universal_newlines,
            timeout=timeout,
            startupinfo=startupinfo,
            creationflags=creationflags,
            env=env
        )


def get_video_info(video_path):
    """
    Get detailed information about a video file using FFprobe
    
    Args:
        video_path: Path to video file
        
    Returns:
        Dictionary with video information or None on error
    """
    try:
        # Get FFprobe executable path
        ffmpeg_exe, ffprobe_exe, ffplay_exe = get_ffmpeg_path()
        
        # Normalize path for FFprobe
        video_path_ffmpeg = video_path.replace("\\", "/")
        
        cmd = [
            ffprobe_exe,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format", 
            "-show_streams",
            video_path_ffmpeg
        ]
        
        # Get startup info to suppress dialogs
        startupinfo, creationflags = get_subprocess_startupinfo()
        
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True,
            startupinfo=startupinfo,
            creationflags=creationflags
        )
        
        if result.returncode != 0:
            logger.error(f"FFprobe failed: {result.stderr}")
            return None
            
        # Parse JSON output
        import json
        info = json.loads(result.stdout)
        
        # Get video stream info
        video_stream = None
        for stream in info.get('streams', []):
            if stream.get('codec_type') == 'video':
                video_stream = stream
                break
                
        if not video_stream:
            logger.error(f"No video stream found in {video_path}")
            return None
                
        # Extract key information
        format_info = info.get('format', {})
        duration = float(format_info.get('duration', 0))
        
        # Parse frame rate
        frame_rate_str = video_stream.get('avg_frame_rate', '0/0')
        if '/' in frame_rate_str:
            num, den = map(int, frame_rate_str.split('/'))
            if den == 0:
                frame_rate = 0
            else:
                frame_rate = num / den
        else:
            frame_rate = float(frame_rate_str or 0)
            
        # Get dimensions and frame count
        width = int(video_stream.get('width', 0))
        height = int(video_stream.get('height', 0))
        frame_count = int(video_stream.get('nb_frames', 0))
        
        # If nb_frames is missing or zero, estimate from duration
        if frame_count == 0 and frame_rate > 0:
            frame_count = int(round(duration * frame_rate))
            
        # Get pixel format
        pix_fmt = video_stream.get('pix_fmt', 'unknown')
        
        return {
            'path': video_path,
            'duration': duration,
            'frame_rate': frame_rate,
            'width': width,
            'height': height,
            'frame_count': frame_count,
            'pix_fmt': pix_fmt
        }
        
    except Exception as e:
        logger.error(f"Error getting video info for {video_path}: {str(e)}")
        return None