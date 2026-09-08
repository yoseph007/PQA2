import json
import logging
import os
import platform
import shutil
import subprocess
import time
import traceback
from datetime import datetime
from enum import Enum

import cv2
import numpy as np
from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal

from app.utils import (
    get_ffmpeg_path,
    get_subprocess_startupinfo,
    get_video_info,
    run_ffmpeg_without_dialogs,
)

logger = logging.getLogger(__name__)


class AlignmentState(Enum):
    IDLE = "idle"
    ANALYZING = "analyzing"
    ALIGNING = "aligning"
    REPAIRING = "repairing"
    COMPLETED = "completed"
    COMPLETE = "completed"  # backward compatibility alias
    FAILED = "failed"
    ERROR = "failed"        # backward compatibility alias
    RUNNING = "aligning"    # backward compatibility alias


# Named timing constants (replace magic numbers)
INITIAL_SKIP_SECONDS = 0.2
BUFFER_FRAMES = 1.5
DEFAULT_CONFIDENCE = 0.95
MAX_REPAIR_ATTEMPTS = 3
FFMPEG_TIMEOUT = 60
MOTION_COMPENSATION_TIMEOUT = 300
DEFAULT_FRAME_OFFSET = 3


def validate_video_file(file_path):
    """Validate if a video file is intact and can be read"""
    if not os.path.exists(file_path):
        logger.error(f"File does not exist: {file_path}")
        return False

    if os.path.getsize(file_path) == 0:
        logger.error(f"File is empty: {file_path}")
        return False

    try:
        _, ffprobe_exe, _ = get_ffmpeg_path()
        startupinfo, creationflags = get_subprocess_startupinfo()
        cmd = [
            ffprobe_exe,
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=codec_type",
            "-of", "json",
            file_path
        ]

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10,
            startupinfo=startupinfo, creationflags=creationflags
        )

        if result.returncode != 0:
            logger.error(f"FFprobe validation failed: {result.stderr}")
            return False

        info = json.loads(result.stdout)
        return 'streams' in info and len(info['streams']) > 0

    except Exception as e:
        logger.error(f"Error validating video file: {e}")
        return False


def repair_video_file(video_path: str, error_callback=None) -> bool:
    """
    Repair a video file with missing moov atom by remuxing it with FFmpeg.
    Uses atomic os.replace and cleans up temp files on failure.
    """
    if not os.path.exists(video_path):
        logger.error(f"Cannot repair nonexistent file: {video_path}")
        return False

    temp_path = f"{video_path}.repaired.mp4"
    ffmpeg_exe, _, _ = get_ffmpeg_path()
    startupinfo, creationflags = get_subprocess_startupinfo()

    for attempt in range(1, MAX_REPAIR_ATTEMPTS + 1):
        try:
            cmd = [
                ffmpeg_exe, "-hide_banner", "-loglevel", "warning", "-y",
                "-i", video_path,
                "-c", "copy",
                "-movflags", "faststart",
                temp_path
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT,
                startupinfo=startupinfo, creationflags=creationflags
            )
            if result.returncode == 0 and os.path.isfile(temp_path):
                os.replace(temp_path, video_path)  # atomic replacement
                logger.info(f"Successfully repaired video file: {video_path}")
                return True
            err_msg = f"Repair attempt {attempt}/{MAX_REPAIR_ATTEMPTS} failed: {result.stderr[-500:]}"
            logger.warning(err_msg)
            if error_callback:
                error_callback(err_msg)
        except subprocess.TimeoutExpired:
            err_msg = f"Repair attempt {attempt} timed out"
            logger.warning(err_msg)
            if error_callback:
                error_callback(err_msg)
        except OSError as e:
            err_msg = f"Repair attempt {attempt} error: {e}"
            logger.warning(err_msg)
            if error_callback:
                error_callback(err_msg)
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
    return False


class BookendAligner(QObject):
    """
    Class for aligning captured video with reference video using white frame bookends
    """
    alignment_progress = pyqtSignal(int)  # 0-100%
    progress_updated = alignment_progress
    alignment_complete = pyqtSignal(dict)  # Results including offset
    error_occurred = pyqtSignal(str)
    status_update = pyqtSignal(str)
    status_updated = status_update

    def __init__(self, options_manager=None, parent=None):
        super().__init__(parent)
        ffmpeg_exe, ffprobe_exe, _ = get_ffmpeg_path()
        self._ffmpeg_path = ffmpeg_exe
        self._ffprobe_path = ffprobe_exe

        self.options_manager = options_manager
        opts = {}
        if options_manager:
            try:
                all_s = options_manager.get_settings() or {}
                bookend_s = options_manager.get_setting("bookend") if hasattr(options_manager, "get_setting") else {}
                if isinstance(bookend_s, dict):
                    opts.update(bookend_s)
                opts.update(all_s)
            except Exception:
                pass

        self.frame_offset = int(opts.get("frame_offset", DEFAULT_FRAME_OFFSET))
        self.white_threshold = float(opts.get("white_threshold", 230.0))

        # Default values for advanced options
        self.frame_sampling_rate = int(opts.get("frame_sampling_rate", 5))
        self.adaptive_brightness = bool(opts.get("adaptive_brightness", True))
        self.motion_compensation = bool(opts.get("motion_compensation", False))
        self.fallback_to_full_video = bool(opts.get("fallback_to_full_video", True))

    def repair_video_file(self, video_path: str) -> bool:
        return repair_video_file(video_path, error_callback=self.error_occurred.emit)

    def set_advanced_options(self, frame_sampling_rate=5, adaptive_brightness=True, 
                             motion_compensation=False, fallback_to_full_video=True):
        """Set advanced options for bookend alignment"""
        prev_motion_comp = self.motion_compensation
        self.frame_sampling_rate = frame_sampling_rate
        self.adaptive_brightness = adaptive_brightness
        self.motion_compensation = motion_compensation
        self.fallback_to_full_video = fallback_to_full_video
        
        if prev_motion_comp != motion_compensation:
            logger.info(f"Motion compensation setting changed: {prev_motion_comp} -> {motion_compensation}")
        
        logger.info(f"Set advanced bookend options: sampling_rate={frame_sampling_rate}, "
                    f"adaptive_brightness={adaptive_brightness}, "
                    f"motion_compensation={motion_compensation}, "
                    f"fallback_to_full_video={fallback_to_full_video}")

    def _apply_motion_compensation(self, video_path, start_time, duration):
        """
        Apply motion compensation to the video to improve alignment for fast-moving content
        """
        try:
            output_dir = os.path.dirname(video_path)
            base_name = os.path.splitext(os.path.basename(video_path))[0]
            output_path = os.path.join(output_dir, f"{base_name}_motion_comp.mp4")
            
            video_info = get_video_info(video_path) or {}
            original_fps = video_info.get('frame_rate', 30)
            
            logger.info(f"Applying motion compensation from {start_time:.3f}s for {duration:.3f}s with fps={original_fps}")
            
            ffmpeg_exe, _, _ = get_ffmpeg_path()
            startupinfo, creationflags = get_subprocess_startupinfo()
            cmd = [
                ffmpeg_exe, "-hide_banner", "-y",
                "-i", video_path,
                "-ss", str(start_time),
                "-t", str(duration),
                "-vf", f"minterpolate=fps={original_fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1",
                "-c:v", "libx264", "-crf", "23", "-preset", "fast",
                "-r", str(original_fps),
                output_path
            ]
            
            logger.info(f"Running motion compensation: {' '.join(cmd)}")
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=MOTION_COMPENSATION_TIMEOUT,
                startupinfo=startupinfo, creationflags=creationflags
            )
            
            if result.returncode != 0:
                logger.error(f"Motion compensation failed: {result.stderr}")
                return None
                
            if not os.path.exists(output_path) or not validate_video_file(output_path):
                logger.error("Motion compensation output file is invalid")
                return None
                
            return output_path
        except Exception as e:
            logger.error(f"Error applying motion compensation: {e}")
            return None

    def align_bookend_videos(self, reference_path, captured_path, output_path=None):
        """
        Align videos based on white frame bookends that surround the content
        """
        try:
            logger.info(f"Starting alignment with motion_compensation={self.motion_compensation}")
            self.status_update.emit("Starting white bookend alignment process...")
            logger.info("Starting white bookend alignment process")

            # Verify files exist
            if not os.path.exists(reference_path):
                error_msg = f"Reference video file not found: {reference_path}"
                logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                return None

            if not os.path.exists(captured_path):
                error_msg = f"Captured video file not found: {captured_path}"
                logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                return None

            # Validate video files first
            if not validate_video_file(captured_path):
                self.status_update.emit("Captured video file appears invalid, attempting repair...")
                if not self.repair_video_file(captured_path):
                    error_msg = "Failed to repair captured video file"
                    logger.error(error_msg)
                    self.error_occurred.emit(error_msg)
                    return None
                else:
                    self.status_update.emit("Video file repaired successfully")

            # Get video info
            ref_info = get_video_info(reference_path)
            cap_info = get_video_info(captured_path)

            if not ref_info or not cap_info:
                error_msg = "Failed to get video information"
                logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                return None

            self.status_update.emit("Detecting white bookend frames in captured video...")
            self.alignment_progress.emit(10)

            bookend_frames = self._detect_white_bookends(captured_path)

            if not bookend_frames or len(bookend_frames) < 2:
                error_msg = "Failed to detect at least two white bookend sections"
                logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                
                if self.fallback_to_full_video:
                    logger.info("Falling back to using entire captured video as content")
                    self.status_update.emit("No bookends detected. Using entire video instead...")
                    
                    content_start_time = INITIAL_SKIP_SECONDS
                    content_duration = cap_info.get('duration', 0) - 2 * INITIAL_SKIP_SECONDS
                    
                    if content_duration <= 0:
                        error_msg = "Video duration too short for proper alignment"
                        logger.error(error_msg)
                        self.error_occurred.emit(error_msg)
                        return None
                else:
                    return None
            else:
                first_bookend = bookend_frames[0]
                last_bookend = bookend_frames[-1]

                logger.info(f"Detected first white bookend at: {first_bookend['start_time']:.3f}s - {first_bookend['end_time']:.3f}s")
                logger.info(f"Detected last white bookend at: {last_bookend['start_time']:.3f}s - {last_bookend['end_time']:.3f}s")

                frame_buffer_time = BUFFER_FRAMES / cap_info.get('frame_rate', 30)
                content_start_time = first_bookend['end_time'] + frame_buffer_time
                content_end_time = last_bookend['start_time'] - frame_buffer_time

                if content_end_time <= content_start_time:
                    error_msg = "Invalid content timing between bookends"
                    logger.error(error_msg)
                    self.error_occurred.emit(error_msg)
                    return None

                content_duration = content_end_time - content_start_time
                logger.info(f"Content duration between bookends: {content_duration:.3f}s")

                ref_duration = ref_info.get('duration', 0)

                # Handle multi-loop videos
                if content_duration > ref_duration * 1.5:
                    logger.info(f"Reference duration ({ref_duration:.3f}s) - content duration ({content_duration:.3f}s)")
                    logger.info("Detected multiple loops in captured video, looking for individual loops")

                    if len(bookend_frames) > 2:
                        best_start_idx = 0
                        best_duration_diff = float('inf')

                        for i in range(len(bookend_frames) - 1):
                            start_bookend = bookend_frames[i]
                            end_bookend = bookend_frames[i + 1]

                            loop_start = start_bookend['end_time'] + frame_buffer_time
                            loop_end = end_bookend['start_time'] - frame_buffer_time
                            loop_duration = loop_end - loop_start

                            duration_diff = abs(loop_duration - ref_duration)
                            logger.info(f"Loop {i+1}: {loop_start:.3f}s - {loop_end:.3f}s = {loop_duration:.3f}s (diff: {duration_diff:.3f}s)")

                            if duration_diff < best_duration_diff:
                                best_duration_diff = duration_diff
                                best_start_idx = i

                        start_bookend = bookend_frames[best_start_idx]
                        end_bookend = bookend_frames[best_start_idx + 1]

                        content_start_time = start_bookend['end_time'] + frame_buffer_time
                        content_end_time = end_bookend['start_time'] - frame_buffer_time
                        content_duration = content_end_time - content_start_time

                        logger.info(f"Selected loop {best_start_idx+1}: {content_start_time:.3f}s - {content_end_time:.3f}s = {content_duration:.3f}s")
                    else:
                        msg = f"Multi-loop video detected with only 2 bookends: trimming to first {ref_duration:.3f}s matching reference"
                        logger.info(msg)
                        self.status_update.emit(msg)
                        content_duration = ref_duration

            self.alignment_progress.emit(50)
            self.status_update.emit("Creating aligned videos...")

            processed_captured_path = captured_path
            if self.motion_compensation:
                logger.info("Motion compensation is ENABLED in settings, applying it...")
                self.status_update.emit("Applying motion compensation for fast-moving content...")
                
                motion_compensated_path = self._apply_motion_compensation(
                    captured_path, 
                    content_start_time, 
                    content_duration
                )
                
                if motion_compensated_path:
                    logger.info(f"Motion compensation applied, using: {motion_compensated_path}")
                    processed_captured_path = motion_compensated_path
                    content_start_time = 0
                    mc_info = get_video_info(motion_compensated_path) or {}
                    content_duration = mc_info.get('duration', content_duration)
                else:
                    logger.warning("Motion compensation failed, proceeding with original footage")
            else:
                logger.info("Motion compensation is DISABLED in settings, skipping...")

            aligned_reference, aligned_captured = self._create_aligned_videos_by_bookends(
                reference_path,
                processed_captured_path,
                content_start_time,
                content_duration,
                output_dir=os.path.dirname(output_path) if output_path else None
            )

            if not aligned_reference or not aligned_captured:
                error_msg = "Failed to create aligned videos"
                logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                return None

            self.alignment_progress.emit(100)
            self.status_update.emit("White bookend alignment complete!")

            result = {
                'alignment_method': 'bookend',
                'offset_frames': 0,
                'offset_seconds': 0,
                'confidence': DEFAULT_CONFIDENCE,
                'aligned_reference': aligned_reference,
                'aligned_captured': aligned_captured,
                'bookend_info': {
                    'first_bookend': bookend_frames[0] if bookend_frames else None,
                    'last_bookend': bookend_frames[-1] if bookend_frames else None,
                    'content_duration': content_duration,
                    'motion_compensated': self.motion_compensation
                }
            }

            self.alignment_complete.emit(result)
            return result
        except Exception as e:
            error_msg = f"Error in bookend alignment: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            self.error_occurred.emit(error_msg)
            return None

    def _create_aligned_videos_by_bookends(self, reference_path, captured_path, content_start_time, content_duration, output_dir=None):
        """Create aligned videos based on bookend content timing with improved naming"""
        try:
            ref_info = get_video_info(reference_path) or {}
            cap_info = get_video_info(captured_path) or {}
            ref_fps = ref_info.get('frame_rate', 30)
            cap_fps = cap_info.get('frame_rate', 30)
            ref_frame_count = ref_info.get('frame_count', 0)
            
            logger.info(f"Preserving original frame rates: reference={ref_fps}fps, captured={cap_fps}fps")
            logger.info(f"Reference frame count: {ref_frame_count}")
            
            if not output_dir:
                ref_parent_dir = os.path.dirname(os.path.dirname(reference_path))
                if os.path.basename(ref_parent_dir) == "test_references":
                    test_results_dir = os.path.join(os.path.dirname(ref_parent_dir), "test_results")
                    if os.path.exists(test_results_dir):
                        capture_dir_name = os.path.basename(os.path.dirname(captured_path))
                        output_dir = os.path.join(test_results_dir, capture_dir_name)
                        os.makedirs(output_dir, exist_ok=True)
                        logger.info(f"Using test_results directory for aligned output: {output_dir}")
                    else:
                        output_dir = os.path.dirname(captured_path)
                else:
                    output_dir = os.path.dirname(captured_path)

            os.makedirs(output_dir, exist_ok=True)

            dir_name = os.path.basename(output_dir)
            timestamp = ""
            if "_" in dir_name:
                parts = dir_name.split("_")
                if len(parts) >= 2 and parts[-1].isdigit():
                    timestamp = parts[-1]
            if not timestamp:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            ref_base = os.path.splitext(os.path.basename(reference_path))[0]
            cap_base = os.path.splitext(os.path.basename(captured_path))[0]
            if "_motion_comp" in cap_base:
                cap_base = cap_base.replace("_motion_comp", "")

            aligned_reference = os.path.join(output_dir, f"{ref_base}_{timestamp}_aligned.mp4")
            aligned_captured = os.path.join(output_dir, f"{cap_base}_{timestamp}_aligned.mp4")

            startupinfo, creationflags = get_subprocess_startupinfo()

            # Trim reference video
            ref_cmd = [
                self._ffmpeg_path, "-y", "-i", reference_path,
                "-r", str(ref_fps),
                "-c:v", "libx264", "-crf", "23", 
                "-preset", "fast", "-c:a", "copy",
                aligned_reference
            ]
            logger.info(f"Creating aligned reference video: {aligned_reference}")
            ref_res = subprocess.run(
                ref_cmd, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT,
                startupinfo=startupinfo, creationflags=creationflags
            )
            if ref_res.returncode != 0:
                logger.error(f"Failed to create aligned reference video: {ref_res.stderr}")
                return None, None

            ref_aligned_info = get_video_info(aligned_reference) or {}
            exact_ref_frames = ref_aligned_info.get('frame_count', ref_frame_count)
            logger.info(f"Exact reference frame count: {exact_ref_frames}")

            frame_offset = getattr(self, 'frame_offset', DEFAULT_FRAME_OFFSET)
            if hasattr(self, 'options_manager') and self.options_manager:
                try:
                    if hasattr(self.options_manager, "get_setting"):
                        val = self.options_manager.get_setting("bookend", "frame_offset")
                        if val is not None:
                            frame_offset = int(val)
                except Exception as e:
                    logger.warning(f"Error getting frame_offset from options_manager: {e}")

            offset_time = frame_offset / cap_fps if cap_fps > 0 else 0
            logger.info(f"Applied frame offset: {frame_offset} frames ({offset_time:.6f}s) at {cap_fps} fps")

            adjusted_start = content_start_time + INITIAL_SKIP_SECONDS

            if adjusted_start > 0 or "motion_comp" not in captured_path:
                cap_cmd = [
                    self._ffmpeg_path, "-y",
                    "-itsoffset", str(offset_time),
                    "-i", captured_path,
                    "-ss", str(adjusted_start),
                    "-c:v", "libx264", "-crf", "23",
                    "-preset", "fast", 
                    "-r", str(ref_fps),
                    "-frames:v", str(exact_ref_frames),
                    aligned_captured
                ]
            else:
                cap_cmd = [
                    self._ffmpeg_path, "-y", 
                    "-i", captured_path,
                    "-c:v", "libx264", "-crf", "23",
                    "-preset", "fast",
                    "-r", str(ref_fps),
                    "-frames:v", str(exact_ref_frames),
                    aligned_captured
                ]

            cap_res = subprocess.run(
                cap_cmd, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT,
                startupinfo=startupinfo, creationflags=creationflags
            )
            if cap_res.returncode != 0:
                logger.error(f"Failed to create aligned captured video: {cap_res.stderr}")
                return None, None

            if not os.path.exists(aligned_reference) or not os.path.exists(aligned_captured):
                logger.error("Failed to create aligned videos")
                return None, None

            # Verify frame counts match exactly
            ref_aligned_info = get_video_info(aligned_reference) or {}
            cap_aligned_info = get_video_info(aligned_captured) or {}
            ref_frames = ref_aligned_info.get('frame_count', 0)
            cap_frames = cap_aligned_info.get('frame_count', 0)
            
            if ref_frames != cap_frames and cap_frames > 0:
                logger.warning(f"Frame count mismatch: reference={ref_frames}, captured={cap_frames}")
                logger.info("Attempting final frame count correction...")
                
                fixed_path = f"{aligned_captured}.fixed.mp4"
                final_fix_cmd = [
                    self._ffmpeg_path, "-y",
                    "-i", aligned_captured,
                    "-frames:v", str(ref_frames),
                    "-c:v", "libx264", "-crf", "23",
                    "-preset", "fast",
                    fixed_path
                ]
                try:
                    fix_res = subprocess.run(
                        final_fix_cmd, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT,
                        startupinfo=startupinfo, creationflags=creationflags
                    )
                    if fix_res.returncode == 0 and os.path.exists(fixed_path):
                        os.replace(fixed_path, aligned_captured)
                        logger.info("Frame count correction applied successfully")
                    else:
                        logger.warning(f"Final frame count correction failed: {fix_res.stderr}")
                except Exception as e:
                    logger.warning(f"Final frame count correction error: {e}")
                finally:
                    if os.path.exists(fixed_path):
                        try:
                            os.remove(fixed_path)
                        except OSError:
                            pass

            if "_motion_comp.mp4" in captured_path and os.path.exists(captured_path):
                try:
                    os.remove(captured_path)
                    logger.info(f"Deleted temporary motion-compensated file: {captured_path}")
                except Exception as e:
                    logger.warning(f"Could not delete temporary file: {e}")

            return aligned_reference, aligned_captured
        except Exception as e:
            logger.error(f"Error creating aligned videos by bookends: {str(e)}")
            logger.error(traceback.format_exc())
            return None, None

    @staticmethod
    def _deduplicate_bookends(candidates: list) -> list:
        """
        Cluster overlapping intervals and pick the best representative per group.
        Never mutates `candidates`. Preference: longest duration, then highest brightness.
        """
        if not candidates:
            return []

        def key(c):
            return (c["start_frame"], c.get("end_frame", c["start_frame"]))

        sorted_c = sorted(candidates, key=key)
        groups = []
        current = [sorted_c[0]]
        current_end = key(sorted_c[0])[1]

        for cand in sorted_c[1:]:
            start, end = key(cand)
            if start <= current_end:  # overlapping
                current.append(cand)
                current_end = max(current_end, end)
            else:
                groups.append(current)
                current = [cand]
                current_end = end
        groups.append(current)

        best = []
        for group in groups:
            best.append(
                max(group, key=lambda c: (
                    (c.get("end_frame", c["start_frame"]) - c["start_frame"]),
                    c.get("brightness", 0.0),
                ))
            )
        return best

    def _detect_white_bookends(self, video_path):
        """
        Performance-optimized white bookend detection with adaptive thresholds
        and non-mutating interval deduplication.
        """
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                logger.error(f"Could not open video: {video_path}")
                return None

            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = frame_count / fps if fps > 0 else 0

            logger.info(f"Video details: duration={duration:.2f}s, frames={frame_count}, fps={fps:.2f}")

            sample_interval = int(fps / self.frame_sampling_rate) if self.frame_sampling_rate > 0 else 1
            if sample_interval < 1:
                sample_interval = 1

            brightness_samples = []
            sample_frames = []
            for i in range(0, frame_count, sample_interval):
                cap.set(cv2.CAP_PROP_POS_FRAMES, i)
                ret, frame = cap.read()
                if ret:
                    sample_frames.append((i, frame))

            for i, frame in sample_frames:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                brightness = float(np.mean(gray))
                std_dev = float(np.std(gray))
                brightness_samples.append((i, brightness, std_dev))

            if not brightness_samples:
                logger.error("Could not sample brightness levels from video")
                cap.release()
                return None

            all_brightness = [b for _, b, _ in brightness_samples]
            all_std_devs = [s for _, _, s in brightness_samples]
            avg_brightness = float(np.mean(all_brightness))
            std_brightness = float(np.std(all_brightness))
            max_brightness = float(np.max(all_brightness))
            avg_std_dev = float(np.mean(all_std_devs))

            white_threshold = getattr(self, "white_threshold", 230.0)
            if self.adaptive_brightness:
                dynamic_threshold = max(
                    avg_brightness + 2.0 * std_brightness,
                    max_brightness * 0.85,
                    white_threshold * 0.8,
                    180.0
                )
                if max_brightness > 240:
                    dynamic_threshold = max(dynamic_threshold, 220.0)
                elif max_brightness < 200:
                    dynamic_threshold = max(avg_brightness + 1.5 * std_brightness, 160.0)

                thresholds = [
                    dynamic_threshold,
                    dynamic_threshold * 0.9,
                    max(avg_brightness + 20, 160.0)
                ]
            else:
                fixed_threshold = white_threshold
                thresholds = [fixed_threshold, fixed_threshold * 0.9, fixed_threshold * 0.8]

            logger.info(f"Using brightness thresholds: {[round(t, 1) for t in thresholds]}")

            if fps > 25:
                min_white_frames = max(3, int(0.1 * fps))
            else:
                min_white_frames = 3

            initial_sample_rate = max(3, int(fps // 8)) if fps > 0 else 3
            std_dev_threshold = min(45.0, avg_std_dev * 1.8)

            regions_of_interest = []
            for threshold_idx, whiteness_threshold in enumerate(thresholds):
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                potential_regions = []
                current_region = None

                for frame_idx in range(0, frame_count, initial_sample_rate):
                    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                    ret, frame = cap.read()
                    if not ret:
                        break

                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    avg_b = float(np.mean(gray))
                    s_dev = float(np.std(gray))

                    if threshold_idx < 2:
                        is_white = avg_b > whiteness_threshold
                    else:
                        is_white = (avg_b > whiteness_threshold and s_dev < std_dev_threshold)

                    if is_white:
                        if current_region is None:
                            current_region = {
                                'start_frame': max(0, frame_idx - initial_sample_rate),
                                'brightness': avg_b
                            }
                    else:
                        if current_region is not None:
                            current_region['end_frame'] = min(frame_count - 1, frame_idx + initial_sample_rate)
                            potential_regions.append(current_region)
                            current_region = None

                if current_region is not None:
                    current_region['end_frame'] = min(frame_count - 1, frame_count - 1)
                    potential_regions.append(current_region)

                if potential_regions:
                    for region in potential_regions:
                        start = max(0, region['start_frame'] - initial_sample_rate)
                        end = min(frame_count - 1, region['end_frame'] + initial_sample_rate)
                        regions_of_interest.append((start, end, whiteness_threshold))

            if not regions_of_interest:
                regions_of_interest = [(0, frame_count - 1, thresholds[-1])]

            if len(regions_of_interest) > 1:
                regions_of_interest.sort()
                merged_regions = []
                current_start, current_end, current_threshold = regions_of_interest[0]
                for start, end, threshold in regions_of_interest[1:]:
                    if start <= current_end:
                        current_end = max(current_end, end)
                        current_threshold = min(current_threshold, threshold)
                    else:
                        merged_regions.append((current_start, current_end, current_threshold))
                        current_start, current_end, current_threshold = start, end, threshold
                merged_regions.append((current_start, current_end, current_threshold))
                regions_of_interest = merged_regions

            all_bookends = []
            for region_idx, (start_frame, end_frame, threshold) in enumerate(regions_of_interest):
                if end_frame - start_frame < min_white_frames:
                    continue

                consecutive_white_frames = 0
                current_bookend = None
                region_bookends = []

                cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
                for frame_idx in range(start_frame, end_frame + 1):
                    ret, frame = cap.read()
                    if not ret:
                        break

                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    avg_b = float(np.mean(gray))
                    s_dev = float(np.std(gray))

                    is_white = False
                    if s_dev < std_dev_threshold * 1.2:
                        if avg_b > threshold * 0.95:
                            is_white = True
                    else:
                        if avg_b > threshold:
                            is_white = True
                        elif avg_b > threshold * 0.9:
                            white_pixels = np.sum(gray > threshold)
                            if (white_pixels / gray.size) > 0.7:
                                is_white = True

                    if is_white:
                        consecutive_white_frames += 1
                        if current_bookend is None:
                            current_bookend = {
                                'start_frame': frame_idx,
                                'start_time': frame_idx / fps if fps > 0 else 0,
                                'frame_count': 1,
                                'brightness': avg_b,
                                'std_dev': s_dev
                            }
                    else:
                        if current_bookend is not None:
                            current_bookend['end_frame'] = frame_idx - 1
                            current_bookend['end_time'] = (frame_idx - 1) / fps if fps > 0 else 0
                            current_bookend['frame_count'] = consecutive_white_frames
                            if consecutive_white_frames >= min_white_frames:
                                region_bookends.append(current_bookend)
                            current_bookend = None
                            consecutive_white_frames = 0

                if current_bookend is not None and consecutive_white_frames >= min_white_frames:
                    current_bookend['end_frame'] = end_frame
                    current_bookend['end_time'] = end_frame / fps if fps > 0 else 0
                    current_bookend['frame_count'] = consecutive_white_frames
                    region_bookends.append(current_bookend)

                all_bookends.extend(region_bookends)

            cap.release()

            # Non-mutating deduplication
            bookends = self._deduplicate_bookends(all_bookends)
            bookends = sorted(bookends, key=lambda x: x['start_frame'])

            if len(bookends) < 2 and self.fallback_to_full_video:
                logger.warning("Falling back to using entire video as no bookends were detected")
                bookends = [
                    {
                        'start_frame': 0,
                        'end_frame': min(5, frame_count - 1),
                        'start_time': 0,
                        'end_time': min(5, frame_count - 1) / fps if fps > 0 else 0,
                        'frame_count': min(5, frame_count),
                        'brightness': 0,
                        'std_dev': 0,
                        'is_fallback': True
                    },
                    {
                        'start_frame': max(0, frame_count - 5),
                        'end_frame': frame_count - 1,
                        'start_time': max(0, frame_count - 5) / fps if fps > 0 else 0,
                        'end_time': duration,
                        'frame_count': min(5, frame_count),
                        'brightness': 0,
                        'std_dev': 0,
                        'is_fallback': True
                    }
                ]

            return bookends
        except Exception as e:
            logger.error(f"Error detecting white bookends: {e}")
            logger.error(traceback.format_exc())
            return None


class BookendAlignmentThread(QThread):
    """Thread for bookend video alignment with reliable progress reporting"""
    alignment_progress = pyqtSignal(int)
    progress_updated = alignment_progress
    alignment_complete = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    status_update = pyqtSignal(str)
    status_updated = status_update
    delete_capture_file = pyqtSignal(bool)

    def __init__(self, reference_path=None, captured_path=None, delete_primary=True,
                 options_manager=None, parent=None, ref_path=None, main_path=None, output_path=None):
        super().__init__(parent)
        self.reference_path = reference_path or ref_path
        self.captured_path = captured_path or main_path
        self.output_path = output_path
        self.delete_primary = delete_primary
        self.options_manager = options_manager
        self.aligner = BookendAligner(options_manager=options_manager)
        self._running = True

        logger.info(f"BookendAlignmentThread initialized with delete_primary={delete_primary}")
        logger.info(f"Reference path: {self.reference_path}")
        logger.info(f"Captured path: {self.captured_path}")

        # Connect signals without Qt.DirectConnection to ensure thread safety
        self.aligner.alignment_progress.connect(self.alignment_progress)
        self.aligner.alignment_complete.connect(self.alignment_complete)
        self.aligner.error_occurred.connect(self.error_occurred)
        self.aligner.status_update.connect(self.status_update)

    def __del__(self):
        pass  # dangerous to call self.wait() in destructor

    def run(self):
        """Run alignment in thread"""
        try:
            if not self._running:
                return

            self.status_update.emit("Starting bookend alignment process...")
            self.alignment_progress.emit(0)

            if not os.path.exists(self.reference_path):
                self.error_occurred.emit(f"Reference video not found: {self.reference_path}")
                return

            if not os.path.exists(self.captured_path):
                self.error_occurred.emit(f"Captured video not found: {self.captured_path}")
                return

            original_capture_path = self.captured_path
            
            result = self.aligner.align_bookend_videos(
                self.reference_path,
                self.captured_path,
                self.output_path
            )

            if not self._running:
                return

            if result:
                if self.delete_primary and os.path.exists(original_capture_path):
                    try:
                        time.sleep(0.5)
                        os.remove(original_capture_path)
                        logger.info(f"Successfully deleted original capture file: {original_capture_path}")
                        self.delete_capture_file.emit(True)
                    except Exception as e:
                        logger.error(f"Error deleting original capture file: {e}")
                        self.delete_capture_file.emit(False)
                
                self.alignment_progress.emit(100)
                self.status_update.emit("Bookend alignment complete!")
        except Exception as e:
            if self._running:
                error_msg = f"Error in bookend alignment thread: {str(e)}"
                self.error_occurred.emit(error_msg)
                logger.error(error_msg)
                logger.error(traceback.format_exc())

    def quit(self):
        self._running = False
        super().quit()


class Aligner(QObject):
    alignment_progress = pyqtSignal(int)
    progress_updated = alignment_progress
    alignment_complete = pyqtSignal(object)
    alignment_error = pyqtSignal(str)
    error_occurred = alignment_error
    alignment_state_changed = pyqtSignal(object)
    status_updated = pyqtSignal(str)
    options_manager = None
    alignment_state = None

    def __init__(self):
        super().__init__()
        self.alignment_state = AlignmentState.COMPLETE

    def set_options_manager(self, options_manager):
        self.options_manager = options_manager

    def align_videos_with_bookends(self, reference_path, captured_path):
        """Align videos based on bookend frames"""
        logger.info("Starting bookend alignment process")
        logger.info(f"Reference: {reference_path}")
        logger.info(f"Captured: {captured_path}")

        self.alignment_state = AlignmentState.RUNNING
        self.alignment_state_changed.emit(self.alignment_state)

        thread = BookendAlignmentThread(
            reference_path, captured_path, options_manager=self.options_manager
        )
        thread.alignment_progress.connect(self.alignment_progress)
        thread.alignment_complete.connect(lambda result: self._on_alignment_complete(result))
        thread.error_occurred.connect(self.alignment_error)
        thread.delete_capture_file.connect(self._on_delete_capture_file)
        thread.start()

    def _on_alignment_complete(self, result):
        """Handle alignment completion"""
        self.alignment_state = AlignmentState.COMPLETE
        self.alignment_state_changed.emit(self.alignment_state)
        self.alignment_complete.emit(f"Alignment complete: {result}")

    def _on_delete_capture_file(self, success: bool):
        """Handle deletion notification from BookendAlignmentThread without deleting again."""
        if success:
            logger.info("Original capture file successfully removed by alignment thread.")
            self.status_updated.emit("Capture file deleted.")
        else:
            logger.warning("Capture file deletion was not completed.")