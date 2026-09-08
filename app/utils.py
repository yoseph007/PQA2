import hashlib
import json
import logging
import os
import platform
import shutil
import subprocess
import tempfile
from fractions import Fraction
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

FFMPEG_TIMEOUT = 30  # seconds


import inspect


class FFmpegPaths(str):
    """
    String representation of ffmpeg path that can also be unpacked as
    (ffmpeg_path, ffprobe_path, ffplay_path) for backward compatibility.
    """
    def __new__(cls, ffmpeg, ffprobe=None, ffplay=None):
        obj = super().__new__(cls, ffmpeg)
        obj.ffmpeg = str(ffmpeg)
        obj.ffprobe = str(ffprobe or ffmpeg.replace("ffmpeg", "ffprobe"))
        obj.ffplay = str(ffplay or ffmpeg.replace("ffmpeg", "ffplay"))
        return obj

    def __iter__(self):
        frame = inspect.currentframe().f_back
        if frame and frame.f_code.co_name == "list2cmdline":
            return super().__iter__()
        return iter((self.ffmpeg, self.ffprobe, self.ffplay))


def get_project_paths():
    """Get absolute paths to key project directories"""
    # Get the current script's directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Navigate up to project root if we're in app folder
    if os.path.basename(current_dir) == 'app':
        root_dir = os.path.dirname(current_dir)
    else:
        root_dir = current_dir
        
    # Build absolute paths
    return {
        'root': root_dir,
        'ffmpeg_bin': os.path.join(root_dir, 'ffmpeg_bin'),
        'models': os.path.join(root_dir, 'models'),
        'temp': os.path.join(root_dir, 'temp')
    }


def get_ffmpeg_path() -> FFmpegPaths:
    """
    Cross-platform ffmpeg resolution:
    1. Bundled ffmpeg_bin/ directory (checked first).
    2. System PATH via shutil.which().
    """
    exe_suffix = ".exe" if platform.system() == "Windows" else ""

    # 1. Bundled binary
    bundled = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "ffmpeg_bin", f"ffmpeg{exe_suffix}"
    )
    if os.path.isfile(bundled):
        probe = os.path.join(os.path.dirname(bundled), f"ffprobe{exe_suffix}")
        play = os.path.join(os.path.dirname(bundled), f"ffplay{exe_suffix}")
        return FFmpegPaths(bundled, probe, play)

    # 2. PATH lookup
    found = shutil.which("ffmpeg")
    if found:
        return FFmpegPaths(found)

    # Fallback for legacy behavior
    return FFmpegPaths(f"ffmpeg{exe_suffix}")


def get_file_sha256(file_path: str, prefix_len: int = 16) -> str:
    """
    Compute SHA-256 hash of a file for traceability.
    Returns prefix_len hex characters (default 16), or 'unknown' on error/missing file.
    """
    if not file_path or not os.path.isfile(file_path):
        return "unknown"
    try:
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(1024 * 1024):
                h.update(chunk)
        full_hex = h.hexdigest()
        return full_hex[:prefix_len] if prefix_len else full_hex
    except Exception as e:
        logger.warning(f"Could not compute SHA-256 for {file_path}: {e}")
        return "unknown"


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

    def get_default_base_dir(self):
        """
        Get the default base directory for test results

        Returns:
            The base directory path
        """
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        default_base_dir = os.path.join(script_dir, "tests", "test_results")
        os.makedirs(default_base_dir, exist_ok=True)
        return default_base_dir

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
        except Exception:
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


def run_unit_tests(test_module=None):
    """
    Run unit tests for the application
    
    Args:
        test_module: Optional module name to test (e.g., 'app.tests.test_utils')
                    If None, runs all tests
    
    Returns:
        Success status (True if all tests passed)
    """
    try:
        import pytest
        args = []
        
        if test_module:
            args.append(test_module)
        else:
            args.append('tests/')
            
        # Add common pytest args
        args.extend(['-v'])
        
        # Run tests
        result = pytest.main(args)
        
        return result == 0
    except Exception as e:
        logger.error(f"Error running unit tests: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def validate_application_state(app_instance):
    """
    Validate that the application is in a consistent state
    
    Args:
        app_instance: Reference to the main application window or options_manager
        
    Returns:
        Dictionary with validation results (or bool if options_manager checked directly)
    """
    if hasattr(app_instance, "get_settings") or hasattr(app_instance, "get_all_settings"):
        try:
            settings = (
                app_instance.get_all_settings()
                if hasattr(app_instance, "get_all_settings")
                else app_instance.get_settings()
            )
        except AttributeError:
            settings = {}
        return isinstance(settings, dict)

    results = {
        'status': 'PASS',
        'issues': [],
        'components_checked': 0,
        'components_passed': 0
    }
    
    try:
        # Check that essential managers exist
        components = [
            ('file_mgr', 'File Manager'),
            ('capture_mgr', 'Capture Manager'),
            ('options_manager', 'Options Manager')
        ]
        
        for attr, name in components:
            results['components_checked'] += 1
            if not hasattr(app_instance, attr) or getattr(app_instance, attr) is None:
                results['issues'].append(f"Missing {name}")
                results['status'] = 'FAIL'
            else:
                results['components_passed'] += 1
                
        # Check that essential UI components exist
        ui_components = [
            ('setup_tab', 'Setup Tab'),
            ('capture_tab', 'Capture Tab'),
            ('analysis_tab', 'Analysis Tab'),
            ('results_tab', 'Results Tab'),
            ('options_tab', 'Options Tab'),
            ('help_tab', 'Help Tab')
        ]
        
        for attr, name in ui_components:
            results['components_checked'] += 1
            if not hasattr(app_instance, attr) or getattr(app_instance, attr) is None:
                results['issues'].append(f"Missing {name}")
                results['status'] = 'FAIL'
            else:
                results['components_passed'] += 1
                
        # Validate file manager operations
        if hasattr(app_instance, 'file_mgr') and app_instance.file_mgr:
            results['components_checked'] += 1
            try:
                # Test creating a temporary file
                temp_file = app_instance.file_mgr.get_temp_file()
                if not temp_file or not os.path.exists(os.path.dirname(temp_file)):
                    results['issues'].append("File Manager failed to create temporary file")
                    results['status'] = 'FAIL'
                else:
                    results['components_passed'] += 1
            except Exception as e:
                results['issues'].append(f"File Manager error: {str(e)}")
                results['status'] = 'FAIL'
                
        # Validate options manager
        if hasattr(app_instance, 'options_manager') and app_instance.options_manager:
            results['components_checked'] += 1
            try:
                # Test loading settings
                settings = app_instance.options_manager.get_all_settings()
                if settings is None:
                    results['issues'].append("Options Manager failed to load settings")
                    results['status'] = 'FAIL'
                else:
                    results['components_passed'] += 1
            except Exception as e:
                results['issues'].append(f"Options Manager error: {str(e)}")
                results['status'] = 'FAIL'
                
        # Check VMAF models
        results['components_checked'] += 1
        models_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
        if not os.path.exists(models_dir) or len(os.listdir(models_dir)) == 0:
            results['issues'].append("VMAF models directory is missing or empty")
            results['status'] = 'FAIL'
        else:
            results['components_passed'] += 1
            
        # Add overall summary
        results['pass_rate'] = f"{results['components_passed']}/{results['components_checked']}"
        
        return results
        
    except Exception as e:
        logger.error(f"Error validating application state: {str(e)}")
        results['status'] = 'ERROR'
        results['issues'].append(f"Validation error: {str(e)}")
        return results



def timestamp_string():
    """
    Generate timestamp string for file naming

    Returns:
        Formatted timestamp string
    """
    return datetime.now().strftime("%y%m%d_%H%M%S")


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
    """Return Windows startupinfo/creationflags to suppress console dialogs."""
    if platform.system() == "Windows":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0  # SW_HIDE
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return startupinfo, creationflags
    return None, 0


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
    startupinfo, creationflags = get_subprocess_startupinfo()
    env = os.environ.copy()
    if platform.system() == "Windows":
        env.update({
            "FFMPEG_HIDE_BANNER": "1",
            "AV_LOG_FORCE_NOCOLOR": "1"
        })

    logging.getLogger(__name__).debug(f"Running FFmpeg command: {' '.join(cmd)}")

    if input_data is not None:
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


def get_video_info(video_path: str) -> Optional[dict]:
    """
    Extract video metadata via ffprobe.
    Returns dictionary with metadata (including 'total_frames') or None on failure.
    """
    if not video_path:
        return None

    _, ffprobe, _ = get_ffmpeg_path()
    startupinfo, creationflags = get_subprocess_startupinfo()


    cmd = [
        ffprobe, "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", video_path,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT,
            startupinfo=startupinfo, creationflags=creationflags,
        )
        if result.returncode != 0:
            logger.error(f"FFprobe failed: {result.stderr}")
            return None

        data = json.loads(result.stdout)
        video_stream = next(
            (s for s in data.get("streams", []) if s.get("codec_type") == "video"), None
        )
        if video_stream is None:
            logger.error(f"No video stream found in {video_path}")
            return None

        # Parse frame rate safely without eval
        try:
            rate_str = str(video_stream.get("avg_frame_rate", "0/1"))
            fps = float(Fraction(rate_str)) if "/" in rate_str else float(rate_str)
        except Exception:
            fps = 0.0

        format_info = data.get("format", {})
        duration = float(format_info.get("duration", 0))

        frame_count = video_stream.get("nb_frames")
        if frame_count is not None:
            try:
                frame_count = int(frame_count)
            except (ValueError, TypeError):
                frame_count = None

        if frame_count is None or frame_count == 0:
            # Estimate from duration and fps
            if fps and duration:
                frame_count = int(round(fps * duration))
            else:
                frame_count = 0

        return {
            "path": video_path,
            "width": int(video_stream.get("width", 0)),
            "height": int(video_stream.get("height", 0)),
            "fps": fps,
            "frame_rate": fps,
            "duration": duration,
            "frame_count": frame_count,
            "total_frames": frame_count,   # alias required by BookendAligner
            "codec": video_stream.get("codec_name", ""),
            "pix_fmt": video_stream.get("pix_fmt", "unknown"),
        }
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as e:
        logger.error(f"Error getting video info for {video_path}: {e}")
        return None