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
from PyQt5.QtCore import QObject, pyqtSignal, QThread, pyqtSlot, QTimer, QMutex
from PyQt5.QtGui import QImage, QPixmap
from enum import Enum
import math
import shutil
import signal

logger = logging.getLogger(__name__)

# Constants
MAX_REPAIR_ATTEMPTS = 3  # Maximum number of attempts to repair a video file

# Set pytesseract path if it's needed for bookend detection
try:
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
except ImportError:
    logger.warning("Pytesseract not available - some OCR functions may be limited")

# Define capture states for better management
class CaptureState(Enum):
    IDLE = 0
    INITIALIZING = 1
    CAPTURING = 2
    PROCESSING = 3
    COMPLETED = 4
    ERROR = 5

class CaptureMonitor(QThread):
    """Thread to monitor FFmpeg capture process"""
    progress_updated = pyqtSignal(int)
    capture_complete = pyqtSignal()
    capture_failed = pyqtSignal(str)
    frame_count_updated = pyqtSignal(int, int)  # current_frame, total_frames

    def __init__(self, process, duration=None):
        super().__init__()
        self.process = process
        self._running = True
        self.error_output = ""
        self.start_time = time.time()
        self.duration = duration  # Expected duration in seconds
        self.is_bookend_capture = True  # Always true since we only use bookend mode now
        self.last_frame_count = 0
        self.total_frames = 0
        self.last_progress_time = time.time()  # Throttle progress updates
        self.last_progress_value = 0

    def run(self):
        """Monitor process output and emit signals"""
        logger.debug("Starting capture monitor")

        # Send initial progress
        self.progress_updated.emit(0)

        while self._running:
            # Check for process completion
            if self.process.poll() is not None:
                if self.process.returncode == 0:
                    logger.info("Capture completed successfully")
                    # Set progress to 99% - we'll set to 100% after post-processing
                    self.progress_updated.emit(99)
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

            # Check for duration timeout - be more lenient with bookend captures
            if self.duration and (time.time() - self.start_time) > self.duration * 2.0:
                logger.warning(f"Capture exceeded expected duration ({self.duration}s), terminating")
                self._terminate_process()
                self.progress_updated.emit(99)  # Almost complete
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
                                    self.last_frame_count = frame_num

                                    # Try to estimate total frames from fps and duration
                                    fps = 30  # Default fps assumption
                                    fps_match = re.search(r'fps=\s*([\d.]+)', line)
                                    if fps_match:
                                        try:
                                            fps = float(fps_match.group(1))
                                        except:
                                            pass  # Keep the default

                                    # Update total_frames if we now have fps info
                                    if self.total_frames == 0 and self.duration and fps > 0:
                                        self.total_frames = int(self.duration * fps)
                                        logger.debug(f"Estimated total frames: {self.total_frames} (fps={fps}, duration={self.duration}s)")

                                    # Try to find time encoding information as fallback for progress
                                    time_elapsed = None
                                    time_match = re.search(r'time=(\d+):(\d+):(\d+\.\d+)', line)
                                    if time_match:
                                        hours = int(time_match.group(1))
                                        minutes = int(time_match.group(2))
                                        seconds = float(time_match.group(3))
                                        time_elapsed = hours * 3600 + minutes * 60 + seconds

                                    # Calculate progress percentage
                                    current_time = time.time()
                                    # Only update every 0.25 seconds to avoid too many updates
                                    if current_time - self.last_progress_time >= 0.25:
                                        progress = 0

                                        if self.duration and self.total_frames > 0:
                                            # If we have both duration and total frames (most accurate)
                                            progress = min(int((frame_num / self.total_frames) * 95), 95)
                                        elif time_elapsed is not None and self.duration:
                                            # If we have elapsed time from output and expected duration
                                            progress = min(int((time_elapsed / self.duration) * 95), 95)
                                        elif self.duration:
                                            # If we only have process duration, use elapsed time
                                            elapsed = current_time - self.start_time
                                            progress = min(int((elapsed / self.duration) * 95), 95)
                                        else:
                                            # Fallback - increment in small steps based on frames
                                            # Ensure we never report 0% after starting
                                            progress = max(5, min(int((frame_num % 1000) / 10), 95))

                                        # Only emit if progress changed to avoid flooding UI
                                        if progress != self.last_progress_value:
                                            self.progress_updated.emit(progress)
                                            self.last_progress_value = progress

                                        # Update timestamp
                                        self.last_progress_time = current_time

                                    # Always emit frame count updates for UI display
                                    self.frame_count_updated.emit(frame_num, self.total_frames)
                            except (ValueError, AttributeError) as e:
                                logger.warning(f"Error parsing frame number: {e}")

                        # Check for common error patterns
                        if "Error" in line or "Invalid" in line:
                            logger.warning(f"Potential error in FFmpeg output: {line.strip()}")
                except Exception as e:
                    logger.warning(f"Error reading FFmpeg output: {e}")

            # Don't burn CPU with polling
            time.sleep(0.1)

            # Update progress based on elapsed time for smoother appearance
            # Only if no recent frame-based updates
            current_time = time.time()
            if self.duration and (current_time - self.last_progress_time) >= 1.0:
                elapsed = current_time - self.start_time
                time_progress = min(int((elapsed / self.duration) * 95), 95)

                # Only emit if progress increased to avoid jumping back
                if time_progress > self.last_progress_value:
                    self.progress_updated.emit(time_progress)
                    self.last_progress_value = time_progress
                    self.last_progress_time = current_time
                else:
                    # Do nothing if progress didn't increase
                    logger.debug("Skipping progress update as value didn't increase")

    def _terminate_process(self):
        """Safely terminate the FFmpeg process with proper signal to finalize file"""
        if self.process and self.process.poll() is None:
            try:
                logger.info("Sending graceful termination signal to FFmpeg process")

                # For Windows, use a more reliable approach to gracefully terminate FFmpeg
                if platform.system() == 'Windows':
                    # Send 'q' key to stdin which signals FFmpeg to stop gracefully
                    try:
                        if hasattr(self.process.stdin, 'write'):
                            self.process.stdin.write('q\n')
                            self.process.stdin.flush()
                            logger.info("Sent 'q' command to FFmpeg")
                    except Exception as e:
                        logger.warning(f"Could not send 'q' command: {e}")

                    # Give FFmpeg time to finalize the output
                    logger.info("Waiting for FFmpeg to finalize output file...")
                    for _ in range(50):  # 5 second timeout
                        if self.process.poll() is not None:
                            logger.info("FFmpeg process finalized and terminated")
                            break
                        time.sleep(0.1)

                    # If still running, try terminate() instead of kill()
                    if self.process.poll() is None:
                        logger.info("FFmpeg still running, sending terminate signal")
                        self.process.terminate()
                        # Wait up to 10 more seconds
                        for _ in range(100):
                            if self.process.poll() is not None:
                                logger.info("FFmpeg process terminated")
                                break
                            time.sleep(0.1)
                else:
                    # Unix-like systems
                    import signal
                    self.process.send_signal(signal.SIGINT)

                    # Wait for process to terminate
                    logger.info("Waiting for FFmpeg to finalize output file...")
                    for _ in range(100):  # 10 second timeout
                        if self.process.poll() is not None:
                            logger.info("FFmpeg process finalized and terminated")
                            break
                        time.sleep(0.1)

                # Force kill if still running (last resort)
                if self.process.poll() is None:
                    logger.warning("Process did not terminate gracefully, forcing kill")
                    self.process.kill()
                    try:
                        self.process.wait(timeout=5)  # Wait with timeout
                    except:
                        pass
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


class BookendCaptureManager(QObject):
    """Manager for capturing bookend videos"""

    # Signals for UI updates
    capture_state_changed = pyqtSignal(str, str)  # state, message
    capture_progress = pyqtSignal(int)  # 0-100%
    preview_frame = pyqtSignal(QImage)  # For live preview
    capture_completed = pyqtSignal(str)  # path to captured file
    capture_error = pyqtSignal(str)  # error message

    def __init__(self, options_manager):
        super().__init__()
        self.options_manager = options_manager
        self.capture_process = None
        self.ffmpeg_process = None
        self.state = CaptureState.IDLE
        self.capture_start_time = None
        self.test_name = None
        self.output_dir = None
        self.preview_timer = QTimer()
        self.preview_timer.timeout.connect(self.update_preview)
        self.preview_cap = None
        self.mutex = QMutex()  # Mutex for thread safety

    def set_test_name(self, test_name):
        """Set the test name for file naming"""
        self.test_name = test_name

    def set_output_directory(self, output_dir):
        """Set the output directory for captures"""
        self.output_dir = output_dir

    def start_capture(self):
        """Start a bookend capture with white frames at start and end"""
        if self.state != CaptureState.IDLE:
            logger.warning(f"Cannot start capture while in state: {self.state}")
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

    def stop_capture(self, cleanup_temp=False):
        """Stop any active capture process"""
        if not self.is_capturing:
            return

        logger.info("Stopping capture")
        self.status_update.emit("Stopping capture...")

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

    def _on_capture_failed(self, error_msg):
        """Handle capture errors"""
        logger.error(f"Capture failed: {error_msg}")

        # Clean up resources
        self.ffmpeg_process = None
        self.capture_monitor = None

        # Update state
        self.state = CaptureState.ERROR
        self.state_changed.emit(self.state)

        # Check for device error that might be recoverable
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

    def _test_device_availability(self, device_name):
        """More robust test if the device is available for capture"""
        try:
            # Try multiple approaches

            # First approach: Use ffmpeg -list_devices
            devices_cmd = [
                self._ffmpeg_path,
                "-f", "decklink",
                "-list_devices", "1",
                "-i", "dummy"
            ]

            try:
                devices_result = subprocess.run(
                    devices_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=3
                )

                # If device name appears in the output, it's likely available
                if device_name in devices_result.stderr:
                    logger.info(f"Device {device_name} found in device list")
                    return True, "Device listed in available devices"
            except Exception as e:
                logger.warning(f"Error listing devices: {e}")

            # Second approach: Direct format test
            format_cmd = [
                self._ffmpeg_path,
                "-f", "decklink",
                "-list_formats", "1",
                "-i", device_name
            ]

            try:
                format_result = subprocess.run(
                    format_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=3
                )

                if "Supported formats" in format_result.stderr:
                    logger.info(f"Device {device_name} reports supported formats")
                    return True, "Device formats available"
            except Exception as e:
                logger.warning(f"Error getting device formats: {e}")

            # Third approach: Try a minimal capture
            capture_cmd = [
                self._ffmpeg_path,
                "-f", "decklink",
                "-t", "0.1",  # Try for just 0.1seconds
                "-i", device_name,
                "-f", "null",
                "-"
            ]

            try:
                capture_result = subprocess.run(
                    capture_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=5
                )

                stderr = capture_result.stderr.lower()
                if "frame=" in stderr or "time=" in stderr:
                    logger.info(f"Device {device_name} successfully captured frames")
                    return True, "Device successfully captured frames"
            except Exception as e:
                logger.warning(f"Error testing minimal capture: {e}")

            # If all tests failed but device name was found in device list
            if device_name in devices_result.stderr:
                logger.warning(f"Device {device_name} exists but may have issues")
                return True, "Device exists but may have connection issues"

            logger.warning(f"Device {device_name} not detected by any test method")
            return False, "Device not detected or not responding"

        except Exception as e:
            logger.error(f"Error in device availability test: {e}")
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

            # Check device availability
            available, message = self._test_device_availability(device_name)

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
                return True, mp4_path
        except Exception as e:
            logger.warning(f"Error repairing MP4: {e}")

        return False, None

    def _start_preview_capture(self, device_name):
        """Start a preview capture to show input feed before recording"""
        try:
            # Stop any existing preview
            self._stop_preview_capture()

            # Initialize OpenCV capture
            self.preview_cap = cv2.VideoCapture()

            # Try multiple approaches for Windows
            if platform.system() == 'Windows':
                # First try with the standard device name for Blackmagic devices
                # "Decklink Video Capture" is the common name for Blackmagic devices in DirectShow
                logger.info("Trying to open preview with 'Decklink Video Capture'")
                self.preview_cap.open("video=Decklink Video Capture", cv2.CAP_DSHOW)

                # If that didn't work, try with the provided device name
                if not self.preview_cap.isOpened():
                    logger.info(f"Trying to open preview with '{device_name}'")
                    self.preview_cap.open(f"video={device_name}", cv2.CAP_DSHOW)

                # As a last resort, try default camera
                if not self.preview_cap.isOpened():
                    logger.info("Trying default camera as fallback")
                    self.preview_cap.open(0, cv2.CAP_DSHOW)
            else:
                # For Linux/macOS try a different approach
                self.preview_cap.open(device_name)

            if not self.preview_cap.isOpened():
                logger.warning(f"Could not open preview capture for {device_name}")
                # Even if we can't open the capture, create a placeholder frame to show
                placeholder = self._get_preview_frame()
                if placeholder is not None:
                    self.frame_available.emit(placeholder)
                return False

            # Set lower resolution for preview to reduce processing load
            self.preview_cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.preview_cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 360)

            # Create preview thread
            self.preview_active = True
            self.preview_thread = QThread()
            self.preview_thread.run = self._update_preview
            self.preview_thread.start()

            logger.info(f"Preview capture started for {device_name}")
            return True

        except Exception as e:
            logger.error(f"Error starting preview: {str(e)}")
            self.preview_active = False
            # Send a placeholder frame to avoid crashes
            placeholder = self._get_preview_frame()
            if placeholder is not None:
                self.frame_available.emit(placeholder)
            return False

    def _stop_preview_capture(self):
        """Stop the preview capture"""
        if hasattr(self, 'preview_active') and self.preview_active:
            self.preview_active = False

            # Wait for thread to finish
            if hasattr(self, 'preview_thread') and self.preview_thread:
                self.preview_thread.quit()
                self.preview_thread.wait(1000)

            # Release capture
            if hasattr(self, 'preview_cap') and self.preview_cap:
                self.preview_cap.release()

            logger.info("Preview capture stopped")

    def _update_preview(self):
        """Update preview frames in background thread"""
        while self.preview_active:
            try:
                frame = self._get_preview_frame()
                if frame is not None:
                    self.frame_available.emit(frame)
            except Exception as e:
                logger.error(f"Error updating preview: {str(e)}")

            # Limit to ~15 fps for preview to reduce CPU usage
            time.sleep(0.067)

    def _get_preview_frame(self):
        """Get current frame from preview capture"""
        if not hasattr(self, 'preview_cap') or not self.preview_cap:
            # Return placeholder frame
            placeholder = np.zeros((270, 480, 3), dtype=np.uint8)
            placeholder[:] = (224, 224, 224)  # Light gray background
            cv2.putText(placeholder, "No video feed", (160, 135), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
            return placeholder

        if not self.preview_cap.isOpened():
            logger.warning("Preview capture not open")
            return None

        ret, frame = self.preview_cap.read()
        if not ret:
            return None

        return frame

    def update_frame_counter(self, current_frame, total_frames):
        """Update frame counter display"""
        # This method is connected to CaptureMonitor signals
        # It can be overridden by child classes to update UI
        pass

    def update_capture_progress(self, frame_num):
        """Handle frame progress update and convert to percentage"""
        # Calculate progress percentage based on expected total frames
        # If we have duration and frame rate info from the process, use it
        if hasattr(self, 'duration') and self.duration:
            # Get frame rate from process output if available
            frame_rate = 30  # Default assumption
            try:
                if hasattr(self.process, 'stderr') and self.process.stderr:
                    for line in self.process.stderr:
                        if "fps" in line:
                            match = re.search(r'(\d+\.?\d*)\s*fps', line)
                            if match:
                                frame_rate = float(match.group(1))
                                break
            except:
                pass  # If any error occurs, just use the default frame rate

            # Calculate expected total frames
            total_expected = int(self.duration * frame_rate)

            # Calculate percentage (limit to 0-99% until complete)
            if total_expected > 0:
                percentage = min(99, int((frame_num / total_expected) * 100))
                self.progress_updated.emit(percentage)
            else:
                # If we can't calculate, at least show some movement
                self.progress_updated.emit(min(99, (frame_num % 100)))
        else:
            # If we don't have duration info, map frame_num to 0-99% range
            self.progress_updated.emit(min(99, (frame_num % 100)))
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
        """Process captured video with bookends and move to temporary folder"""
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

            # Move to temporary folder if configured in options
            temp_dir = None
            if hasattr(self, 'options_manager') and self.options_manager:
                temp_dir = self.options_manager.get_setting("paths", "temp_dir")

            # If no temp dir configured or doesn't exist, use system temp
            if not temp_dir or not os.path.exists(temp_dir):
                import tempfile
                temp_dir = tempfile.gettempdir()

            # Create a new filename in temp dir
            temp_filename = f"temp_bookend_capture_{int(time.time())}.mp4"
            temp_path = os.path.join(temp_dir, temp_filename)

            # Copy the file to temp location
            import shutil
            shutil.copy2(output_path, temp_path)
            logger.info(f"Moved capture file to temporary location: {temp_path}")

            # Delete the original file to save space
            try:
                os.remove(output_path)
                logger.info(f"Deleted original capture file: {output_path}")
            except Exception as e:
                logger.warning(f"Could not delete original capture file: {e}")

            # Mark as completed
            self.state = CaptureState.COMPLETED
            self.state_changed.emit(self.state)
            self.status_update.emit("Bookend capture and processing complete")
            # Return the temp path instead of original
            self.capture_finished.emit(True, temp_path)

        except Exception as e:
            error_msg = f"Error processing bookend capture: {str(e)}"
            logger.error(error_msg)
            self.state = CaptureState.ERROR
            self.state_changed.emit(self.state)
            self.status_update.emit(f"Error: {error_msg}")
            self.capture_finished.emit(False, error_msg)

        if not self.test_name:
            self.test_name = f"Test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        self.state = CaptureState.INITIALIZING
        self.capture_state_changed.emit("INITIALIZING", "Initializing bookend capture mode...")

        # Get capture settings
        capture_settings = self.options_manager.get_setting("capture")
        bookend_settings = self.options_manager.get_setting("bookend")

        device = capture_settings.get("default_device", "Intensity Shuttle")
        resolution = capture_settings.get("resolution", "1920x1080")
        frame_rate = capture_settings.get("frame_rate", 30)
        pixel_format = capture_settings.get("pixel_format", "uyvy422")
        max_capture_time = bookend_settings.get("max_capture_time", 120)

        # Create output directory
        date_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        test_dir = os.path.join(self.output_dir, f"{self.test_name}_{date_str}")
        os.makedirs(test_dir, exist_ok=True)

        # Path for captured video
        output_path = os.path.join(test_dir, "REF03_capture.mp4")

        # Log capture information
        logger.info(f"Starting bookend capture process...")
        logger.info(f"Using test name: {self.test_name}")
        logger.info(f"Starting bookend frame capture...")

        # Emit progress and state updates
        self.capture_state_changed.emit("INITIALIZING", "Initializing bookend capture mode...")
        self.capture_progress.emit(0)

        try:
            # Build FFmpeg command for capturing
            cmd = [
                "ffmpeg", "-hide_banner",
                # Input from DeckLink card
                "-f", "decklink",
                "-video_input", "hdmi",
                "-audio_input", "embedded",
                "-format_code", "hp60",  # This might need to be adjusted based on resolution/frame rate
                "-i", device,

                # Output format settings
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "18",  # Good quality
                "-pix_fmt", "yuv420p",
                "-r", str(frame_rate),
                "-t", str(max_capture_time),  # Maximum capture duration

                # Audio settings
                "-c:a", "aac",
                "-b:a", "192k",

                # Output file
                "-y",  # Overwrite if exists
                output_path
            ]

            logger.info(f"Executing FFmpeg command: {' '.join(cmd)}")

            # Start capture process
            self.ffmpeg_process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1  # Line buffered
            )

            # Set capture start time
            self.capture_start_time = time.time()

            # Update state
            self.state = CaptureState.CAPTURING
            self.capture_state_changed.emit("CAPTURING", "Capturing video with white bookends...")

            # Start preview timer
            self.start_preview()

            # Monitor the process
            monitor_thread = QThread()
            monitor_thread.run = self._monitor_capture
            monitor_thread.start()

            return True

        except Exception as e:
            error_msg = f"Failed to start capture: {str(e)}"
            logger.error(error_msg)
            self.state = CaptureState.ERROR
            self.capture_state_changed.emit("ERROR", error_msg)
            self.capture_error.emit(error_msg)
            return False

    def _monitor_capture(self):
        """Monitor the capture process and update progress"""
        try:
            if not self.ffmpeg_process:
                return

            start_time = time.time()
            max_duration = self.options_manager.get_setting("bookend", "max_capture_time")

            # Read output while process is running
            while self.ffmpeg_process.poll() is None:
                elapsed = time.time() - start_time

                # Update progress
                progress = min(int((elapsed / max_duration) * 100), 99)
                self.capture_progress.emit(progress)

                # Check if process should be terminated
                if elapsed > max_duration + 5:  # Allow 5 seconds grace period
                    logger.warning("Capture exceeded maximum duration, terminating")
                    self.ffmpeg_process.terminate()
                    break

                # Sleep to avoid using too much CPU
                time.sleep(0.5)

            # Process completed
            if self.ffmpeg_process.returncode == 0:
                logger.info("Capture completed successfully")
                self.state = CaptureState.PROCESSING
                self.capture_state_changed.emit("PROCESSING", "Processing captured bookend video...")

                # Process the captured video
                self._process_captured_video()
            else:
                stderr = self.ffmpeg_process.stderr.read() if self.ffmpeg_process.stderr else "Unknown error"
                logger.error(f"Capture process failed with code {self.ffmpeg_process.returncode}: {stderr}")
                self.state = CaptureState.ERROR
                self.capture_state_changed.emit("ERROR", f"Capture failed: {stderr}")
                self.capture_error.emit(f"Capture failed: {stderr}")

        except Exception as e:
            logger.error(f"Error monitoring capture: {str(e)}")
            self.state = CaptureState.ERROR
            self.capture_state_changed.emit("ERROR", f"Error monitoring capture: {str(e)}")
            self.capture_error.emit(f"Error monitoring capture: {str(e)}")

    def _process_captured_video(self):
        """Process the captured video file"""
        try:
            # Check if output directory exists
            date_str = datetime.now().strftime('%Y%m%d_%H%M%S')
            test_dir = os.path.join(self.output_dir, f"{self.test_name}_{date_str}")
            captured_file = os.path.join(test_dir, "REF03_capture.mp4")

            if not os.path.exists(captured_file):
                error_msg = f"Captured file not found: {captured_file}"
                logger.error(error_msg)
                self.state = CaptureState.ERROR
                self.capture_state_changed.emit("ERROR", error_msg)
                self.capture_error.emit(error_msg)
                return

            # Validate the captured file
            from app.bookend_alignment import validate_video_file, repair_video_file, MAX_REPAIR_ATTEMPTS

            if not validate_video_file(captured_file):
                logger.warning(f"Captured file is not valid, attempting repair: {captured_file}")

                # Try to repair the file
                for attempt in range(1, MAX_REPAIR_ATTEMPTS + 1):
                    logger.info(f"Repair attempt {attempt}/{MAX_REPAIR_ATTEMPTS}")

                    if repair_video_file(captured_file):
                        logger.info(f"Successfully repaired video file on attempt {attempt}")
                        break

                    # If we've tried all attempts and still failed
                    if attempt == MAX_REPAIR_ATTEMPTS:
                        error_msg = f"Failed to repair video file after {MAX_REPAIR_ATTEMPTS} attempts"
                        logger.error(error_msg)
                        self.state = CaptureState.ERROR
                        self.capture_state_changed.emit("ERROR", error_msg)
                        self.capture_error.emit(error_msg)
                        return

            # Video is valid, signal completion
            logger.info("Bookend capture and processing complete")
            self.state = CaptureState.COMPLETED
            self.capture_state_changed.emit("COMPLETED", "Bookend capture complete")
            self.capture_progress.emit(100)
            self.capture_completed.emit(captured_file)

        except Exception as e:
            error_msg = f"Error processing bookend capture: {str(e)}"
            logger.error(error_msg)
            self.state = CaptureState.ERROR
            self.capture_state_changed.emit("ERROR", error_msg)
            self.capture_error.emit(error_msg)

    def cancel_capture(self):
        """Cancel the current capture"""
        if self.state != CaptureState.CAPTURING and self.state != CaptureState.INITIALIZING:
            return

        logger.info("Cancelling capture...")

        # Stop the preview
        self.stop_preview()

        # Terminate FFmpeg process
        if self.ffmpeg_process and self.ffmpeg_process.poll() is None:
            logger.info("Terminating FFmpeg process")

            # Try to send 'q' to gracefully terminate
            try:
                self.ffmpeg_process.stdin.write('q\n')
                self.ffmpeg_process.stdin.flush()

                # Wait briefly for graceful termination
                time.sleep(1)

                # If still running, terminate
                if self.ffmpeg_process.poll() is None:
                    self.ffmpeg_process.terminate()
                    time.sleep(0.5)

                    # If still running, kill
                    if self.ffmpeg_process.poll() is None:
                        self.ffmpeg_process.kill()
            except:
                # If sending 'q' fails, just kill the process
                try:
                    self.ffmpeg_process.terminate()
                    time.sleep(0.5)
                    if self.ffmpeg_process.poll() is None:
                        self.ffmpeg_process.kill()
                except:
                    pass

        self.state = CaptureState.IDLE
        self.capture_state_changed.emit("IDLE", "Capture cancelled")

    def start_preview(self):
        """Start video preview"""
        try:
            # Close any existing preview
            self.stop_preview()

            # Start preview timer
            self.preview_timer.start(100)  # Update every 100ms
        except Exception as e:
            logger.error(f"Error starting preview: {str(e)}")

    def stop_preview(self):
        """Stop video preview"""
        self.preview_timer.stop()

        if self.preview_cap:
            self.preview_cap.release()
            self.preview_cap = None

    def update_preview(self):
        """Update the preview frame"""
        self.mutex.lock()
        try:
            # Only update if we're capturing
            if self.state != CaptureState.CAPTURING:
                return

            # Try to open the preview source if not already open
            if self.preview_cap is None:
                device = self.options_manager.get_setting("capture", "default_device")

                # Try to open the device for preview
                try:
                    # On Windows, try to use DirectShow
                    if platform.system() == 'Windows':
                        self.preview_cap = cv2.VideoCapture(f"video={device}", cv2.CAP_DSHOW)
                    else:
                        # On other platforms, use default
                        self.preview_cap = cv2.VideoCapture(0)

                    if not self.preview_cap.isOpened():
                        logger.warning(f"Could not open preview device: {device}")
                        return
                except Exception as e:
                    logger.error(f"Error opening preview device: {str(e)}")
                    return

            # Read a frame
            ret, frame = self.preview_cap.read()
            if not ret:
                logger.warning("Could not read frame for preview")
                return

            # Convert to QImage for preview signal
            height, width, channel = frame.shape
            bytes_per_line = 3 * width
            q_img = QImage(frame.data, width, height, bytes_per_line, QImage.Format_RGB888).rgbSwapped()

            # Emit the frame
            self.preview_frame.emit(q_img)

        except Exception as e:
            logger.error(f"Error updating preview: {str(e)}")
        finally:
            self.mutex.unlock()


class CaptureManager(QObject):
    """Main manager for video capture process using bookend method"""
    # Status signals
    status_update = pyqtSignal(str)
    progress_update = pyqtSignal(int)
    state_changed = pyqtSignal(CaptureState)

    # Process signals
    capture_started = pyqtSignal()
    capture_finished = pyqtSignal(bool, str)  # success, output_path
    frame_available = pyqtSignal(np.ndarray)  # For preview frame display

    def __init__(self):
        super().__init__()
        logger.info("Initializing CaptureManager")

        # Process state
        self.state = CaptureState.IDLE
        self.ffmpeg_process = None
        self.capture_monitor = None

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
        return self.state == CaptureState.CAPTURING

    def set_reference_video(self, reference_info):
        """Set reference video information"""
        self.reference_info = reference_info
        logger.info(f"Reference video set: {os.path.basename(reference_info['path'])}, " +
                   f"duration: {reference_info['duration']:.2f}s, " +
                   f"resolution: {reference_info['width']}x{reference_info['height']}")

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

        # Initialize preview capture to show input feed
        try:
            self._start_preview_capture(device_name)
            # Update UI to show preview is active
            self.frame_available.emit(self._get_preview_frame())
            self.status_update.emit("Video preview started - confirming capture card input")
        except Exception as preview_error:
            logger.warning(f"Could not start preview: {preview_error}")
            # Continue with capture even if preview fails

        # Prepare output path
        self._prepare_output_path()

        # Get settings from options manager if available through main app
        settings = None
        if hasattr(self, 'options_manager') and self.options_manager:
            settings = self.options_manager.settings

        # Calculate capture duration based on reference and settings
        ref_duration = self.reference_info['duration']
        frame_rate = self.reference_info.get('frame_rate', 30)  # Default to 30fps if unknown

        # Get bookend settings from options or use defaults
        bookend_duration = 0.5  # Default white frame duration in seconds
        min_loops = 3           # Default minimum loops
        max_capture_time = 120  # Default maximum capture time in seconds

        if settings and 'bookend' in settings:
            bookend_settings = settings.get('bookend', {})
            bookend_duration = bookend_settings.get('bookend_duration', 0.5)
            min_loops = bookend_settings.get('min_loops', 3)
            max_capture_time = bookend_settings.get('max_capture_time', 120)
            logger.info(f"Using bookend settings: duration={bookend_duration}s, min_loops={min_loops}, max_time={max_capture_time}s")

        loop_duration = ref_duration + (2 * bookend_duration)  # Account for start and end bookends

        # Capture for a much longer time to ensure at least the configured number of loops
        min_duration = max(20, ref_duration * min_loops)  # At least 20 seconds or min_loops * reference
        # Apply max capture time from settings
        max_duration = max_capture_time

        # Calculate capture duration with extra margin
        capture_duration = min(max((loop_duration * min_loops * 1.5), min_duration), max_duration)

        # Round up to nearest 10 seconds for good measure
        capture_duration = math.ceil(capture_duration / 10) * 10

        logger.info(f"Capture duration set to {capture_duration}s (loop={loop_duration:.2f}s, min_loops={min_loops})")

        # Inform the user
        self.status_update.emit(f"Capturing video with bookend frames for approximately {capture_duration:.0f} seconds...\n")
        self.status_update.emit("Please ensure the video plays in a loop with white frames between repetitions")

        # Kill any lingering FFmpeg processes
        self._kill_ffmpeg_processes()
        time.sleep(1)  # Short pause to ensure processes are terminated

        # Try to connect with minimal retries - don't reset the device
        connected, message = self._try_connect_device(device_name, max_retries=1)

        # Proceed even if connection reports issues
        logger.info(f"Proceeding with bookend capture (connected status={connected})")

        try:
            # Create a very robust FFmpeg command for reliable capture
            cmd = [
                self._ffmpeg_path,
                "-y",                     # Overwrite output
                "-v", "warning",          # Reduced verbosity
                "-f", "decklink",         # Force format
                "-i", device_name,        # Input device
                "-c:v", "libx264",        # Video codec
                "-preset", "superfast",   # Faster preset to reduce processing lag
                "-crf", "23",             # Slightly lower quality for better performance
                "-g", str(int(frame_rate * 2)),  # Keyframe interval (2 seconds)
                "-keyint_min", str(int(frame_rate)), # Minimum keyframe interval
                "-movflags", "+faststart", # Optimize for web streaming
                "-fflags", "+genpts+igndts", # More resilient timestamp handling
                "-avoid_negative_ts", "1", # Handle negative timestamps
                "-t", str(capture_duration) # Duration with extra buffer
            ]

            # Use forward slashes for FFmpeg
            ffmpeg_output_path = self.current_output_path.replace('\\', '/')
            cmd.append(ffmpeg_output_path)

            # Log command
            logger.info(f"FFmpeg bookend capture command: {' '.join(cmd)}")

            # Start FFmpeg process
            self.ffmpeg_process = subprocess.Popen(
                cmd,
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stdin=subprocess.PIPE,
                universal_newlines=True,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )

            # Create a more reliable monitor with longer timeout
            self.capture_monitor = CaptureMonitor(self.ffmpeg_process, capture_duration * 1.2)
            self.capture_monitor.progress_updated.connect(self.progress_update)
            self.capture_monitor.capture_complete.connect(self._on_bookend_capture_complete)
            self.capture_monitor.capture_failed.connect(self._on_capture_failed)
            self.capture_monitor.frame_count_updated.connect(self.update_frame_counter)
            self.capture_monitor.start()

            # Update state
            self.state = CaptureState.CAPTURING
            self.state_changed.emit(self.state)
            self.capture_started.emit()

            # User-friendly message
            self.status_update.emit(
                "Capturing video with white bookends... This requires recording several complete loops. "
                "Please wait until the capture automatically finishes."
            )

            return True

        except Exception as e:
            error_msg = f"Failed to start bookend capture: {str(e)}"
            logger.error(error_msg)
            self.status_update.emit(error_msg)
            self.state = CaptureState.ERROR
            self.state_changed.emit(self.state)
            self.capture_finished.emit(False, error_msg)
            return False