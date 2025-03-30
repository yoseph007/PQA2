import cv2
import os
import numpy as np
import logging
import subprocess
from PyQt5.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)

class TriggerDetectorThread(QThread):
    """Thread for detecting white frame triggers using FFmpeg"""
    trigger_detected = pyqtSignal(int)  # Frame number where trigger was detected
    frame_processed = pyqtSignal(np.ndarray)
    error_occurred = pyqtSignal(str)
    status_update = pyqtSignal(str)
    
    def __init__(self, device_name, threshold=0.85, consecutive_frames=3):
        super().__init__()
        self.device_name = device_name
        self.threshold = threshold
        self.consecutive_frames = consecutive_frames
        self.white_frame_count = 0
        self._running = True
        self.frame_count = 0
        self.process = None
        
    def run(self):
        """Main detection loop"""
        temp_dir = None
        try:
            # Create a temp dir for frames if needed
            import tempfile
            temp_dir = tempfile.mkdtemp()
            self.status_update.emit(f"Opening device: {self.device_name}")
            
            # Build FFmpeg command to capture frames from DeckLink
            cmd = [
                "ffmpeg",
                "-f", "decklink",
                "-i", self.device_name,
                "-vf", "fps=10",  # Reduce frame rate for processing
                "-vframes", "300",  # Limit to 30 seconds at 10fps
                "-c:v", "mjpeg",  # Use MJPEG for fast encoding
                "-q:v", "3",  # High quality
                "-f", "image2pipe",  # Pipe to stdout
                "-"  # Output to pipe
            ]
            
            logger.info(f"Starting FFmpeg for trigger detection: {' '.join(cmd)}")
            
            # Start FFmpeg process
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=10*1024*1024  # 10MB buffer
            )
            
            self.status_update.emit("Watching for white 'STARTING' frame...")
            
            # Prepare buffer for collecting frame data
            buffer = bytearray()
            jpg_start = bytearray([0xFF, 0xD8])
            jpg_end = bytearray([0xFF, 0xD9])
            
            # Process frames until trigger detected
            while self._running:
                # Read chunk from FFmpeg stdout
                chunk = self.process.stdout.read(4096)
                if not chunk:
                    break
                    
                # Add to buffer
                buffer.extend(chunk)
                
                # Look for complete JPEG frames
                start_pos = buffer.find(jpg_start)
                while start_pos != -1:
                    end_pos = buffer.find(jpg_end, start_pos)
                    if end_pos == -1:
                        # Incomplete frame, keep reading
                        break
                        
                    # Extract complete JPEG frame
                    frame_data = buffer[start_pos:end_pos+2]
                    
                    # Remove processed data from buffer
                    buffer = buffer[end_pos+2:]
                    
                    # Decode frame
                    frame = cv2.imdecode(np.frombuffer(frame_data, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if frame is None:
                        start_pos = buffer.find(jpg_start)
                        continue
                        
                    # Process frame
                    self.frame_count += 1
                    
                    # Send frame for display
                    self.frame_processed.emit(frame)
                    
                    # Check if this is a white frame
                    is_white = self._is_white_frame(frame)
                    
                    if is_white:
                        self.white_frame_count += 1
                        self.status_update.emit(f"Potential trigger frame: {self.white_frame_count}/{self.consecutive_frames}")
                        
                        if self.white_frame_count >= self.consecutive_frames:
                            trigger_frame = self.frame_count
                            logger.info(f"Trigger detected at frame {trigger_frame}")
                            self.status_update.emit(f"TRIGGER DETECTED at frame {trigger_frame}")
                            self.trigger_detected.emit(trigger_frame)
                            self._running = False
                            break
                    else:
                        # Reset counter if frames aren't consecutive
                        if self.white_frame_count > 0:
                            self.white_frame_count = 0
                            
                    # Update start position for next search
                    start_pos = buffer.find(jpg_start)
                    
            # Clean up
            if self.process and self.process.poll() is None:
                self.process.terminate()
                
        except Exception as e:
            error_msg = f"Trigger detection error: {str(e)}"
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            
        finally:
            # Clean up temp dir if created
            if temp_dir and os.path.exists(temp_dir):
                import shutil
                shutil.rmtree(temp_dir)
                
    def _is_white_frame(self, frame):
        """Determine if frame is predominantly white (trigger frame)"""
        # Convert to grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Count white pixels (brightness > 200 out of 255)
        white_pixel_count = np.sum(gray > 200)
        total_pixels = gray.shape[0] * gray.shape[1]
        white_percentage = white_pixel_count / total_pixels
        
        # Return True if percentage exceeds threshold
        return white_percentage > self.threshold
        
    def stop(self):
        """Stop trigger detection"""
        self._running = False
        
        # Stop FFmpeg process if running
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    logger.warning("FFmpeg process didn't terminate, killing it")
                    self.process.kill()
                    self.process.wait()
            except Exception as e:
                logger.error(f"Error stopping FFmpeg process: {e}")
                pass