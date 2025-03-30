import logging
import time
import os
import cv2
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)

class DummyCaptureThread(QThread):
    """Simulates a capture device for testing without hardware"""
    progress_updated = pyqtSignal(int)
    frame_captured = pyqtSignal(np.ndarray)
    capture_complete = pyqtSignal()
    capture_failed = pyqtSignal(str)
    
    def __init__(self, output_path, duration=10):
        super().__init__()
        self.output_path = output_path
        self.duration = duration  # seconds
        self.fps = 30
        self.resolution = (1920, 1080)
        self._running = True
        
    def run(self):
        """Generate simulated video frames"""
        logger.info(f"Starting dummy capture to {self.output_path}")
        
        try:
            # Create output directory if needed
            os.makedirs(os.path.dirname(os.path.abspath(self.output_path)), exist_ok=True)
            
            # Create video writer
            fourcc = cv2.VideoWriter_fourcc(*'XVID')
            out = cv2.VideoWriter(self.output_path, fourcc, self.fps, self.resolution)
            
            total_frames = self.fps * self.duration
            
            # Create some test patterns
            patterns = [
                self._create_color_bars(),
                self._create_gradient(),
                self._create_checkerboard()
            ]
            
            # Simulate white "STARTING" frame at the beginning
            start_frame = np.ones((self.resolution[1], self.resolution[0], 3), dtype=np.uint8) * 255
            cv2.putText(start_frame, "STARTING", (self.resolution[0]//2 - 200, self.resolution[1]//2),
                        cv2.FONT_HERSHEY_SIMPLEX, 3, (0, 0, 0), 5)
            
            # Write start frame for half a second
            for _ in range(self.fps // 2):
                out.write(start_frame)
            
            # Generate test pattern frames
            for frame_num in range(total_frames):
                if not self._running:
                    break
                    
                # Choose pattern based on time
                pattern_idx = (frame_num // (self.fps * 2)) % len(patterns)
                frame = patterns[pattern_idx].copy()
                
                # Add frame counter
                cv2.putText(frame, f"Frame: {frame_num}", (50, 50),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                
                # Add timestamp
                timestamp = time.strftime("%H:%M:%S")
                cv2.putText(frame, timestamp, (50, self.resolution[1] - 50),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                
                # Write frame
                out.write(frame)
                
                # Emit progress
                self.progress_updated.emit(frame_num)
                self.frame_captured.emit(frame)
                
                # Simulate realistic timing
                time.sleep(1.0 / self.fps)
            
            # Release resources
            out.release()
            self.capture_complete.emit()
            logger.info("Dummy capture completed successfully")
            
        except Exception as e:
            error_msg = f"Dummy capture failed: {str(e)}"
            logger.error(error_msg)
            self.capture_failed.emit(error_msg)
    
    def stop(self):
        """Stop the capture simulation"""
        self._running = False
    
    def _create_color_bars(self):
        """Create color bars test pattern"""
        frame = np.zeros((self.resolution[1], self.resolution[0], 3), dtype=np.uint8)
        bar_width = self.resolution[0] // 8
        
        colors = [
            (255, 255, 255),  # White
            (255, 255, 0),    # Yellow
            (0, 255, 255),    # Cyan
            (0, 255, 0),      # Green
            (255, 0, 255),    # Magenta
            (255, 0, 0),      # Red
            (0, 0, 255),      # Blue
            (0, 0, 0)         # Black
        ]
        
        for i, color in enumerate(colors):
            frame[:, i*bar_width:(i+1)*bar_width] = color
            
        return frame
    
    def _create_gradient(self):
        """Create gradient test pattern"""
        frame = np.zeros((self.resolution[1], self.resolution[0], 3), dtype=np.uint8)
        
        # Create horizontal gradient
        for i in range(self.resolution[0]):
            value = int(255 * i / self.resolution[0])
            frame[:, i] = (value, value, value)
            
        return frame
    
    def _create_checkerboard(self):
        """Create checkerboard test pattern"""
        frame = np.zeros((self.resolution[1], self.resolution[0], 3), dtype=np.uint8)
        square_size = 64
        
        for y in range(0, self.resolution[1], square_size):
            for x in range(0, self.resolution[0], square_size):
                if ((x // square_size) + (y // square_size)) % 2 == 0:
                    frame[y:min(y+square_size, self.resolution[1]), 
                          x:min(x+square_size, self.resolution[0])] = (255, 255, 255)
                    
        return frame

class DummyMode:
    """Allows the application to run without actual capture hardware"""
    
    @staticmethod
    def get_dummy_devices():
        """Return a list of simulated devices"""
        return [
            {
                "id": "dummy0",
                "name": "Simulated DeckLink 4K",
                "input": True
            },
            {
                "id": "dummy1",
                "name": "Simulated Intensity Pro",
                "input": True
            }
        ]
    
    @staticmethod
    def is_dummy_device(device_id):
        """Check if a device ID is a dummy device"""
        return device_id and device_id.startswith("dummy")
    
    @staticmethod
    def create_capture_thread(device_id, output_path, duration=10):
        """Create a dummy capture thread for the specified device"""
        return DummyCaptureThread(output_path, duration)