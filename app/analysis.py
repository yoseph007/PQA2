import os
import logging
import json
import subprocess
import re
import tempfile
from datetime import datetime
from PyQt5.QtCore import QObject, pyqtSignal, QThread


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
        """
        Run VMAF analysis on reference and distorted videos
        
        Parameters:
        - reference_path: Path to reference video
        - distorted_path: Path to distorted (captured) video
        - model_path: VMAF model name (without .json extension)
        - duration: Optional duration limit in seconds
        
        Returns dictionary with VMAF results
        """
        try:
            self.status_update.emit(f"Starting VMAF analysis...")
            
            # Verify files exist
            if not os.path.exists(reference_path):
                raise FileNotFoundError(f"Reference video not found: {reference_path}")
                
            if not os.path.exists(distorted_path):
                raise FileNotFoundError(f"Distorted video not found: {distorted_path}")
                    
            # Get info about the videos
            ref_info = self._get_video_info(reference_path)
            dist_info = self._get_video_info(distorted_path)
            
            if not ref_info or not dist_info:
                error_msg = "Could not get video information"
                logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                return None
            
            # Create output path for VMAF results
            output_dir = os.path.dirname(reference_path)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_json = os.path.join(output_dir, f"vmaf_results_{timestamp}.json")
            
            # Convert paths to use forward slashes for FFmpeg
            ref_path_ffmpeg = reference_path.replace('\\', '/')
            dist_path_ffmpeg = distorted_path.replace('\\', '/')
            
            # Create output paths for VMAF results
            output_dir = os.path.dirname(reference_path)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_json = os.path.join(output_dir, f"vmaf_results_{timestamp}.json")
            output_csv = os.path.join(output_dir, f"vmaf_results_{timestamp}.csv")
            
            # Advanced filter chain for both JSON and CSV output
            # Windows paths need special handling in filter_complex
            json_path = output_json.replace('\\', '/')
            csv_path = output_csv.replace('\\', '/')
            
            # Use single output for simplicity (instead of trying to use both JSON and CSV)
            # Properly escape Windows paths - enclose the entire path in quotes
            filter_str = f"libvmaf=log_path='{json_path}':log_fmt=json"
            
            # Create FFmpeg command with hide_banner for cleaner output
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-i", dist_path_ffmpeg,
                "-i", ref_path_ffmpeg,
                "-lavfi", filter_str
            ]
            
            # Add duration limit if specified
            if duration:
                cmd.extend(["-t", str(duration)])
                    
            # Add output format
            cmd.extend(["-f", "null", "-"])
            
            self.status_update.emit("Running VMAF analysis...")
            logger.info(f"VMAF command: {' '.join(cmd)}")
            
            # Run the process with progress monitoring
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # For progress and capturing output
            stderr_output = ""
            total_frames = ref_info.get('frame_count', 0)
            if total_frames == 0 and duration:
                total_frames = int(duration * ref_info.get('frame_rate', 25))
                
            # Read output for progress
            while process.poll() is None:
                line = process.stderr.readline()
                if not line:
                    continue
                    
                stderr_output += line
                
                # Parse frame progress
                if "frame=" in line:
                    try:
                        match = re.search(r'frame=\s*(\d+)', line)
                        if match and total_frames > 0:
                            current_frame = int(match.group(1))
                            progress = min(99, int((current_frame / total_frames) * 100))
                            self.analysis_progress.emit(progress)
                    except (ValueError, AttributeError) as e:
                        logger.warning(f"Error parsing frame progress: {e}")
            
            # Get remaining output
            stdout, stderr = process.communicate()
            stderr_output += stderr
            
            # Complete progress
            self.analysis_progress.emit(100)
            
            # Parse VMAF score from output (since we're not using JSON output)
            vmaf_match = re.search(r'VMAF score: (\d+\.\d+)', stderr_output)
            if vmaf_match:
                vmaf_score = float(vmaf_match.group(1))
                logger.info(f"Extracted VMAF score from output: {vmaf_score}")
                
                # Create results object
                formatted_results = {
                    'vmaf_score': vmaf_score,
                    'psnr': None,  # Will need to be extracted from JSON if needed
                    'ssim': None,  # Will need to be extracted from JSON if needed
                    'reference_path': reference_path,
                    'distorted_path': distorted_path,
                    'model_path': model_path,
                    'json_path': output_json,
                    'csv_path': output_csv,
                    'raw_results': {'vmaf': {'score': vmaf_score}}
                }
                
                # Parse JSON results if available
                if os.path.exists(output_json):
                    try:
                        with open(output_json, 'r') as f:
                            json_data = json.load(f)
                            formatted_results['raw_results'] = json_data
                    except Exception as e:
                        logger.warning(f"Error parsing JSON results: {str(e)}")
                
                # Log and emit results
                logger.info(f"VMAF analysis complete. Score: {vmaf_score}")
                self.status_update.emit(f"VMAF analysis complete. Score: {vmaf_score:.2f}")
                self.analysis_complete.emit(formatted_results)
                
                return formatted_results
            else:
                error_msg = "Could not extract VMAF score from output"
                logger.error(error_msg)
                logger.error(f"STDERR: {stderr_output}")
                # Provide more detailed error message to user
                detailed_error = f"{error_msg}\nCommand: {' '.join(cmd)}\nFFmpeg error: {stderr_output.splitlines()[0] if stderr_output else 'Unknown error'}"
                self.error_occurred.emit(detailed_error)
                return None
                
        except Exception as e:
            error_msg = f"Error in VMAF analysis: {str(e)}"
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            return None
  
  
           
    def _get_video_info(self, video_path):
        """Get video information using FFprobe"""
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
            
            # Find video stream
            video_stream = None
            for stream in info.get('streams', []):
                if stream.get('codec_type') == 'video':
                    video_stream = stream
                    break
                    
            if not video_stream:
                logger.error("No video stream found")
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
            logger.error(f"Error getting video info: {str(e)}")
            return None
            
    def _resize_video(self, video_path, target_width, target_height):
        """Resize a video to match the target dimensions"""
        try:
            # Create temporary file for output
            output_dir = os.path.dirname(video_path)
            output_name = f"{os.path.splitext(os.path.basename(video_path))[0]}_resized.mp4"
            output_path = os.path.join(output_dir, output_name)
            
            # Build FFmpeg command
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
            
            # Run command
            self.status_update.emit(f"Resizing video to {target_width}x{target_height}...")
            subprocess.run(cmd, capture_output=True, check=True)
            
            # Verify file was created
            if not os.path.exists(output_path):
                raise RuntimeError("Failed to create resized video")
                
            return output_path
            
        except Exception as e:
            logger.error(f"Error resizing video: {str(e)}")
            self.error_occurred.emit(f"Error resizing video: {str(e)}")
            return video_path  # Return original on error

class VMAFAnalysisThread(QThread):
    """Thread for running VMAF analysis"""
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
        
        # Connect signals
        self.analyzer.analysis_progress.connect(self.analysis_progress)
        self.analyzer.analysis_complete.connect(self.analysis_complete)
        self.analyzer.error_occurred.connect(self.error_occurred)
        self.analyzer.status_update.connect(self.status_update)
        
    def run(self):
        """Run analysis in thread"""
        self.analyzer.analyze_videos(
            self.reference_path,
            self.distorted_path,
            self.model_path,
            self.duration
        )