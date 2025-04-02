import os
import logging
import subprocess
import cv2
import numpy as np
from datetime import datetime
from PyQt5.QtCore import QObject, pyqtSignal, QThread, Qt

logger = logging.getLogger(__name__)

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
            # Get the test directory from captured_path
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
        Enhanced white bookend detection with multiple thresholds and diagnostic output
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
            
            # Try multiple thresholds - from strict to lenient
            thresholds = [230, 200, 180, 160]
            
            # Sample brightness values across the video
            brightness_samples = []
            sample_points = 20
            sample_interval = max(1, frame_count // sample_points)
            
            for i in range(0, min(frame_count, sample_points * sample_interval), sample_interval):
                cap.set(cv2.CAP_PROP_POS_FRAMES, i)
                ret, frame = cap.read()
                if ret:
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    brightness = np.mean(gray)
                    brightness_samples.append((i, brightness))
                    logger.info(f"Frame {i} (t={i/fps:.2f}s) brightness: {brightness:.1f}")
            
            # Calculate stats
            if brightness_samples:
                all_brightness = [b for _, b in brightness_samples]
                avg_brightness = np.mean(all_brightness)
                std_brightness = np.std(all_brightness)
                max_brightness = np.max(all_brightness)
                
                logger.info(f"Video brightness stats: avg={avg_brightness:.1f}, std={std_brightness:.1f}, max={max_brightness:.1f}")
                
                # Adjust thresholds based on video statistics
                if avg_brightness > 200:
                    # Very bright video, increase thresholds
                    thresholds = [240, 230, 220, 210]
                elif avg_brightness > 150:
                    # Bright video
                    thresholds = [230, 210, 190, 170]
                elif avg_brightness < 100:
                    # Dark video, lower thresholds
                    thresholds = [200, 180, 160, 140]
            
            # Try each threshold
            for threshold_idx, whiteness_threshold in enumerate(thresholds):
                logger.info(f"Trying whiteness threshold: {whiteness_threshold}")
                
                # Reset video position
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                
                # Set sampling rate - check more frames for the lower thresholds
                sample_rate = 5 if threshold_idx < 2 else 3
                
                # Minimum frames to consider as bookend
                min_white_frames = max(1, int(0.15 * fps / sample_rate))  # At least 0.15 seconds
                
                consecutive_white_frames = 0
                current_bookend = None
                current_bookends = []
                
                for frame_idx in range(0, frame_count, sample_rate):
                    # Report progress
                    if frame_count > 1000 and frame_idx % 500 == 0:
                        progress = int(30 + (frame_idx / frame_count) * 40)  # Scale to 30-70%
                        self.alignment_progress.emit(progress)
                        
                    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                    ret, frame = cap.read()
                    
                    if not ret:
                        break
                        
                    # Calculate average brightness
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    avg_brightness = np.mean(gray)
                    std_dev = np.std(gray)
                    
                    # More lenient white frame detection for lower thresholds
                    is_white_frame = False
                    if threshold_idx < 2:
                        # Strict detection (high threshold)
                        is_white_frame = avg_brightness > whiteness_threshold
                    else:
                        # Lenient detection (lower threshold but consider uniformity)
                        is_white_frame = (avg_brightness > whiteness_threshold and std_dev < 40)
                    
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
                            
                            # Skip saving frames for diagnostic purposes
                    else:
                        # Check if we just finished a bookend
                        if current_bookend is not None:
                            # Update end time
                            current_bookend['end_frame'] = frame_idx - sample_rate
                            current_bookend['end_time'] = current_bookend['end_frame'] / fps
                            current_bookend['frame_count'] = consecutive_white_frames
                            
                            # Add to bookends if long enough
                            if consecutive_white_frames >= min_white_frames:
                                current_bookends.append(current_bookend)
                                logger.info(f"Detected white bookend: {current_bookend['start_time']:.3f}s - {current_bookend['end_time']:.3f}s " +
                                        f"(brightness: {current_bookend.get('brightness', 0):.1f}, frames: {consecutive_white_frames})")
                                
                            # Reset for next bookend
                            current_bookend = None
                            consecutive_white_frames = 0
                
                # Check if we have an unfinished bookend at the end
                if current_bookend is not None:
                    current_bookend['end_frame'] = frame_count - 1
                    current_bookend['end_time'] = duration
                    current_bookend['frame_count'] = consecutive_white_frames
                    
                    if consecutive_white_frames >= min_white_frames:
                        current_bookends.append(current_bookend)
                        logger.info(f"Detected white bookend at end: {current_bookend['start_time']:.3f}s - {current_bookend['end_time']:.3f}s " +
                                f"(brightness: {current_bookend.get('brightness', 0):.1f}, frames: {consecutive_white_frames})")
                
                # If we found at least 2 bookends, use these results
                if len(current_bookends) >= 2:
                    logger.info(f"Found {len(current_bookends)} white bookend sections with threshold {whiteness_threshold}")
                    bookends = current_bookends
                    break
                    
                logger.warning(f"Found only {len(current_bookends)} white bookend sections with threshold {whiteness_threshold} (need at least 2)")
            
            cap.release()
            
            # Final check and summary
            if len(bookends) < 2:
                logger.warning(f"Failed to detect white bookends with any threshold.")
                logger.warning("Make sure your video has clear white frames at the beginning and end of each loop")
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

    def __init__(self, reference_path, captured_path):
        super().__init__()
        self.reference_path = reference_path
        self.captured_path = captured_path
        self.aligner = BookendAligner()

        # Connect signals with direct connections for responsive UI updates
        self.aligner.alignment_progress.connect(self.alignment_progress, Qt.DirectConnection)
        self.aligner.alignment_complete.connect(self.alignment_complete, Qt.DirectConnection)
        self.aligner.error_occurred.connect(self.error_occurred, Qt.DirectConnection)
        self.aligner.status_update.connect(self.status_update, Qt.DirectConnection)

    def run(self):
        """Run alignment in thread"""
        try:
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

            if result:
                # Ensure progress is set to 100% at completion
                self.alignment_progress.emit(100)
                self.alignment_complete.emit(result)
                self.status_update.emit("Bookend alignment complete!")
            else:
                self.error_occurred.emit("Bookend alignment failed")
        except Exception as e:
            error_msg = f"Error in bookend alignment thread: {str(e)}"
            self.error_occurred.emit(error_msg)
            logger.error(error_msg)
            import traceback
            logger.error(traceback.format_exc())
