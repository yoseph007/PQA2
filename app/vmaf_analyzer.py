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
        self.output_directory = output_dir
        logger.info(f"Set output directory to: {output_dir}")

    def set_test_name(self, test_name):
        """Set test name for organizing results"""
        self.test_name = test_name
        logger.info(f"Set test name to: {test_name}")

    def analyze_videos(self, reference_path, distorted_path, model="vmaf_v0.6.1", duration=None):
        """Run VMAF analysis with the correct command format and properly escaped paths"""
        try:
            self.status_update.emit(f"Analyzing videos with model: {model}")

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
            
            # Create test directory with timestamp appended to test name
            test_dir_name = f"{test_name}_{timestamp}"
            test_dir = os.path.join(output_dir, test_dir_name)
            os.makedirs(test_dir, exist_ok=True)
            
            logger.info(f"Created test results directory: {test_dir}")

            # Create consistent filenames with test name and timestamp
            vmaf_filename = f"{test_name}_{timestamp}_vmaf.json"
            csv_filename = f"{test_name}_{timestamp}_vmaf.csv"
            psnr_filename = f"{test_name}_{timestamp}_psnr.txt"
            ssim_filename = f"{test_name}_{timestamp}_ssim.txt"

            # Create full paths
            json_path = os.path.join(test_dir, vmaf_filename).replace("\\", "/")
            csv_path = os.path.join(test_dir, csv_filename).replace("\\", "/")
            psnr_log = os.path.join(test_dir, psnr_filename).replace("\\", "/")
            ssim_log = os.path.join(test_dir, ssim_filename).replace("\\", "/")
            
            # For command line logging, save a copy
            vmaf_cmd_log = os.path.join(test_dir, f"{test_name}_{timestamp}_vmaf_command.txt").replace("\\", "/")

            # Convert input paths to forward slashes
            reference_path_unix = reference_path.replace("\\", "/")
            distorted_path_unix = distorted_path.replace("\\", "/")

            # Duration parameter if needed
            duration_cmd = []
            if duration and duration > 0:
                duration_cmd = ["-t", str(duration)]
                self.status_update.emit(f"Analyzing {duration}s of video")

            # Make sure model has .json extension if not already
            model_name = model
            if not model.endswith('.json'):
                model_name = f"{model}.json"

            # Build a more reliable FFmpeg command using separate filters
            # instead of a complex filter chain that has path escaping issues
            vmaf_cmd = [
                "ffmpeg", 
                "-hide_banner",
                "-i", distorted_path_unix,  # Distorted is first input
                "-i", reference_path_unix   # Reference is second input
            ]

            # Add duration limit if specified
            if duration_cmd:
                vmaf_cmd.extend(duration_cmd)

            # Change directory to the vmaf output dir to use relative paths in the command
            # This avoids Windows path escaping issues with colons
            current_dir = os.getcwd()
            os.chdir(vmaf_dir)

            # Now use simple filenames instead of full paths in the filter
            filter_complex = (
                "[0:v]setpts=PTS-STARTPTS,split=2[ref1][ref2];"
                "[1:v]setpts=PTS-STARTPTS,split=2[dist1][dist2];"
                f"[ref1][dist1]libvmaf=log_path='{vmaf_filename}':log_fmt=json;"
                f"[ref2][dist2]libvmaf=log_path='{csv_filename}':log_fmt=csv;"
                f"[0:v][1:v]psnr=stats_file='{psnr_filename}';"
                f"[0:v][1:v]ssim=stats_file='{ssim_filename}'"
            )

            # Use the -filter_complex parameter instead of -lavfi which seems more compatible
            vmaf_cmd.extend([
                "-filter_complex", filter_complex,
                "-f", "null", "-"
            ])

            # Log the exact command for debugging
            cmd_str = ' '.join(vmaf_cmd)
            logger.info(f"VMAF command: {cmd_str}")

            # Save the command to a file for reference/debugging
            with open(vmaf_cmd_log, "w") as f:
                f.write(cmd_str)

            # Execute VMAF command with extra error handling
            try:
                process = subprocess.Popen(
                    vmaf_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1
                )
                logger.info("VMAF subprocess started successfully")
            except Exception as subprocess_error:
                error_msg = f"Failed to start VMAF subprocess: {str(subprocess_error)}"
                logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                # Restore original directory
                os.chdir(current_dir)
                return None
            # Monitor progress
            frame_total = 0
            frame_count = 0
            last_progress_time = time.time()

            self.analysis_progress.emit(10)  # Initial progress

            while True:
                line = process.stderr.readline()
                if not line and process.poll() is not None:
                    break

                # Try to extract progress info
                if "frame=" in line:
                    try:
                        match = re.search(r'frame=\s*(\d+)', line)
                        if match:
                            frame_count = int(match.group(1))

                            # Calculate progress percentage
                            if frame_total == 0:
                                # We don't have total frames yet, just update based on current frame
                                progress = min(95, max(10, 10 + (frame_count % 100)))

                                # Only update every second to avoid too many signals
                                current_time = time.time()
                                if current_time - last_progress_time >= 1.0:
                                    self.analysis_progress.emit(progress)
                                    last_progress_time = current_time
                            else:
                                progress = min(95, max(10, int((frame_count / frame_total) * 85) + 10))
                                # Only update every second to avoid too many signals
                                current_time = time.time()
                                if current_time - last_progress_time >= 1.0:
                                    self.analysis_progress.emit(progress)
                                    last_progress_time = current_time

                            # Extract time for total frame estimate if we don't have it yet
                            if frame_total == 0:
                                time_match = re.search(r'time=\s*(\d+):(\d+):(\d+\.\d+)', line)
                                if time_match:
                                    hours = int(time_match.group(1))
                                    minutes = int(time_match.group(2))
                                    seconds = float(time_match.group(3))
                                    time_secs = hours * 3600 + minutes * 60 + seconds
                                    # Get approx duration from file metadata
                                    try:
                                        ref_info = self._get_video_info(reference_path)
                                        if ref_info and ref_info.get('duration', 0) > 0:
                                            # If we know the full duration, we can estimate total frames
                                            ref_duration = ref_info.get('duration', 0)
                                            fps = ref_info.get('frame_rate', 25)
                                            if fps > 0 and ref_duration > 0:
                                                frame_total = int(ref_duration * fps)
                                                logger.info(f"Estimated total frames: {frame_total}")
                                    except Exception as e:
                                        logger.warning(f"Error estimating total frames: {e}")

                    except Exception as e:
                        logger.error(f"Error parsing progress: {str(e)}")

                # Check for errors
                if "Error" in line or "error" in line:
                    logger.error(f"VMAF error: {line.strip()}")

                # Log output for debugging
                logger.debug(line.strip())

            # Get process result
            returncode = process.poll()
            stdout, stderr = process.communicate()

            # Check if process completed successfully
            if returncode != 0:
                error_msg = f"VMAF analysis failed with code {returncode}: {stderr}"
                logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                # Restore original directory
                os.chdir(current_dir)
                return None

            # Check if output files exist
            json_path_win = json_path.replace("/", "\\")
            if not os.path.exists(json_path_win):
                error_msg = "VMAF analysis completed but JSON output file not found"
                logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                # Restore original directory
                os.chdir(current_dir)
                return None

            # Parse VMAF results from JSON
            try:
                with open(json_path_win, 'r') as f:
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
                        if "ssim" in pool:
                            ssim_score = pool["ssim"]["mean"]
                    except Exception as e:
                        logger.error(f"Error parsing VMAF metrics from pooled_metrics: {str(e)}")
                
                # If PSNR/SSIM are still None, try to parse from the log files
                if psnr_score is None and os.path.exists(psnr_log.replace("/", "\\")):
                    try:
                        with open(psnr_log.replace("/", "\\"), 'r') as f:
                            psnr_content = f.read()
                            # Try to find the average PSNR value
                            psnr_match = re.search(r'average:([0-9.]+)', psnr_content)
                            if psnr_match:
                                psnr_score = float(psnr_match.group(1))
                                logger.info(f"Parsed PSNR from log file: {psnr_score}")
                    except Exception as e:
                        logger.error(f"Error parsing PSNR log: {str(e)}")
                
                if ssim_score is None and os.path.exists(ssim_log.replace("/", "\\")):
                    try:
                        with open(ssim_log.replace("/", "\\"), 'r') as f:
                            ssim_content = f.read()
                            # Try to find the average SSIM value
                            ssim_match = re.search(r'All:([0-9.]+)', ssim_content)
                            if ssim_match:
                                ssim_score = float(ssim_match.group(1))
                                logger.info(f"Parsed SSIM from log file: {ssim_score}")
                    except Exception as e:
                        logger.error(f"Error parsing SSIM log: {str(e)}")
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
                                if "psnr" in metrics:
                                    psnr_values.append(metrics["psnr"])
                                if "ssim" in metrics:
                                    ssim_values.append(metrics["ssim"])

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

                # Return results with Windows paths for consistency with rest of app
                results = {
                    'vmaf_score': vmaf_score,
                    'psnr': psnr_score,
                    'ssim': ssim_score,
                    'json_path': json_path_win,
                    'csv_path': csv_path.replace("/", "\\"),
                    'psnr_log': psnr_log.replace("/", "\\"),
                    'ssim_log': ssim_log.replace("/", "\\"),
                    'reference_path': reference_path,
                    'distorted_path': distorted_path,
                    'raw_results': raw_results
                }

                # Set progress to 100%
                self.analysis_progress.emit(100)
                self.status_update.emit(f"VMAF analysis complete! Score: {vmaf_score:.2f}")

                # Restore original directory
                os.chdir(current_dir)

                # Return results
                self.analysis_complete.emit(results)
                return results

            except Exception as e:
                error_msg = f"Error parsing VMAF results: {str(e)}"
                logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                import traceback
                logger.error(traceback.format_exc())
                # Restore original directory
                os.chdir(current_dir)
                return None

        except Exception as e:
            error_msg = f"Error in VMAF analysis: {str(e)}"
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            import traceback
            logger.error(traceback.format_exc())
            # Restore original directory
            os.chdir(current_dir)
            return None

    def _get_video_info(self, video_path):
        """Get detailed information about a video file using FFprobe"""
        try:
            cmd = [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                "-count_frames",
                video_path
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
            # Disconnect all signals to prevent issues during thread destruction
            self.disconnect()

            # Also disconnect signals from the analyzer if it exists
            if hasattr(self, 'analyzer'):
                self.analyzer.analysis_progress.disconnect()
                self.analyzer.status_update.disconnect()
                self.analyzer.error_occurred.disconnect()
                self.analyzer.analysis_complete.disconnect()
        except Exception as e:
            # Just log errors during cleanup but don't raise them
            pass

    def set_output_directory(self, output_dir):
        """Set output directory for results"""
        self.output_directory = output_dir
        self.analyzer.set_output_directory(output_dir)

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