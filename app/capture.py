import os
import logging
import subprocess
import re
import time
import platform
from datetime import datetime
import cv2
import numpy as np
from PyQt5.QtCore import QObject, pyqtSignal, QThread, pyqtSlot, QTimer
from enum import Enum
from .trigger_detector import TriggerDetectorThread

logger = logging.getLogger(__name__)


class CaptureMonitor(QThread):
    """Thread to monitor FFmpeg capture process"""
    progress_updated = pyqtSignal(int)
    capture_complete = pyqtSignal()
    capture_failed = pyqtSignal(str)

    def __init__(self, process, duration=None):
        super().__init__()
        self.process = process
        self._running = True
        self.error_output = ""
        self.start_time = time.time()
        self.duration = duration  # Expected duration in seconds
        
    def run(self):
        """Monitor process output and emit signals"""
        logger.debug("Starting capture monitor")
        
        while self._running:
            # Check for process completion
            if self.process.poll() is not None:
                if self.process.returncode == 0:
                    logger.info("Capture completed successfully")
                    self.capture_complete.emit()
                else:
                    # Get any remaining error output
                    error = self.error_output
                    if hasattr(self.process.stderr, 'read'):
                        try:
                            remaining = self.process.stderr.read()
                            if remaining:
                                error += remaining
                        except:
                            pass
                            
                    logger.error(f"Capture failed with code {self.process.returncode}: {error}")
                    self.capture_failed.emit(error)
                break
                
            # Check for duration timeout
            if self.duration and (time.time() - self.start_time) > self.duration + 30:  # Add 10s buffer
                logger.warning(f"Capture exceeded expected duration ({self.duration}s), terminating")
                self._terminate_process()
                self.capture_complete.emit()
                break

            # Parse process output
            if hasattr(self.process.stderr, 'readline'):
                try:
                    line = self.process.stderr.readline()
                    if line:
                        self.error_output += line
                        logger.debug(f"FFmpeg output: {line.strip()}")
                        
                        # Parse progress (frame number)
                        if "frame=" in line:
                            try:
                                match = re.search(r'frame=\s*(\d+)', line)
                                if match:
                                    frame_num = int(match.group(1))
                                    self.progress_updated.emit(frame_num)
                            except (ValueError, AttributeError) as e:
                                logger.warning(f"Error parsing frame number: {e}")
                        
                        # Check for common error patterns
                        if "Error" in line or "Invalid" in line:
                            logger.warning(f"Potential error in FFmpeg output: {line.strip()}")
                except Exception as e:
                    logger.warning(f"Error reading FFmpeg output: {e}")
                        
            time.sleep(0.1)
            
    def _terminate_process(self):
        """Safely terminate the FFmpeg process"""
        if self.process and self.process.poll() is None:
            try:
                logger.info("Terminating FFmpeg process")
                self.process.terminate()
                
                # Wait for process to terminate
                for _ in range(50):  # 5 second timeout
                    if self.process.poll() is not None:
                        break
                    time.sleep(0.1)
                    
                # Force kill if still running
                if self.process.poll() is None:
                    logger.warning("Process did not terminate, forcing kill")
                    self.process.kill()
            except Exception as e:
                logger.error(f"Error terminating process: {e}")

    def stop(self):
        """Stop monitoring"""
        self._running = False
        self._terminate_process()





class CaptureState(Enum):
    """Capture process states"""
    IDLE = 0
    WAITING_FOR_TRIGGER = 1
    CAPTURING = 2
    PROCESSING = 3
    COMPLETED = 4
    ERROR = 5

class CaptureManager(QObject):
    """Main manager for video capture process with trigger detection"""
    # Status signals
    status_update = pyqtSignal(str)
    progress_update = pyqtSignal(int)
    state_changed = pyqtSignal(CaptureState)
    
    # Process signals
    capture_started = pyqtSignal()
    capture_finished = pyqtSignal(bool, str)  # success, output_path
    trigger_frame_available = pyqtSignal(np.ndarray)
    
    def __init__(self):
        super().__init__()
        logger.info("Initializing CaptureManager")
        
        # Process state
        self.state = CaptureState.IDLE
        self.ffmpeg_process = None
        self.capture_monitor = None
        self.trigger_detector = None
        
        # Video info
        self.reference_info = None
        self.current_output_path = None
        
        # Output settings
        self.output_directory = None
        self.test_name = None
        
        # Path manager (will be set by main app)
        self.path_manager = None
        
        # Find ffmpeg
        self._ffmpeg_path = self._find_ffmpeg()
        if self._ffmpeg_path:
            logger.info(f"Found FFmpeg at: {self._ffmpeg_path}")
        else:
            logger.warning("FFmpeg not found, using 'ffmpeg' command")
            self._ffmpeg_path = "ffmpeg"
            
    def _find_ffmpeg(self):
        """Find FFmpeg executable"""
        try:
            # Simple check if ffmpeg is in PATH
            result = subprocess.run(
                ["ffmpeg", "-version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            if result.returncode == 0:
                return "ffmpeg"
        except Exception as e:
            logger.error(f"Error locating FFmpeg: {e}")
            
        return "ffmpeg"  # Default to command name
    
    def set_output_directory(self, output_dir):
        """Set custom output directory"""
        self.output_directory = output_dir
        logger.info(f"Output directory set to: {output_dir}")
    
    def set_test_name(self, test_name):
        """Set test name for output files"""
        self.test_name = test_name
        logger.info(f"Test name set to: {test_name}")
        
    @property
    def is_capturing(self):
        """Check if capture is active"""
        return self.state in [CaptureState.WAITING_FOR_TRIGGER, CaptureState.CAPTURING]
        
    def set_reference_video(self, reference_info):
        """Set reference video information"""
        self.reference_info = reference_info
        logger.info(f"Reference video set: {os.path.basename(reference_info['path'])}, " +
                   f"duration: {reference_info['duration']:.2f}s, " +
                   f"resolution: {reference_info['width']}x{reference_info['height']}")
                   
    def start_trigger_detection(self, device_name, threshold=0.85, consecutive_frames=3):
        """Start detecting the white frame trigger"""
        if self.is_capturing:
            logger.warning("Capture already in progress")
            return False
            
        if not self.reference_info:
            error_msg = "No reference video set. Please select a reference video first."
            logger.error(error_msg)
            self.status_update.emit(error_msg)
            self.capture_finished.emit(False, error_msg)
            return False
        
        # Try to connect to the device with retries
        connected, message = self._try_connect_device(device_name, max_retries=3)
        if not connected:
            # Try force-reset as last resort
            logger.warning("Initial connection attempts failed, trying force reset...")
            self.status_update.emit("Connection attempts failed, trying device reset...")
            reset_success, reset_msg = self._force_reset_device(device_name)
            
            if not reset_success:
                error_msg = f"Cannot access capture device after reset: {reset_msg}"
                logger.error(error_msg)
                self.status_update.emit(error_msg)
                self.state = CaptureState.ERROR
                self.state_changed.emit(self.state)
                self.capture_finished.emit(False, error_msg)
                return False
                
            # Try one more connection after reset
            connected, message = self._try_connect_device(device_name, max_retries=1)
            if not connected:
                error_msg = f"Cannot access capture device even after reset: {message}"
                logger.error(error_msg)
                self.status_update.emit(error_msg)
                self.state = CaptureState.ERROR
                self.state_changed.emit(self.state)
                self.capture_finished.emit(False, error_msg)
                return False
            
        # Update state
        self.state = CaptureState.WAITING_FOR_TRIGGER
        self.state_changed.emit(self.state)
        
        # Create trigger detector with the specified settings
        self.trigger_detector = TriggerDetectorThread(
            device_name,
            threshold=threshold,
            consecutive_frames=consecutive_frames
        )
        
        # Connect signals
        self.trigger_detector.trigger_detected.connect(self._on_trigger_detected)
        self.trigger_detector.frame_processed.connect(self.trigger_frame_available)
        self.trigger_detector.status_update.connect(self.status_update)
        self.trigger_detector.error_occurred.connect(self._on_trigger_error)
        
        # Start detection
        self.trigger_detector.start()
        self.status_update.emit(f"Waiting for white 'STARTING' frame (need {consecutive_frames} consecutive frames)...")
        logger.info(f"Trigger detection started for device: {device_name}, threshold: {threshold}, consecutive frames: {consecutive_frames}")
        
        return True
        
    def _on_trigger_detected(self, trigger_frame):
        """Handle trigger detection"""
        logger.info(f"Trigger detected at frame {trigger_frame}")
        self.status_update.emit(f"Trigger detected! Starting capture...")
        
        # Stop the detector now that we've found the trigger
        if self.trigger_detector:
            self.trigger_detector.stop()
            self.trigger_detector = None
            
        # Get ready to start capturing
        self._prepare_output_path()
        
        # Delay slightly to make sure we're past the trigger frame
        QTimer.singleShot(500, self._start_capture_after_trigger)
        
    def _on_trigger_error(self, error_msg):
        """Handle trigger detection errors"""
        logger.error(f"Trigger detection error: {error_msg}")
        self.status_update.emit(f"Error: {error_msg}")
        self.state = CaptureState.ERROR
        self.state_changed.emit(self.state)
        self.capture_finished.emit(False, error_msg)
        
    def _prepare_output_path(self):
        """Generate output path based on user settings and reference video"""
        # Get reference info for filename
        ref_path = self.reference_info['path']
        ref_name = os.path.splitext(os.path.basename(ref_path))[0]
        
        # If path manager isn't set, use basic path handling
        if not hasattr(self, 'path_manager') or self.path_manager is None:
            # Determine output directory
            if self.output_directory and os.path.exists(self.output_directory):
                # Use user-selected output directory
                output_dir = self.output_directory
                
                # Create test subdirectory if test name is specified
                if self.test_name:
                    # Clean test name to avoid path issues
                    safe_test_name = self.test_name.replace('\\', '_').replace('/', '_')
                    output_dir = os.path.join(output_dir, safe_test_name)
                    
                # Ensure the directory exists
                os.makedirs(output_dir, exist_ok=True)
            else:
                # Fallback to reference directory if no custom directory set
                output_dir = os.path.dirname(ref_path)
                logger.warning("No custom output directory set, using reference directory")
            
            # Create output path
            self.current_output_path = os.path.join(output_dir, f"{ref_name}_capture.mp4")
        else:
            # Use path manager for consistent path handling
            if self.output_directory and os.path.exists(self.output_directory):
                test_name = self.test_name or "default_test"
                output_filename = f"{ref_name}_capture.mp4"
                
                self.current_output_path = self.path_manager.get_output_path(
                    self.output_directory, 
                    test_name,
                    output_filename
                )
            else:
                # Fallback to reference directory
                output_dir = os.path.dirname(ref_path)
                output_filename = f"{ref_name}_capture.mp4"
                
                self.current_output_path = self.path_manager.get_output_path(
                    output_dir,
                    "default_test",
                    output_filename
                )
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(os.path.abspath(self.current_output_path)), exist_ok=True)
        
        logger.info(f"Output path set to: {self.current_output_path}")
            
    def _start_capture_after_trigger(self):
        """Start the actual FFmpeg capture process after trigger"""
        # Reset state from WAITING_FOR_TRIGGER to IDLE before starting capture
        self.state = CaptureState.IDLE
        
        if not self.reference_info:
            error_msg = "No reference video selected"
            logger.error(error_msg)
            self.capture_finished.emit(False, error_msg)
            return
            
        # Calculate duration based on reference, subtracting time for trigger frame
        duration = self.reference_info['duration']
        frame_rate = self.reference_info.get('frame_rate', 25)
        
        # Subtract one frame worth of time if using trigger
        if frame_rate > 0:
            frame_duration = 1.0 / frame_rate
            adjusted_duration = duration - frame_duration
        else:
            adjusted_duration = duration
            
        logger.info(f"Adjusting capture duration from {duration}s to {adjusted_duration}s to account for trigger frame")
        
        # Start capture process
        self.start_capture(
            "Intensity Shuttle",  # Hardcoded for now, should match trigger device
            self.current_output_path,
            duration=adjusted_duration
        )
        
    def start_capture(self, device_name, output_path=None, duration=None):
        """Start capture process directly (without trigger detection)"""
        if self.is_capturing:
            logger.warning("Capture already in progress")
            return False
            
        if not self.reference_info and not duration:
            error_msg = "No reference video selected and no duration specified"
            logger.error(error_msg)
            self.status_update.emit(error_msg)
            self.capture_finished.emit(False, error_msg)
            return False
        
        # Try to connect to the device with retries
        connected, message = self._try_connect_device(device_name, max_retries=3)
        if not connected:
            # Try force-reset as last resort
            logger.warning("Initial connection attempts failed, trying force reset...")
            self.status_update.emit("Connection attempts failed, trying device reset...")
            reset_success, reset_msg = self._force_reset_device(device_name)
            
            if not reset_success:
                error_msg = f"Cannot access capture device after reset: {reset_msg}"
                logger.error(error_msg)
                self.status_update.emit(error_msg)
                self.state = CaptureState.ERROR
                self.state_changed.emit(self.state)
                self.capture_finished.emit(False, error_msg)
                return False
                
            # Try one more connection after reset
            connected, message = self._try_connect_device(device_name, max_retries=1)
            if not connected:
                error_msg = f"Cannot access capture device even after reset: {message}"
                logger.error(error_msg)
                self.status_update.emit(error_msg)
                self.state = CaptureState.ERROR
                self.state_changed.emit(self.state)
                self.capture_finished.emit(False, error_msg)
                return False
            
        # Calculate duration from reference if not specified
        if not duration and self.reference_info:
            duration = self.reference_info['duration']
            
        # Set output path if not specified
        if output_path:
            self.current_output_path = output_path
        else:
            self._prepare_output_path()
            
        # Create output directory if needed
        output_dir = os.path.dirname(os.path.abspath(self.current_output_path))
        os.makedirs(output_dir, exist_ok=True)
        
        # Test directory write permissions
        test_file_path = os.path.join(output_dir, "test_write.tmp")
        try:
            with open(test_file_path, 'w') as f:
                f.write("test")
            os.remove(test_file_path)
        except Exception as e:
            error_msg = f"Cannot write to output directory: {e}"
            logger.error(error_msg)
            self.status_update.emit(error_msg)
            self.state = CaptureState.ERROR
            self.state_changed.emit(self.state)
            self.capture_finished.emit(False, error_msg)
            return False
        
        try:
            logger.info(f"Starting capture from {device_name} to {self.current_output_path}")
            self.status_update.emit(f"Starting capture for {duration:.1f} seconds...")
            
            # Build FFmpeg command
            cmd = [
                self._ffmpeg_path,
                "-y",  # Overwrite output
                "-f", "decklink",
                "-i", device_name,  # No @ symbol
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "18"  # Better quality
            ]
            
            # Add duration limit
            if duration:
                cmd.extend(["-t", str(duration)])
                
            # Use forward slashes for FFmpeg
            ffmpeg_output_path = self.current_output_path.replace('\\', '/')
                
            # Add output path
            cmd.append(ffmpeg_output_path)
            
            # Log command
            logger.info(f"FFmpeg capture command: {' '.join(cmd)}")
            
            # Start FFmpeg process
            self.ffmpeg_process = subprocess.Popen(
                cmd,
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stdin=subprocess.PIPE,
                universal_newlines=True
            )
            
            # Start monitoring
            self.capture_monitor = CaptureMonitor(self.ffmpeg_process, duration)
            self.capture_monitor.progress_updated.connect(self.progress_update)
            self.capture_monitor.capture_complete.connect(self._on_capture_complete)
            self.capture_monitor.capture_failed.connect(self._on_capture_failed)
            self.capture_monitor.start()
            
            # Update state
            self.state = CaptureState.CAPTURING
            self.state_changed.emit(self.state)
            self.capture_started.emit()
            
            return True
            
        except Exception as e:
            error_msg = f"Failed to start capture: {str(e)}"
            logger.error(error_msg)
            self.status_update.emit(error_msg)
            self.state = CaptureState.ERROR
            self.state_changed.emit(self.state)
            self.capture_finished.emit(False, error_msg)
            return False
            
    def stop_capture(self):
        """Stop any active capture process"""
        if not self.is_capturing:
            return
            
        logger.info("Stopping capture")
        self.status_update.emit("Stopping capture...")
        
        # Stop trigger detection if active
        if self.trigger_detector:
            self.trigger_detector.stop()
            self.trigger_detector = None
            
        # Stop capture monitor if active
        if self.capture_monitor:
            self.capture_monitor.stop()
        
        # Force kill any lingering FFmpeg processes
        if self.ffmpeg_process and self.ffmpeg_process.poll() is None:
            try:
                # Try to terminate gracefully first
                self.ffmpeg_process.terminate()
                # Wait a short time for it to terminate
                for _ in range(10):  # 1 second timeout
                    if self.ffmpeg_process.poll() is not None:
                        break
                    time.sleep(0.1)
                    
                # If still running, force kill
                if self.ffmpeg_process.poll() is None:
                    self.ffmpeg_process.kill()
                    # Make sure it's dead
                    self.ffmpeg_process.wait()
            except Exception as e:
                logger.error(f"Error killing FFmpeg process: {e}")
        
        # Reset state
        self.state = CaptureState.IDLE
        self.state_changed.emit(self.state)
        self.ffmpeg_process = None
        
        # Add delay before allowing another capture
        time.sleep(1)  # 1 second delay
        
        self.status_update.emit("Capture stopped by user")
        self.capture_finished.emit(True, self.current_output_path)
        
    def _on_capture_complete(self):
        """Handle successful capture"""
        output_path = self.current_output_path
        logger.info(f"Capture completed: {output_path}")
        
        # Verify the output file
        if not os.path.exists(output_path):
            logger.error(f"Output file doesn't exist: {output_path}")
            error_msg = f"Capture failed: Output file is missing"
            self.state = CaptureState.ERROR
            self.state_changed.emit(self.state)
            self.capture_finished.emit(False, error_msg)
            return
            
        if os.path.getsize(output_path) == 0:
            logger.error(f"Output file is empty: {output_path}")
            error_msg = f"Capture failed: Output file is empty"
            self.state = CaptureState.ERROR
            self.state_changed.emit(self.state)
            self.capture_finished.emit(False, error_msg)
            return
            
        # Move to processing state
        self.state = CaptureState.PROCESSING
        self.state_changed.emit(self.state)
        self.status_update.emit("Capture complete, processing video...")
        
        # Start post-processing
        QTimer.singleShot(500, lambda: self._post_process_capture(output_path))
        
    def _on_capture_failed(self, error_msg):
        """Handle capture failure"""
        logger.error(f"Capture failed: {error_msg}")
        
        # Clean up resources
        self.ffmpeg_process = None
        self.capture_monitor = None
        
        # Update state
        self.state = CaptureState.ERROR
        self.state_changed.emit(self.state)
        
        # Check if it's a device error that might be recoverable
        device_error = "Cannot access" in error_msg or "Error opening input" in error_msg or "No such device" in error_msg
        
        if device_error:
            # Try recovery
            self.status_update.emit("Device error detected, attempting recovery...")
            recovered, message = self.recover_from_error("Intensity Shuttle", error_msg)
            
            if recovered:
                user_msg = f"Capture failed but device has been recovered. You can try capturing again.\n\nOriginal error: {error_msg}"
            else:
                user_msg = "Cannot access the capture device. Please check that:\n\n" \
                           "1. The device is properly connected\n" \
                           "2. Blackmagic drivers are installed\n" \
                           "3. No other application is using the device\n" \
                           "4. Try restarting the application"
        else:
            user_msg = f"Capture failed: {error_msg}"
            
        self.status_update.emit(f"Error: {user_msg}")
        self.capture_finished.emit(False, user_msg)
 
    def _post_process_capture(self, output_path):
        """Process captured video to remove trigger and prepare for VMAF"""
        try:
            # For now, just verify the file is valid
            logger.info(f"Processing captured video: {output_path}")
            self.status_update.emit("Processing captured video...")
            
            # Give some time for file finalization
            max_retries = 5
            for retry in range(max_retries):
                # Verify file exists and is valid
                if not os.path.exists(output_path):
                    if retry < max_retries - 1:
                        logger.warning(f"Output file not found, waiting (retry {retry+1}/{max_retries})")
                        time.sleep(1)
                        continue
                    raise FileNotFoundError(f"Output file not found: {output_path}")
                    
                if os.path.getsize(output_path) == 0:
                    if retry < max_retries - 1:
                        logger.warning(f"Output file is empty, waiting (retry {retry+1}/{max_retries})")
                        time.sleep(1)
                        continue
                    raise ValueError("Output file is empty")
                
                # Try to repair MP4 file if needed
                try:
                    self._repair_mp4_if_needed(output_path)
                except Exception as repair_e:
                    logger.warning(f"Could not repair MP4: {repair_e}")
                
                # Check file using FFprobe
                cmd = [
                    "ffprobe",
                    "-v", "error",
                    "-select_streams", "v:0",
                    "-show_entries", "stream=codec_type",
                    "-of", "csv=p=0",
                    output_path
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0 or "video" not in result.stdout:
                    if retry < max_retries - 1:
                        logger.warning(f"Invalid video file, waiting (retry {retry+1}/{max_retries})")
                        time.sleep(2)  # Wait longer on validation errors
                        continue
                    raise ValueError(f"Invalid video file: {result.stderr}")
                
                # If we got here, file is valid
                break
            
            # Mark as completed
            self.state = CaptureState.COMPLETED
            self.state_changed.emit(self.state)
            self.status_update.emit("Capture and processing complete")
            self.capture_finished.emit(True, output_path)
            
        except Exception as e:
            error_msg = f"Error processing capture: {str(e)}"
            logger.error(error_msg)
            self.state = CaptureState.ERROR
            self.state_changed.emit(self.state)
            self.status_update.emit(f"Error: {error_msg}")
            self.capture_finished.emit(False, error_msg)

    def _repair_mp4_if_needed(self, mp4_path):
        """Attempt to repair an MP4 file with missing moov atom"""
        try:
            # Create temporary output path
            output_dir = os.path.dirname(mp4_path)
            temp_path = os.path.join(output_dir, f"temp_fixed_{os.path.basename(mp4_path)}")
            
            # Run FFmpeg to copy and potentially fix the file
            cmd = [
                self._ffmpeg_path,
                "-v", "warning",
                "-i", mp4_path,
                "-c", "copy",
                "-movflags", "faststart",  # This helps with fixing moov atom issues
                temp_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0 and os.path.exists(temp_path):
                # Replace original with fixed version
                os.replace(temp_path, mp4_path)
                logger.info(f"Successfully repaired MP4 file: {mp4_path}")
                return True
        except Exception as e:
            logger.warning(f"Error repairing MP4: {e}")
            
        return False
        




    def _try_connect_device(self, device_name, max_retries=3):
        """Try to connect to a device with retries and increasing backoff"""
        for attempt in range(1, max_retries + 1):
            logger.info(f"Attempt {attempt}/{max_retries} to connect to {device_name}")
            self.status_update.emit(f"Connecting to device (attempt {attempt}/{max_retries})...")
            
            # Try to open the device
            available, message = self._test_device_availability(device_name)
            if available:
                logger.info(f"Successfully connected to {device_name}")
                self.status_update.emit(f"Connected to {device_name}")
                return True, "Device connected successfully"
                
            # If not available but not on last attempt, wait and retry
            if attempt < max_retries:
                # Exponential backoff: 2s, 4s, 8s...
                retry_delay = 2 ** attempt
                logger.info(f"Device busy, waiting {retry_delay}s before retry: {message}")
                
                # Show countdown to user
                for remaining in range(retry_delay, 0, -1):
                    self.status_update.emit(f"Device busy: {message}. Retrying in {remaining}s...")
                    time.sleep(1)
            else:
                logger.error(f"Failed to connect to device after {max_retries} attempts: {message}")
        
        # If we get here, all attempts failed
        return False, f"Failed to connect to device after {max_retries} attempts: {message}"

    def _test_device_availability(self, device_name):
        """Test if the device is available for capture"""
        try:
            # Quick test with short timeout
            cmd = [
                self._ffmpeg_path,
                "-f", "decklink",
                "-list_devices", "true",  # First list devices to prime the connection
                "-i", "dummy",  # Dummy input that will be ignored
                "-t", "0"  # Zero duration
            ]
            
            # Run device listing first (ignoring errors)
            subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=2
            )
            
            # Now try to connect to specific device
            cmd = [
                self._ffmpeg_path,
                "-f", "decklink",
                "-i", device_name,
                "-t", "0.5",  # Very short duration
                "-f", "null",
                "-"
            ]
            
            # Run with short timeout
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=3  # 3 second timeout
            )
            
            # Check for specific error patterns
            stderr = result.stderr.lower()
            
            if "cannot autodetect" in stderr or "no signal" in stderr:
                logger.warning(f"Device {device_name} reports no signal")
                return False, "No signal detected. Please check device connection."
                
            if "error opening input" in stderr and "i/o error" in stderr:
                logger.warning(f"Device {device_name} reports I/O error - may be in use")
                return False, "Device is busy or unavailable. Wait a moment and try again."
                
            if "device or resource busy" in stderr:
                logger.warning(f"Device {device_name} is busy")
                return False, "Device is currently in use by another application."
                
            if "permission denied" in stderr:
                logger.warning(f"Permission denied for device {device_name}")
                return False, "Permission denied. Try running as administrator."
                
            if "not found" in stderr:
                logger.warning(f"Device {device_name} not found")
                return False, "Device not found. Check connections and drivers."
            
            # Check if we got any frames - success indicator
            if "frame=" in stderr or result.returncode == 0:
                logger.info(f"Device {device_name} is available")
                return True, "Device available"
                
            # If we get here, something else went wrong
            logger.warning(f"Unknown device status: {stderr[:100]}...")
            return False, "Unknown device status. Check logs for details."
            
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout testing device {device_name}")
            return False, "Device test timed out. The device may be unresponsive."
        except Exception as e:
            logger.error(f"Error testing device {device_name}: {e}")
            return False, f"Error testing device: {str(e)}"

    def _force_reset_device(self, device_name):
        """
        Attempt to force-reset device connection
        This is a more aggressive approach for when normal retry fails
        """
        logger.info(f"Attempting to force-reset device: {device_name}")
        self.status_update.emit("Attempting to reset device connection...")
        
        try:
            # Kill any FFmpeg processes that might be using the device
            self._kill_ffmpeg_processes()
            
            # On Windows, try to reset the device using system command
            if platform.system() == 'Windows':
                try:
                    # Reset USB devices - might help with some capture cards
                    subprocess.run(
                        ["devcon", "restart", "*USB*"], 
                        shell=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=5
                    )
                except:
                    logger.info("Devcon not available or failed - skipping USB reset")
                    
            # Wait for device to reset
            time.sleep(3)
            
            # Try a basic connection to verify reset worked
            available, message = self._test_device_availability(device_name)
            return available, message
            
        except Exception as e:
            logger.error(f"Error resetting device: {e}")
            return False, f"Error resetting device: {str(e)}"

    def _kill_ffmpeg_processes(self):
        """Kill any lingering FFmpeg processes that might be using the capture device"""
        try:
            logger.info("Attempting to kill lingering FFmpeg processes")
            
            if platform.system() == 'Windows':
                # Windows approach
                subprocess.run(
                    ["taskkill", "/F", "/IM", "ffmpeg.exe"], 
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
            else:
                # Unix approach
                subprocess.run(
                    ["pkill", "-9", "ffmpeg"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                
            logger.info("FFmpeg processes terminated")
            return True
        except Exception as e:
            logger.error(f"Error killing FFmpeg processes: {e}")
            return False
            
    def check_device_health(self, device_name):
        """
        Run a comprehensive device health check and attempt recovery if needed
        Returns: (is_healthy, message)
        """
        logger.info(f"Running health check for device: {device_name}")
        self.status_update.emit("Checking device health...")
        
        # Step 1: Basic availability test
        available, message = self._test_device_availability(device_name)
        if available:
            logger.info("Device health check passed")
            self.status_update.emit("Device is healthy")
            return True, "Device is healthy"
            
        # Step 2: If not available, check what's wrong
        logger.warning(f"Device health check failed: {message}")
        self.status_update.emit(f"Device health check failed: {message}")
        
        # Check if it's a signal issue
        if "No signal" in message:
            return False, "No video signal detected. Check if source device is powered on and properly connected."
            
        # Check if it's a busy issue
        if "busy" in message.lower() or "in use" in message.lower():
            # Try to kill processes that might be using it
            self._kill_ffmpeg_processes()
            time.sleep(2)
            
            # Retest after killing processes
            available, new_message = self._test_device_availability(device_name)
            if available:
                logger.info("Device recovered after killing processes")
                self.status_update.emit("Device recovered")
                return True, "Device recovered after freeing resources"
            else:
                return False, "Device still busy after attempted recovery. Try restarting the application."
                
        # General error
        return False, f"Device issue: {message}"
    
    def recover_from_error(self, device_name, error_message):
        """
        Attempt to recover from a capture error
        Returns: (success, recovery_message)
        """
        logger.info(f"Attempting to recover from error: {error_message}")
        self.status_update.emit("Attempting recovery after error...")
        
        # Reset state
        self.state = CaptureState.IDLE
        self.state_changed.emit(self.state)
        
        # Kill any FFmpeg processes
        self._kill_ffmpeg_processes()
        
        # Wait a moment for resources to be freed
        time.sleep(3)
        
        # Try to connect to verify recovery
        return self._try_connect_device(device_name, max_retries=1)