import json
import logging
import os
import platform
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import QObject, pyqtSignal

# Now using the improved utility functions
from .utils import get_ffmpeg_path

logger = logging.getLogger(__name__)

class VMAFAnalyzer(QObject):
    """VMAF analyzer for measuring video quality with signals for UI integration"""
    analysis_progress = pyqtSignal(int)  # 0-100%
    analysis_complete = pyqtSignal(dict)  # VMAF results
    error_occurred = pyqtSignal(str)
    status_update = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.output_directory = None
        self.test_name = None
        self._process_lock = threading.Lock()
        self._current_process = None
        self._terminate_requested = False
        self.threads = 4  # Default number of threads for VMAF analysis
        # Default values for advanced options
        self.pool_method = "mean"  # Options: mean, min, harmonic_mean
        self.enable_motion_score = False
        self.enable_temporal_features = False
        self.feature_subsample = 1
        self.psnr_enabled = True
        self.ssim_enabled = True




    def set_options_from_manager(self, options_manager):
        """Set VMAF options from the options manager"""
        if not options_manager:
            logger.warning("No options manager provided, using default settings")
            return
            
        try:
            # Get VMAF settings
            vmaf_settings = options_manager.get_setting("vmaf")
            
            # Set threads from settings (default to 4 if not found)
            self.threads = vmaf_settings.get("threads", 4)
            
            # Set feature subsample (default to 1 if not found)
            self.feature_subsample = vmaf_settings.get("feature_subsample", 1)
            
            # Set other options
            self.pool_method = vmaf_settings.get("pool_method", "mean")
            self.enable_motion_score = vmaf_settings.get("enable_motion_score", False)
            self.enable_temporal_features = vmaf_settings.get("enable_temporal_features", False)
            self.psnr_enabled = vmaf_settings.get("psnr_enabled", True)
            self.ssim_enabled = vmaf_settings.get("ssim_enabled", True)
            
            logger.info(f"VMAF options set from manager: threads={self.threads}, "
                    f"feature_subsample={self.feature_subsample}, pool={self.pool_method}")
        except Exception as e:
            logger.error(f"Error setting VMAF options from manager: {e}")






    def set_options_manager(self, options_manager):
        """Set VMAF options from the options manager"""
        if not options_manager:
            logger.warning("No options manager provided, using default settings")
            return
            
        try:
            # Get VMAF settings
            vmaf_settings = options_manager.get_setting("vmaf")
            
            # Set threads from settings (default to 4 if not found)
            self.threads = vmaf_settings.get("threads", 4)
            
            # Set feature subsample (default to 1 if not found)
            self.feature_subsample = vmaf_settings.get("feature_subsample", 1)
            
            # Set other options
            self.pool_method = vmaf_settings.get("pool_method", "mean")
            self.enable_motion_score = vmaf_settings.get("enable_motion_score", False)
            self.enable_temporal_features = vmaf_settings.get("enable_temporal_features", False)
            self.psnr_enabled = vmaf_settings.get("psnr_enabled", True)
            self.ssim_enabled = vmaf_settings.get("ssim_enabled", True)
            
            logger.info(f"VMAF options set from manager: threads={self.threads}, "
                    f"feature_subsample={self.feature_subsample}, pool={self.pool_method}")
        except Exception as e:
            logger.error(f"Error setting VMAF options from manager: {e}")







    def set_output_directory(self, output_dir):
        """Set output directory for results"""
        self.output_directory = output_dir
        logger.info(f"Set output directory to: {self.output_directory}")

    def set_test_name(self, test_name):
        """Set test name for organizing results"""
        self.test_name = test_name
        logger.info(f"Set test name to: {test_name}")
        
    def set_advanced_options(self, pool_method="mean", enable_motion_score=False, 
                            enable_temporal_features=False, feature_subsample=1,
                            psnr_enabled=True, ssim_enabled=True):
        """Set advanced VMAF analysis options for fine-tuning"""
        self.pool_method = pool_method
        self.enable_motion_score = enable_motion_score
        self.enable_temporal_features = enable_temporal_features
        self.feature_subsample = feature_subsample
        self.psnr_enabled = psnr_enabled
        self.ssim_enabled = ssim_enabled
        
        logger.info(f"Set advanced VMAF options: pool={pool_method}, "
                    f"motion_score={enable_motion_score}, "
                    f"temporal={enable_temporal_features}, "
                    f"feature_subsample={feature_subsample}, "
                    f"psnr_enabled={psnr_enabled}, "
                    f"ssim_enabled={ssim_enabled}")

    def terminate_analysis(self):
        """Terminate running analysis"""
        self._terminate_requested = True
        if self._current_process:
            try:
                logger.info("Terminating VMAF analysis process")
                self._current_process.terminate()
                time.sleep(0.5)
                if self._current_process.poll() is None:
                    logger.info("Force killing VMAF analysis process")
                    self._current_process.kill()
            except Exception as e:
                logger.error(f"Error terminating VMAF process: {e}")

    def _prepare_ffmpeg_path(self, path):
        """Format a path for FFmpeg use in Windows"""
        if not path:
            return ""
            
        # First normalize to use forward slashes
        norm_path = str(Path(path).resolve()).replace('\\', '/')
        return norm_path

    def get_video_metadata(self, video_path, ffprobe_exe=None):
        """Extract comprehensive video metadata using FFprobe"""
        try:
            # Get FFprobe executable
            if not ffprobe_exe:
                _, ffprobe_exe, _ = get_ffmpeg_path()
            
            # Normalize path for FFprobe
            video_path_norm = self._prepare_ffmpeg_path(video_path)
            
            # Get detailed video information
            cmd = [
                ffprobe_exe,
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                video_path_norm
            ]
            
            # Setup subprocess for no window
            startupinfo = None
            creationflags = 0
            if platform.system() == 'Windows':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0
                if hasattr(subprocess, 'CREATE_NO_WINDOW'):
                    creationflags = subprocess.CREATE_NO_WINDOW
            
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
                
            info = json.loads(result.stdout)
            
            # Find video stream
            video_stream = next((s for s in info.get('streams', []) if s.get('codec_type') == 'video'), None)
            if not video_stream:
                logger.error(f"No video stream found in {video_path}")
                return None
                
            # Parse frame rate
            fr_str = video_stream.get('avg_frame_rate', '0/0')
            if '/' in fr_str:
                num, den = map(int, fr_str.split('/'))
                frame_rate = num / den if den else 0
            else:
                frame_rate = float(fr_str) if fr_str else 0
                
            # Get metadata
            metadata = {
                'path': video_path,
                'duration': float(info.get('format', {}).get('duration', 0)),
                'frame_rate': frame_rate,
                'width': int(video_stream.get('width', 0)),
                'height': int(video_stream.get('height', 0)),
                'pix_fmt': video_stream.get('pix_fmt', 'unknown'),
                'codec_name': video_stream.get('codec_name', 'unknown'),
                'bit_rate': int(info.get('format', {}).get('bit_rate', 0)),
                'nb_frames': int(video_stream.get('nb_frames', 0))
            }
            
            logger.info(f"Video metadata extracted: {metadata['width']}x{metadata['height']} @ {metadata['frame_rate']}fps")
            return metadata
            
        except Exception as e:
            logger.error(f"Error extracting video metadata: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def analyze_videos(self, reference_path, distorted_path, model="vmaf_v0.6.1", duration=None):
        """Run VMAF analysis with the correct command format and properly escaped paths"""
        
        import psutil
        cpu_count = psutil.cpu_count(logical=True)
        print(f"System has {cpu_count} logical CPUs")
        print(f"Current CPU usage: {psutil.cpu_percent(interval=0.1)}%")
        
        print("VMAF ANALYZER STARTING - DIRECT CONSOLE OUTPUT")
        with self._process_lock:  # Use lock to prevent duplicate processing
            original_dir = os.getcwd()
            try:
                self._terminate_requested = False
                self.status_update.emit(f"Analyzing videos with model: {model}")
                logger.info(f"Starting VMAF analysis with model: {model}")

                # Verify files
                if not os.path.exists(reference_path):
                    error_msg = f"Reference video not found: {reference_path}"
                    logger.error(error_msg)
                    self.error_occurred.emit(error_msg)
                    return None

                if not os.path.exists(distorted_path):
                    error_msg = f"Distorted video not found: {distorted_path}"
                    logger.error(error_msg)
                    self.error_occurred.emit(error_msg)
                    return None

                # Log basic video information to help with debugging
                logger.info(f"VMAF Reference: {reference_path}")
                logger.info(f"VMAF Distorted: {distorted_path}")

                # Create output directory
                output_dir = self.output_directory
                if not output_dir:
                    output_dir = os.path.dirname(reference_path)

                # Create a consistent timestamp for all files
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

                # Get test name or use "Test" as default
                test_name = self.test_name or "Test"

                # Determine if we should use an existing directory
                # Check if reference or distorted paths are already in a test directory
                parent_dir = os.path.dirname(reference_path)

                if test_name and test_name in parent_dir:
                    # If reference path is already in a test directory, use that directory
                    test_dir = parent_dir
                    logger.info(f"Using existing test directory: {test_dir}")
                else:
                    # Create a test results directory with timestamp
                    test_dir = os.path.join(output_dir, f"{test_name}_{timestamp}")
                    os.makedirs(test_dir, exist_ok=True)
                    logger.info(f"Created test results directory: {test_dir}")

                # Find paths to FFmpeg executables using the utility function
                ffmpeg_exe, ffprobe_exe, ffplay_exe = get_ffmpeg_path()

                # Create consistent filenames with test name and timestamp
                vmaf_filename = f"{test_name}_{timestamp}_vmaf.json"
                psnr_filename = f"{test_name}_{timestamp}_psnr.txt"
                ssim_filename = f"{test_name}_{timestamp}_ssim.txt"

                # Create full paths with proper OS handling
                json_path = os.path.join(test_dir, vmaf_filename)
                psnr_path = os.path.join(test_dir, psnr_filename)
                ssim_path = os.path.join(test_dir, ssim_filename)

                # Get video metadata to estimate progress
                self.get_video_metadata(reference_path, ffprobe_exe)
                dist_meta = self.get_video_metadata(distorted_path, ffprobe_exe)
                
                # Estimate total frames for progress tracking
                total_frames = 0
                if dist_meta:
                    if dist_meta.get('nb_frames', 0) > 0:
                        total_frames = dist_meta.get('nb_frames')
                    elif dist_meta.get('frame_rate', 0) > 0 and dist_meta.get('duration', 0) > 0:
                        total_frames = int(dist_meta.get('frame_rate') * dist_meta.get('duration'))
                
                logger.info(f"Estimated total frames: {total_frames}")

                # Make sure model has .json extension if not already
                if model is None:
                    # Use a default model if none is provided
                    model = "vmaf_v0.6.1"
                    logger.info(f"No model specified, using default model: {model}")

                # Format model string correctly for the 'model' parameter
                # More compatible model format for FFmpeg 7.1.1
                if not model.startswith("path=") and not any(sep in model for sep in ["/", "\\"]):
                    if model in ["vmaf_v0.6.1", "vmaf_4k_v0.6.1", "vmaf_b_v0.6.3"]:
                        model_name = f"model={model}"  # Use standard format for built-in models
                    else:
                        model_name = f"path={model}"   # Use path format for custom models
                else:
                    model_name = f"path={model}"  # Already a path

                # Use current directory as a base for relative paths
                os.getcwd()
                
                # Check if we need to change directory
                if platform.system() == 'Windows':
                    # Get the common base directory to use for relative paths
                    base_dir = os.path.commonpath([reference_path, distorted_path, json_path])
                    os.chdir(base_dir)
                    
                    # Calculate relative paths from the base directory
                    ref_rel_path = os.path.relpath(reference_path, base_dir)
                    dist_rel_path = os.path.relpath(distorted_path, base_dir)
                    json_rel_path = os.path.relpath(json_path, base_dir)
                    
                    # Update paths to use forward slashes
                    ref_rel_path = ref_rel_path.replace('\\', '/')
                    dist_rel_path = dist_rel_path.replace('\\', '/')
                    json_rel_path = json_rel_path.replace('\\', '/')
                    
                    logger.info(f"Changed directory to: {base_dir}")
                    logger.info(f"Using relative reference path: {ref_rel_path}")
                    logger.info(f"Using relative distorted path: {dist_rel_path}")
                    logger.info(f"Using relative JSON path: {json_rel_path}")
                else:
                    # On non-Windows systems, we can use the paths as they are
                    ref_rel_path = reference_path
                    dist_rel_path = distorted_path
                    json_rel_path = json_path
                
                # Set up VMAF options with advanced parameters
                vmaf_options = [
                    f"log_path={json_rel_path}",
                    "log_fmt=json",
                    # Use the exact format from your working command
                    f"model=version={model}" if not any(sep in model for sep in ["/", "\\"]) else f"model=path={model}",
                    f"n_threads={self.threads if hasattr(self, 'threads') else 4}",
                    f"n_subsample={self.feature_subsample}"
]
                
                # Add pool method if not using default
                if self.pool_method != "mean":
                    vmaf_options.append(f"pool={self.pool_method}")
                    vmaf_options.append("psnr=1")
                    vmaf_options.append("ssim=1")
                # Enable motion score if requested
                if self.enable_motion_score:
                    vmaf_options.append("feature=name=motion:enable=1")
                
                # Enable temporal features if requested
                if self.enable_temporal_features:
                    vmaf_options.append("feature=name=vif_scale0:enable=1")
                    vmaf_options.append("feature=name=vif_scale1:enable=1")
                    vmaf_options.append("feature=name=vif_scale2:enable=1")
                    vmaf_options.append("feature=name=vif_scale3:enable=1")
                    vmaf_options.append("feature=name=adm2:enable=1")
                    vmaf_options.append("feature=name=motion:enable=1")
                    
                    # Only add motion feature if it's not already added and motion score is enabled
                    if self.enable_motion_score:
                        vmaf_options.append("feature=name=motion:enable=1")                   
                    
                
                # Build the filter option
                vmaf_filter = f"libvmaf={':'.join(vmaf_options)}"
                # Log the actual filter string for debugging
                logger.info(f"VMAF filter: {vmaf_filter}")
                
                # Use optimized VMAF command with relative paths and quoted filter
                optimized_cmd = [
                    ffmpeg_exe,
                    "-hide_banner",
                    "-loglevel", "info",  # Use info level to see progress but not too verbose
                    "-i", dist_rel_path,
                    "-i", ref_rel_path,
                    "-lavfi", vmaf_filter,
                    "-f", "null", "-"
                ]

                logger.info(f"VMAF Command: {' '.join(optimized_cmd)}")
                
                # Create startupinfo to suppress Windows error dialogs
                startupinfo = None
                creationflags = 0
                env = os.environ.copy()

                if platform.system() == 'Windows':
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = 0  # SW_HIDE
                    if hasattr(subprocess, 'CREATE_NO_WINDOW'):
                        creationflags = subprocess.CREATE_NO_WINDOW
                    # Add environment variables to suppress FFmpeg dialogs
                    env.update({
                        "FFMPEG_HIDE_BANNER": "1",
                        "AV_LOG_FORCE_NOCOLOR": "1"
                    })

                # Emit initial progress
                self.analysis_progress.emit(0)
                self.status_update.emit("Starting VMAF analysis...")

                try:
                    # Start the process
                    self._current_process = subprocess.Popen(
                        optimized_cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        bufsize=1,
                        startupinfo=startupinfo,
                        creationflags=creationflags,
                        env=env
                    )

                    # Monitor progress in real-time
                    stderr_lines = []
                    last_progress_time = time.time()
                    frame_count = 0
                    
                    # Read stderr line by line to capture progress
                    for line in iter(self._current_process.stderr.readline, ''):
                        if self._terminate_requested:
                            logger.info("VMAF analysis termination requested")
                            break
                            
                        stderr_lines.append(line)
                        
                        # Log progress line if it contains useful information
                        if "frame=" in line or "speed=" in line or "VMAF score" in line:
                            logger.info(f"VMAF progress: {line.strip()}")
                        
                        # Extract frame count for progress reporting
                        if "frame=" in line:
                            try:
                                frame_info = line.split("frame=")[1].split()[0].strip()
                                if frame_info.isdigit():
                                    frame_count = int(frame_info)
                                    
                                    # Calculate progress percentage
                                    if total_frames > 0:
                                        progress = min(95, int((frame_count / total_frames) * 100))
                                        
                                        # Only update UI every 0.5 seconds to avoid overwhelming it
                                        current_time = time.time()
                                        if current_time - last_progress_time > 0.5:
                                            self.analysis_progress.emit(progress)
                                            last_progress_time = current_time
                                            
                                            # Also update status text with frame info
                                            self.status_update.emit(f"Processing frame {frame_count}/{total_frames} ({progress}%)")
                            except Exception as e:
                                logger.debug(f"Error parsing frame progress: {str(e)}")
                        
                        # Check if process is still running
                        if self._current_process.poll() is not None:
                            logger.info("VMAF process completed")
                            break
                    
                    # Get any remaining output
                    remaining_stderr = self._current_process.stderr.read()
                    if remaining_stderr:
                        stderr_lines.append(remaining_stderr)
                    
                    # Wait for process to complete
                    returncode = self._current_process.wait(timeout=10)
                    error = ''.join(stderr_lines)
                    
                    # Process completed
                    logger.info(f"VMAF process completed with return code: {returncode}")
                    self._current_process = None
                    
                    if self._terminate_requested:
                        error_msg = "VMAF analysis was terminated by user"
                        logger.warning(error_msg)
                        self.error_occurred.emit(error_msg)
                        return None
                        
                    if returncode != 0:
                        error_msg = f"VMAF analysis failed with return code {returncode}: {error}"
                        logger.error(error_msg)
                        self.error_occurred.emit(error_msg)
                        return None
                    
                except subprocess.TimeoutExpired:
                    error_msg = "VMAF analysis timed out"
                    logger.error(error_msg)
                    self.error_occurred.emit(error_msg)
                    
                    # Clean up the process
                    if self._current_process:
                        try:
                            self._current_process.kill()
                            self._current_process.wait(timeout=5)
                        except:
                            pass
                        self._current_process = None
                    return None
                
                except Exception as e:
                    error_msg = f"Error running VMAF analysis: {str(e)}"
                    logger.error(error_msg)
                    self.error_occurred.emit(error_msg)
                    
                    # Clean up the process
                    if self._current_process:
                        try:
                            self._current_process.kill()
                            self._current_process.wait(timeout=5)
                        except:
                            pass
                        self._current_process = None
                    return None
                
                finally:
                    # Ensure process is cleaned up
                    if self._current_process:
                        try:
                            if self._current_process.poll() is None:
                                self._current_process.terminate()
                                time.sleep(0.5)
                                if self._current_process.poll() is None:
                                    self._current_process.kill()
                        except:
                            pass
                        self._current_process = None

                # Now run PSNR and SSIM analyses if enabled
                if self.psnr_enabled or self.ssim_enabled:
                    self.status_update.emit("VMAF completed, running PSNR/SSIM analysis...")
                    
                    # Use the same relative path approach for PSNR/SSIM
                    if platform.system() == 'Windows':
                        psnr_rel_path = os.path.relpath(psnr_path, base_dir).replace('\\', '/')
                        ssim_rel_path = os.path.relpath(ssim_path, base_dir).replace('\\', '/')
                    else:
                        psnr_rel_path = psnr_path
                        ssim_rel_path = ssim_path
                    
                    psnr_ssim_success = self._run_psnr_ssim_analysis(
                        ffmpeg_exe, 
                        dist_rel_path, 
                        ref_rel_path, 
                        psnr_rel_path if self.psnr_enabled else None, 
                        ssim_rel_path if self.ssim_enabled else None
                    )
                    
                    if not psnr_ssim_success:
                        logger.warning("PSNR/SSIM analysis failed, but continuing with VMAF results")
                else:
                    logger.info("Skipping PSNR/SSIM analysis as they are disabled")

                # Return to original directory before parsing results
                os.chdir(original_dir)
                
                # Parse the VMAF results
                return self._parse_vmaf_results(json_path, 
                                               psnr_path if self.psnr_enabled else None, 
                                               ssim_path if self.ssim_enabled else None, 
                                               distorted_path, reference_path)

            except Exception as e:
                error_msg = f"Error in VMAF analysis: {str(e)}"
                logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                import traceback
                logger.error(traceback.format_exc())
                return None
            finally:
                # Always restore original directory
                try:
                    if original_dir != os.getcwd():
                        os.chdir(original_dir)
                except Exception as e:
                    logger.warning(f"Failed to restore original directory: {e}")











    def _parse_vmaf_results(self, json_path, psnr_path, ssim_path, distorted_path, reference_path):
        """Parse VMAF results from the output files"""
        try:
            # Check if output files exist
            if not os.path.exists(json_path):
                error_msg = "VMAF analysis completed but JSON output file not found"
                logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                return None

            # Parse VMAF results from JSON
            try:
                with open(json_path, 'r') as f:
                    vmaf_data = json.load(f)

                # Extract VMAF score
                vmaf_score = None
                psnr_score = None
                ssim_score = None

                if "pooled_metrics" in vmaf_data:
                    # New format
                    try:
                        pool = vmaf_data["pooled_metrics"]
                        if "vmaf" in pool:
                            vmaf_score = pool["vmaf"]["mean"]
                        if "psnr" in pool:
                            psnr_score = pool["psnr"]["mean"]
                        if "psnr_y" in pool:  # Sometimes it's labeled as psnr_y
                            psnr_score = pool["psnr_y"]["mean"]
                        if "ssim" in pool:
                            ssim_score = pool["ssim"]["mean"]
                        if "ssim_y" in pool:  # Sometimes it's labeled as ssim_y
                            ssim_score = pool["ssim_y"]["mean"]
                    except Exception as e:
                        logger.error(f"Error parsing VMAF metrics from pooled_metrics: {str(e)}")

                # Fallback to frames if pooled metrics don't exist
                elif "frames" in vmaf_data:
                    # Extract scores from frames
                    frames = vmaf_data["frames"]
                    if frames:
                        vmaf_values = []
                        psnr_values = []
                        ssim_values = []

                        for frame in frames:
                            if "metrics" in frame:
                                metrics = frame["metrics"]
                                if "vmaf" in metrics:
                                    vmaf_values.append(metrics["vmaf"])
                                if "psnr" in metrics or "psnr_y" in metrics:
                                    psnr_values.append(metrics.get("psnr", metrics.get("psnr_y", 0)))
                                if "ssim" in metrics or "ssim_y" in metrics:
                                    ssim_values.append(metrics.get("ssim", metrics.get("ssim_y", 0)))

                        # Calculate averages
                        if vmaf_values:
                            vmaf_score = sum(vmaf_values) / len(vmaf_values)
                        if psnr_values:
                            psnr_score = sum(psnr_values) / len(psnr_values)
                        if ssim_values:
                            ssim_score = sum(ssim_values) / len(ssim_values)

                # Try to get PSNR from separate file if not found in VMAF results
                if (psnr_score is None or psnr_score == 0) and os.path.exists(psnr_path):
                    try:
                        with open(psnr_path, 'r') as f:
                            psnr_lines = f.readlines()
                            # Look for average PSNR line
                            psnr_avg_line = None
                            for line in psnr_lines:
                                if "average" in line.lower() and "psnr" in line.lower():
                                    psnr_avg_line = line
                                    break
                            
                            # Try to extract the PSNR value
                            if psnr_avg_line:
                                import re
                                match = re.search(r'(\d+\.\d+)', psnr_avg_line)
                                if match:
                                    psnr_score = float(match.group(1))
                    except Exception as e:
                        logger.warning(f"Error parsing PSNR from file: {str(e)}")

                # Try to get SSIM from separate file if not found in VMAF results
                if (ssim_score is None or ssim_score == 0) and os.path.exists(ssim_path):
                    try:
                        with open(ssim_path, 'r') as f:
                            ssim_lines = f.readlines()
                            # Look for average SSIM line
                            ssim_avg_line = None
                            for line in ssim_lines:
                                if "average" in line.lower() and "ssim" in line.lower():
                                    ssim_avg_line = line
                                    break
                            
                            # Try to extract the SSIM value
                            if ssim_avg_line:
                                import re
                                match = re.search(r'(\d+\.\d+)', ssim_avg_line)
                                if match:
                                    ssim_score = float(match.group(1))
                    except Exception as e:
                        logger.warning(f"Error parsing SSIM from file: {str(e)}")

                # Log results
                logger.info(f"VMAF Score: {vmaf_score}")
                logger.info(f"PSNR Score: {psnr_score}")
                logger.info(f"SSIM Score: {ssim_score}")

                # Store raw results for potential detailed analysis
                raw_results = vmaf_data

                # Get FFprobe path
                _, ffprobe_exe, _ = get_ffmpeg_path()
                
                # Get video metadata
                dist_meta = self.get_video_metadata(distorted_path, ffprobe_exe)
                self.get_video_metadata(reference_path, ffprobe_exe)
 
 
                # Add a direct call to ffprobe to ensure we get accurate frame count and duration
                if dist_meta and (dist_meta.get('frame_count', 0) == 0 or dist_meta.get('duration', 0) == 0):
                    try:
                        # Use ffprobe to get exact frame count and duration
                        cmd = [
                            ffprobe_exe,
                            "-v", "error",
                            "-select_streams", "v:0",
                            "-count_frames",
                            "-show_entries", "stream=nb_read_frames,duration,r_frame_rate",
                            "-of", "default=noprint_wrappers=1:nokey=1",
                            self._prepare_ffmpeg_path(distorted_path)
                        ]
                        
                        startupinfo = None
                        if platform.system() == 'Windows':
                            startupinfo = subprocess.STARTUPINFO()
                            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                        
                        result = subprocess.run(cmd, capture_output=True, text=True, startupinfo=startupinfo)
                        
                        if result.returncode == 0:
                            # Parse the output - should be duration and frame count on separate lines
                            output_lines = result.stdout.strip().split('\n')
                            if len(output_lines) >= 3:
                                # Extract duration from first line
                                duration = float(output_lines[0])
                                # Extract frame count from second line
                                frame_count = int(output_lines[1])
                                # Extract framerate from third line (typically in format like "30000/1001")
                                fps_str = output_lines[2]
                                if '/' in fps_str:
                                    num, den = map(int, fps_str.split('/'))
                                    fps = num / den if den > 0 else 0
                                else:
                                    fps = float(fps_str) if fps_str else 0
                                
                                # Update dist_meta
                                if dist_meta:
                                    dist_meta['duration'] = duration
                                    dist_meta['nb_frames'] = frame_count
                                    dist_meta['frame_rate'] = fps
                                    
                                logger.info(f"Updated video metadata from ffprobe: duration={duration}s, frames={frame_count}, fps={fps}")
                        else:
                            logger.warning(f"Failed to get accurate frame count and duration: {result.stderr}")
                    except Exception as e:
                        logger.error(f"Error getting accurate frame count and duration: {str(e)}")
                
                
 
 
 
 
 
 
 
 
 
 
 
 
 
 
                
                # Extract video dimensions if available
                width = 0
                height = 0
                if dist_meta:
                    width = dist_meta.get('width', 0)
                    height = dist_meta.get('height', 0)
                
                # Get just filenames for path references
                os.path.basename(json_path) if json_path else ""
                psnr_filename = os.path.basename(psnr_path) if psnr_path else ""
                ssim_filename = os.path.basename(ssim_path) if ssim_path else ""
                reference_filename = os.path.basename(reference_path) if reference_path else ""
                distorted_filename = os.path.basename(distorted_path) if distorted_path else ""
                
                # Create PSNR and SSIM status text
                psnr_status = psnr_filename if os.path.exists(psnr_path) else "Not Available"
                ssim_status = ssim_filename if os.path.exists(ssim_path) else "Not Available"
                
                # Extract model information from raw results or use a default value
                model_info = "unknown"
                if "model" in vmaf_data:
                    model_info = vmaf_data["model"]
                elif "version" in vmaf_data:
                    model_info = vmaf_data["version"]
                    
                    
                # Calculate frame count and duration
                frame_count = 0
                duration = 0
                fps = 0
                width = 0
                height = 0  
                if dist_meta:
                    frame_count = dist_meta.get('nb_frames', 0)
                    duration = dist_meta.get('duration', 0)
                    fps = dist_meta.get('frame_rate', 0)
                    width = dist_meta.get('width', 0)   
                    height = dist_meta.get('height', 0)
                    
                    # Estimate if not available
                    if frame_count == 0 and fps > 0 and duration > 0:
                        frame_count = int(fps * duration)

                # Return results with consistent path format and additional metadata
                results = {
                    'vmaf_score': vmaf_score,
                    'psnr_score': psnr_status,  # Changed to use filename or status
                    'ssim_score': ssim_status,  # Changed to use filename or status
                    'json_path': json_path,
                    'psnr_log': psnr_path,
                    'ssim_log': ssim_path,
                    'reference_video': reference_filename,  # Changed to just filename
                    'distorted_video': distorted_filename,  # Changed to just filename
                    'raw_results': raw_results,
                    'metadata': {
                        'test': {
                            'model': model_info,
                            'date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            'test_name': self.test_name or "Unnamed Test"
                        },
                        'video': {
                            'width': width,
                            'height': height,
                            'frame_count': frame_count,
                            'duration': duration,
                            'fps': fps,
                            'format': dist_meta.get('pix_fmt', 'unknown') if dist_meta else 'unknown',
                            'codec': dist_meta.get('codec_name', 'unknown') if dist_meta else 'unknown',
                            'bitrate': dist_meta.get('bit_rate', 0) if dist_meta else 0
                        },
                        'vmaf_options': {
                            'pool_method': self.pool_method,
                            'feature_subsample': self.feature_subsample,
                            'motion_score': self.enable_motion_score,
                            'temporal_features': self.enable_temporal_features
                        }
                    }
                }                    
                                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
                
                # Return results with consistent path format and additional metadata
                results = {
                    'vmaf_score': vmaf_score,
                    'psnr_score': psnr_status,  # Changed to use filename or status
                    'ssim_score': ssim_status,  # Changed to use filename or status
                    'json_path': json_path,
                    'psnr_log': psnr_path,
                    'ssim_log': ssim_path,
                    'reference_video': reference_filename,  # Changed to just filename
                    'distorted_video': distorted_filename,  # Changed to just filename
                    'raw_results': raw_results,
                    'model': model_info,
                    'width': width,
                    'height': height
                }

                # Set progress to 100%
                self.analysis_progress.emit(100)
                self.status_update.emit(f"VMAF analysis complete! Score: {vmaf_score:.2f}")

                # Handle file cleanup properly
                if 'distorted_path' in results:
                    # Get the aligned capture file path
                    aligned_capture = results['distorted_path']

                    # Get the original capture file if it exists (before alignment)
                    original_capture = None
                    if "aligned" in aligned_capture.lower():
                        # Try to find the original unaligned file
                        original_path = aligned_capture.replace("_aligned", "")
                        if os.path.exists(original_path):
                            original_capture = original_path

                    # Log the file status
                    logger.info(f"Keeping aligned capture file for results: {aligned_capture}")

                    # Delete the original unaligned file if it exists
                    if original_capture and os.path.exists(original_capture):
                        try:
                            logger.info(f"Deleting original unaligned capture file: {original_capture}")
                            os.remove(original_capture)
                        except Exception as cleanup_error:
                            logger.warning(f"Could not delete original capture file: {cleanup_error}")

                # Return results
                self.analysis_complete.emit(results)
                return results

            except Exception as e:
                error_msg = f"Error parsing VMAF results: {str(e)}"
                logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                import traceback
                logger.error(traceback.format_exc())
                return None

        except Exception as e:
            error_msg = f"Error processing VMAF results: {str(e)}"
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            import traceback
            logger.error(traceback.format_exc())
            return None















    def _run_psnr_ssim_analysis(self, ffmpeg_exe, distorted_path, reference_path, psnr_path, ssim_path):
        """Run PSNR and SSIM analysis separately using absolute paths"""
        try:
            # Set up startupinfo to suppress dialog windows
            startupinfo = None
            creationflags = 0
            env = os.environ.copy()

            # Add environment variables to suppress FFmpeg dialogs
            env.update({
                "FFMPEG_HIDE_BANNER": "1",
                "AV_LOG_FORCE_NOCOLOR": "1",
                "SDL_VIDEODRIVER": "dummy",
                "SDL_AUDIODRIVER": "dummy"
            })

            if platform.system() == 'Windows':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0  # SW_HIDE
                creationflags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0x08000000
            
            # Calculate feature subsample parameter for PSNR/SSIM
            subsample_param = f":max_samples={self.feature_subsample}" if self.feature_subsample > 1 else ""
            
            results_ok = [False, False]  # [psnr_ok, ssim_ok]
            
            # Run PSNR analysis if path is provided
            if psnr_path:
                logger.info("Running PSNR analysis...")
                self.status_update.emit("Running PSNR analysis...")
                psnr_cmd = [
                    ffmpeg_exe,
                    "-hide_banner",
                    "-i", distorted_path,
                    "-i", reference_path,
                    "-lavfi", f"psnr=stats_file={psnr_path}{subsample_param}",
                    "-f", "null", "-"
                ]

                logger.info(f"PSNR command: {' '.join(psnr_cmd)}")
                psnr_result = subprocess.run(
                    psnr_cmd,
                    check=False, 
                    capture_output=True, 
                    startupinfo=startupinfo,
                    creationflags=creationflags,
                    env=env,
                    timeout=120  # 2 minute timeout
                )
                
                if psnr_result.returncode != 0:
                    logger.warning(f"PSNR analysis failed: {psnr_result.stderr}")
                else:
                    logger.info("PSNR analysis completed successfully")
                    results_ok[0] = True

            # Run SSIM analysis if path is provided
            if ssim_path:
                logger.info("Running SSIM analysis...")
                self.status_update.emit("Running SSIM analysis...")
                ssim_cmd = [
                    ffmpeg_exe,
                    "-hide_banner",
                    "-i", distorted_path,
                    "-i", reference_path,
                    "-lavfi", f"ssim=stats_file={ssim_path}{subsample_param}",
                    "-f", "null", "-"
                ]

                logger.info(f"SSIM command: {' '.join(ssim_cmd)}")
                ssim_result = subprocess.run(
                    ssim_cmd,
                    check=False, 
                    capture_output=True,
                    startupinfo=startupinfo,
                    creationflags=creationflags,
                    env=env,
                    timeout=120  # 2 minute timeout
                )
                
                if ssim_result.returncode != 0:
                    logger.warning(f"SSIM analysis failed: {ssim_result.stderr}")
                else:
                    logger.info("SSIM analysis completed successfully")
                    results_ok[1] = True

            # Consider the operation successful if at least one metric was calculated
            # or if neither was requested
            return (results_ok[0] or not psnr_path) and (results_ok[1] or not ssim_path)
            
        except subprocess.TimeoutExpired:
            logger.warning(f"PSNR/SSIM analysis timed out")
            return False
        except Exception as e:
            logger.warning(f"Error running PSNR/SSIM analysis: {str(e)}")
            return False






























