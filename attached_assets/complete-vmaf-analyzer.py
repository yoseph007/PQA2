import os
import logging
import json
import subprocess
import re
import time
from datetime import datetime
from PyQt5.QtCore import QObject, pyqtSignal, QThread, Qt
from .utils import normalize_path

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

    def set_output_directory(self, output_dir):
        """Set output directory for results"""
        self.output_directory = normalize_path(output_dir)
        logger.info(f"Set output directory to: {self.output_directory}")

    def set_test_name(self, test_name):
        """Set test name for organizing results"""
        self.test_name = test_name
        logger.info(f"Set test name to: {test_name}")

    def analyze_videos(self, reference_path, distorted_path, model="vmaf_v0.6.1", duration=None):
        """Run VMAF analysis with the correct command format and properly escaped paths"""
        current_dir = os.getcwd()
        try:
            self.status_update.emit(f"Analyzing videos with model: {model}")

            # Normalize paths for consistency
            reference_path = reference_path.replace("/", "\\")
            distorted_path = distorted_path.replace("/", "\\")

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
            using_existing_dir = False

            if test_name and test_name in parent_dir:
                # If reference path is already in a test directory, use that directory
                test_dir = parent_dir
                using_existing_dir = True
                logger.info(f"Using existing test directory: {test_dir}")
            else:
                # Create a test results directory with timestamp
                test_dir = os.path.join(output_dir, f"{test_name}_{timestamp}")
                os.makedirs(test_dir, exist_ok=True)
                logger.info(f"Created test results directory: {test_dir}")

            # Create consistent filenames with test name and timestamp
            vmaf_filename = f"{test_name}_{timestamp}_vmaf.json"
            csv_filename = f"{test_name}_{timestamp}_vmaf.csv"
            psnr_filename = f"{test_name}_{timestamp}_psnr.txt"
            ssim_filename = f"{test_name}_{timestamp}_ssim.txt"

            # Create full paths with forward slashes for FFmpeg
            json_path = os.path.join(test_dir, vmaf_filename).replace("\\", "/")
            csv_path = os.path.join(test_dir, csv_filename).replace("\\", "/")
            psnr_path = os.path.join(test_dir, psnr_filename).replace("\\", "/")
            ssim_path = os.path.join(test_dir, ssim_filename).replace("\\", "/")

            # For command line logging, save a copy
            vmaf_cmd_log = os.path.join(test_dir, f"{test_name}_{timestamp}_vmaf_command.txt").replace("\\", "/")

            # Convert input paths to forward slashes for FFmpeg
            reference_path_ffmpeg = reference_path.replace("\\", "/")
            distorted_path_ffmpeg = distorted_path.replace("\\", "/")

            # Duration parameter if needed
            duration_cmd = []
            if duration and duration > 0:
                duration_cmd = ["-t", str(duration)]
                self.status_update.emit(f"Analyzing {duration}s of video")

            # Make sure model has .json extension if not already
            model_name = model
            if not model.endswith('.json'):
                model_name = f"{model}.json"
            
            # Find paths to FFmpeg executables using the utility function
            from .utils import get_ffmpeg_path
            ffmpeg_exe, ffprobe_exe, ffplay_exe = get_ffmpeg_path()
            
            # Find the model path in models directory
            current_dir = os.path.dirname(os.path.abspath(__file__))
            
            # Check if we're in the app directory or at the root
            if os.path.basename(current_dir) == "app":
                root_dir = os.path.dirname(current_dir)  # Go up one level if in app directory
            else:
                root_dir = current_dir  # We're already at root
                
            models_dir = os.path.join(root_dir, "models")
            model_path = os.path.join(models_dir, model_name)
            
            logger.info(f"Looking for VMAF model at: {model_path}")
            
            # Check if model file exists in models directory
            if not os.path.exists(model_path):
                logger.warning(f"VMAF model file not found at {model_path}, using default path")
                model_param = ""  # Don't specify model_path, let FFmpeg use default
            else:
                logger.info(f"Using VMAF model from: {model_path}")
                # Ensure path uses forward slashes for FFmpeg
                model_path_ffmpeg = model_path.replace("\\", "/")
                model_param = f"model_path={model_path_ffmpeg}:"

            # Change directory to the test directory for relative paths
            os.chdir(test_dir)
            
            # Use just filenames after changing directory (this avoids Windows path character issues)
            # These are relative to the test_dir we just changed to
            rel_vmaf_json = vmaf_filename
            rel_vmaf_csv = csv_filename 
            rel_psnr_txt = psnr_filename
            rel_ssim_txt = ssim_filename
            
            logger.info("Working directory changed to test directory for relative paths")
            logger.info(f"Using relative paths: {rel_vmaf_json}, {rel_vmaf_csv}, {rel_psnr_txt}, {rel_ssim_txt}")

            # Try the simplest format possible first - just use basic libvmaf with relative paths
            try:
                logger.info("Trying basic VMAF command with relative paths...")
                # Use -lavfi instead of -filter_complex for simpler syntax
                basic_cmd = [
                    ffmpeg_exe,
                    "-hide_banner",
                    "-i", distorted_path_ffmpeg,
                    "-i", reference_path_ffmpeg,
                    "-lavfi", f"libvmaf=log_path={rel_vmaf_json}:log_fmt=json",
                    "-f", "null", "-"
                ]
                
                logger.info(f"Command: {' '.join(basic_cmd)}")
                process = subprocess.Popen(
                    basic_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1
                )
                
                # Monitor progress
                output, error = process.communicate()
                returncode = process.returncode
                
                if returncode == 0:
                    logger.info("Basic VMAF command succeeded!")
                    # Now try to run PSNR and SSIM separately with relative paths
                    self._run_psnr_ssim_analysis(ffmpeg_exe, distorted_path_ffmpeg, reference_path_ffmpeg, rel_psnr_txt, rel_ssim_txt)
                    
                    # Build full paths for the results
                    json_path_full = os.path.join(test_dir, rel_vmaf_json).replace("\\", "/")
                    psnr_path_full = os.path.join(test_dir, rel_psnr_txt).replace("\\", "/")
                    ssim_path_full = os.path.join(test_dir, rel_ssim_txt).replace("\\", "/")
                    
                    return self._parse_vmaf_results(json_path_full, psnr_path_full, ssim_path_full, distorted_path, reference_path, current_dir)
                else:
                    logger.error(f"Basic VMAF command failed: {error}")
                    
                    # Try with full filter complex, but using relative paths
                    logger.info("Trying with complete filter complex but using relative paths...")
                    filter_str = (
                        "[0:v]setpts=PTS-STARTPTS,split=2[ref1][ref2];"
                        "[1:v]setpts=PTS-STARTPTS,split=2[dist1][dist2];"
                        f"[ref1][dist1]libvmaf=log_path={rel_vmaf_json}:log_fmt=json;"
                        f"[ref2][dist2]libvmaf=log_path={rel_vmaf_csv}:log_fmt=csv;"
                        f"[0:v][1:v]psnr=stats_file={rel_psnr_txt};"
                        f"[0:v][1:v]ssim=stats_file={rel_ssim_txt}"
                    )
                    
                    # Use shell=True on Windows for proper handling of complex filter
                    # Carefully format the command as a single string with escaped quotes 
                    if os.name == 'nt':  # Windows
                        cmd_str = f'"{ffmpeg_exe}" -hide_banner -i "{distorted_path_ffmpeg}" -i "{reference_path_ffmpeg}" -filter_complex "{filter_str}" -f null -'
                        logger.info(f"Shell command: {cmd_str}")
                        
                        process = subprocess.Popen(
                            cmd_str,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            shell=True
                        )
                    else:  # Unix
                        complex_cmd = [
                            ffmpeg_exe,
                            "-hide_banner",
                            "-i", distorted_path_ffmpeg,
                            "-i", reference_path_ffmpeg,
                            "-filter_complex", filter_str,
                            "-f", "null", "-"
                        ]
                        logger.info(f"Command: {' '.join(complex_cmd)}")
                        
                        process = subprocess.Popen(
                            complex_cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True
                        )
                    
                    output, error = process.communicate()
                    returncode = process.returncode
                    
                    if returncode == 0:
                        logger.info("Complex filter command succeeded!")
                        # Build full paths for the results
                        json_path_full = os.path.join(test_dir, rel_vmaf_json).replace("\\", "/")
                        psnr_path_full = os.path.join(test_dir, rel_psnr_txt).replace("\\", "/")
                        ssim_path_full = os.path.join(test_dir, rel_ssim_txt).replace("\\", "/")
                        
                        return self._parse_vmaf_results(json_path_full, psnr_path_full, ssim_path_full, distorted_path, reference_path, current_dir)
                    else:
                        logger.error(f"Complex filter command failed: {error}")
                        
                        # Last resort: use system FFmpeg with basic command
                        logger.info("Trying with system FFmpeg as last resort...")
                        basic_sys_cmd = [
                            "ffmpeg",
                            "-hide_banner",
                            "-i", distorted_path_ffmpeg,
                            "-i", reference_path_ffmpeg,
                            "-lavfi", f"libvmaf=log_path={rel_vmaf_json}:log_fmt=json",
                            "-f", "null", "-"
                        ]
                        
                        logger.info(f"Command: {' '.join(basic_sys_cmd)}")
                        process = subprocess.Popen(
                            basic_sys_cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True
                        )
                        
                        output, error = process.communicate()
                        returncode = process.returncode
                        
                        if returncode == 0:
                            logger.info("System FFmpeg VMAF command succeeded!")
                            # Now try to run PSNR and SSIM separately
                            self._run_psnr_ssim_analysis("ffmpeg", distorted_path_ffmpeg, reference_path_ffmpeg, rel_psnr_txt, rel_ssim_txt)
                            
                            # Build full paths for the results
                            json_path_full = os.path.join(test_dir, rel_vmaf_json).replace("\\", "/")
                            psnr_path_full = os.path.join(test_dir, rel_psnr_txt).replace("\\", "/")
                            ssim_path_full = os.path.join(test_dir, rel_ssim_txt).replace("\\", "/")
                            
                            return self._parse_vmaf_results(json_path_full, psnr_path_full, ssim_path_full, distorted_path, reference_path, current_dir)
                        else:
                            logger.error(f"System FFmpeg VMAF command failed: {error}")
                            self.error_occurred.emit("VMAF analysis failed with all methods")
                            os.chdir(current_dir)
                            return None
            except Exception as e:
                error_msg = f"Error in VMAF analysis: {str(e)}"
                logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                import traceback
                logger.error(traceback.format_exc())
                os.chdir(current_dir)
                return None

        except Exception as e:
            error_msg = f"Error in VMAF analysis: {str(e)}"
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            import traceback
            logger.error(traceback.format_exc())
            try:
                os.chdir(current_dir)
            except:
                pass
            return None

    def _run_psnr_ssim_analysis(self, ffmpeg_exe, distorted_path, reference_path, psnr_filename, ssim_filename):
        """Run PSNR and SSIM analysis separately using relative paths"""
        try:
            # Run PSNR analysis with relative paths
            logger.info("Running PSNR analysis...")
            psnr_cmd = [
                ffmpeg_exe,
                "-hide_banner",
                "-i", distorted_path,
                "-i", reference_path,
                "-lavfi", f"psnr=stats_file={psnr_filename}",
                "-f", "null", "-"
            ]
            
            logger.info(f"PSNR command: {' '.join(psnr_cmd)}")
            subprocess.run(psnr_cmd, check=False, capture_output=True)
            
            # Run SSIM analysis with relative paths
            logger.info("Running SSIM analysis...")
            ssim_cmd = [
                ffmpeg_exe,
                "-hide_banner",
                "-i", distorted_path,
                "-i", reference_path,
                "-lavfi", f"ssim=stats_file={ssim_filename}",
                "-f", "null", "-"
            ]
            
            logger.info(f"SSIM command: {' '.join(ssim_cmd)}")
            subprocess.run(ssim_cmd, check=False, capture_output=True)
            
            return True
        except Exception as e:
            logger.warning(f"Error running PSNR/SSIM analysis: {str(e)}")
            return False
    
    def _parse_vmaf_results(self, json_path, psnr_path, ssim_path, distorted_path, reference_path, current_dir):
        """Parse VMAF results from the output files"""
        try:
            # Check if output files exist
            if not os.path.exists(json_path.replace("/", "\\")):
                error_msg = "VMAF analysis completed but JSON output file not found"
                logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                os.chdir(current_dir)
                return None

            # Parse VMAF results from JSON
            try:
                with open(json_path.replace("/", "\\"), 'r') as f:
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

                # Log results
                logger.info(f"VMAF Score: {vmaf_score}")
                logger.info(f"PSNR Score: {psnr_score}")
                logger.info(f"SSIM Score: {ssim_score}")

                # Store raw results for potential detailed analysis
                raw_results = vmaf_data

                # Return results with consistent path format based on the system
                # (Use normalize_path to ensure consistent format)
                results = {
                    'vmaf_score': vmaf_score,
                    'psnr': psnr_score,
                    'ssim': ssim_score,
                    'json_path': json_path.replace("/", "\\"),
                    'csv_path': json_path.replace("vmaf.json", "vmaf.csv").replace("/", "\\"),
                    'psnr_log': psnr_path.replace("/", "\\"),
                    'ssim_log': ssim_path.replace("/", "\\"),
                    'reference_path': reference_path,
                    'distorted_path': distorted_path,
                    'raw_results': raw_results
                }

                # Set progress to 100%
                self.analysis_progress.emit(100)
                self.status_update.emit(f"VMAF analysis complete! Score: {vmaf_score:.2f}")

                # Restore original directory
                os.chdir(current_dir)

                # Delete the primary capture file if it exists (and if explicitly labeled as a capture)
                if 'distorted_path' in results:
                    primary_capture = results['distorted_path']
                    try:
                        if os.path.exists(primary_capture) and "capture" in primary_capture.lower():
                            logger.info(f"Deleting primary capture file: {primary_capture}")
                            os.remove(primary_capture)
                    except Exception as cleanup_error:
                        logger.warning(f"Could not delete primary capture file: {cleanup_error}")

                # Return results
                self.analysis_complete.emit(results)
                return results

            except Exception as e:
                error_msg = f"Error parsing VMAF results: {str(e)}"
                logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                import traceback
                logger.error(traceback.format_exc())
                os.chdir(current_dir)
                return None

        except Exception as e:
            error_msg = f"Error processing VMAF results: {str(e)}"
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            import traceback
            logger.error(traceback.format_exc())
            os.chdir(current_dir)
            return None

    def _get_video_info(self, video_path):
        """Get detailed information about a video file using FFprobe"""
        try:
            # Find path to FFprobe executable
            from .utils import get_ffmpeg_path
            ffmpeg_exe, ffprobe_exe, ffplay_exe = get_ffmpeg_path()
            
            # Normalize path for FFprobe
            video_path_ffmpeg = video_path.replace("\\", "/")
            
            # Use a simpler command that's more likely to work across FFmpeg versions
            cmd = [
                ffprobe_exe,  # Use full path to ffprobe.exe
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                video_path_ffmpeg
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"FFprobe failed: {result.stderr}")
                return None

            info = json.loads(result.stdout)
            video_stream = next((s for s in info.get('streams', []) if s.get('codec_type') == 'video'), None)
            if not video_stream:
                logger.error("No video stream found")
                return None

            format_info = info.get('format', {})
            duration = float(format_info.get('duration', 0))
            fr_str = video_stream.get('avg_frame_rate', '0/0')
            num, den = map(int, fr_str.split('/')) if '/' in fr_str else (0, 1)
            frame_rate = num / den if den else 0
            width = int(video_stream.get('width', 0))
            height = int(video_stream.get('height', 0))
            frame_count = int(video_stream.get('nb_frames', 0))
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
            logger.error(f"Error getting video info: {str(e)}")
            return None


class VMAFAnalysisThread(QThread):
    """Thread for VMAF analysis with reliable progress reporting"""
    analysis_progress = pyqtSignal(int)
    analysis_complete = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    status_update = pyqtSignal(str)

    def __init__(self, reference_path, distorted_path, model="vmaf_v0.6.1", duration=None):
        super().__init__()
        self.reference_path = reference_path
        self.distorted_path = distorted_path
        self.model = model
        self.duration = duration
        self.analyzer = VMAFAnalyzer()

        # Connect signals with direct connections for responsive UI updates
        self.analyzer.analysis_progress.connect(self._handle_progress, Qt.DirectConnection)
        self.analyzer.status_update.connect(self.status_update, Qt.DirectConnection)
        self.analyzer.error_occurred.connect(self.error_occurred, Qt.DirectConnection)
        self.analyzer.analysis_complete.connect(self.analysis_complete, Qt.DirectConnection)

        # Output directory will be set from outside if needed
        self.output_directory = None
        self.test_name = None

    def __del__(self):
        """Clean up resources when thread is destroyed"""
        try:
            # Wait for thread to finish before disconnecting signals
            self.wait()
            
            # Disconnect all signals to prevent issues during thread destruction
            try:
                self.disconnect()
            except:
                pass

            # Also disconnect signals from the analyzer if it exists
            if hasattr(self, 'analyzer'):
                try:
                    self.analyzer.analysis_progress.disconnect()
                    self.analyzer.status_update.disconnect()
                    self.analyzer.error_occurred.disconnect()
                    self.analyzer.analysis_complete.disconnect()
                except:
                    pass
        except Exception as e:
            # Just log errors during cleanup but don't raise them
            pass

    def set_output_directory(self, output_dir):
        """Set output directory for results"""
        self.output_directory = normalize_path(output_dir)
        self.analyzer.set_output_directory(self.output_directory)

    def set_test_name(self, test_name):
        """Set test name for organizing results"""
        self.test_name = test_name
        self.analyzer.set_test_name(self.test_name)

    def _handle_progress(self, progress):
        """Handle progress updates from analyzer, ensuring proper values"""
        try:
            # Ensure progress is an integer between 0-100
            progress_value = int(progress)
            progress_value = max(0, min(100, progress_value))
            self.analysis_progress.emit(progress_value)
        except (ValueError, TypeError):
            # In case of non-integer progress, emit a safe value
            self.analysis_progress.emit(0)

    def run(self):
        """Run analysis in thread"""
        try:            
            # Check if thread should exit (in case quit was called right after start)
            if self.isInterruptionRequested():
                logger.info("VMAF analysis thread: interruption requested before starting")
                return           
            self.status_update.emit("Starting VMAF analysis...")

            # Report initial progress
            self.analysis_progress.emit(0)

            # Verify input files
            if not os.path.exists(self.reference_path):
                self.error_occurred.emit(f"Reference video not found: {self.reference_path}")
                return

            if not os.path.exists(self.distorted_path):
                self.error_occurred.emit(f"Distorted video not found: {self.distorted_path}")
                return

            # If output directory was set, pass it to the analyzer
            if self.output_directory:
                self.analyzer.set_output_directory(self.output_directory)

            if self.test_name:
                self.analyzer.set_test_name(self.test_name)

            # Run analysis
            self.analyzer.analyze_videos(
                self.reference_path,
                self.distorted_path,
                self.model,
                self.duration
            )

        except Exception as e:
            error_msg = f"Error in VMAF analysis thread: {str(e)}"
            self.error_occurred.emit(error_msg)
            logger.error(error_msg)
            import traceback
            logger.error(traceback.format_exc())
