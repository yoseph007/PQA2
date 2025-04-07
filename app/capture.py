import logging
import math
import os
import platform
import re
import subprocess
import threading
import time
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

import cv2
import numpy as np
import psutil
from PyQt5.QtCore import QMutex, QObject, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QImage

logger = logging.getLogger(__name__)

# Constants
MAX_REPAIR_ATTEMPTS = 3  # Maximum number of attempts to repair a video file

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

    def __init__(self, process, duration=None, total_frames=0):
        super().__init__()
        self.process = process
        self._running = True
        self.error_output = ""
        self.start_time = time.time()
        self.duration = duration  # Expected duration in seconds
        self.is_bookend_capture = True  # Always true since we only use bookend mode now
        self.last_frame_count = 0
        self.total_frames = total_frames  # Use predefined total frames if provided
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
                                error += remaining.decode('utf-8') if isinstance(remaining, bytes) else remaining
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
                        # Convert bytes to string if needed
                        if isinstance(line, bytes):
                            line = line.decode('utf-8', errors='replace')
                            
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

                                    # Always update total_frames when we have fps info, even if it was set before
                                    if self.duration and fps > 0:
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
                            if hasattr(self.process.stdin, 'buffer'):
                                # Handle text mode
                                self.process.stdin.write('q\n')
                            else:
                                # Handle binary mode
                                self.process.stdin.write(b'q\n')
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

    def __init__(self, options_manager=None):
        super().__init__()
        logger.info("Initializing CaptureManager")

        # Store options manager reference
        self.options_manager = options_manager

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

        # Setup preview mutex
        self.preview_mutex = QMutex()
        
        # Preview frame data
        self.preview_frame = None
        self.preview_cap = None
        self.preview_active = False
        self.preview_timer = QTimer()
        self.preview_timer.timeout.connect(self.update_preview)

        # Find ffmpeg
        self._ffmpeg_path = self._find_ffmpeg()
        if self._ffmpeg_path:
            logger.info(f"Found FFmpeg at: {self._ffmpeg_path}")
        else:
            logger.warning("FFmpeg not found, using 'ffmpeg' command")
            self._ffmpeg_path = "ffmpeg"

    def _find_ffmpeg(self):
        """Find FFmpeg executable using options manager if available"""
        if self.options_manager:
            return self.options_manager.get_ffmpeg_path()
        
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
        return self.state == CaptureState.CAPTURING or self.state == CaptureState.INITIALIZING

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
        return self.current_output_path

    def _kill_all_ffmpeg(self):
        """Kill any lingering FFmpeg processes to avoid device conflicts"""
        try:
            logger.info("Looking for lingering FFmpeg processes to terminate")
            killed_count = 0
            
            if platform.system() == 'Windows':
                # On Windows, use taskkill for more reliable FFmpeg process termination
                try:
                    # Use subprocess with startupinfo to suppress dialog boxes
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = 0  # SW_HIDE
                    
                    subprocess.run(
                        ["taskkill", "/F", "/IM", "ffmpeg.exe"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        startupinfo=startupinfo,
                        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
                    )
                    logger.info("Used taskkill to terminate FFmpeg processes")
                    time.sleep(1)  # Give Windows time to fully release resources
                    return
                except Exception as e:
                    logger.warning(f"Taskkill failed, falling back to psutil: {e}")
            
            # Standard psutil approach (works on all platforms)
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

    def update_frame_counter(self, current_frame, total_frames):
        """Update frame counter display during capture process"""
        try:
            # Format a user-friendly frame counter message
            if total_frames > 0:
                percentage = min(100, int((current_frame / total_frames) * 100))
                frame_msg = f"Capturing: Frame {current_frame}/{total_frames} ({percentage}%)"
            else:
                frame_msg = f"Capturing: Frame {current_frame}"

            # Update status
            self.status_update.emit(frame_msg)

            # Log every 100 frames to avoid excessive logging
            if current_frame % 100 == 0:
                logger.debug(f"Capture progress: Frame {current_frame}")
        except Exception as e:
            logger.error(f"Error updating frame counter: {e}")








    def _get_expected_duration(self):
        """Get expected capture duration in seconds"""
        # Use bookend settings from options
        if self.options_manager:
            return self.options_manager.get_setting("bookend", "max_capture_time") or 30
        return 30  # Default fallback

    def start_preview(self):
        """Start video preview - modified to avoid device access during capture"""
        try:
            # Stop any existing preview timer
            self.stop_preview()

            # Start preview timer
            self.preview_timer.start(200)  # Update every 200ms (5 fps is enough for status display)
            self.preview_active = True
            logger.info("Started preview status display")
        except Exception as e:
            logger.error(f"Error starting preview: {str(e)}")

    def stop_preview(self):
        """Stop video preview"""
        self.preview_timer.stop()
        self.preview_active = False

        # Close any open preview capture
        if hasattr(self, 'preview_cap') and self.preview_cap is not None:
            try:
                self.preview_cap.release()
                self.preview_cap = None
                logger.info("Stopped video preview")
            except Exception as e:
                logger.error(f"Error stopping preview: {str(e)}")










    def update_preview(self):
        """Update the preview frame while capture is active - with improved device handling"""
        if not self.is_capturing:
            return
                
        self.preview_mutex.lock()
        try:
            # For Blackmagic devices, we can't access the device directly during capture
            # Instead, create a status display that shows capture is in progress
            
            # Create a status display
            placeholder = np.zeros((270, 480, 3), dtype=np.uint8)
            placeholder[:] = (50, 50, 50)  # Dark gray background
            
            # Get capture info
            elapsed = time.time() - getattr(self, 'capture_start_time', time.time())
            frame_count = 0
            total_frames = 0
            
            if hasattr(self, 'capture_monitor') and self.capture_monitor:
                frame_count = getattr(self.capture_monitor, 'last_frame_count', 0)
                total_frames = getattr(self.capture_monitor, 'total_frames', 0)
            
            # Add recording indicator (pulsating red circle)
            pulse_size = 8 + int((math.sin(elapsed * 3) + 1) * 4)  # Pulsating size between 8-16px
            cv2.circle(placeholder, (30, 30), pulse_size, (0, 0, 255), -1)
            
            # Add active recording text
            cv2.putText(placeholder, "RECORDING ACTIVE", (60, 35), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 255), 2)
            
            # Add elapsed time
            cv2.putText(placeholder, f"Elapsed: {elapsed:.1f}s", (30, 70), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
            
            # Add frame info
            if total_frames > 0:
                progress = min(100, int((frame_count / total_frames) * 100))
                frame_text = f"Frame: {frame_count}/{total_frames} ({progress}%)"
            else:
                frame_text = f"Frame: {frame_count}"
                
            cv2.putText(placeholder, frame_text, (30, 100), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
            
            # Add capture device
            device_name = self._get_capture_device_name()
            cv2.putText(placeholder, f"Device: {device_name}", (30, 130), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
            
            # Add progress bar
            progress_width = 400
            progress_height = 20
            progress_value = min(95, int(elapsed / self._get_expected_duration() * 100))
            
            # Background bar
            cv2.rectangle(placeholder, (40, 180), (40 + progress_width, 180 + progress_height), 
                        (80, 80, 80), -1)
            
            # Progress fill
            fill_width = int(progress_width * progress_value / 100)
            cv2.rectangle(placeholder, (40, 180), (40 + fill_width, 180 + progress_height), 
                        (0, 120, 255), -1)
            
            # Frame counter text
            cv2.putText(placeholder, f"{progress_value}%", (40 + progress_width//2 - 15, 180 + 15), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            # Add warning about preview limitations
            cv2.putText(placeholder, "Live preview unavailable during capture", (30, 230), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)
            cv2.putText(placeholder, "with Blackmagic hardware", (30, 250), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)
            
            # Emit the frame for display
            self.frame_available.emit(placeholder)
                
        except Exception as e:
            logger.error(f"Error in preview update: {str(e)}")
        finally:
            self.preview_mutex.unlock()















    def _get_capture_device_name(self):
        """Get the configured capture device name from options"""
        if self.options_manager:
            return self.options_manager.get_setting("capture", "default_device")
        return "Intensity Shuttle"  # Default fallback

    def _get_capture_options(self):
        """Get capture configuration from options manager"""
        options = {
            # Default options
            "device": "Intensity Shuttle",
            "resolution": "1920x1080",
            "frame_rate": 29.97,
            "pixel_format": "uyvy422",
            "video_input": "hdmi",
            "audio_input": "embedded",
            "encoder": "libx264",
            "crf": 18,
            "preset": "fast",
            "format_code": "Hp29",
            "disable_audio": False,
            "low_latency": True, 
            "force_format": False,
            "retry_attempts": 3,
            "retry_delay": 3,
            "recovery_timeout": 10
        }
        
        # Override with options from options_manager if available
        if self.options_manager:
            capture_settings = self.options_manager.get_setting("capture")
            if capture_settings:
                for key in options:
                    if key in capture_settings:
                        options[key] = capture_settings[key]
        
        return options




    def _map_format_code(self, code):
        """Map internal format codes to Decklink format codes"""
        format_map = {
            "Hp29": "hp1080p2997",
            "Hp30": "hp1080p30",
            "Hp25": "hp1080p25",
            "hp59": "hp720p5994",
            "hp60": "hp720p60",
            "hp50": "hp720p50",
            # Add more mappings as needed
        }
        return format_map.get(code, code)  # Return original if no mapping found







    def _get_bookend_options(self):
        """Get bookend configuration from options manager"""
        options = {
            # Default options
            "min_loops": 3,
            "max_loops": 10,
            "min_capture_time": 5,
            "max_capture_time": 30,
            "bookend_duration": 0.2,
            "white_threshold": 200,
            "frame_sampling_rate": 5,
            "frame_offset": 3,
            "adaptive_brightness": True,
            "motion_compensation": False,
            "fallback_to_full_video": True
        }
        
        # Override with options from options_manager if available
        if self.options_manager:
            bookend_settings = self.options_manager.get_setting("bookend")
            if bookend_settings:
                for key in options:
                    if key in bookend_settings:
                        options[key] = bookend_settings[key]
        
        return options

    def _on_capture_failed(self, error_msg):
        """Handle capture failure"""
        logger.error(f"Capture failed: {error_msg}")

        # Update state
        self.state = CaptureState.ERROR
        self.state_changed.emit(self.state)

        # Emit failure signal
        self.status_update.emit(f"Error: {error_msg}")
        self.capture_finished.emit(False, error_msg)

        # Clean up resources
        if self.ffmpeg_process and self.ffmpeg_process.poll() is None:
            try:
                self.ffmpeg_process.terminate()
                time.sleep(0.5)
                if self.ffmpeg_process.poll() is None:
                    self.ffmpeg_process.kill()
            except Exception as e:
                logger.error(f"Error terminating FFmpeg process: {e}")

        # Reset capture monitor
        self.capture_monitor = None
        
        # Stop preview
        self.stop_preview()

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

        # Move to completed state
        self.state = CaptureState.COMPLETED
        self.state_changed.emit(self.state)
        self.status_update.emit("Capture completed successfully!")
        self.capture_finished.emit(True, output_path)
        
        # Stop preview
        self.stop_preview()

    def stop_capture(self, cleanup_temp=False):
        """Stop any active capture process"""
        if not self.is_capturing:
            return

        logger.info("Stopping capture")
        self.status_update.emit("Stopping capture...")

        # Stop capture monitor if active
        if hasattr(self, 'capture_monitor') and self.capture_monitor:
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
            except Exception as e:
                logger.error(f"Error removing temporary file: {e}")

        # Add delay before allowing another capture
        time.sleep(1)  # 1 second delay

        # Stop preview
        self.stop_preview()

        self.status_update.emit("Capture stopped by user")
        self.capture_finished.emit(False, "Capture cancelled by user")







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

        # Start preview
        self.start_preview()

        # Prepare output path
        output_path = self._prepare_output_path()

        # Calculate capture duration based on reference and settings
        ref_duration = self.reference_info['duration']
        frame_rate = self.reference_info.get('frame_rate', 30)  # Default to 30fps if unknown

        # Get options
        bookend_options = self._get_bookend_options()
        capture_options = self._get_capture_options()
        
        # Extract bookend parameters
        bookend_duration = bookend_options['bookend_duration'] 
        min_loops = bookend_options['min_loops']
        max_loops = bookend_options['max_loops']
        min_capture_time = bookend_options['min_capture_time']
        max_capture_time = bookend_options['max_capture_time']
        
        # Calculate base loop duration including bookends
        loop_duration = ref_duration + (2 * bookend_duration)  # Account for start and end bookends

        # Calculate min and max durations based on loops
        min_loop_duration = max(loop_duration * min_loops, min_capture_time)
        max_loop_duration = min(loop_duration * max_loops, max_capture_time)
        
        # Calculate final capture duration with extra margin for reliability
        # Use 1.2x multiplier to ensure we capture at least the minimum number of loops
        capture_duration = min(min_loop_duration * 1.2, max_loop_duration)

        # Round up to nearest second for clean timing
        capture_duration = math.ceil(capture_duration)
        
        logger.info(f"Reference duration: {ref_duration:.2f}s")
        logger.info(f"Single loop duration (with bookends): {loop_duration:.2f}s")
        logger.info(f"Minimum required duration: {min_loop_duration:.2f}s ({min_loops} loops)")
        logger.info(f"Maximum allowed duration: {max_loop_duration:.2f}s ({max_loops} loops)")
        logger.info(f"Final capture duration: {capture_duration:.2f}s")

        # Inform the user
        self.status_update.emit(f"Capturing video with bookend frames for approximately {capture_duration:.1f} seconds...")
        self.status_update.emit("Please ensure the video plays in a loop with white frames between repetitions")

        # Kill any lingering FFmpeg processes
        self._kill_all_ffmpeg()
        time.sleep(1)  # Short pause to ensure processes are terminated

        try:
            # Get format code and map to appropriate decklink format if needed
            format_code = capture_options.get('format_code')
            if format_code:
                # Map common format codes to decklink-specific format codes
                format_map = {
                    "Hp29": "hp1080p2997",
                    "Hp30": "hp1080p30",
                    "Hp25": "hp1080p25",
                    "hp59": "hp720p5994",
                    "hp60": "hp720p60",
                    "hp50": "hp720p50",
                }
                decklink_format = format_map.get(format_code, format_code)
                logger.info(f"Mapped format code {format_code} to {decklink_format}")
            else:
                decklink_format = None
                logger.warning("No format code specified - device will use autodetection")

            # Create FFmpeg command with format code in the correct position
            cmd = [
                self._ffmpeg_path,
                "-y",                     # Overwrite output
                "-v", "info",             # Use info verbosity to show more feedback
                "-f", "decklink",         # Force format
            ]
                
            # Add format code BEFORE the input device - this is critical for decklink
            if decklink_format:
                cmd.extend(["-format_code", decklink_format])
                
            # Add video input selection
            cmd.extend(["-video_input", capture_options.get('video_input', 'hdmi')])
            
            # Add audio input if not disabled
            if not capture_options.get('disable_audio', False):
                cmd.extend(["-audio_input", capture_options.get('audio_input', 'embedded')])
            
            # Add input device
            cmd.extend(["-i", device_name])
            
            # Add video codec settings
            cmd.extend([
                "-c:v", capture_options.get('encoder', 'libx264'),
                "-preset", capture_options.get('preset', 'fast'),
                "-crf", str(capture_options.get('crf', 18)),
                "-g", str(int(frame_rate)),    # Fix keyframe interval to match frame rate
                "-keyint_min", str(int(frame_rate)), # Minimum keyframe interval
                "-movflags", "+faststart", # Optimize for web streaming
                "-fflags", "+genpts+igndts", # More resilient timestamp handling
                "-avoid_negative_ts", "1", # Handle negative timestamps
                "-t", str(capture_duration) # Use calculated capture duration
            ])
            
            # Add audio codec settings if audio not disabled
            if not capture_options.get('disable_audio', False):
                cmd.extend([
                    "-c:a", "aac",
                    "-b:a", "192k"
                ])

            # Use forward slashes for FFmpeg
            ffmpeg_output_path = self.current_output_path.replace('\\', '/')
            cmd.append(ffmpeg_output_path)

            # Log command
            logger.info(f"FFmpeg bookend capture command: {' '.join(cmd)}")

            # Start FFmpeg process with enhanced error suppression for Windows
            if platform.system() == 'Windows':
                # Windows-specific settings to completely suppress error dialogs
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0  # SW_HIDE
                
                # Use all available methods to suppress dialog boxes
                creationflags = 0
                if hasattr(subprocess, 'CREATE_NO_WINDOW'):
                    creationflags |= subprocess.CREATE_NO_WINDOW
                
                # Also redirect stderr to a pipe to intercept error messages
                env = os.environ.copy()
                env.update({"FFMPEG_HIDE_BANNER": "1", "AV_LOG_FORCE_NOCOLOR": "1"})
                
                self.ffmpeg_process = subprocess.Popen(
                    cmd,
                    stderr=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stdin=subprocess.PIPE,
                    creationflags=creationflags,
                    startupinfo=startupinfo,
                    env=env
                )
            else:
                # Regular process creation for non-Windows platforms
                self.ffmpeg_process = subprocess.Popen(
                    cmd,
                    stderr=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stdin=subprocess.PIPE
                )

            # Create a more reliable monitor with proper frame estimation based on capture_duration
            total_frames = int(capture_duration * frame_rate)
            logger.info(f"Estimated total frames: {total_frames} based on capture_duration={capture_duration}s and fps={frame_rate}")
            
            self.capture_monitor = CaptureMonitor(self.ffmpeg_process, capture_duration, total_frames)
            
            # Connect signals
            self.capture_monitor.progress_updated.connect(self.progress_update)
            self.capture_monitor.capture_complete.connect(self._on_bookend_capture_complete)
            self.capture_monitor.capture_failed.connect(self._on_capture_failed)
            self.capture_monitor.frame_count_updated.connect(self.update_frame_counter)
            
            # Start monitor thread
            self.capture_monitor.start()

            # Set capture start time
            self.capture_start_time = time.time()
            
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
            
            # Stop preview
            self.stop_preview()
            
            return False





















