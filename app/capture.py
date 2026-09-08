import collections
import logging
import math
import os
import platform
import queue
import re
import signal
import subprocess
import threading
import time
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
import psutil
from PyQt6.QtCore import QMutex, QObject, QThread, QTimer, pyqtSignal

logger = logging.getLogger(__name__)

# Constants
MAX_REPAIR_ATTEMPTS = 3  # Maximum number of attempts to repair a video file

# Precompiled regex patterns for stderr parsing
FRAME_PATTERN = re.compile(r'frame=\s*(\d+)')
FPS_PATTERN = re.compile(r'fps=\s*([\d.]+)')
TIME_PATTERN = re.compile(r'time=(\d+):(\d+):(\d+\.\d+)')


# Define capture states for better management
class CaptureState(Enum):
    IDLE = 0
    INITIALIZING = 1
    CAPTURING = 2
    PROCESSING = 3
    COMPLETED = 4
    ERROR = 5


class CaptureMonitor(QThread):
    """Thread to monitor FFmpeg capture process with non-blocking stderr reading and watchdog supervision"""
    progress_updated = pyqtSignal(int)
    capture_complete = pyqtSignal()
    capture_failed = pyqtSignal(str)
    capture_stalled = pyqtSignal(str)  # Emitted with reason when stream stall is detected
    frame_count_updated = pyqtSignal(int, int)  # current_frame, total_frames
    capture_metadata = pyqtSignal(dict)
    capture_truncated = pyqtSignal(str)

    def __init__(
        self,
        process,
        duration=None,
        total_frames=0,
        output_path=None,
        stop_mode="graceful",
        startup_timeout: float = 10.0,
        stall_timeout: float = 5.0,
        clock=None,
    ):
        super().__init__()
        self.process = process
        self._running = True
        self._stopping = False  # Set to True on deliberate user stop to disarm watchdog (Annotation 1)
        self._watchdog_triggered = False  # True if watchdog triggered shutdown
        self._watchdog_reason = ""
        self.duration = duration  # Expected duration in seconds
        self.total_frames = total_frames  # Use predefined total frames if provided
        self.output_path = output_path
        self.stop_mode = stop_mode
        self.startup_timeout = float(startup_timeout)
        self.stall_timeout = float(stall_timeout)
        self._clock = clock or time.monotonic  # Injectable monotonic clock (Annotations 2 & 4)
        self._is_custom_clock = clock is not None

        self.start_time = self._clock()
        self.last_frame_rx_time = self._clock()
        self.frames_received = False
        self.is_bookend_capture = True
        self.last_frame_count = 0
        self.last_progress_time = self._clock()
        self.last_progress_value = 0
        self.last_frame_emit_time = 0
        self.last_emitted_frame = -1

        # Telemetry flags for near-miss logging (Annotation 3)
        self._startup_near_miss_logged = False
        self._stall_near_miss_logged = False

        self.gaps_detected = False
        self.gap_warning_emitted = False
        self.capture_truncated_flag = False
        self.escalation_used = False

        self._stderr_buffer = collections.deque(maxlen=200)
        self._stderr_queue = queue.Queue(maxsize=1000)
        self._pump_thread = None

    @property
    def error_output(self) -> str:
        return "".join(self._stderr_buffer)

    def _stderr_pump(self):
        """Dedicated pump thread reading stderr line-by-line without blocking monitor loop"""
        try:
            if hasattr(self.process, 'stderr') and self.process.stderr:
                for line in iter(self.process.stderr.readline, ''):
                    if not line:
                        break
                    if isinstance(line, bytes):
                        line = line.decode('utf-8', errors='replace')
                    self._stderr_buffer.append(line)
                    try:
                        self._stderr_queue.put(line, block=False)
                    except queue.Full:
                        try:
                            self._stderr_queue.get_nowait()
                        except queue.Empty:
                            pass
                        self._stderr_queue.put(line, block=False)
            self._stderr_queue.put(None)
        except (OSError, ValueError):
            self._stderr_queue.put(None)

    def run(self):
        """Monitor process output and emit signals using bounded queue with watchdog supervision"""
        logger.debug("Starting capture monitor")
        self.progress_updated.emit(0)

        self._pump_thread = threading.Thread(target=self._stderr_pump, daemon=True)
        self._pump_thread.start()

        fps = 30.0
        while self._running:
            # Check for process completion
            if self.process.poll() is not None:
                # Drain remaining lines from queue
                while True:
                    try:
                        drain_line = self._stderr_queue.get_nowait()
                        if drain_line is None:
                            break
                    except queue.Empty:
                        break

                if self._watchdog_triggered:
                    error = self._watchdog_reason or self.error_output
                    logger.error(f"Capture failed due to watchdog trigger: {error}")
                    self.capture_failed.emit(error)
                elif self._stopping:
                    logger.info("Capture stopped cleanly by deliberate user request")
                elif self.process.returncode == 0:
                    logger.info("Capture completed successfully")
                    self.progress_updated.emit(99)
                    self._verify_output_and_emit_metadata()
                    self.capture_complete.emit()
                else:
                    error = self.error_output
                    logger.error(f"Capture failed with code {self.process.returncode}: {error}")
                    self.capture_failed.emit(error)
                return

            now = self._clock()

            # Check for duration timeout - be more lenient with bookend captures
            if self.duration and (now - self.start_time) > self.duration * 2.0:
                logger.warning(f"Capture exceeded expected duration ({self.duration}s), terminating gracefully")
                self._graceful_shutdown()
                self.progress_updated.emit(99)
                self.capture_complete.emit()
                return

            # Parse process output from queue
            timeout_val = 0.005 if self._is_custom_clock else 0.25
            try:
                line = self._stderr_queue.get(timeout=timeout_val)
            except queue.Empty:
                line = None

            if line is not None:
                logger.debug(f"FFmpeg output: {line.strip()}")

                frame_match = FRAME_PATTERN.search(line)
                if frame_match:
                    try:
                        frame_num = int(frame_match.group(1))
                        self.last_frame_count = frame_num
                        self.frames_received = True
                        self.last_frame_rx_time = self._clock()
                        self._stall_near_miss_logged = False

                        fps_match = FPS_PATTERN.search(line)
                        if fps_match:
                            try:
                                fps = float(fps_match.group(1))
                            except Exception:
                                pass

                        if self.duration and fps > 0:
                            self.total_frames = int(self.duration * fps)

                        time_elapsed = None
                        time_match = TIME_PATTERN.search(line)
                        if time_match:
                            hours = int(time_match.group(1))
                            minutes = int(time_match.group(2))
                            seconds = float(time_match.group(3))
                            time_elapsed = hours * 3600 + minutes * 60 + seconds

                        # Frame gap / drop detection
                        elapsed_run = self._clock() - self.start_time
                        if elapsed_run > 2.0 and fps > 0:
                            expected_so_far = elapsed_run * fps
                            delta = frame_num - expected_so_far
                            if abs(delta) > max(expected_so_far * 0.02, 5):
                                self.gaps_detected = True
                                if not self.gap_warning_emitted:
                                    logger.warning(
                                        f"Frame gap detected: expected ~{int(expected_so_far)}, captured {frame_num}"
                                    )
                                    self.gap_warning_emitted = True

                        # Calculate progress percentage throttled to 0.25s
                        current_time = self._clock()
                        if current_time - self.last_progress_time >= 0.25:
                            progress = 0
                            if self.duration and self.total_frames > 0:
                                progress = min(int((frame_num / self.total_frames) * 95), 95)
                            elif time_elapsed is not None and self.duration:
                                progress = min(int((time_elapsed / self.duration) * 95), 95)
                            elif self.duration:
                                progress = min(int((elapsed_run / self.duration) * 95), 95)
                            else:
                                progress = max(5, min(int((frame_num % 1000) / 10), 95))

                            if progress != self.last_progress_value:
                                self.progress_updated.emit(progress)
                                self.last_progress_value = progress
                            self.last_progress_time = current_time

                        # Throttle frame count emissions (every 5 frames or 100ms)
                        if (frame_num - self.last_emitted_frame >= 5) or (current_time - self.last_frame_emit_time >= 0.1):
                            self.frame_count_updated.emit(frame_num, self.total_frames)
                            self.last_emitted_frame = frame_num
                            self.last_frame_emit_time = current_time

                    except Exception as e:
                        logger.debug(f"Error parsing frame number: {e}")

                if "Error" in line or "Invalid" in line:
                    logger.warning(f"Potential error in FFmpeg output: {line.strip()}")

            # Watchdog Evaluation (Annotation 1: disarmed during deliberate stops; Annotation 2: monotonic)
            now = self._clock()
            if not self._stopping and not self._watchdog_triggered:
                if not self.frames_received:
                    startup_elapsed = now - self.start_time
                    # Annotation 3: Log warning when stall is within 2x of threshold without firing
                    if startup_elapsed >= (self.startup_timeout * 0.5) and not self._startup_near_miss_logged:
                        logger.warning(
                            f"Watchdog telemetry: No video frames received for {startup_elapsed:.1f}s "
                            f"(threshold is {self.startup_timeout:.1f}s)"
                        )
                        self._startup_near_miss_logged = True

                    if startup_elapsed > self.startup_timeout:
                        reason = (
                            f"Capture pipeline stalled during initialization: no video frames "
                            f"received from device within {self.startup_timeout:.1f}s"
                        )
                        logger.error(f"WATCHDOG TRIGGERED: {reason}")
                        self._watchdog_triggered = True
                        self._watchdog_reason = reason
                        self.capture_stalled.emit(reason)
                        self._graceful_shutdown()
                        self.capture_failed.emit(reason)
                        return
                else:
                    stall_elapsed = now - self.last_frame_rx_time
                    # Annotation 3: Log warning when stall is within 2x of threshold without firing
                    if stall_elapsed >= (self.stall_timeout * 0.5) and not self._stall_near_miss_logged:
                        logger.warning(
                            f"Watchdog telemetry: Frame ingestion delayed for {stall_elapsed:.1f}s "
                            f"(threshold is {self.stall_timeout:.1f}s)"
                        )
                        self._stall_near_miss_logged = True

                    if stall_elapsed > self.stall_timeout:
                        reason = (
                            f"Capture pipeline stalled during recording: video stream frozen, "
                            f"no new frames for {stall_elapsed:.1f}s (threshold {self.stall_timeout:.1f}s)"
                        )
                        logger.error(f"WATCHDOG TRIGGERED: {reason}")
                        self._watchdog_triggered = True
                        self._watchdog_reason = reason
                        self.capture_stalled.emit(reason)
                        self._graceful_shutdown()
                        self.capture_failed.emit(reason)
                        return

            if line is None:
                if self.process.poll() is not None:
                    continue
                time.sleep(0.001 if self._is_custom_clock else 0.05)

    def _graceful_shutdown(self, deadline=5.0):
        """Safely terminate FFmpeg process with 'q' key and escalating signals to avoid MP4 corruption"""
        if not self.process or self.process.poll() is not None:
            self._verify_output_and_emit_metadata()
            return

        logger.info(f"Initiating FFmpeg shutdown (mode={self.stop_mode})...")

        if self.stop_mode == "immediate":
            logger.warning("Immediate stop mode: terminating FFmpeg directly")
            self.escalation_used = True
            try:
                self.process.terminate()
                for _ in range(10):
                    if self.process.poll() is not None:
                        break
                    time.sleep(0.1)
                if self.process.poll() is None:
                    self.process.kill()
                    self.capture_truncated_flag = True
            except Exception as e:
                logger.error(f"Error terminating process: {e}")
            self._verify_output_and_emit_metadata()
            return

        # 1. Send 'q' key to stdin
        try:
            if hasattr(self.process, 'stdin') and self.process.stdin:
                try:
                    self.process.stdin.write('q\n')
                except TypeError:
                    self.process.stdin.write(b'q\n')
                self.process.stdin.flush()
                logger.info("Sent 'q' command to FFmpeg via stdin")
        except Exception as e:
            logger.warning(f"Could not send 'q' command to FFmpeg: {e}")

        # 2. Wait up to 2 seconds for clean exit
        for _ in range(20):
            if self.process.poll() is not None:
                logger.info("FFmpeg stopped cleanly after 'q' command")
                self._verify_output_and_emit_metadata()
                return
            time.sleep(0.1)

        # 3. Send CTRL_BREAK_EVENT (Windows) or SIGINT (POSIX)
        logger.info("FFmpeg still running; sending break/interrupt signal...")
        try:
            if platform.system() == "Windows":
                if hasattr(signal, "CTRL_BREAK_EVENT"):
                    self.process.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    self.process.send_signal(signal.SIGINT)
            else:
                self.process.send_signal(signal.SIGINT)
        except Exception as e:
            logger.warning(f"Error sending interrupt signal: {e}")

        # Wait up to 2 seconds more
        for _ in range(20):
            if self.process.poll() is not None:
                logger.info("FFmpeg stopped cleanly after interrupt signal")
                self._verify_output_and_emit_metadata()
                return
            time.sleep(0.1)

        # 4. Escalate to terminate() then kill()
        logger.warning("FFmpeg did not stop gracefully; escalating to terminate()")
        self.escalation_used = True
        try:
            self.process.terminate()
            for _ in range(10):
                if self.process.poll() is not None:
                    logger.info("FFmpeg terminated after terminate()")
                    self._verify_output_and_emit_metadata()
                    return
                time.sleep(0.1)
        except Exception as e:
            logger.warning(f"Error escalating to terminate(): {e}")

        if self.process.poll() is None:
            logger.warning("FFmpeg still alive; forcing kill()")
            self.capture_truncated_flag = True
            try:
                self.process.kill()
                self.process.wait(timeout=2)
            except Exception as e:
                logger.error(f"Error force-killing FFmpeg: {e}")

        self._verify_output_and_emit_metadata()

    def _verify_output_and_emit_metadata(self):
        """Verify output integrity with ffprobe if escalated, and emit metadata"""
        if self.output_path and os.path.isfile(self.output_path):
            if self.escalation_used:
                from app.utils import get_video_info
                info = get_video_info(self.output_path)
                if not info or not info.get("total_frames"):
                    self.capture_truncated_flag = True
                    logger.warning(f"Capture output {self.output_path} appears unfinalized / truncated")
                    self.capture_truncated.emit(self.output_path)
        self._emit_final_metadata()

    def _emit_final_metadata(self):
        fps = 30.0
        expected = self.total_frames
        if not expected and self.duration:
            expected = int(self.duration * fps)
        metadata = {
            "frames_captured": self.last_frame_count,
            "expected_frames": expected,
            "gaps_detected": self.gaps_detected,
            "driver_tier": "unknown",
            "capture_truncated": self.capture_truncated_flag,
        }
        self.capture_metadata.emit(metadata)

    def stop(self):
        """Stop monitoring and shut down FFmpeg gracefully (deliberate user stop, disarms watchdog)"""
        self._stopping = True
        self._running = False
        self._graceful_shutdown()


class CaptureManager(QObject):
    """Main manager for video capture process using bookend method"""
    # Status signals
    status_update = pyqtSignal(str)
    progress_update = pyqtSignal(int)
    state_changed = pyqtSignal(CaptureState)
    capture_stalled = pyqtSignal(str)  # Emitted when watchdog detects a stall

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
        self._spawned_pids = set()
        self.latest_capture_metadata = None

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
        """Kill only FFmpeg processes spawned by this manager to avoid collateral damage"""
        try:
            logger.info("Looking for recorded FFmpeg child processes to terminate")
            killed_count = 0
            remaining_pids = set()

            for pid in list(self._spawned_pids):
                try:
                    if psutil.pid_exists(pid):
                        proc = psutil.Process(pid)
                        if "ffmpeg" in proc.name().lower():
                            proc.kill()
                            killed_count += 1
                            logger.info(f"Killed spawned FFmpeg PID {pid}")
                        else:
                            remaining_pids.add(pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            self._spawned_pids = remaining_pids

            if killed_count == 0 and self.ffmpeg_process and self.ffmpeg_process.poll() is None:
                try:
                    self.ffmpeg_process.kill()
                    killed_count += 1
                except Exception:
                    pass

            if killed_count > 0:
                time.sleep(0.2)
        except Exception as e:
            logger.error(f"Error terminating spawned FFmpeg processes: {e}")

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
        if self.options_manager:
            val = self.options_manager.get_setting("bookend", "max_capture_time")
            if val is not None and val > 0:
                return val
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
            "recovery_timeout": 10,
            "startup_timeout_s": 10.0,
            "stall_timeout_s": 5.0,
            "preflight_min_disk_mb": 2048,
            "bitrate_mbps": 50.0,
        }
        
        # Override with options from options_manager if available
        if self.options_manager:
            capture_settings = self.options_manager.get_setting("capture")
            if capture_settings:
                for key in options:
                    if key in capture_settings:
                        options[key] = capture_settings[key]
        
        return options

    def _on_capture_stalled(self, reason: str):
        """Handle capture pipeline stall detected by watchdog"""
        logger.warning(f"Capture stalled: {reason}")
        self.status_update.emit(f"Warning: {reason}")
        self.capture_stalled.emit(reason)

    def run_preflight_checks(
        self,
        device_name: str,
        duration: float,
        capture_options: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        """
        Perform preflight checks before launching FFmpeg capture process.

        Semantics & Division of Labor (Annotation 5):
        1. Directory & Storage: Validates destination directory existence, write permissions,
           and checks available disk space against estimated run size + safety floor.
        2. Device Presence: Checks device ENUMERATION only against options_manager / detected devices.
           On Windows, DirectShow and DeckLink devices can be enumerable but busy/locked by another app.
           Preflight intentionally does NOT attempt to open the device to prevent hardware side effects;
           hardware open failures and stream lockups are handled by the startup watchdog.

        Returns:
            (success: bool, diagnostic_message: str)
        """
        import shutil

        opts = capture_options or self._get_capture_options()
        min_floor_mb = int(opts.get("preflight_min_disk_mb", 2048))

        # 1. Directory & Storage Validation
        target_dir = self.output_directory
        if not target_dir and self.current_output_path:
            target_dir = os.path.dirname(os.path.abspath(self.current_output_path))
        if not target_dir:
            target_dir = os.path.join(os.getcwd(), "captures")

        try:
            os.makedirs(target_dir, exist_ok=True)
        except Exception as e:
            return False, f"Preflight failed: Unable to create destination directory '{target_dir}': {e}"

        if not os.access(target_dir, os.W_OK):
            return False, f"Preflight failed: Destination directory '{target_dir}' is not writable."

        bitrate_mbps = float(opts.get("bitrate_mbps", 50.0))
        estimated_run_mb = (bitrate_mbps * duration) / 8.0
        required_mb = max(min_floor_mb, int(estimated_run_mb + min_floor_mb))

        try:
            _, _, free_bytes = shutil.disk_usage(target_dir)
            free_mb = free_bytes // (1024 * 1024)
            drive = os.path.splitdrive(os.path.abspath(target_dir))[0] or target_dir
            if free_mb < required_mb:
                return False, (
                    f"Preflight failed: Insufficient disk space on {drive}. "
                    f"Requires ~{required_mb} MB (estimated {int(estimated_run_mb)} MB + {min_floor_mb} MB buffer), "
                    f"found {free_mb} MB free."
                )
        except Exception as e:
            logger.warning(f"Could not check disk usage on {target_dir}: {e}")

        # 2. Device Presence Check (Enumeration only)
        if self.options_manager and hasattr(self.options_manager, "get_decklink_devices"):
            try:
                detected = self.options_manager.get_decklink_devices()
                if detected is not None and len(detected) > 0:
                    match = any(
                        device_name.strip().lower() in d.strip().lower() or d.strip().lower() in device_name.strip().lower()
                        for d in detected
                    )
                    if not match:
                        return False, (
                            f"Preflight failed: Capture device '{device_name}' not found in detected device list: {detected}."
                        )
            except Exception as dev_err:
                logger.warning(f"Error querying detected devices during preflight: {dev_err}")

        drive_str = os.path.splitdrive(os.path.abspath(target_dir))[0] or target_dir
        return True, f"Preflight passed: Disk space OK (>= {required_mb} MB required on {drive_str}), device '{device_name}' enumerated."

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
        
    def _on_capture_metadata(self, metadata: dict):
        self.latest_capture_metadata = metadata
        logger.info(f"Capture metadata recorded: {metadata}")

    def _on_capture_truncated(self, path: str):
        logger.warning(f"Capture output flagged as truncated: {path}")
        self.status_update.emit("Warning: Capture file may be truncated.")

    def stop_capture(self, cleanup_temp=False):
        """Stop any active capture process gracefully"""
        if not self.is_capturing:
            return

        logger.info("Stopping capture")
        self.status_update.emit("Stopping capture...")

        # Delegate graceful shutdown to capture monitor (runs without freezing UI)
        if hasattr(self, 'capture_monitor') and self.capture_monitor:
            self.capture_monitor.stop()

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
        self._prepare_output_path()

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

        # Run preflight validation checks (Annotation 5)
        preflight_ok, preflight_msg = self.run_preflight_checks(device_name, capture_duration, capture_options)
        if not preflight_ok:
            logger.error(f"Preflight validation failed: {preflight_msg}")
            self.status_update.emit(preflight_msg)
            self.state = CaptureState.ERROR
            self.state_changed.emit(self.state)
            self.capture_finished.emit(False, preflight_msg)
            self.stop_preview()
            return False

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
                # Use the centralized format code mapping method
                decklink_format = self._map_format_code(format_code)
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
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0  # SW_HIDE
                
                creationflags = 0
                if hasattr(subprocess, 'CREATE_NO_WINDOW'):
                    creationflags |= subprocess.CREATE_NO_WINDOW
                if hasattr(subprocess, 'CREATE_NEW_PROCESS_GROUP'):
                    creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP
                
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
                self.ffmpeg_process = subprocess.Popen(
                    cmd,
                    stderr=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stdin=subprocess.PIPE
                )

            if self.ffmpeg_process:
                self._spawned_pids.add(self.ffmpeg_process.pid)

            total_frames = int(capture_duration * frame_rate)
            logger.info(f"Estimated total frames: {total_frames} based on capture_duration={capture_duration}s and fps={frame_rate}")
            
            stop_mode = "graceful"
            if self.options_manager:
                stop_mode = self.options_manager.get_setting("capture", "stop_mode") or "graceful"

            startup_timeout = float(capture_options.get("startup_timeout_s", 10.0))
            stall_timeout = float(capture_options.get("stall_timeout_s", 5.0))

            self.capture_monitor = CaptureMonitor(
                self.ffmpeg_process,
                capture_duration,
                total_frames,
                output_path=self.current_output_path,
                stop_mode=stop_mode,
                startup_timeout=startup_timeout,
                stall_timeout=stall_timeout,
            )
            
            # Connect signals
            self.capture_monitor.progress_updated.connect(self.progress_update)
            self.capture_monitor.capture_complete.connect(self._on_bookend_capture_complete)
            self.capture_monitor.capture_failed.connect(self._on_capture_failed)
            self.capture_monitor.capture_stalled.connect(self._on_capture_stalled)
            self.capture_monitor.frame_count_updated.connect(self.update_frame_counter)
            self.capture_monitor.capture_metadata.connect(self._on_capture_metadata)
            self.capture_monitor.capture_truncated.connect(self._on_capture_truncated)
            
            # Start monitor thread
            self.capture_monitor.start()

            # Set capture start time (monotonic per Annotation 2)
            self.capture_start_time = time.monotonic()
            
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





















