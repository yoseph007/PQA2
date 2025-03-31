import os
import logging
import json
import subprocess
import re
import tempfile
from datetime import datetime
from PyQt5.QtCore import QObject, pyqtSignal, QThread
import shutil

logger = logging.getLogger(__name__)

class VMAFAnalyzer(QObject):
    """Class for running VMAF analysis on reference and captured videos"""
    analysis_progress = pyqtSignal(int)  # 0-100%
    analysis_complete = pyqtSignal(dict)  # VMAF results
    error_occurred = pyqtSignal(str)
    status_update = pyqtSignal(str)

    def __init__(self):
        super().__init__()

    def analyze_videos(self, reference_path, distorted_path, model_path="vmaf_v0.6.1", duration=None):
        stderr_output = ""  # Initialize early to prevent UnboundLocalError
        original_dir = os.getcwd()  # Save original directory
        temp_dir = None
        
        try:
            self.status_update.emit("Starting VMAF analysis...")

            # Validate input files
            if not os.path.exists(reference_path):
                raise FileNotFoundError(f"Reference video not found: {reference_path}")
            if not os.path.exists(distorted_path):
                raise FileNotFoundError(f"Distorted video not found: {distorted_path}")

            # Get video metadata
            ref_info = self._get_video_info(reference_path)
            dist_info = self._get_video_info(distorted_path)
            if not ref_info or not dist_info:
                error_msg = "Could not get video information"
                logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                return None

            # Create temporary directory for output files
            temp_dir = tempfile.mkdtemp()
            
            # File names for output - SIMPLE NAMES, NO PATHS
            json_file = "vmaf_log.json"
            csv_file = "vmaf_log.csv"
            psnr_file = "psnr_log.txt"
            ssim_file = "ssim_log.txt"
            
            # Change to temp directory before running ffmpeg
            os.chdir(temp_dir)
            
            # Create the filter complex string - USING ONLY FILE NAMES, NO PATHS
            filter_complex = (
                "[0:v]setpts=PTS-STARTPTS,split=2[ref1][ref2];"
                "[1:v]setpts=PTS-STARTPTS,split=2[dist1][dist2];"
                f"[ref1][dist1]libvmaf=log_path={json_file}:log_fmt=json;"
                f"[ref2][dist2]libvmaf=log_path={csv_file}:log_fmt=csv;"
                f"[0:v][1:v]psnr=stats_file={psnr_file};"
                f"[0:v][1:v]ssim=stats_file={ssim_file}"
            )
            
            # Construct the full command
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-i", reference_path,  # Reference video
                "-i", distorted_path,  # Distorted video
                "-filter_complex", filter_complex,
                "-f", "null", "-"
            ]
            
            # Add duration if specified
            if duration:
                cmd.extend(["-t", str(duration)])
            
            # Log and execute the command
            logger.info(f"Running VMAF command: {' '.join(cmd)}")
            self.status_update.emit("Running VMAF analysis...")
            
            # Execute the command
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            # Progress tracking
            total_frames = ref_info.get('frame_count', 0)
            if total_frames == 0 and duration:
                total_frames = int(duration * ref_info.get('frame_rate', 25))
                
            while process.poll() is None:
                line = process.stderr.readline()
                stderr_output += line
                if "frame=" in line:
                    try:
                        match = re.search(r'frame=\s*(\d+)', line)
                        if match and total_frames > 0:
                            current_frame = int(match.group(1))
                            progress = min(99, int((current_frame / total_frames) * 100))
                            self.analysis_progress.emit(progress)
                    except Exception as e:
                        logger.warning(f"Progress parsing error: {str(e)}")
            
            # Capture remaining output
            stdout, stderr = process.communicate()
            stderr_output += stderr
            self.analysis_progress.emit(100)
            
            # Check if the files were created
            # Since we're in the temp directory, just use the filenames
            if not os.path.exists(json_file):
                logger.error(f"VMAF JSON output file missing: {os.path.join(temp_dir, json_file)}")
                logger.error(f"FFmpeg STDERR: {stderr_output}")
                raise FileNotFoundError(f"VMAF output file not created")
            
            # Prepare output paths for final destination
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = os.path.dirname(reference_path)
            output_json = os.path.join(output_dir, f"vmaf_results_{timestamp}.json")
            output_csv = os.path.join(output_dir, f"vmaf_results_{timestamp}.csv")
            psnr_log = os.path.join(output_dir, f"psnr_log_{timestamp}.txt")
            ssim_log = os.path.join(output_dir, f"ssim_log_{timestamp}.txt")
            
            # Read results from JSON file
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)
                    vmaf_score = data.get('pooled_metrics', {}).get('vmaf', {}).get('mean')
                    if vmaf_score is None:
                        raise ValueError("No valid VMAF score found in results")
                    
                # Copy results files to final destination
                # We're still in the temp directory, so use the simple filenames for source
                shutil.copy2(json_file, output_json)
                if os.path.exists(csv_file):
                    shutil.copy2(csv_file, output_csv)
                if os.path.exists(psnr_file):
                    shutil.copy2(psnr_file, psnr_log)
                if os.path.exists(ssim_file):
                    shutil.copy2(ssim_file, ssim_log)
                    
            except Exception as e:
                logger.error(f"Error processing results: {str(e)}")
                raise
            
            # Format the results object
            formatted_results = {
                'vmaf_score': vmaf_score,
                'psnr_log': psnr_log if os.path.exists(psnr_log) else None,
                'ssim_log': ssim_log if os.path.exists(ssim_log) else None,
                'json_path': output_json,
                'csv_path': output_csv if os.path.exists(output_csv) else None,
                'reference_path': reference_path,
                'distorted_path': distorted_path,
                'model_path': model_path,
                'raw_results': data
            }
            
            logger.info(f"VMAF analysis complete. Score: {vmaf_score:.2f}")
            self.status_update.emit(f"VMAF Score: {vmaf_score:.2f}")
            self.analysis_complete.emit(formatted_results)
            return formatted_results
            
        except Exception as e:
            error_msg = f"Analysis failed: {str(e)}"
            logger.error(error_msg)
            if stderr_output:
                logger.error(f"FFmpeg STDERR: {stderr_output[:1000]}")
            self.error_occurred.emit(error_msg)
            return None
        
        finally:
            # Change back to original directory
            os.chdir(original_dir)
            
            # Clean up temp directory
            if temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                except Exception as e:
                    logger.warning(f"Failed to clean up temp directory: {str(e)}")

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
    analysis_progress = pyqtSignal(int)
    analysis_complete = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    status_update = pyqtSignal(str)

    def __init__(self, reference_path, distorted_path, model_path="vmaf_v0.6.1", duration=None):
        super().__init__()
        self.reference_path = reference_path
        self.distorted_path = distorted_path
        self.model_path = model_path
        self.duration = duration
        self.analyzer = VMAFAnalyzer()
        self.analyzer.analysis_progress.connect(self.analysis_progress)
        self.analyzer.analysis_complete.connect(self.analysis_complete)
        self.analyzer.error_occurred.connect(self.error_occurred)
        self.analyzer.status_update.connect(self.status_update)

    def run(self):
        self.analyzer.analyze_videos(
            self.reference_path,
            self.distorted_path,
            self.model_path,
            self.duration
        )