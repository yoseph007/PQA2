import os
import logging
import subprocess

import subprocess
import os
import logging
import cv2
import numpy as np
import time
from datetime import datetime
from PyQt5.QtCore import QObject, pyqtSignal, QThread, Qt
import shutil

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

def repair_video_file(file_path):
    """Attempt to repair a corrupted MP4 file"""
    try:
        logger.info(f"Attempting to repair video file: {file_path}")

        # Create temporary output path
        output_dir = os.path.dirname(file_path)
        temp_path = os.path.join(output_dir, f"temp_fixed_{os.path.basename(file_path)}")

        # Run FFmpeg to copy and potentially fix the file
        cmd = [
            "ffmpeg",
            "-v", "warning",
            "-i", file_path,
            "-c", "copy",
            "-movflags", "faststart",  # This helps with fixing moov atom issues
            "-y",  # Overwrite if file exists
            temp_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        if result.returncode == 0 and os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
            # Replace original with fixed version
            import shutil
            shutil.move(temp_path, file_path)
            logger.info(f"Successfully repaired video file: {file_path}")

            # Validate the repaired file
            if validate_video_file(file_path):
                return True

        # If the standard repair didn't work, try a more aggressive approach
        cmd = [
            "ffmpeg",
            "-v", "warning",
            "-err_detect", "ignore_err",  # More tolerant of errors
            "-i", file_path,
            "-c:v", "libx264",  # Re-encode video
            "-preset", "ultrafast",
            "-crf", "23",
            "-y",
            temp_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        if result.returncode == 0 and os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
            # Replace original with fixed version
            import shutil
            shutil.move(temp_path, file_path)
            logger.info(f"Successfully repaired video file using re-encoding: {file_path}")
            return validate_video_file(file_path)

    except Exception as e:
        logger.error(f"Error repairing video file: {e}")

    return False

# Define maximum repair attempts
MAX_REPAIR_ATTEMPTS = 3



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

def validate_video_file(video_path):
    """
    Validate that a video file is readable and has proper format

    Args:
        video_path: Path to the video file to validate

    Returns:
        bool: True if file is valid, False otherwise
    """
    if not os.path.exists(video_path):
        logger.error(f"Cannot validate nonexistent file: {video_path}")
        return False

    try:
        # Use FFmpeg to probe the file
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-i", video_path,
            "-f", "null", "-"  # Output to null
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.warning(f"Video file validation failed: {video_path}")
            logger.warning(f"FFmpeg error: {result.stderr}")
            return False

        return True
    except Exception as e:
        logger.error(f"Error validating video: {e}")
        return False


logger = logging.getLogger(__name__)

# Maximum retries for processing video files
MAX_REPAIR_ATTEMPTS = 3

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

    def align_bookend_videos(self, reference_path, captured_path):
        """
        Align videos based on white frame bookends that surround the content

        Returns a dictionary with:
        - aligned_reference: Path to trimmed reference video
        - aligned_captured: Path to trimmed captured video
        """
        try:
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
                return None

            # We need at least 2 bookends
            first_bookend = bookend_frames[0]
            last_bookend = bookend_frames[-1]

            logger.info(f"Detected first white bookend at: {first_bookend['start_time']:.3f}s - {first_bookend['end_time']:.3f}s")
            logger.info(f"Detected last white bookend at: {last_bookend['start_time']:.3f}s - {last_bookend['end_time']:.3f}s")

            # The content is between the end of the first bookend and the start of the last bookend
            content_start_time = first_bookend['end_time'] + 0.033  # Add one frame buffer (30fps)
            content_end_time = last_bookend['start_time'] - 0.033  # Subtract one frame buffer

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
                logger.warning(f"Reference duration ({ref_duration:.3f}s) differs from content duration ({content_duration:.3f}s)")
                logger.info("Detected multiple loops in captured video, looking for individual loops")

                # If we have more than 2 bookends, try to find the correct loop
                if len(bookend_frames) > 2:
                    # Try to find consecutive bookends that match the reference duration
                    best_start_idx = 0
                    best_duration_diff = float('inf')

                    for i in range(len(bookend_frames) - 1):
                        start_bookend = bookend_frames[i]
                        end_bookend = bookend_frames[i + 1]

                        loop_start = start_bookend['end_time'] + 0.033
                        loop_end = end_bookend['start_time'] - 0.033
                        loop_duration = loop_end - loop_start

                        duration_diff = abs(loop_duration - ref_duration)

                        logger.info(f"Loop {i+1}: {loop_start:.3f}s - {loop_end:.3f}s = {loop_duration:.3f}s (diff: {duration_diff:.3f}s)")

                        if duration_diff < best_duration_diff:
                            best_duration_diff = duration_diff
                            best_start_idx = i

                    # Use the best matching loop
                    start_bookend = bookend_frames[best_start_idx]
                    end_bookend = bookend_frames[best_start_idx + 1]

                    content_start_time = start_bookend['end_time'] + 0.033
                    content_end_time = end_bookend['start_time'] - 0.033
                    content_duration = content_end_time - content_start_time

                    logger.info(f"Selected loop {best_start_idx+1}: {content_start_time:.3f}s - {content_end_time:.3f}s = {content_duration:.3f}s")
                else:
                    # Just use a single reference duration from the start
                    logger.info(f"Using only first {ref_duration:.3f}s of content")
                    content_duration = ref_duration

            self.alignment_progress.emit(50)
            self.status_update.emit("Creating aligned videos...")

            # Create aligned videos by trimming the content between bookends
            aligned_reference, aligned_captured = self._create_aligned_videos_by_bookends(
                reference_path,
                captured_path,
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
                    'content_duration': content_duration
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

            # Create output paths
            aligned_reference = os.path.join(output_dir, f"{ref_base}_{timestamp}_aligned.mp4")
            aligned_captured = os.path.join(output_dir, f"{cap_base}_{timestamp}_aligned.mp4")

            # Trim reference video - use the whole reference
            ref_cmd = [
                "ffmpeg", "-y", "-i", reference_path,
                "-c:v", "libx264", "-crf", "18", 
                "-preset", "fast", "-c:a", "copy",
                aligned_reference
            ]

            logger.info(f"Creating aligned reference video: {aligned_reference}")
            subprocess.run(ref_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # Trim captured video - extract just the content between bookends
            cap_cmd = [
                "ffmpeg", "-y", "-i", captured_path,
                "-ss", str(content_start_time),
                "-t", str(content_duration),
                "-c:v", "libx264", "-crf", "18",
                "-preset", "fast", "-c:a", "copy",
                aligned_captured
            ]

            logger.info(f"Creating aligned captured video from {content_start_time:.3f}s to {content_start_time + content_duration:.3f}s")
            subprocess.run(cap_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # Verify the files were created
            if not os.path.exists(aligned_reference) or not os.path.exists(aligned_captured):
                logger.error("Failed to create aligned videos")
                return None, None

            # Get info for aligned videos to verify
            ref_aligned_info = self._get_video_info(aligned_reference)
            cap_aligned_info = self._get_video_info(aligned_captured)

            if ref_aligned_info and cap_aligned_info:
                logger.info(f"Created aligned videos: {ref_aligned_info.get('duration'):.2f}s / {cap_aligned_info.get('duration'):.2f}s")
            else:
                logger.warning("Could not verify aligned video info")

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
            sample_points = 30
            sample_interval = max(1, frame_count // sample_points)

            for i in range(0, min(frame_count, sample_points * sample_interval), sample_interval):
                cap.set(cv2.CAP_PROP_POS_FRAMES, i)
                ret, frame = cap.read()
                if ret:
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    brightness = np.mean(gray)
                    std_dev = np.std(gray)
                    brightness_samples.append((i, brightness, std_dev))
                    logger.info(f"Frame {i} (t={i/fps:.2f}s) brightness: {brightness:.1f}, std_dev: {std_dev:.1f}")

            # Calculate stats
            if not brightness_samples:
                logger.error("Could not sample brightness levels from video")
                return None
                
            all_brightness = [b for _, b, _ in brightness_samples]
            all_std_devs = [s for _, _, s in brightness_samples]
            avg_brightness = np.mean(all_brightness)
            std_brightness = np.std(all_brightness)
            max_brightness = np.max(all_brightness)
            avg_std_dev = np.mean(all_std_devs)

            logger.info(f"Video brightness stats: avg={avg_brightness:.1f}, std={std_brightness:.1f}, max={max_brightness:.1f}, avg_std_dev={avg_std_dev:.1f}")

            # Dynamic threshold calculation
            dynamic_threshold = max(
                avg_brightness + 1.5 * std_brightness,
                max_brightness * 0.9,
                120
            )
            
            # Create adaptive thresholds
            thresholds = [
                dynamic_threshold,
                dynamic_threshold * 0.9,
                max(avg_brightness + 15, 110)
            ]
            
            logger.info(f"Using dynamic thresholds: {[round(t, 1) for t in thresholds]}")

            # PERFORMANCE OPTIMIZATION 1: Use two-pass approach
            # First pass: Sample frames at higher intervals to quickly find candidate regions
            # Second pass: Only analyze the candidate regions in detail
            
            # Define regions of interest to examine in detail
            regions_of_interest = []
            
            # Set minimum frame sequence length based on frame rate
            if fps > 25:
                min_white_frames = max(3, int(0.1 * fps))
            else:
                min_white_frames = 3
            
            logger.info(f"Using minimum bookend size of {min_white_frames} frames ({min_white_frames/fps:.3f}s)")
            
            # PERFORMANCE OPTIMIZATION 2: Use a larger sampling interval for initial scan
            initial_sample_rate = max(3, int(fps // 8))  # 8 samples per second
            logger.info(f"Using initial sampling rate of {initial_sample_rate} (about {fps/initial_sample_rate:.1f} samples/second)")
            
            # Std dev threshold based on video characteristics
            std_dev_threshold = min(40, avg_std_dev * 1.5)
            
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
                    if threshold_idx < 2:
                        is_white_frame = avg_brightness > whiteness_threshold
                    else:
                        is_white_frame = (avg_brightness > whiteness_threshold and std_dev < std_dev_threshold)
                    
                    if is_white_frame:
                        if current_region is None:
                            current_region = {
                                'start_frame': max(0, frame_idx - initial_sample_rate),  # Look a bit before
                                'brightness': avg_brightness
                            }
                    else:
                        if current_region is not None:
                            current_region['end_frame'] = min(frame_count - 1, frame_idx + initial_sample_rate)  # Look a bit after
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
            
            # If we didn't find any regions with quick scan, scan the entire video with the most lenient threshold
            if not regions_of_interest:
                logger.info("No potential regions found in quick scan, will scan entire video")
                regions_of_interest = [(0, frame_count - 1, thresholds[-1])]
            
            # PERFORMANCE OPTIMIZATION 3: Merge overlapping regions to avoid duplicate processing
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
                
                # Use standard detection for detailed pass
                cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
                
                # Skip too small regions
                if end_frame - start_frame < min_white_frames:
                    logger.info(f"Region too small, skipping")
                    continue
                    
                consecutive_white_frames = 0
                current_bookend = None
                region_bookends = []
                
                # Process each frame in this region
                for frame_idx in range(start_frame, end_frame + 1):
                    # Skip setting position if we're already there (big performance gain)
                    if frame_idx > start_frame:
                        ret, frame = cap.read()
                    else:
                        ret, frame = cap.isOpened(), cap.read()[1] if cap.isOpened() else (False, None)
                    
                    if not ret:
                        break
                    
                    # Calculate brightness
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    avg_brightness = np.mean(gray)
                    std_dev = np.std(gray)
                    
                    # Determine if white frame
                    is_white_frame = False
                    if avg_brightness > threshold:
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
                if hasattr(self, 'fallback_to_full_video') and self.fallback_to_full_video:
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

    def __init__(self, reference_path, captured_path, delete_primary=False):
        super().__init__()
        self.reference_path = reference_path
        self.captured_path = captured_path
        self.delete_primary = delete_primary
        self.aligner = BookendAligner()
        self._running = True

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

            # Run alignment
            result = self.aligner.align_bookend_videos(
                self.reference_path,
                self.captured_path
            )

            # Check if thread is still running before emitting signals
            if not self._running:
                return

            if result:
                # After successful alignment, we can delete the primary capture file
                if self.delete_primary and os.path.exists(self.captured_path):
                    try:
                        # Signal that we want to delete this file
                        self.delete_capture_file.emit(True)
                        logger.info(f"Primary capture file flagged for deletion: {self.captured_path}")
                    except Exception as e:
                        logger.warning(f"Error marking capture file for deletion: {str(e)}")

                # Ensure progress is set to 100% at completion
                self.alignment_progress.emit(100)
                self.alignment_complete.emit(result)
                self.status_update.emit("Bookend alignment complete!")
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

        # Create bookend aligner
        aligner = BookendAligner()

        # Pass frame sampling rate from options if available
        if hasattr(self, 'options_manager') and self.options_manager:
            try:
                bookend_settings = self.options_manager.get_setting('bookend')
                if isinstance(bookend_settings, dict) and 'frame_sampling_rate' in bookend_settings:
                    frame_sampling_rate = int(bookend_settings.get('frame_sampling_rate', 5))
                    # Ensure value is in valid range
                    frame_sampling_rate = min(30, max(1, frame_sampling_rate))
                    logger.info(f"Using frame sampling rate from options: {frame_sampling_rate}")
                    aligner.frame_sampling_rate = frame_sampling_rate
                else:
                    logger.warning("Frame sampling rate not found in bookend settings, using default (5)")
            except Exception as e:
                logger.error(f"Error getting frame sampling rate from options: {e}")

        # Start alignment thread
        thread = BookendAlignmentThread(reference_path, captured_path)
        thread.alignment_progress.connect(self.alignment_progress)
        thread.alignment_complete.connect(lambda result: self._on_alignment_complete(result))
        thread.error_occurred.connect(self.alignment_error)
        thread.delete_capture_file.connect(self._on_delete_capture_file) # Connect delete signal
        thread.start()

        self.alignment_state = AlignmentState.RUNNING
        self.alignment_state_changed.emit(self.alignment_state)

    def _on_alignment_complete(self, result):
        """Handle alignment completion"""
        self.alignment_state = AlignmentState.COMPLETE
        self.alignment_state_changed.emit(self.alignment_state)
        self.alignment_complete.emit(f"Alignment complete: {result}")

    def _on_delete_capture_file(self, should_delete):
        """Handle deletion of capture file"""
        if should_delete:
            try:
                os.remove(self.captured_path)
                logger.info(f"Successfully deleted capture file: {self.captured_path}")
            except Exception as e:
                logger.error(f"Error deleting capture file: {e}")


# ... rest of the file remains unchanged ...

from enum import Enum
class AlignmentState(Enum):
    COMPLETE = 0
    RUNNING = 1
    ERROR = 2