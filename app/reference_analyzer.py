import subprocess
import json
import re
import os
import logging
import cv2
from PyQt5.QtCore import QObject, pyqtSignal, QThread

logger = logging.getLogger(__name__)

class ReferenceAnalyzer(QObject):
    """Analyzes reference videos to extract metadata"""
    analysis_complete = pyqtSignal(dict)
    progress_update = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        
    def get_video_info(self, video_path):
        """Extract metadata from video file using FFprobe"""
        try:
            self.progress_update.emit(f"Analyzing reference video: {os.path.basename(video_path)}")
            
            # Use FFprobe to get video information
            cmd = [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                video_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                error_msg = f"FFprobe failed: {result.stderr}"
                logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                return None
                
            # Parse JSON output
            info = json.loads(result.stdout)
            
            # Get video stream info
            video_stream = None
            for stream in info.get('streams', []):
                if stream.get('codec_type') == 'video':
                    video_stream = stream
                    break
            
            if not video_stream:
                self.error_occurred.emit("No video stream found in reference file")
                return None
                
            # Extract key information
            format_info = info.get('format', {})
            duration = float(format_info.get('duration', 0))
            
            frame_rate_str = video_stream.get('avg_frame_rate', '0/0')
            frame_rate = self._parse_frame_rate(frame_rate_str)
            
            total_frames = int(video_stream.get('nb_frames', 0))
            
            # If nb_frames is not available, estimate from duration and frame rate
            if total_frames == 0 and frame_rate > 0:
                total_frames = int(duration * frame_rate)
            
            # Get width, height, codec
            width = int(video_stream.get('width', 0))
            height = int(video_stream.get('height', 0))
            codec = video_stream.get('codec_name', 'unknown')
            
            # Check for trigger frame
            has_trigger = self._check_for_trigger(video_path)
            
            video_info = {
                'path': video_path,
                'duration': duration,
                'frame_rate': frame_rate,
                'total_frames': total_frames,
                'width': width,
                'height': height,
                'codec': codec,
                'has_trigger': has_trigger
            }
            
            self.progress_update.emit(f"Analysis complete: {duration:.2f} seconds, {frame_rate} fps, {width}x{height}")
            self.analysis_complete.emit(video_info)
            return video_info
            
        except Exception as e:
            error_msg = f"Error analyzing video: {str(e)}"
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            return None
            
    def _parse_frame_rate(self, frame_rate_str):
        """Parse frame rate string (e.g., '30000/1001') to float"""
        try:
            if '/' in frame_rate_str:
                num, den = map(int, frame_rate_str.split('/'))
                if den == 0:
                    return 0
                return num / den
            else:
                return float(frame_rate_str)
        except (ValueError, ZeroDivisionError):
            return 0
            
    def _check_for_trigger(self, video_path):
        """Check if video begins with a white 'STARTING' trigger frame"""
        try:
            # Open video
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                logger.warning(f"Could not open video for trigger check: {video_path}")
                return False
                
            # Sample first few frames
            white_frame_detected = False
            
            # Check first 30 frames (or first second) for trigger
            max_frames = 30
            
            for i in range(max_frames):
                ret, frame = cap.read()
                if not ret:
                    break
                    
                # Convert to grayscale
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                
                # Check if predominantly white
                white_pixel_count = cv2.countNonZero(cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)[1])
                total_pixels = gray.shape[0] * gray.shape[1]
                white_percentage = white_pixel_count / total_pixels
                
                # If at least 85% white, consider it a trigger frame
                if white_percentage > 0.85:
                    white_frame_detected = True
                    logger.info(f"White trigger frame detected at frame {i}")
                    break
                    
            cap.release()
            return white_frame_detected
            
        except Exception as e:
            logger.error(f"Error checking for trigger frame: {e}")
            return False
            
class ReferenceAnalysisThread(QThread):
    """Thread for reference video analysis"""
    analysis_complete = pyqtSignal(dict)
    progress_update = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, video_path):
        super().__init__()
        self.video_path = video_path
        self.analyzer = ReferenceAnalyzer()
        
        # Connect signals
        self.analyzer.analysis_complete.connect(self.analysis_complete)
        self.analyzer.progress_update.connect(self.progress_update)
        self.analyzer.error_occurred.connect(self.error_occurred)
        
    def run(self):
        """Run analysis in separate thread"""
        self.analyzer.get_video_info(self.video_path)