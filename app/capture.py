import os
import logging
import subprocess
import re
import time
import platform
from datetime import datetime
import cv2
import numpy as np
import psutil
from PyQt5.QtCore import QObject, pyqtSignal, QThread, pyqtSlot, QTimer
from enum import Enum
from .trigger_detector import TriggerDetectorThread
import pytesseract
from .alignment import VideoAligner
from .video_normalizer import normalize_videos_for_comparison

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'  # Adjust path as needed



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
        """Safely terminate the FFmpeg process with proper signal to finalize file"""
        if self.process and self.process.poll() is None:
            try:
                logger.info("Sending graceful termination signal to FFmpeg process")
                
                # First try to send a SIGINT (Ctrl+C) which allows FFmpeg to finalize the file
                if hasattr(signal, 'SIGINT'):  # Unix-like systems
                    import signal
                    self.process.send_signal(signal.SIGINT)
                else:  # Windows
                    # On Windows, try to send Ctrl+C event
                    import ctypes
                    kernel32 = ctypes.WinDLL('kernel32')
                    kernel32.GenerateConsoleCtrlEvent(0, 0)  # 0 is CTRL_C_EVENT
                
                # Wait for process to terminate (longer timeout for finalization)
                logger.info("Waiting for FFmpeg to finalize output file...")
                for _ in range(100):  # 10 second timeout
                    if self.process.poll() is not None:
                        logger.info("FFmpeg process finalized and terminated")
                        break
                    time.sleep(0.1)
                    
                # Force kill if still running
                if self.process.poll() is None:
                    logger.warning("Process did not terminate gracefully, forcing kill")
                    self.process.kill()
                    self.process.wait(timeout=5)  # Wait with timeout
            except Exception as e:
                logger.error(f"Error terminating process: {e}")
                # As a last resort, try to kill it
                try:
                    self.process.kill()
                except:
                    pass


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
    WAITING_FOR_BOOKEND = 6       # Waiting for first white bookend
    CAPTURING_BOOKEND = 7         # Capturing between bookends
    WAITING_FOR_END_BOOKEND = 8   # Waiting for second bookend

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
        self.bookend_detector = None
        
        # Video info
        self.reference_info = None
        self.current_output_path = None
        
        # Output settings
        self.output_directory = None
        self.test_name = None
        self.capture_method = "trigger"  # Default to trigger method, alternative is "bookend"
        
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
 
    def start_trigger_detection(self, device_name, threshold=0.85, consecutive_frames=2):
        """Modified to be more tolerant of initial device issues"""
        if self.is_capturing:
            logger.warning("Capture already in progress")
            return False
            
        if not self.reference_info:
            error_msg = "No reference video set. Please select a reference video first."
            logger.error(error_msg)
            self.status_update.emit(error_msg)
            self.capture_finished.emit(False, error_msg)
            return False
        
        # Always force a device reset first
        logger.info("Pre-resetting device before trigger detection")
        self.status_update.emit("Initializing device...")
        reset_success, reset_msg = self._force_reset_device(device_name)
        
        # Try to connect to the device with retries
        connected, message = self._try_connect_device(device_name, max_retries=2)
        
        # Even if connection reports issues, proceed anyway
        # Blackmagic devices often show as "not connected" but still work
        logger.info(f"Proceeding with trigger detection (connected={connected})")
        
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
            logger.info("Stopping trigger detector")
            self.trigger_detector.stop()
            self.trigger_detector.wait()  # Wait for thread to finish
            self.trigger_detector = None
            
        # Get ready to start capturing
        self._prepare_output_path()
        
        # Add a proper delay to allow DeckLink driver to release
        QTimer.singleShot(1500, self._start_capture_after_trigger)
        
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

    def set_capture_method(self, method):
        """Set the capture method to use (trigger or bookend)"""
        if method in ["trigger", "bookend"]:
            self.capture_method = method
            logger.info(f"Set capture method to: {method}")
        else:
            logger.warning(f"Unknown capture method: {method}, using 'trigger'")
            self.capture_method = "trigger"
            
    def start_bookend_capture(self, device_name):
        """
        Start capture of a looped video with white frame bookends
        Captures until detecting at least two white frame bookend sequences
        """
        if self.is_capturing:
            logger.warning("Capture already in progress")
            return False
            
        if not self.reference_info:
            error_msg = "No reference video set. Please select a reference video first."
            logger.error(error_msg)
            self.status_update.emit(error_msg)
            self.capture_finished.emit(False, error_msg)
            return False
            
        logger.info("Starting bookend capture mode")
        self.status_update.emit("Initializing bookend capture mode...")
        
        # Reset device to ensure clean start
        reset_success, reset_msg = self._force_reset_device(device_name)
        
        # Try to connect to the device
        connected, message = self._try_connect_device(device_name, max_retries=2)
        
        # Even if connection reports issues, proceed anyway since Blackmagic devices
        # often show as "not connected" but still work
        logger.info(f"Proceeding with bookend capture (connected={connected})")
        
        # Prepare output path
        self._prepare_output_path()
        
        # Calculate a longer duration based on reference
        # We need to capture at least two complete loops of the video with bookends
        ref_duration = self.reference_info['duration']
        bookend_duration = 0.5  # White frame duration in seconds
        loop_duration = ref_duration + bookend_duration
        
        # Capture a bit more than 2 full loops to ensure we get complete bookends
        capture_duration = (loop_duration * 2.5)
        
        logger.info(f"Estimated single loop duration: {loop_duration:.2f}s")
        logger.info(f"Setting capture duration for at least 2 loops: {capture_duration:.2f}s")
        
        # Create a longer timeout for the capture monitor
        timeout_duration = capture_duration * 1.5  # 50% extra time as buffer
        
        # Start long-running capture
        try:
            logger.info(f"Starting bookend capture from {device_name} for ~{capture_duration:.1f} seconds")
            self.status_update.emit(f"Starting bookend capture for ~{capture_duration:.1f} seconds...")
            
            # Kill any lingering FFmpeg processes
            self._kill_ffmpeg_processes()
            
            # Build FFmpeg command
            cmd = [
                self._ffmpeg_path,
                "-y",  # Overwrite output
                "-f", "decklink",
                "-i", device_name,
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "18",  # Better quality
                # Add options to help with file finalization
                "-movflags", "+faststart",  # Write moov atom at the beginning
                "-fflags", "+genpts",       # Generate PTS if missing
                "-avoid_negative_ts", "1"   # Handle negative timestamps
            ]
            
            # Add duration limit with buffer
            cmd.extend(["-t", str(timeout_duration)])
                
            # Use forward slashes for FFmpeg
            ffmpeg_output_path = self.current_output_path.replace('\\', '/')
            
            # Add output path
            cmd.append(ffmpeg_output_path)
            
            # Log command
            logger.info(f"FFmpeg bookend capture command: {' '.join(cmd)}")
            
            # Start FFmpeg process
            self.ffmpeg_process = subprocess.Popen(
                cmd,
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stdin=subprocess.PIPE,
                universal_newlines=True
            )
            
            # Start monitoring with the extended timeout
            self.capture_monitor = CaptureMonitor(self.ffmpeg_process, timeout_duration)
            self.capture_monitor.progress_updated.connect(self.progress_update)
            self.capture_monitor.capture_complete.connect(self._on_bookend_capture_complete)
            self.capture_monitor.capture_failed.connect(self._on_capture_failed)
            self.capture_monitor.start()
            
            # Update state
            self.state = CaptureState.CAPTURING_BOOKEND
            self.state_changed.emit(self.state)
            self.capture_started.emit()
            
            # User-friendly message
            self.status_update.emit("Capturing looped video with white frame bookends. This will take at least two full loops to complete...")
            
            return True
            
        except Exception as e:
            error_msg = f"Failed to start bookend capture: {str(e)}"
            logger.error(error_msg)
            self.status_update.emit(error_msg)
            self.state = CaptureState.ERROR
            self.state_changed.emit(self.state)
            self.capture_finished.emit(False, error_msg)
            return False

    def _on_bookend_capture_complete(self):
        """Handle completion of bookend capture"""
        output_path = self.current_output_path
        logger.info(f"Bookend capture completed: {output_path}")
        
        # Ensure progress shows 100% when complete to fix stuck progress issue
        self.progress_update.emit(100)
        
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
        self.status_update.emit("Bookend capture complete, processing video...")
        
        # Start post-processing
        QTimer.singleShot(500, lambda: self._post_process_bookend_capture(output_path))
        
    def _post_process_bookend_capture(self, output_path):
        """Process captured video with bookends"""
        try:
            # Verify file integrity
            logger.info(f"Processing captured bookend video: {output_path}")
            self.status_update.emit("Processing captured bookend video...")
            
            # First check if file exists and is valid
            if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                raise FileNotFoundError(f"Output file missing or empty: {output_path}")
                
            # Try to repair MP4 if needed
            repaired, repaired_path = self._repair_mp4_if_needed(output_path)
            if repaired and repaired_path:
                logger.info(f"MP4 repair succeeded, using repaired file: {repaired_path}")
                output_path = repaired_path
                
            # Verify file using FFprobe
            cmd = [
                "ffprobe",
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=codec_type,duration",
                "-of", "json",
                output_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise ValueError(f"Invalid video file: {result.stderr}")
                
            # Parse duration from output
            import json
            try:
                info = json.loads(result.stdout)
                duration = float(info.get('streams', [{}])[0].get('duration', 0))
                
                if duration < 1.0:
                    raise ValueError(f"Video too short: {duration:.2f}s")
                    
                logger.info(f"Captured bookend video duration: {duration:.2f}s")
            except (json.JSONDecodeError, IndexError) as e:
                logger.warning(f"Could not parse duration: {e}, continuing anyway")
                
            # Mark as completed
            self.state = CaptureState.COMPLETED
            self.state_changed.emit(self.state)
            self.status_update.emit("Bookend capture and processing complete")
            self.capture_finished.emit(True, output_path)
            
        except Exception as e:
            error_msg = f"Error processing bookend capture: {str(e)}"
            logger.error(error_msg)
            self.state = CaptureState.ERROR
            self.state_changed.emit(self.state)
            self.status_update.emit(f"Error: {error_msg}")
            self.capture_finished.emit(False, error_msg)

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
            
    def _kill_all_ffmpeg(self):
        """Kill any lingering FFmpeg processes to avoid device conflicts"""
        try:
            logger.info("Looking for lingering FFmpeg processes to terminate")
            killed_count = 0
            for proc in psutil.process_iter(['pid', 'name']):
                if proc.info['name'] and 'ffmpeg' in proc.info['name'].lower():
                    try:
                        proc.kill()
                        killed_count += 1
                        logger.info(f"Killed FFmpeg process with PID {proc.info['pid']}")
                    except Exception as e:
                        logger.warning(f"Failed to kill FFmpeg process with PID {proc.info['pid']}: {e}")
            
            if killed_count > 0:
                logger.info(f"Killed {killed_count} lingering FFmpeg processes")
                # Brief pause to ensure processes are fully terminated
                time.sleep(0.5)
        except Exception as e:
            logger.error(f"Error killing FFmpeg processes: {e}")
    
    def _start_capture_after_trigger(self):
        """Start the actual FFmpeg capture process after trigger"""
        # Reset state from WAITING_FOR_TRIGGER to IDLE before starting capture
        self.state = CaptureState.IDLE
        
        # Force a device reset before capture
        self._force_reset_device("Intensity Shuttle")
        
        # Add additional delay for device stabilization
        time.sleep(1)
        
        if not self.reference_info:
            error_msg = "No reference video selected"
            logger.error(error_msg)
            self.capture_finished.emit(False, error_msg)
            return
            
        # Kill any lingering FFmpeg processes before starting new capture
        self._kill_all_ffmpeg()
            
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
            
        # Kill any lingering FFmpeg processes before starting new capture
        self._kill_all_ffmpeg()
        
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
                "-crf", "18",  # Better quality
                # Add options to help with file finalization
                "-movflags", "+faststart",  # Write moov atom at the beginning
                "-fflags", "+genpts",       # Generate PTS if missing
                "-avoid_negative_ts", "1"   # Handle negative timestamps
            ]
                       
            # Add duration limit
            if duration:
                cmd.extend(["-t", str(duration*1.5)])
                
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




            
    def stop_capture(self, cleanup_temp=False):
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
        
        # Clean up temporary files if requested
        if cleanup_temp and self.current_output_path and os.path.exists(self.current_output_path):
            try:
                logger.info(f"Cleaning up temporary capture file: {self.current_output_path}")
                os.remove(self.current_output_path)
                self.current_output_path = None
                
                # Also clean up any other temp files in the same directory
                temp_dir = os.path.dirname(self.current_output_path)
                for file in os.listdir(temp_dir):
                    if file.startswith("temp_") or file.startswith("tmp_"):
                        try:
                            file_path = os.path.join(temp_dir, file)
                            logger.info(f"Removing additional temp file: {file_path}")
                            os.remove(file_path)
                        except Exception as e:
                            logger.warning(f"Could not remove temp file {file}: {e}")
            except Exception as e:
                logger.error(f"Error removing temporary file: {e}")
        
        # Add delay before allowing another capture
        time.sleep(1)  # 1 second delay
        
        self.status_update.emit("Capture stopped by user")
        
        # If we're cleaning up, don't report success
        if cleanup_temp:
            self.capture_finished.emit(False, "Capture cancelled by user")
        else:
            self.capture_finished.emit(True, self.current_output_path)
        
    def _on_capture_complete(self):
        """Handle successful capture"""
        output_path = self.current_output_path
        logger.info(f"Capture completed: {output_path}")
        
        # Ensure progress shows 100% when complete to fix stuck progress issue
        self.progress_update.emit(100)
        
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
        
        # Check for signal loss error specifically
        if "Cannot Autodetect input stream or No signal" in error_msg:
            self.status_update.emit("Signal lost during capture initialization. Attempting recovery...")
            
            # Kill any processes and wait
            self._kill_ffmpeg_processes()
            time.sleep(3)
            
            # Try again with a longer initialization delay
            self.status_update.emit("Retrying capture with longer initialization delay...")
            
            # Reset output path (in case it was partially written)
            QTimer.singleShot(2000, lambda: self.start_capture(
                "Intensity Shuttle",
                self.current_output_path,
                duration=self.reference_info['duration'] - (1.0 / self.reference_info.get('frame_rate', 25))
            ))
            return
        
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
                    
                # Try to repair MP4 file if needed - ALWAYS TRY REPAIR
                try:
                    repaired, repaired_path = self._repair_mp4_if_needed(output_path)
                    if repaired and repaired_path:
                        logger.info(f"MP4 repair succeeded, using repaired file: {repaired_path}")
                        output_path = repaired_path
                    else:
                        logger.warning("MP4 repair was attempted but may not have been successful")
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
                        
                    # Final retry - attempt emergency repair
                    self.status_update.emit("Final attempt at emergency repair...")
                    try:
                        # Get a new path for the emergency repair
                        emergency_path = os.path.join(
                            os.path.dirname(output_path),
                            f"emergency_repair_{int(time.time())}_{os.path.basename(output_path)}"
                        )
                        
                        # Try to remux with a different approach
                        emergency_cmd = [
                            self._ffmpeg_path,
                            "-v", "warning",
                            "-i", output_path,
                            "-c", "copy",
                            "-f", "mp4",
                            emergency_path
                        ]
                        
                        logger.info(f"Emergency repair attempt with command: {' '.join(emergency_cmd)}")
                        emerg_result = subprocess.run(emergency_cmd, capture_output=True, text=True, timeout=30)
                        
                        if emerg_result.returncode == 0 and os.path.exists(emergency_path) and os.path.getsize(emergency_path) > 0:
                            # Verify the emergency repair
                            verify_cmd = [
                                "ffprobe",
                                "-v", "error",
                                "-select_streams", "v:0", 
                                "-show_entries", "stream=codec_type",
                                "-of", "csv=p=0",
                                emergency_path
                            ]
                            
                            verify_result = subprocess.run(verify_cmd, capture_output=True, text=True)
                            if verify_result.returncode == 0 and "video" in verify_result.stdout:
                                logger.info("Emergency repair succeeded!")
                                output_path = emergency_path
                                break
                        
                        # If we reach here, emergency repair failed
                        raise ValueError(f"Invalid video file after all repair attempts: {result.stderr}")
                        
                    except Exception as e:
                        logger.error(f"Emergency repair failed: {e}")
                        raise ValueError(f"Invalid video file: {result.stderr}")
                
                # If we got here, file is valid
                logger.info("Capture successful. Note that captured video is intentionally longer than the reference.")
                self.status_update.emit("Capture successful. The video is intentionally longer to ensure complete coverage.")
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
        """More robust repair for MP4 files with missing moov atom or other issues"""
        logger.info(f"Attempting to repair MP4 file: {mp4_path}")
        
        try:
            # Create temporary output path
            output_dir = os.path.dirname(mp4_path)
            temp_filename = f"temp_fixed_{int(time.time())}_{os.path.basename(mp4_path)}"
            temp_path = os.path.join(output_dir, temp_filename)
            
            # Try multiple repair approaches
            
            # Approach 1: Use FFmpeg with faststart flag (helps with moov atom)
            cmd = [
                self._ffmpeg_path,
                "-v", "warning",
                "-i", mp4_path,
                "-c", "copy",
                "-movflags", "faststart",  # This helps with fixing moov atom issues
                temp_path
            ]
            
            logger.info(f"Running repair with faststart: {' '.join(cmd)}")
            self.status_update.emit("Attempting to repair output file...")
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0 and os.path.exists(temp_path):
                # Verify the repaired file
                verify_cmd = [
                    "ffprobe",
                    "-v", "error",
                    "-select_streams", "v:0",
                    "-show_entries", "stream=codec_type",
                    "-of", "csv=p=0",
                    temp_path
                ]
                
                verify_result = subprocess.run(verify_cmd, capture_output=True, text=True)
                
                if verify_result.returncode == 0 and "video" in verify_result.stdout:
                    # Replace original with fixed version
                    logger.info(f"Repair successful, replacing with fixed file")
                    
                    # First check if original still exists (it might be locked)
                    if os.path.exists(mp4_path):
                        try:
                            os.unlink(mp4_path)
                        except Exception as e:
                            logger.warning(f"Could not delete original file: {e}")
                            # Try with a different name
                            mp4_path = os.path.join(output_dir, f"repaired_{os.path.basename(mp4_path)}")
                    
                    os.rename(temp_path, mp4_path)
                    logger.info(f"Successfully repaired MP4 file: {mp4_path}")
                    return True, mp4_path
                else:
                    logger.warning(f"Repaired file verification failed: {verify_result.stderr}")
                    
                    # Try alternative approach if first repair failed
                    alt_temp_path = os.path.join(output_dir, f"alt_fixed_{os.path.basename(mp4_path)}")
                    
                    # Approach 2: Try with different container format
                    cmd2 = [
                        self._ffmpeg_path,
                        "-v", "warning",
                        "-i", mp4_path,
                        "-c", "copy",
                        "-f", "mp4",  # Explicitly set format
                        alt_temp_path
                    ]
                    
                    logger.info(f"Trying alternative repair approach")
                    result2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=30)
                    
                    if result2.returncode == 0 and os.path.exists(alt_temp_path):
                        # Verify again
                        verify_result2 = subprocess.run(verify_cmd[:-1] + [alt_temp_path], 
                                                    capture_output=True, text=True)
                        
                        if verify_result2.returncode == 0 and "video" in verify_result2.stdout:
                            # Replace original
                            if os.path.exists(mp4_path):
                                try:
                                    os.unlink(mp4_path)
                                except:
                                    mp4_path = os.path.join(output_dir, f"repaired_{os.path.basename(mp4_path)}")
                                    
                            os.rename(alt_temp_path, mp4_path)
                            logger.info(f"Alternative repair succeeded: {mp4_path}")
                            return True, mp4_path
            
            # If we get here, repair failed
            logger.warning(f"All MP4 repair attempts failed")
            return False, None
            
        except Exception as e:
            logger.error(f"Error during MP4 repair: {e}")
            return False, None

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
        
    def _test_device_thoroughly(self, device_name):
        """More thorough device test with multiple approaches"""
        try:
            # Approach 1: Try getting format information
            cmd = [
                self._ffmpeg_path,
                "-f", "decklink",
                "-list_formats", "1",
                "-i", device_name
            ]
            
            format_result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=4
            )
            
            # If we can get format info, the device is working
            if "Supported formats" in format_result.stderr:
                logger.info(f"Device {device_name} is available (formats listed)")
                return True, "Device formats available"
                
            # Approach 2: Try a very minimal capture
            cmd = [
                self._ffmpeg_path, 
                "-f", "decklink",
                "-i", device_name,
                "-frames:v", "1",  # Just 1 frame
                "-f", "null", 
                "-"
            ]
            
            test_result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5
            )
            
            # Check for specific patterns indicating success
            stderr = test_result.stderr.lower()
            if "frame=" in stderr or "fps=" in stderr:
                logger.info(f"Device {device_name} is available (frame captured)")
                return True, "Device captured frame"
                
            # If we get this far without success, check errors
            if "cannot autodetect" in stderr or "no signal" in stderr:
                logger.warning(f"Device {device_name} reports no signal")
                return False, "No signal detected. Please check device connection."
            
            # Generic failure
            logger.warning(f"Thorough device test failed with: {stderr[:100]}...")
            return False, "Device test failed. See logs for details."
                
        except subprocess.TimeoutExpired:
            logger.warning(f"Thorough device test timed out for {device_name}")
            # Return TRUE here - this often means the device is working but busy
            return True, "Device appears busy but likely working"
        except Exception as e:
            logger.error(f"Error in thorough device test: {e}")
            return False, f"Error testing device: {str(e)}"

    def _try_connect_device(self, device_name, max_retries=3):
        """Try to connect to a device with retries and improved reliability"""
        
        # First, proactively kill any FFmpeg processes
        self._kill_ffmpeg_processes()
        
        # Force a small delay before first try
        time.sleep(2)
        
        # Try multiple connection approaches
        for attempt in range(1, max_retries + 1):
            logger.info(f"Attempt {attempt}/{max_retries} to connect to {device_name}")
            self.status_update.emit(f"Connecting to device (attempt {attempt}/{max_retries})...")
            
            # Alternate between different connection approaches
            if attempt % 2 == 1:
                # Approach 1: Quick availability check
                available, message = self._test_device_availability(device_name)
            else:
                # Approach 2: More thorough test with longer timeout
                available, message = self._test_device_thoroughly(device_name)
                
            if available:
                logger.info(f"Successfully connected to {device_name}")
                self.status_update.emit(f"Connected to {device_name}")
                return True, "Device connected successfully"
            
            # If not successful but not last attempt
            if attempt < max_retries:
                # More consistent retry delay - 3 seconds between attempts
                retry_delay = 3
                logger.info(f"Device busy, waiting {retry_delay}s before retry: {message}")
                
                # Show countdown to user
                self.status_update.emit(f"Device busy: {message}. Waiting {retry_delay}s...")
                time.sleep(retry_delay)
        
        return False, f"Failed to connect after {max_retries} attempts: {message}"


    def _test_device_availability(self, device_name):
        """Quick test if the device is available for capture"""
        try:
            # Use a simpler and faster test command
            cmd = [
                self._ffmpeg_path,
                "-f", "decklink",
                "-list_formats", "1",  # Just list formats
                "-i", device_name
            ]
            
            # Run with short timeout
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=3  # 3 second timeout
            )
            
            # If we get format info, that's success
            if "Supported formats" in result.stderr:
                logger.info(f"Device {device_name} is available")
                return True, "Device available"
                
            # Even if command failed, check for signs the device exists
            if device_name in result.stderr:
                # Device exists but might have issues
                logger.info(f"Device {device_name} exists but may have issues")
                return True, "Device exists but may have connection issues"
                
            # Check for specific error patterns
            stderr = result.stderr.lower()
            
            if "cannot autodetect" in stderr or "no signal" in stderr:
                # This is often a non-fatal error - device exists but no signal
                logger.warning(f"Device {device_name} reports no signal")
                return True, "Device found but no signal detected"
                
            if "error opening input" in stderr:
                logger.warning(f"Device {device_name} reports opening error")
                return False, "Error opening device. It may be in use."
                
            if "device or resource busy" in stderr:
                logger.warning(f"Device {device_name} is busy")
                return False, "Device is currently in use by another application."
                
            if "permission denied" in stderr:
                logger.warning(f"Permission denied for device {device_name}")
                return False, "Permission denied. Try running as administrator."
                
            if "not found" in stderr:
                logger.warning(f"Device {device_name} not found")
                return False, "Device not found. Check connections and drivers."
            
            # If we can't determine status clearly, lean toward available
            logger.warning(f"Uncertain device status: {stderr[:100]}...")
            return True, "Device status uncertain but proceeding"
                
        except subprocess.TimeoutExpired:
            # Timeout often means the device is there but busy/responsive
            logger.warning(f"Timeout testing device {device_name}")
            return True, "Device test timed out but proceeding anyway"
        except Exception as e:
            logger.error(f"Error testing device {device_name}: {e}")
            return False, f"Error testing device: {str(e)}"


    def _force_reset_device(self, device_name):
        """More thorough device reset procedure"""
        logger.info(f"Attempting to force-reset device: {device_name}")
        self.status_update.emit("Resetting device connection...")
        
        # First kill any FFmpeg processes
        self._kill_ffmpeg_processes()
        
        # On Windows, try additional device resets
        if platform.system() == 'Windows':
            try:
                # Try net stop/start for Blackmagic service
                logger.info("Attempting to restart Blackmagic services")
                service_name = "BlackmagicDesktopVideo"
                
                # Check if service exists
                service_check = subprocess.run(
                    ["sc", "query", service_name],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=5
                )
                
                if "running" in service_check.stdout.lower():
                    # Restart the service
                    try:
                        subprocess.run(
                            ["net", "stop", service_name],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            timeout=10
                        )
                        time.sleep(1)
                        subprocess.run(
                            ["net", "start", service_name],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            timeout=10
                        )
                        logger.info("Blackmagic service restarted")
                    except:
                        logger.warning("Failed to restart Blackmagic service - continuing anyway")
            except Exception as e:
                logger.warning(f"Service restart attempt failed: {e}")
        
        # Allow more time for device to reset
        time.sleep(5)
        
        # Try a direct simple test (without error messages to user)
        try:
            cmd = [
                self._ffmpeg_path,
                "-f", "decklink",
                "-list_formats", "1",
                "-i", device_name
            ]
            
            subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=3
            )
        except:
            pass
        
        # Wait again
        time.sleep(2)
        
        # Do a proper connection test
        available, message = self._test_device_availability(device_name)
        if available:
            logger.info(f"Device {device_name} successfully reset")
        else:
            logger.warning(f"Device {device_name} reset attempt completed but status uncertain")
            # Return true anyway - we want to continue the workflow
            available = True
        
        return available, message

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
        time.sleep(10)
        
        # Try to connect to verify recovery
        return self._try_connect_device(device_name, max_retries=1)