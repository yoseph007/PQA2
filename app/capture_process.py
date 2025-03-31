import logging
import subprocess
import re
import time
import os
import threading
from PyQt5.QtCore import QObject, pyqtSignal, QThread, pyqtSlot, QTimer

logger = logging.getLogger(__name__)

class CaptureMonitor(QThread):
    """Thread to monitor FFmpeg capture process"""
    progress_updated = pyqtSignal(int)
    capture_complete = pyqtSignal()
    capture_failed = pyqtSignal(str)

    def __init__(self, process, max_duration=None):
        super().__init__()
        self.process = process
        self._running = True
        self.error_output = ""
        self.start_time = time.time()
        self.max_duration = max_duration  # Maximum capture duration in seconds
        
    def run(self):
        """Monitor process output and emit signals"""
        logger.debug("Starting capture monitor")
        
        while self._running:
            # Check if max duration has been reached
            if self.max_duration and time.time() - self.start_time > self.max_duration:
                logger.info(f"Maximum capture duration ({self.max_duration}s) reached")
                self._terminate_process()
                self.capture_complete.emit()
                break
                
            # Check process status
            if self.process.poll() is not None:
                if self.process.returncode == 0:
                    logger.info("Capture completed successfully")
                    self.capture_complete.emit()
                else:
                    # Read any remaining error output
                    if hasattr(self.process.stderr, 'read'):
                        remaining_error = self.process.stderr.read()
                        if remaining_error:
                            self.error_output += remaining_error
                    
                    logger.error(f"Capture failed with code {self.process.returncode}: {self.error_output}")
                    self.capture_failed.emit(self.error_output)
                break

            # Read and parse FFmpeg output
            if hasattr(self.process.stderr, 'readline'):
                line = self.process.stderr.readline()
                if line:
                    # Store error output for diagnostics
                    self.error_output += line
                    logger.debug(f"FFmpeg output: {line.strip()}")
                    
                    # Parse progress information
                    if "frame=" in line:
                        try:
                            frame_match = re.search(r'frame=\s*(\d+)', line)
                            if frame_match:
                                frame_num = int(frame_match.group(1))
                                self.progress_updated.emit(frame_num)
                        except (AttributeError, ValueError) as e:
                            logger.warning(f"Failed to parse frame number: {e}")
                    
                    # Check for hanging patterns
                    if "No packets in" in line or "error reading from" in line:
                        logger.warning("Detected potential hang condition")
                        self._terminate_process()
                        self.capture_failed.emit("Capture process appears to be hanging")
                        break

            time.sleep(0.1)
        logger.debug("Capture monitor exiting")

    def _terminate_process(self):
        """Safely terminate the process"""
        if self.process and self.process.poll() is None:
            logger.info("Terminating FFmpeg process")
            try:
                # Send 'q' key to FFmpeg to gracefully terminate
                if hasattr(self.process, 'stdin') and self.process.stdin:
                    self.process.stdin.write('q\n')
                    self.process.stdin.flush()
                    time.sleep(0.5)  # Give it a moment to respond
                
                # If still running, terminate properly
                if self.process.poll() is None:
                    self.process.terminate()
                    self.process.wait(timeout=5)
                    
                    # Force kill if still running
                    if self.process.poll() is None:
                        self.process.kill()
                        
            except Exception as e:
                logger.error(f"Error terminating process: {e}")
                # Try harder to kill it
                try:
                    self.process.kill()
                except:
                    pass

    def stop(self):
        """Gracefully stop monitoring"""
        self._running = False
        self._terminate_process()
        self.wait()

class CaptureManager(QObject):
    """Main capture controller with Qt signals"""
    status_update = pyqtSignal(str)
    progress_update = pyqtSignal(int)
    capture_started = pyqtSignal()
    capture_finished = pyqtSignal(bool, str)  # success, message

    def __init__(self):
        super().__init__()
        logger.info("Initializing CaptureManager")
        self.process = None
        self.monitor = None
        self._capture_active = False
        self.current_output_path = None
        self._ffmpeg_path = self._find_ffmpeg()
        self.output_directory = None
        self.test_name = None
        
        # Timeout to prevent hanging captures
        self.capture_timeout = 3600  # Default 1 hour max
        
        if self._ffmpeg_path:
            logger.info(f"Found FFmpeg at: {self._ffmpeg_path}")
        else:
            logger.warning("FFmpeg not found, using 'ffmpeg' command")
            self._ffmpeg_path = "ffmpeg"

    def _find_ffmpeg(self):
        """Find the FFmpeg executable path"""
        try:
            # Look for ffmpeg in common locations or PATH
            ffmpeg_cmd = "ffmpeg"
            if os.path.exists(ffmpeg_cmd):
                return ffmpeg_cmd
                
            # Try running ffmpeg to see if it's in PATH
            result = subprocess.run(
                [ffmpeg_cmd, "-version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            if result.returncode == 0:
                return ffmpeg_cmd
                
            return ffmpeg_cmd  # Default fallback
        except Exception as e:
            logger.error(f"Error finding FFmpeg: {e}")
            return "ffmpeg"  # Default fallback

    @property
    def is_capturing(self):
        """Property to check if capture is active"""
        return self._capture_active

    def set_max_duration(self, seconds):
        """Set maximum capture duration in seconds"""
        self.capture_timeout = seconds
        logger.info(f"Maximum capture duration set to {seconds} seconds")

    def start_capture(self, device_name, output_path, duration=None):
        """Start video capture with error handling"""
        if self._capture_active:
            logger.warning("Capture already in progress")
            return False

        logger.info(f"Starting capture on device '{device_name}' to {output_path}")
        self.status_update.emit(f"Starting capture on {device_name}...")
        self.current_output_path = output_path
        
        # Create output directory if needed
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        try:
            # Set max duration (either passed value or the default timeout)
            max_duration = duration if duration else self.capture_timeout
            
            # Build FFmpeg command using the exact format that worked for the user
            cmd = [
                self._ffmpeg_path,
                "-y",  # Overwrite output
                "-f", "decklink",
                "-i", device_name,  # Use the actual device name, not @device_id
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "18",  # Better quality than 23
            ]
            
            # Add duration limit if specified
            if duration:
                cmd.extend(["-t", str(duration)])
                
            # Add output path
            cmd.append(output_path)
            
            logger.debug(f"FFmpeg command: {' '.join(cmd)}")

            # Start FFmpeg process with input pipe (so we can send 'q' to stop it cleanly)
            self.process = subprocess.Popen(
                cmd,
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stdin=subprocess.PIPE,
                universal_newlines=True
            )

            # Start monitoring thread
            self.monitor = CaptureMonitor(self.process, max_duration)
            self.monitor.progress_updated.connect(self._handle_progress)
            self.monitor.capture_complete.connect(self._handle_success)
            self.monitor.capture_failed.connect(self._handle_error)
            self.monitor.start()

            # Watchdog timer to prevent infinite hanging
            self.watchdog_timer = QTimer(self)
            self.watchdog_timer.timeout.connect(self._check_capture_status)
            self.watchdog_timer.start(60000)  # Check every minute
            
            self._capture_active = True
            self._capture_start_time = time.time()
            self.capture_started.emit()
            self.status_update.emit(f"Capture running on {device_name}")
            logger.info("Capture started successfully")
            return True

        except Exception as e:
            error_msg = f"Failed to start capture: {str(e)}"
            logger.error(error_msg)
            self.status_update.emit(error_msg)
            self._cleanup()
            self.capture_finished.emit(False, error_msg)
            return False

    def _check_capture_status(self):
        """Check if capture hasn't made progress in too long"""
        if not self._capture_active or not self.monitor:
            return
            
        # Check if it's been running longer than the timeout
        elapsed = time.time() - self._capture_start_time
        if elapsed > self.capture_timeout + 600:  # 10 minute grace period
            logger.warning(f"Capture timed out after {elapsed:.1f} seconds")
            self.stop_capture()
            self._handle_error("Capture timed out - forced termination")

    def set_output_directory(self, output_dir):
        """Set custom output directory"""
        self.output_directory = output_dir
        
    def set_test_name(self, test_name):
        """Set test name for output files"""
        self.test_name = test_name

    def stop_capture(self):
        """Stop current capture gracefully"""
        if not self._capture_active:
            return

        logger.info("Stopping capture")
        self.status_update.emit("Stopping capture...")

        try:
            if self.watchdog_timer:
                self.watchdog_timer.stop()
                
            if self.monitor:
                self.monitor.stop()
                
            self._cleanup()
            logger.info("Capture stopped successfully")
            self.capture_finished.emit(True, "Capture stopped by user")
            return True
        except Exception as e:
            error_msg = f"Error stopping capture: {str(e)}"
            logger.error(error_msg)
            self.status_update.emit(error_msg)
            self.capture_finished.emit(False, error_msg)
            return False

    def _cleanup(self):
        """Clean up resources"""
        if self.monitor:
            self.monitor.stop()
            self.monitor = None

        if self.watchdog_timer:
            self.watchdog_timer.stop()
            self.watchdog_timer = None
            
        self.process = None
        self._capture_active = False

    @pyqtSlot(int)
    def _handle_progress(self, frame_num):
        """Handle progress updates"""
        self.progress_update.emit(frame_num)

    @pyqtSlot()
    def _handle_success(self):
        """Handle successful capture completion"""
        output_path = self.current_output_path
        self._cleanup()
        self.capture_finished.emit(True, output_path)
        self.status_update.emit(f"Capture completed: {output_path}")

    @pyqtSlot(str)
    def _handle_error(self, error_msg):
        """Handle capture errors"""
        self._cleanup()
        
        # Make error message more user-friendly
        if "No such device" in error_msg or "Error opening input" in error_msg:
            user_msg = "Cannot access the DeckLink device. Please check that:\n\n" \
                      "1. The device is properly connected\n" \
                      "2. Blackmagic drivers are installed\n" \
                      "3. No other application is using the device"
        else:
            user_msg = f"Capture failed: {error_msg}"
            
        self.capture_finished.emit(False, user_msg)
        self.status_update.emit("Capture failed")