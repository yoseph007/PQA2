import os
import logging
import json
import subprocess
import re
import tempfile
import platform
from datetime import datetime
from PyQt5.QtCore import QObject, pyqtSignal, QThread, Qt
import shutil
from .alignment import VideoAligner

logger = logging.getLogger(__name__)

class VMAFAnalyzer(QObject):
    """Class for running VMAF analysis on reference and captured videos"""
    analysis_progress = pyqtSignal(int)  # 0-100%
    analysis_complete = pyqtSignal(dict)  # VMAF results
    error_occurred = pyqtSignal(str)
    status_update = pyqtSignal(str)

    def __init__(self):
        super().__init__()


    def analyze_videos(self, reference_path, distorted_path, model="vmaf_v0.6.1", duration=None):
        """Analyze videos using VMAF with the correct command format and properly escaped paths"""
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
            output_dir = os.path.dirname(reference_path)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            vmaf_dir = os.path.join(output_dir, f"vmaf_{timestamp}")
            os.makedirs(vmaf_dir, exist_ok=True)

            # Output filenames - Convert paths to use forward slashes to avoid FFmpeg filter syntax issues
            json_path = os.path.join(vmaf_dir, "vmaf_log.json").replace("\\", "/")
            csv_path = os.path.join(vmaf_dir, "vmaf_log.csv").replace("\\", "/")
            psnr_log = os.path.join(vmaf_dir, "psnr_log.txt").replace("\\", "/")
            ssim_log = os.path.join(vmaf_dir, "ssim_log.txt").replace("\\", "/")

            # Convert input paths to forward slashes too
            reference_path_unix = reference_path.replace("\\", "/")
            distorted_path_unix = distorted_path.replace("\\", "/")

            # Duration parameter if needed
            duration_cmd = []
            if duration and duration > 0:
                duration_cmd = ["-t", str(duration)]
                self.status_update.emit(f"Analyzing {duration}s of video")

            # Build FFmpeg command for VMAF - using exact format from working example
            vmaf_cmd = [
                "ffmpeg", 
                "-hide_banner",
                "-i", distorted_path_unix, #Corrected input order
                "-i", reference_path_unix #Corrected input order
            ]

            # Add duration limit if specified
            if duration_cmd:
                vmaf_cmd.extend(duration_cmd)

            # Add complex filter with exact format from working example
            # Use the working command format from the user's example, but with simpler filter to avoid path issues
            if platform.system() == 'Windows':
                # Escape the path for Windows - replace colons in drive letters with escaped version
                json_path_escaped = json_path.replace(':', '\\:')
                filter_complex = (
                    f"libvmaf=log_path={json_path_escaped}:log_fmt=json:model={model}:psnr=1:ssim=1"
                )
            else:
                filter_complex = (
                    f"libvmaf=log_path={json_path}:log_fmt=json:model={model}:psnr=1:ssim=1"
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
            with open(os.path.join(os.path.dirname(vmaf_dir), "last_vmaf_command.txt"), "w") as f:
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
                return None

            # Monitor progress
            frame_total = 0
            frame_count = 0

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
                                self.analysis_progress.emit(min(99, frame_count % 100))
                            else:
                                progress = min(99, int((frame_count / frame_total) * 100))
                                self.analysis_progress.emit(progress)

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
            stdout, stderr = process.communicate()

            # Check if process completed successfully
            if process.returncode != 0:
                error_msg = f"VMAF analysis failed with code {process.returncode}: {stderr}"
                logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                return None

            # Check if output files exist
            if not os.path.exists(json_path.replace("/", "\\")):
                error_msg = "VMAF analysis completed but JSON output file not found"
                logger.error(error_msg)
                self.error_occurred.emit(error_msg)
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
                        if "ssim" in pool:
                            ssim_score = pool["ssim"]["mean"]
                    except Exception as e:
                        logger.error(f"Error parsing VMAF metrics: {str(e)}")
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

                # Try to parse PSNR and SSIM from their log files if available
                if (psnr_score is None or ssim_score is None):
                    psnr_log_win = psnr_log.replace("/", "\\")
                    ssim_log_win = ssim_log.replace("/", "\\")

                    if (os.path.exists(psnr_log_win) or os.path.exists(ssim_log_win)):
                        # Parse PSNR log
                        if os.path.exists(psnr_log_win) and psnr_score is None:
                            try:
                                psnr_values = []
                                with open(psnr_log_win, 'r') as f:
                                    for line in f:
                                        if "psnr_avg" in line:
                                            match = re.search(r'psnr_avg:(\d+\.\d+)', line)
                                            if match:
                                                psnr_values.append(float(match.group(1)))
                                if psnr_values:
                                    psnr_score = sum(psnr_values) / len(psnr_values)
                            except Exception as e:
                                logger.warning(f"Error parsing PSNR log: {e}")

                        # Parse SSIM log
                        if os.path.exists(ssim_log_win) and ssim_score is None:
                            try:
                                ssim_values = []
                                with open(ssim_log_win, 'r') as f:
                                    for line in f:
                                        if "All:" in line:
                                            match = re.search(r'All:(\d+\.\d+)', line)
                                            if match:
                                                ssim_values.append(float(match.group(1)))
                                if ssim_values:
                                    ssim_score = sum(ssim_values) / len(ssim_values)
                            except Exception as e:
                                logger.warning(f"Error parsing SSIM log: {e}")

                # Log results
                logger.info(f"VMAF Score: {vmaf_score}")
                logger.info(f"PSNR Score: {psnr_score}")
                logger.info(f"SSIM Score: {ssim_score}")

                # Return results with Windows paths for consistency with rest of app
                results = {
                    'vmaf_score': vmaf_score,
                    'psnr': psnr_score,
                    'ssim': ssim_score,
                    'json_path': json_path.replace("/", "\\"),
                    'csv_path': csv_path.replace("/", "\\"),
                    'psnr_log': psnr_log.replace("/", "\\"),
                    'ssim_log': ssim_log.replace("/", "\\"),
                    'reference_path': reference_path,
                    'distorted_path': distorted_path
                }

                # Set progress to 100%
                self.analysis_progress.emit(100)

                # Return results
                return results

            except Exception as e:
                error_msg = f"Error parsing VMAF results: {str(e)}"
                logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                import traceback
                logger.error(traceback.format_exc())
                return None

        except Exception as e:
            error_msg = f"Error in VMAF analysis: {str(e)}"
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            import traceback
            logger.error(traceback.format_exc())
            return None

    def _get_video_info(self, video_path):
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

    def _resize_video(self, video_path, target_width, target_height):
        try:
            output_dir = os.path.dirname(video_path)
            output_name = f"{os.path.splitext(os.path.basename(video_path))[0]}_resized.mp4"
            output_path = os.path.join(output_dir, output_name)
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-vf", f"scale={target_width}:{target_height}",
                "-c:v", "libx264",
                "-crf", "18",
                "-preset", "fast",
                "-c:a", "copy",
                output_path
            ]
            self.status_update.emit(f"Resizing video to {target_width}x{target_height}...")
            subprocess.run(cmd, capture_output=True, check=True)
            if not os.path.exists(output_path):
                raise RuntimeError("Failed to create resized video")
            return output_path
        except Exception as e:
            logger.error(f"Error resizing video: {str(e)}")
            self.error_occurred.emit(f"Error resizing video: {str(e)}")
            return video_path





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

        # Connect signals with direct connections to ensure they're processed immediately
        self.analyzer.analysis_progress.connect(self._handle_progress, Qt.DirectConnection)
        self.analyzer.status_update.connect(self.status_update, Qt.DirectConnection)
        self.analyzer.error_occurred.connect(self.error_occurred, Qt.DirectConnection)

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
        """Run VMAF analysis in thread"""
        try:
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

            # Run analysis
            results = self.analyzer.analyze_videos(
                self.reference_path,
                self.distorted_path,
                self.model,
                self.duration
            )

            if results:
                # Ensure progress is set to 100% at completion
                self.analysis_progress.emit(100)
                self.analysis_complete.emit(results)
                self.status_update.emit("VMAF analysis complete!")
            else:
                self.error_occurred.emit("VMAF analysis failed to produce results")

        except Exception as e:
            error_msg = f"Error in VMAF analysis thread: {str(e)}"
            self.error_occurred.emit(error_msg)
            logger.error(error_msg)
            import traceback
            logger.error(traceback.format_exc())

    def __del__(self):
        """Ensure thread is properly stopped on destruction"""
        try:
            if self.isRunning():
                self.wait(1000)  # Give it 1 second to finish
                if self.isRunning():
                    self.terminate()
                    logger.warning("VMAFAnalysisThread terminated during destruction")
        except Exception as e:
            logger.error(f"Error during VMAFAnalysisThread cleanup: {e}")

def run_vmaf_analysis(reference_path, distorted_path, output_dir=None, model_path="vmaf_v0.6.1"):
    """Run VMAF analysis with multiple output formats"""
    try:
        if output_dir is None:
            output_dir = os.path.dirname(reference_path)

        # Create results folder with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_dir = os.path.join(output_dir, f"vmaf_{timestamp}")
        os.makedirs(results_dir, exist_ok=True)

        # Set up output paths
        json_output = os.path.join(results_dir, "vmaf_log.json")
        psnr_output = os.path.join(results_dir, "psnr_log.txt")
        ssim_output = os.path.join(results_dir, "ssim_log.txt")

        # Make sure model has .json extension if not already
        if not model_path.endswith('.json'):
            model_path += '.json'

        # Get absolute paths
        reference_path = os.path.abspath(reference_path)
        distorted_path = os.path.abspath(distorted_path)

        # Simplified filter complex - avoid too many splits which causes errors
        filter_complex = f"libvmaf=log_path={json_output}:log_fmt=json:model={model_path}:psnr=1:ssim=1"

        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-i", distorted_path,  # Distorted is first input for libvmaf filter
            "-i", reference_path,  # Reference is second input
            "-lavfi", filter_complex,
            "-f", "null", "-"  # Output to null
        ]

        # Log the command for debugging
        logger.info(f"VMAF Reference: {reference_path}")
        logger.info(f"VMAF Distorted: {distorted_path}")
        logger.info(f"VMAF command: {' '.join(cmd)}")

        # Run the command
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        # Check for errors
        if result.returncode != 0:
            for line in result.stderr.splitlines():
                logger.error(f"VMAF error: {line}")
            logger.error(f"VMAF analysis failed with code {result.returncode}: {result.stderr}")
            return None

    except Exception as e:
        logger.error(f"Error during VMAF analysis: {str(e)}")
        return None