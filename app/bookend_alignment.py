import logging
import os
import subprocess
import time
from datetime import datetime

import cv2
import numpy as np
from PyQt5.QtCore import QObject, Qt, QThread, pyqtSignal

logger = logging.getLogger(__name__)

# Define MAX_REPAIR_ATTEMPTS constant
MAX_REPAIR_ATTEMPTS = 3

def validate_video_file(file_path):
    """Validate if a video file is intact and can be read"""
    if not os.path.exists(file_path):
        logger.error(f"File does not exist: {file_path}")
        return False

    if os.path.getsize(file_path) == 0:
        logger.error(f"File is empty: {file_path}")
        return False

    try:
        # Use ffprobe to validate file
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=codec_type",
            "-of", "json",
            file_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        if result.returncode != 0:
            logger.error(f"FFprobe validation failed: {result.stderr}")
            return False

        # Check if we got valid JSON output with a video stream
        import json
        try:
            info = json.loads(result.stdout)
            return 'streams' in info and len(info['streams']) > 0
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON response from FFprobe")
            return False

    except Exception as e:
        logger.error(f"Error validating video file: {e}")
        return False

    return True

def repair_video_file(video_path):
    """
    Repair a video file with missing moov atom by remuxing it with FFmpeg

    Args:
        video_path: Path to the video file that needs repair

    Returns:
        bool: True if repair was successful, False otherwise
    """
    if not os.path.exists(video_path):
        logger.error(f"Cannot repair nonexistent file: {video_path}")
        return False

    try:
        # Create a temporary file name
        temp_path = f"{video_path}.repaired.mp4"
        logger.info(f"Attempting to repair video file: {video_path}")

        # Use FFmpeg to remux the file - this often fixes moov atom issues
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning",
            "-i", video_path, 
            "-c", "copy",  # Copy streams without re-encoding
            "-movflags", "faststart",  # Place moov atom at the beginning
            temp_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"FFmpeg repair failed: {result.stderr}")
            return False

        # Replace the original file with the repaired one
        try:
            # Remove original if repair was successful
            os.remove(video_path)
            os.rename(temp_path, video_path)
            logger.info(f"Successfully repaired video file: {video_path}")
            return True
        except Exception as e:
            logger.error(f"Error replacing original file after repair: {e}")
            return False

    except Exception as e:
        logger.error(f"Error during video repair: {e}")
        return False

class BookendAligner(QObject):
    """
    Class for aligning captured video with reference video using white frame bookends
    """
    alignment_progress = pyqtSignal(int)  # 0-100%
    alignment_complete = pyqtSignal(dict)  # Results including offset
    error_occurred = pyqtSignal(str)
    status_update = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._ffmpeg_path = "ffmpeg"  # Assume ffmpeg is in PATH
        
        # Default values for advanced options
        self.frame_sampling_rate = 5  # Frames to sample per second during detection
        self.adaptive_brightness = True  # Use adaptive brightness threshold
        self.motion_compensation = False  # Apply motion compensation
        self.fallback_to_full_video = True  # Use full video if no bookends detected


















    def set_advanced_options(self, frame_sampling_rate=5, adaptive_brightness=True, 
                        motion_compensation=True, fallback_to_full_video=True):
        """Set advanced options for bookend alignment"""
        # Store the previous settings for logging
        prev_motion_comp = self.motion_compensation
        
        # Update the settings
        self.frame_sampling_rate = frame_sampling_rate
        self.adaptive_brightness = adaptive_brightness
        self.motion_compensation = motion_compensation
        self.fallback_to_full_video = fallback_to_full_video
        
        # Log the change in motion compensation setting
        if prev_motion_comp != motion_compensation:
            logger.info(f"Motion compensation setting changed: {prev_motion_comp} -> {motion_compensation}")
        
        logger.info(f"Set advanced bookend options: sampling_rate={frame_sampling_rate}, "
                f"adaptive_brightness={adaptive_brightness}, "
                f"motion_compensation={motion_compensation}, "
                f"fallback_to_full_video={fallback_to_full_video}")














    def _apply_motion_compensation(self, video_path, start_time, duration):
        """
        Apply motion compensation to the video to improve alignment for fast-moving content
        
        Args:
            video_path: Path to the input video
            start_time: Start time for content section
            duration: Duration of content
            
        Returns:
            Path to motion-compensated video or None if failed
        """
        try:
            # Create output filename with _motion_comp suffix
            output_dir = os.path.dirname(video_path)
            base_name = os.path.splitext(os.path.basename(video_path))[0]
            output_path = os.path.join(output_dir, f"{base_name}_motion_comp.mp4")
            
            # Get input video frame rate
            video_info = self._get_video_info(video_path)
            original_fps = video_info.get('frame_rate', 30)
            
            logger.info(f"Applying motion compensation from {start_time:.3f}s for {duration:.3f}s with fps={original_fps}")
            
            # Create FFmpeg command for motion compensation
            # First extract the section we want to process
            cmd = [
                "ffmpeg", "-hide_banner", "-y",
                "-i", video_path,
                "-ss", str(start_time),
                "-t", str(duration),
                "-vf", f"minterpolate=fps={original_fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1",
                "-c:v", "libx264", "-crf", "18", "-preset", "fast",
                "-r", str(original_fps),  # Ensure output frame rate matches source
                output_path
            ]
            
            # Run the command
            logger.info(f"Running motion compensation: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error(f"Motion compensation failed: {result.stderr}")
                return None
                
            # Verify the output file exists and is valid
            if not os.path.exists(output_path) or not validate_video_file(output_path):
                logger.error("Motion compensation output file is invalid")
                return None
                
            return output_path
            
        except Exception as e:
            logger.error(f"Error applying motion compensation: {e}")
            return None







    def align_bookend_videos(self, reference_path, captured_path):
        """
        Align videos based on white frame bookends that surround the content

        Returns a dictionary with:
        - aligned_reference: Path to trimmed reference video
        - aligned_captured: Path to trimmed captured video
        """
        try:
            # Log the current setting of motion_compensation at the start
            logger.info(f"Starting alignment with motion_compensation={self.motion_compensation}")
            
            self.status_update.emit("Starting white bookend alignment process...")
            logger.info("Starting white bookend alignment process")           
            
            
            
            
            
            
            
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
                if not repair_video_file(captured_path):
                    error_msg = "Failed to repair captured video file"
                    logger.error(error_msg)
                    self.error_occurred.emit(error_msg)
                    return None
                else:
                    self.status_update.emit("Video file repaired successfully")

            # Get video info
            ref_info = self._get_video_info(reference_path)
            cap_info = self._get_video_info(captured_path)

            if not ref_info or not cap_info:
                error_msg = "Failed to get video information"
                logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                return None

            # First find the white bookends in the captured video
            self.status_update.emit("Detecting white bookend frames in captured video...")
            self.alignment_progress.emit(10)

            bookend_frames = self._detect_white_bookends(captured_path)

            if not bookend_frames or len(bookend_frames) < 2:
                error_msg = "Failed to detect at least two white bookend sections"
                logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                
                # If fallback is enabled, use the entire video
                if self.fallback_to_full_video:
                    logger.info("Falling back to using entire captured video as content")
                    self.status_update.emit("No bookends detected. Using entire video instead...")
                    
                    # Create fallback bookends
                    content_start_time = 0.2  # Skip first 0.2 sec to avoid any initial issues
                    content_duration = cap_info.get('duration', 0) - 0.4  # Leave 0.2 sec at the end
                    
                    if content_duration <= 0:
                        error_msg = "Video duration too short for proper alignment"
                        logger.error(error_msg)
                        self.error_occurred.emit(error_msg)
                        return None
                else:
                    return None

            # We need at least 2 bookends
            first_bookend = bookend_frames[0]
            last_bookend = bookend_frames[-1]

            logger.info(f"Detected first white bookend at: {first_bookend['start_time']:.3f}s - {first_bookend['end_time']:.3f}s")
            logger.info(f"Detected last white bookend at: {last_bookend['start_time']:.3f}s - {last_bookend['end_time']:.3f}s")

            # The content is between the end of the first bookend and the start of the last bookend
            # Calculate frame buffer time based on actual frame rate
            frame_buffer_time = 1.5 / cap_info.get('frame_rate', 30)  # Buffer of 1.5 frames
            content_start_time = first_bookend['end_time'] + frame_buffer_time
            content_end_time = last_bookend['start_time'] - frame_buffer_time

            # Make sure we have valid timing
            if content_end_time <= content_start_time:
                error_msg = "Invalid content timing between bookends"
                logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                return None

            content_duration = content_end_time - content_start_time
            logger.info(f"Content duration between bookends: {content_duration:.3f}s")

            # Check if reference video duration is similar
            ref_duration = ref_info.get('duration', 0)

            # Handle multi-loop videos
            if content_duration > ref_duration * 1.5:
                logger.info(f"Reference duration ({ref_duration:.3f}s) - content duration ({content_duration:.3f}s)")
                logger.info("Detected multiple loops in captured video, looking for individual loops")

                # If we have more than 2 bookends, try to find the correct loop
                if len(bookend_frames) > 2:
                    # Try to find consecutive bookends that match the reference duration
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

                    # Use the best matching loop
                    start_bookend = bookend_frames[best_start_idx]
                    end_bookend = bookend_frames[best_start_idx + 1]

                    content_start_time = start_bookend['end_time'] + frame_buffer_time
                    content_end_time = end_bookend['start_time'] - frame_buffer_time
                    content_duration = content_end_time - content_start_time

                    logger.info(f"Selected loop {best_start_idx+1}: {content_start_time:.3f}s - {content_end_time:.3f}s = {content_duration:.3f}s")
                else:
                    # Just use a single reference duration from the start
                    logger.info(f"Using only first {ref_duration:.3f}s of content")
                    content_duration = ref_duration

            self.alignment_progress.emit(50)
            self.status_update.emit("Creating aligned videos...")

            # KEY FIX: Only apply motion compensation if explicitly enabled
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
                    content_duration = self._get_video_info(motion_compensated_path).get('duration', content_duration)
                else:
                    logger.warning("Motion compensation failed, proceeding with original footage")
            else:
                # Explicitly log that we're skipping motion compensation
                logger.info("Motion compensation is DISABLED in settings, skipping...")
            
            # Create aligned videos without motion compensation
            aligned_reference, aligned_captured = self._create_aligned_videos_by_bookends(
                reference_path,
                processed_captured_path,
                content_start_time,
                content_duration
            )

            if not aligned_reference or not aligned_captured:
                error_msg = "Failed to create aligned videos"
                logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                return None

            self.alignment_progress.emit(100)
            self.status_update.emit("White bookend alignment complete!")

            # Prepare result object
            result = {
                'alignment_method': 'bookend',
                'offset_frames': 0,  # Not applicable for bookend method
                'offset_seconds': 0, # Not applicable for bookend method
                'confidence': 0.95,  # High confidence with bookend method
                'aligned_reference': aligned_reference,
                'aligned_captured': aligned_captured,
                'bookend_info': {
                    'first_bookend': first_bookend,
                    'last_bookend': last_bookend,
                    'content_duration': content_duration,
                    'motion_compensated': self.motion_compensation  # Record whether we actually used motion compensation
                }
            }

            self.alignment_complete.emit(result)
            return result

        except Exception as e:
            error_msg = f"Error in bookend alignment: {str(e)}"
            logger.error(error_msg)
            import traceback
            logger.error(traceback.format_exc())
            self.error_occurred.emit(error_msg)
            return None







    def _create_aligned_videos_by_bookends(self, reference_path, captured_path, content_start_time, content_duration):
        """Create aligned videos based on bookend content timing with improved naming"""
        try:
            # Get frame rates and counts to ensure we preserve them
            ref_info = self._get_video_info(reference_path)
            cap_info = self._get_video_info(captured_path)
            ref_fps = ref_info.get('frame_rate', 30)
            cap_fps = cap_info.get('frame_rate', 30)
            ref_frame_count = ref_info.get('frame_count', 0)
            
            logger.info(f"Preserving original frame rates: reference={ref_fps}fps, captured={cap_fps}fps")
            logger.info(f"Reference frame count: {ref_frame_count}")
            
            # IMPORTANT: Include directory handling code
            # First try to get output directory from parent of reference path
            # This ensures results go in test_results, not test_references
            ref_parent_dir = os.path.dirname(os.path.dirname(reference_path))
            if os.path.basename(ref_parent_dir) == "test_references":
                # If reference is in test_references, use test_results instead
                test_results_dir = os.path.join(os.path.dirname(ref_parent_dir), "test_results")
                if os.path.exists(test_results_dir):
                    # Get test name from captured_path directory
                    capture_dir_name = os.path.basename(os.path.dirname(captured_path))
                    # Create matching directory in test_results
                    output_dir = os.path.join(test_results_dir, capture_dir_name)
                    os.makedirs(output_dir, exist_ok=True)
                    logger.info(f"Using test_results directory for aligned output: {output_dir}")
                else:
                    # Fallback to captured path directory
                    output_dir = os.path.dirname(captured_path)
                    logger.warning(f"test_results directory not found, using: {output_dir}")
            else:
                # If not in test_references, use the captured path directory
                output_dir = os.path.dirname(captured_path)

            # Get the timestamp from the directory name if possible
            dir_name = os.path.basename(output_dir)
            timestamp = ""
            if "_" in dir_name:
                parts = dir_name.split("_")
                if len(parts) >= 2 and parts[-1].isdigit():
                    timestamp = parts[-1]
                else:
                    # Use current timestamp if we can't extract it
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            else:
                # Use current timestamp if there's no underscore
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Get base name parts
            ref_base = os.path.splitext(os.path.basename(reference_path))[0]
            cap_base = os.path.splitext(os.path.basename(captured_path))[0]
            
            # Remove any existing "_motion_comp" suffix from captured file base name
            if "_motion_comp" in cap_base:
                cap_base = cap_base.replace("_motion_comp", "")

            # Create output paths
            aligned_reference = os.path.join(output_dir, f"{ref_base}_{timestamp}_aligned.mp4")
            aligned_captured = os.path.join(output_dir, f"{cap_base}_{timestamp}_aligned.mp4")

            # Trim reference video - use the whole reference with high quality settings
            ref_cmd = [
                "ffmpeg", "-y", "-i", reference_path,
                "-r", str(ref_fps),  # Preserve original frame rate
                "-c:v", "libx264", "-crf", "18", 
                "-preset", "fast", "-c:a", "copy",
                aligned_reference
            ]

            logger.info(f"Creating aligned reference video: {aligned_reference}")
            subprocess.run(ref_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # Ensure exact reference frame count for perfect alignment
            ref_aligned_info = self._get_video_info(aligned_reference)
            exact_ref_frames = ref_aligned_info.get('frame_count', ref_frame_count)
            logger.info(f"Exact reference frame count: {exact_ref_frames}")
            
            # Calculate exact duration for frame matching
            frame_duration = exact_ref_frames / ref_fps if ref_fps > 0 else content_duration
            
            # Get frame offset from options manager
            frame_offset = 6  # Default value if not configured
            
            # Check if options_manager is directly available
            if hasattr(self, 'options_manager') and self.options_manager:
                try:
                    frame_offset = self.options_manager.get_setting("bookend", "frame_offset")
                    logger.info(f"Using frame offset from options_manager: {frame_offset}")
                except Exception as e:
                    logger.warning(f"Error getting frame_offset from options_manager: {e}")
            
            # Calculate the offset time based on frame rate
            offset_time = frame_offset / cap_fps
            logger.info(f"Applied frame offset: {frame_offset} frames ({offset_time:.6f}s) at {cap_fps} fps")
            
            # Adjust start time to skip white frames at the beginning
            # The 0.2 second adjustment is to ensure we start after any white frames
            adjusted_start = content_start_time + 0.2
            
            logger.info(f"Adjusting content timing: original={content_start_time:.3f}s, adjusted={adjusted_start:.3f}s")
            logger.info(f"Content duration: {content_duration:.3f}s, frame-based duration: {frame_duration:.3f}s")

            # Trim captured video with precise frame count control
            if adjusted_start > 0 or "motion_comp" not in captured_path:
                cap_cmd = [
                    "ffmpeg", "-y",
                    "-itsoffset", str(offset_time),  # Offset to align with reference
                    "-i", captured_path,
                    "-ss", str(adjusted_start),
                    "-c:v", "libx264", "-crf", "18",
                    "-preset", "fast", 
                    "-r", str(cap_fps),  # Ensure exact frame rate
                    "-frames:v", str(exact_ref_frames),  # Force exact frame count match
                    aligned_captured
                ]
                
                logger.info(f"Creating aligned captured video from {adjusted_start:.3f}s with exact {exact_ref_frames} frames")
            else:
                # Motion compensated clip needs different handling
                cap_cmd = [
                    "ffmpeg", "-y", 
                    "-i", captured_path,
                    "-c:v", "libx264", "-crf", "18",
                    "-preset", "fast",
                    "-r", str(cap_fps),  # Ensure exact frame rate
                    "-frames:v", str(exact_ref_frames),  # Force exact frame count match
                    aligned_captured
                ]
                
                logger.info(f"Using motion-compensated clip with forced {exact_ref_frames} frames")
            
            # Run the alignment command
            subprocess.run(cap_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # Verify aligned videos
            if not os.path.exists(aligned_reference) or not os.path.exists(aligned_captured):
                logger.error("Failed to create aligned videos")
                return None, None

            # Verify frame counts match exactly
            ref_aligned_info = self._get_video_info(aligned_reference)
            cap_aligned_info = self._get_video_info(aligned_captured)

            if ref_aligned_info and cap_aligned_info:
                ref_frames = ref_aligned_info.get('frame_count', 0)
                cap_frames = cap_aligned_info.get('frame_count', 0)
                
                logger.info(f"Final frame counts: reference={ref_frames}, captured={cap_frames}")
                
                if ref_frames != cap_frames:
                    logger.warning(f"Frame count mismatch: reference={ref_frames}, captured={cap_frames}")
                    
                    # If still mismatched, try one more fix to ensure exact frame count
                    if cap_frames != ref_frames:
                        logger.info("Attempting final frame count correction...")
                        
                        # One more try with direct frame extraction
                        final_fix_cmd = [
                            "ffmpeg", "-y",
                            "-i", aligned_captured,
                            "-vf", f"select=1:n={ref_frames}",  # Select exact number of frames
                            "-vsync", "0",  # Do not duplicate/drop frames
                            "-c:v", "libx264", "-crf", "18",
                            "-preset", "fast",
                            f"{aligned_captured}.fixed.mp4"
                        ]
                        
                        try:
                            subprocess.run(final_fix_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                            
                            # If successful, replace the original
                            if os.path.exists(f"{aligned_captured}.fixed.mp4"):
                                os.replace(f"{aligned_captured}.fixed.mp4", aligned_captured)
                                logger.info("Frame count correction applied successfully")
                        except Exception as e:
                            logger.warning(f"Final frame count correction failed: {e}")
            else:
                logger.warning("Could not verify aligned video info")

            # Delete temporary motion-compensated file if it exists
            if "_motion_comp.mp4" in captured_path and os.path.exists(captured_path):
                try:
                    os.remove(captured_path)
                    logger.info(f"Deleted temporary motion-compensated file: {captured_path}")
                except Exception as e:
                    logger.warning(f"Could not delete temporary file: {e}")

            return aligned_reference, aligned_captured

        except Exception as e:
            logger.error(f"Error creating aligned videos by bookends: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None, None
















    def _get_video_info(self, video_path):
        """Get detailed information about a video file using FFprobe"""
        try:
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
                logger.error(f"FFprobe failed: {result.stderr}")
                return None

            # Parse JSON output
            import json
            info = json.loads(result.stdout)

            # Get video stream info
            video_stream = None
            for stream in info.get('streams', []):
                if stream.get('codec_type') == 'video':
                    video_stream = stream
                    break

            if not video_stream:
                logger.error(f"No video stream found in {video_path}")
                return None

            # Extract key information
            format_info = info.get('format', {})
            duration = float(format_info.get('duration', 0))

            # Parse frame rate
            frame_rate_str = video_stream.get('avg_frame_rate', '0/0')
            if '/' in frame_rate_str:
                num, den = map(int, frame_rate_str.split('/'))
                if den == 0:
                    frame_rate = 0
                else:
                    frame_rate = num / den
            else:
                frame_rate = float(frame_rate_str or 0)

            # Get dimensions and frame count
            width = int(video_stream.get('width', 0))
            height = int(video_stream.get('height', 0))
            frame_count = int(video_stream.get('nb_frames', 0))

            # If nb_frames is missing or zero, estimate from duration
            if frame_count == 0 and frame_rate > 0:
                frame_count = int(round(duration * frame_rate))

            # Get pixel format
            pix_fmt = video_stream.get('pix_fmt', 'unknown')

            return {
                'path': video_path,
                'duration': duration,
                'frame_rate': frame_rate,
                'width': width,
                'height': height,
                'frame_count': frame_count,
                'pix_fmt': pix_fmt,
                'total_frames': frame_count
            }

        except Exception as e:
            logger.error(f"Error getting video info for {video_path}: {str(e)}")
            return None 

    def _detect_white_bookends(self, video_path):
        """
        Performance-optimized white bookend detection that maintains accuracy
        while significantly reducing processing time
        """
        try:
            bookends = []
            cap = cv2.VideoCapture(video_path)

            if not cap.isOpened():
                logger.error(f"Could not open video: {video_path}")
                return None

            # Get video properties
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = frame_count / fps if fps > 0 else 0

            logger.info(f"Video details: duration={duration:.2f}s, frames={frame_count}, fps={fps:.2f}")

            # Sample brightness values across the video
            brightness_samples = []
            
            # Use frame_sampling_rate to determine sample interval
            # Higher frame_sampling_rate = more precise detection
            sample_interval = int(fps / self.frame_sampling_rate)
            if sample_interval < 1:
                sample_interval = 1
                
            logger.info(f"Using frame sampling interval of {sample_interval} frames " +
                    f"({self.frame_sampling_rate} samples per second)")
            
            # Sample frames throughout the video for brightness analysis
            sample_frames = []
            for i in range(0, frame_count, sample_interval):
                cap.set(cv2.CAP_PROP_POS_FRAMES, i)
                ret, frame = cap.read()
                if ret:
                    sample_frames.append((i, frame))
            
            # Calculate brightness statistics
            for i, frame in sample_frames:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                brightness = np.mean(gray)
                std_dev = np.std(gray)
                brightness_samples.append((i, brightness, std_dev))
                
            if not brightness_samples:
                logger.error("Could not sample brightness levels from video")
                return None
                
            # Calculate stats for adaptive thresholds
            all_brightness = [b for _, b, _ in brightness_samples]
            all_std_devs = [s for _, _, s in brightness_samples]
            avg_brightness = np.mean(all_brightness)
            std_brightness = np.std(all_brightness)
            max_brightness = np.max(all_brightness)
            avg_std_dev = np.mean(all_std_devs)

            logger.info(f"Video brightness stats: avg={avg_brightness:.1f}, std={std_brightness:.1f}, " +
                    f"max={max_brightness:.1f}, avg_std_dev={avg_std_dev:.1f}")

    
            # Dynamic threshold calculation based on adaptive brightness
            if self.adaptive_brightness:
                # Smarter threshold calculation for varying lighting conditions
                dynamic_threshold = max(
                    avg_brightness + 2.0 * std_brightness,  # Statistical outlier detection
                    max_brightness * 0.85,  # Percentage of maximum
                    180  # Minimum acceptable value for white
                )
                
                # Adjust for very bright or dim videos
                if max_brightness > 240:  # Very bright video
                    dynamic_threshold = max(dynamic_threshold, 220)
                elif max_brightness < 200:  # Dim video
                    dynamic_threshold = max(avg_brightness + 1.5 * std_brightness, 160)
                    
                thresholds = [
                    dynamic_threshold,
                    dynamic_threshold * 0.9,  # First fallback
                    max(avg_brightness + 20, 160)  # Second fallback
                ]
            else:
                # Use white threshold value from settings
                white_threshold = 230  # Default value if not set
                
                # If options_manager is available, get the configured white threshold
                if hasattr(self, 'options_manager') and self.options_manager:
                    try:
                        white_threshold = self.options_manager.get_setting("bookend", "white_threshold")
                        logger.info(f"Using configured white threshold: {white_threshold}")
                    except Exception as e:
                        logger.warning(f"Error getting white threshold from options: {e}")
                
                # Use the white threshold as fixed threshold with fallbacks
                fixed_threshold = white_threshold
                thresholds = [fixed_threshold, fixed_threshold * 0.9, fixed_threshold * 0.8]










            
            logger.info(f"Using brightness thresholds: {[round(t, 1) for t in thresholds]}")
            
            # Quick scan to identify potential bookend regions
            regions_of_interest = []
            
            # Define minimum white frame sequence based on frame rate
            if fps > 25:
                min_white_frames = max(3, int(0.1 * fps))
            else:
                min_white_frames = 3
                
            logger.info(f"Using minimum bookend size of {min_white_frames} frames ({min_white_frames/fps:.3f}s)")
            
            # Use a larger sampling interval for initial scan
            initial_sample_rate = max(3, int(fps // 8))
            
            # Std dev threshold based on video characteristics
            std_dev_threshold = min(45, avg_std_dev * 1.8)
            
            # First pass: Quick scan to find potential bookend regions
            for threshold_idx, whiteness_threshold in enumerate(thresholds):
                logger.info(f"Quick scan with threshold: {whiteness_threshold:.1f}")
                
                # Reset video position
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                
                potential_regions = []
                current_region = None
                
                # Process frames at the initial sampling rate
                for frame_idx in range(0, frame_count, initial_sample_rate):
                    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                    ret, frame = cap.read()
                    
                    if not ret:
                        break
                    
                    # Calculate brightness
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    avg_brightness = np.mean(gray)
                    std_dev = np.std(gray)
                    
                    # Determine if this is a candidate white frame
                    is_white_frame = False
                    
                    # Adaptive criteria for white frame detection
                    if threshold_idx < 2:
                        is_white_frame = avg_brightness > whiteness_threshold
                    else:
                        is_white_frame = (avg_brightness > whiteness_threshold and std_dev < std_dev_threshold)
                    
                    if is_white_frame:
                        if current_region is None:
                            current_region = {
                                'start_frame': max(0, frame_idx - initial_sample_rate),
                                'brightness': avg_brightness
                            }
                    else:
                        if current_region is not None:
                            current_region['end_frame'] = min(frame_count - 1, frame_idx + initial_sample_rate)
                            potential_regions.append(current_region)
                            current_region = None
                
                # Handle last region if exists
                if current_region is not None:
                    current_region['end_frame'] = min(frame_count - 1, frame_idx + initial_sample_rate)
                    potential_regions.append(current_region)
                
                # If we found potential regions, add them to our analysis list
                if potential_regions:
                    logger.info(f"Found {len(potential_regions)} potential bookend regions with threshold {whiteness_threshold:.1f}")
                    for region in potential_regions:
                        # Expand region slightly to ensure we don't miss any frames
                        padding = initial_sample_rate
                        start = max(0, region['start_frame'] - padding)
                        end = min(frame_count - 1, region['end_frame'] + padding)
                        regions_of_interest.append((start, end, whiteness_threshold))
            
            # If no regions found, scan the entire video with the most lenient threshold
            if not regions_of_interest:
                logger.info("No potential regions found in quick scan, will scan entire video")
                regions_of_interest = [(0, frame_count - 1, thresholds[-1])]
            
            # Merge overlapping regions to avoid duplicate processing
            if len(regions_of_interest) > 1:
                regions_of_interest.sort()  # Sort by start frame
                merged_regions = []
                current_start, current_end, current_threshold = regions_of_interest[0]
                
                for start, end, threshold in regions_of_interest[1:]:
                    if start <= current_end:  # Regions overlap
                        current_end = max(current_end, end)
                        current_threshold = min(current_threshold, threshold)  # Use the more lenient threshold
                    else:
                        merged_regions.append((current_start, current_end, current_threshold))
                        current_start, current_end, current_threshold = start, end, threshold
                
                merged_regions.append((current_start, current_end, current_threshold))
                regions_of_interest = merged_regions
                
                logger.info(f"Merged into {len(regions_of_interest)} regions for detailed analysis")
            
            # Second pass: Detailed analysis of potential regions
            logger.info("Starting detailed analysis of potential bookend regions")
            
            all_bookends = []
            
            for region_idx, (start_frame, end_frame, threshold) in enumerate(regions_of_interest):
                logger.info(f"Analyzing region {region_idx+1}/{len(regions_of_interest)}: frames {start_frame}-{end_frame}")
                
                # Skip too small regions
                if end_frame - start_frame < min_white_frames:
                    logger.info(f"Region too small, skipping")
                    continue
                    
                consecutive_white_frames = 0
                current_bookend = None
                region_bookends = []
                
                # Process each frame in this region
                cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
                
                for frame_idx in range(start_frame, end_frame + 1):
                    if frame_idx > start_frame:
                        ret, frame = cap.read()
                    else:
                        ret = cap.isOpened()
                        if ret:
                            ret, frame = cap.read()
                    
                    if not ret:
                        break
                    
                    # Calculate brightness
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    avg_brightness = np.mean(gray)
                    std_dev = np.std(gray)
                    
                    # Enhanced white frame detection logic for fast-moving content
                    is_white_frame = False
                    
                    # For high-speed content, we need to be more flexible with white detection
                    if std_dev < std_dev_threshold * 1.2:
                        # Low std dev means more uniform frame - good for white detection
                        if avg_brightness > threshold * 0.95:
                            is_white_frame = True
                    else:
                        # Higher std dev might mean partial white frame or motion blur
                        # Check if a significant portion is white
                        if avg_brightness > threshold:
                            is_white_frame = True
                        elif avg_brightness > threshold * 0.9:
                            # Check for large white areas (could be partial white frame)
                            white_pixels = np.sum(gray > threshold)
                            white_ratio = white_pixels / gray.size
                            if white_ratio > 0.7:  # If >70% of pixels are above threshold
                                is_white_frame = True
                    
                    if is_white_frame:
                        consecutive_white_frames += 1
                        
                        # Start a new bookend if needed
                        if current_bookend is None:
                            frame_time = frame_idx / fps
                            current_bookend = {
                                'start_frame': frame_idx,
                                'start_time': frame_time,
                                'frame_count': 1,
                                'brightness': avg_brightness,
                                'std_dev': std_dev
                            }
                    else:
                        # Check if we just finished a bookend
                        if current_bookend is not None:
                            # Update end time
                            current_bookend['end_frame'] = frame_idx - 1
                            current_bookend['end_time'] = current_bookend['end_frame'] / fps
                            current_bookend['frame_count'] = consecutive_white_frames
                            
                            # Add to bookends if long enough
                            if consecutive_white_frames >= min_white_frames:
                                region_bookends.append(current_bookend)
                                logger.info(f"Detected white bookend: {current_bookend['start_time']:.3f}s - {current_bookend['end_time']:.3f}s " +
                                        f"(brightness: {current_bookend.get('brightness', 0):.1f}, frames: {consecutive_white_frames})")
                            
                            # Reset for next bookend
                            current_bookend = None
                            consecutive_white_frames = 0
                
                # Check for unfinished bookend
                if current_bookend is not None and consecutive_white_frames >= min_white_frames:
                    current_bookend['end_frame'] = end_frame
                    current_bookend['end_time'] = end_frame / fps
                    current_bookend['frame_count'] = consecutive_white_frames
                    region_bookends.append(current_bookend)
                    logger.info(f"Detected white bookend at region end: {current_bookend['start_time']:.3f}s - {current_bookend['end_time']:.3f}s " +
                            f"(brightness: {current_bookend.get('brightness', 0):.1f}, frames: {consecutive_white_frames})")
                
                # Add all bookends from this region
                all_bookends.extend(region_bookends)
            
            # Remove duplicate bookends (can happen with overlapping regions)
            if all_bookends:
                unique_bookends = []
                for bookend in all_bookends:                            
                    
                    
                    
                    # Check if this bookend overlaps with any existing ones
                    is_duplicate = False
                    for existing in unique_bookends:
                        # If frames overlap significantly, consider it a duplicate
                        if (bookend['start_frame'] <= existing['end_frame'] and 
                            bookend['end_frame'] >= existing['start_frame']):
                            # Keep the larger/brighter one
                            if bookend['frame_count'] > existing['frame_count'] or bookend['brightness'] > existing['brightness']:
                                # Replace existing with this one
                                unique_bookends.remove(existing)
                                unique_bookends.append(bookend)
                            is_duplicate = True
                            break
                    
                    if not is_duplicate:
                        unique_bookends.append(bookend)
                
                # Sort bookends by start time
                bookends = sorted(unique_bookends, key=lambda x: x['start_frame'])
                logger.info(f"Found {len(bookends)} unique bookends after deduplication")
            
            cap.release()
            
            # Final check and summary
            if len(bookends) < 2:
                logger.warning(f"Failed to detect at least two white bookends")
                
                # Last resort: use the beginning and end of the video
                if self.fallback_to_full_video:
                    logger.warning("Falling back to using entire video as no bookends were detected")
                    bookends = [
                        {
                            'start_frame': 0,
                            'end_frame': min(5, frame_count - 1),
                            'start_time': 0,
                            'end_time': min(5, frame_count - 1) / fps,
                            'frame_count': min(5, frame_count),
                            'brightness': 0,
                            'std_dev': 0,
                            'is_fallback': True
                        },
                        {
                            'start_frame': max(0, frame_count - 5),
                            'end_frame': frame_count - 1,
                            'start_time': max(0, frame_count - 5) / fps,
                            'end_time': duration,
                            'frame_count': min(5, frame_count),
                            'brightness': 0,
                            'std_dev': 0,
                            'is_fallback': True
                        }
                    ]
                    logger.warning("Created fallback bookends at beginning and end of video")
            else:
                logger.info(f"Successfully detected {len(bookends)} white bookend sections")
                
            return bookends

        except Exception as e:
            logger.error(f"Error detecting white bookends: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None


class BookendAlignmentThread(QThread):
    """Thread for bookend video alignment with reliable progress reporting"""
    alignment_progress = pyqtSignal(int)
    alignment_complete = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    status_update = pyqtSignal(str)
    delete_capture_file = pyqtSignal(bool)  # Signal to indicate if primary capture file should be deleted

    def __init__(self, reference_path, captured_path, delete_primary=True, options_manager=None):
        super().__init__()
        self.reference_path = reference_path
        self.captured_path = captured_path
        self.delete_primary = delete_primary  # Default to True to delete original capture file
        self.options_manager = options_manager
        self.aligner = BookendAligner()
        self._running = True
        
        # Log the delete_primary setting
        logger.info(f"BookendAlignmentThread initialized with delete_primary={delete_primary}")
        logger.info(f"Reference path: {reference_path}")
        logger.info(f"Captured path: {captured_path}")

        # Initialize advanced options from options_manager if provided
        if options_manager:
            try:
                # DEBUGGING: Add logging of the entire options dictionary
                all_settings = options_manager.get_settings()
                logger.info(f"All settings from options_manager: {all_settings}")
                
                # Get the specific bookend settings
                bookend_settings = options_manager.get_setting('bookend')
                logger.info(f"Raw bookend settings from options_manager: {bookend_settings}")
                
                if isinstance(bookend_settings, dict):
                    # Extract settings with more explicit error checking
                    frame_sampling_rate = bookend_settings.get('frame_sampling_rate', 5)
                    adaptive_brightness = bookend_settings.get('adaptive_brightness', True)
                    
                    # IMPORTANT: Force log the motion compensation setting to diagnose
                    motion_comp_setting = bookend_settings.get('motion_compensation', False)  # Default to False if not found
                    logger.info(f"Motion compensation setting from options_manager: {motion_comp_setting}")
                    
                    fallback_to_full_video = bookend_settings.get('fallback_to_full_video', True)
                    
                    # Apply the settings to the aligner
                    self.aligner.set_advanced_options(
                        frame_sampling_rate=frame_sampling_rate,
                        adaptive_brightness=adaptive_brightness,
                        motion_compensation=motion_comp_setting,  # Use the explicit variable
                        fallback_to_full_video=fallback_to_full_video
                    )
                    
                    # Double-check that settings were applied correctly
                    logger.info(f"Aligner motion_compensation after setting: {self.aligner.motion_compensation}")
                    
                    logger.info(f"Applied bookend settings from options_manager: " +
                            f"frame_sampling_rate={frame_sampling_rate}, " +
                            f"adaptive_brightness={adaptive_brightness}, " +
                            f"motion_compensation={motion_comp_setting}, " + 
                            f"fallback_to_full_video={fallback_to_full_video}")
            except Exception as e:
                logger.error(f"Error loading bookend options: {e}")
                import traceback
                logger.error(traceback.format_exc())
                
                # Set default values explicitly if there's an error
                self.aligner.set_advanced_options(
                    frame_sampling_rate=5,
                    adaptive_brightness=True,
                    motion_compensation=False,  # Default to FALSE for motion compensation
                    fallback_to_full_video=True
                )

        # Connect signals with direct connections for responsive UI updates
        self.aligner.alignment_progress.connect(self.alignment_progress, Qt.DirectConnection)
        self.aligner.alignment_complete.connect(self.alignment_complete, Qt.DirectConnection)
        self.aligner.error_occurred.connect(self.error_occurred, Qt.DirectConnection)
        self.aligner.status_update.connect(self.status_update, Qt.DirectConnection)               
                
                
                
                
                
                
                
                
                
                
                
                
                

    def __del__(self):
        """Clean up resources when thread is destroyed"""
        self.wait()  # Wait for thread to finish before destroying

    def run(self):
        """Run alignment in thread"""
        try:
            if not self._running:
                return

            self.status_update.emit("Starting bookend alignment process...")

            # Report initial progress
            self.alignment_progress.emit(0)

            # Verify input files
            if not os.path.exists(self.reference_path):
                self.error_occurred.emit(f"Reference video not found: {self.reference_path}")
                return

            if not os.path.exists(self.captured_path):
                self.error_occurred.emit(f"Captured video not found: {self.captured_path}")
                return

            # Store the original capture path before alignment
            original_capture_path = self.captured_path
            
            # Run alignment
            result = self.aligner.align_bookend_videos(
                self.reference_path,
                self.captured_path
            )

            # Check if thread is still running before emitting signals
            if not self._running:
                return

            if result:
                # After successful alignment, delete the primary capture file
                # Use the stored original path to ensure we're deleting the right file
                if self.delete_primary and os.path.exists(original_capture_path):
                    try:
                        # Add a small delay to ensure file is not still in use
                        time.sleep(1)
                        
                        # Directly delete the file here
                        os.remove(original_capture_path)
                        logger.info(f"Successfully deleted original capture file: {original_capture_path}")
                        
                        # Also signal that we deleted this file (for backward compatibility)
                        self.delete_capture_file.emit(True)
                    except Exception as e:
                        # Log detailed error for debugging
                        logger.error(f"Error deleting original capture file: {str(e)}")
                        import traceback
                        logger.error(traceback.format_exc())
                        
                        # Signal that deletion failed
                        self.delete_capture_file.emit(False)
                else:
                    logger.warning(f"Not deleting capture file. delete_primary={self.delete_primary}, file exists={os.path.exists(original_capture_path)}")

                # Ensure progress is set to 100% at completion
                self.alignment_progress.emit(100)
                
                self.status_update.emit("Bookend alignment complete! Original capture file deleted.")
            else:
                self.error_occurred.emit("Bookend alignment failed")
        except Exception as e:
            if self._running:  # Only emit errors if thread is still running
                error_msg = f"Error in bookend alignment thread: {str(e)}"
                self.error_occurred.emit(error_msg)
                logger.error(error_msg)
                import traceback
                logger.error(traceback.format_exc())

    def quit(self):
        """Override quit to properly clean up resources"""
        self._running = False
        super().quit()

class Aligner(QObject):
    alignment_progress = pyqtSignal(int)
    alignment_complete = pyqtSignal(str)
    alignment_error = pyqtSignal(str)
    alignment_state_changed = pyqtSignal(int)
    options_manager = None
    alignment_state = None

    def __init__(self):
        super().__init__()
        self.alignment_state = AlignmentState.COMPLETE

    def set_options_manager(self, options_manager):
        self.options_manager = options_manager




    def align_videos_with_bookends(self, reference_path, captured_path):
        """Align videos based on bookend frames"""
        logger.info(f"Starting bookend alignment process")
        logger.info(f"Reference: {reference_path}")
        logger.info(f"Captured: {captured_path}")

        self.alignment_state = AlignmentState.RUNNING
        self.alignment_state_changed.emit(self.alignment_state)

        # Debug log to show options_manager settings
        if self.options_manager:
            try:
                bookend_settings = self.options_manager.get_setting('bookend')
                logger.info(f"Bookend settings from options_manager before thread creation: {bookend_settings}")
                
                # Specific debug for motion compensation
                motion_comp_setting = False
                if isinstance(bookend_settings, dict):
                    motion_comp_setting = bookend_settings.get('motion_compensation', False)
                logger.info(f"Motion compensation setting to be passed to thread: {motion_comp_setting}")
            except Exception as e:
                logger.error(f"Error accessing bookend settings: {e}")

        # Start alignment thread with options manager
        thread = BookendAlignmentThread(reference_path, captured_path, options_manager=self.options_manager)
        thread.alignment_progress.connect(self.alignment_progress)
        thread.alignment_complete.connect(lambda result: self._on_alignment_complete(result))
        thread.error_occurred.connect(self.alignment_error)
        thread.delete_capture_file.connect(self._on_delete_capture_file)
        thread.start()

        self.alignment_state = AlignmentState.RUNNING
        self.alignment_state_changed.emit(self.alignment_state)




    def _on_alignment_complete(self, result):
        """Handle alignment completion"""
        self.alignment_state = AlignmentState.COMPLETE
        self.alignment_state_changed.emit(self.alignment_state)
        self.alignment_complete.emit(f"Alignment complete: {result}")

    def _on_delete_capture_file(self, should_delete):
        """Handle deletion of capture file (if not already deleted in the thread)"""
        if should_delete and hasattr(self, 'captured_path'):
            try:
                if os.path.exists(self.captured_path):
                    os.remove(self.captured_path)
                    logger.info(f"Successfully deleted capture file: {self.captured_path}")
                else:
                    logger.info(f"Capture file already deleted: {self.captured_path}")
            except Exception as e:
                logger.error(f"Error deleting capture file: {e}")


from enum import Enum

class AlignmentState(Enum):
    COMPLETE = 0
    RUNNING = 1
    ERROR = 2