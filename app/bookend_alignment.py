import os
import logging
import subprocess
import cv2
import numpy as np
import time
from datetime import datetime
from PyQt5.QtCore import QObject, pyqtSignal, QThread, Qt

logger = logging.getLogger(__name__)

# Set up default logger if not configured elsewhere
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

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
            self.status_update.emit(f"Starting white bookend alignment process...")
            logger.info(f"Starting white bookend alignment process")
            
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
            
            # Allow a small margin of error
            if abs(ref_duration - content_duration) > 0.5:  # More than half a second difference
                logger.warning(f"Reference duration ({ref_duration:.3f}s) differs from content duration ({content_duration:.3f}s)")
                # Continue anyway, but log warning
                
            self.alignment_progress.emit(50)
            self.status_update.emit(f"Creating aligned videos...")
                
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
  
  
  
def _detect_white_bookends(self, video_path):
    """
    Detect white frame bookend sections in video
    IMPROVED: More reliable detection with adaptive thresholds
    
    Returns list of bookend dictionaries with start/end times
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
        
        # IMPROVED: Adaptive sampling rate based on video length
        # Sample more frequently for better detection in shorter videos
        if frame_count < 1000:
            sample_rate = 2  # Check every 2 frames for short videos
        elif frame_count < 3000:
            sample_rate = 3  # Check every 3 frames for medium videos
        else:
            sample_rate = 5  # Check every 5 frames for long videos
        
        # IMPROVED: Dynamic min_white_frames based on frame rate
        # At least 0.2 seconds but minimum of 3 frames
        min_white_frames = max(3, int(0.2 * fps / sample_rate))
        
        # IMPROVED: Try multiple whiteness thresholds if needed
        # Start with a high threshold, then try lower ones if detection fails
        whiteness_thresholds = [225, 210, 195]  # Try progressively lower thresholds
        
        logger.info(f"Scanning for white bookends in {video_path}")
        logger.info(f"Frame count: {frame_count}, Duration: {duration:.2f}s, FPS: {fps:.2f}")
        logger.info(f"Using sample rate: {sample_rate}, min white frames: {min_white_frames}")
        
        # Try each threshold until we find at least 2 bookends
        for threshold_idx, whiteness_threshold in enumerate(whiteness_thresholds):
            logger.info(f"Trying whiteness threshold: {whiteness_threshold}")
            bookends = []
            
            # Counters for white frame detection
            consecutive_white_frames = 0
            
            # Current bookend being built
            current_bookend = None
            
            # First quick scan to find brightness statistics
            brightness_samples = []
            for quick_idx in range(0, min(frame_count, 500), 20):  # Sample up to 25 frames
                cap.set(cv2.CAP_PROP_POS_FRAMES, quick_idx)
                ret, frame = cap.read()
                if ret:
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    brightness_samples.append(np.mean(gray))
            
            # IMPROVED: Adaptive threshold based on video brightness
            if brightness_samples:
                median_brightness = np.median(brightness_samples)
                # If video is generally very bright, increase threshold
                if median_brightness > 200:
                    adaptive_threshold = whiteness_threshold + 10
                # If video is generally dark, decrease threshold slightly
                elif median_brightness < 100:
                    adaptive_threshold = whiteness_threshold - 10
                else:
                    adaptive_threshold = whiteness_threshold
                
                logger.info(f"Median brightness: {median_brightness:.1f}, Adaptive threshold: {adaptive_threshold}")
            else:
                adaptive_threshold = whiteness_threshold
            
            # Reset to beginning for full scan
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            
            # Main scan for white frames
            for frame_idx in range(0, frame_count, sample_rate):
                # Report progress periodically
                if frame_count > 1000 and frame_idx % 500 == 0:
                    progress = int(30 + (frame_idx / frame_count) * 40)  # Scale to 30-70%
                    self.alignment_progress.emit(progress)
                    logger.debug(f"Scanning frame {frame_idx}/{frame_count} ({progress}%)")
                    
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame = cap.read()
                
                if not ret:
                    break
                    
                # Calculate average brightness
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                avg_brightness = np.mean(gray)
                
                # IMPROVED: Also check standard deviation - white frames have low std dev
                std_dev = np.std(gray)
                
                # IMPROVED: More sophisticated white frame detection
                # Consider both brightness and uniformity (low std dev)
                is_white_frame = (avg_brightness > adaptive_threshold and std_dev < 25)
                
                if is_white_frame:
                    consecutive_white_frames += 1
                    
                    # Start a new bookend if needed
                    if current_bookend is None:
                        frame_time = frame_idx / fps
                        current_bookend = {
                            'start_frame': frame_idx,
                            'start_time': frame_time,
                            'frame_count': 1,
                            'avg_brightness': avg_brightness,
                            'std_dev': std_dev
                        }
                else:
                    # Check if we just finished a bookend
                    if current_bookend is not None:
                        # Update end time
                        current_bookend['end_frame'] = frame_idx - sample_rate
                        current_bookend['end_time'] = current_bookend['end_frame'] / fps
                        current_bookend['frame_count'] = consecutive_white_frames
                        
                        # Add to bookends if long enough
                        if consecutive_white_frames >= min_white_frames:
                            bookends.append(current_bookend)
                            logger.info(f"Detected white bookend: {current_bookend['start_time']:.3f}s - {current_bookend['end_time']:.3f}s " +
                                      f"(brightness: {current_bookend.get('avg_brightness', 0):.1f}, stddev: {current_bookend.get('std_dev', 0):.1f})")
                            
                        # Reset for next bookend
                        current_bookend = None
                        consecutive_white_frames = 0
            
            # Check if we have an unfinished bookend at the end
            if current_bookend is not None:
                current_bookend['end_frame'] = frame_count - 1
                current_bookend['end_time'] = duration
                current_bookend['frame_count'] = consecutive_white_frames
                
                if consecutive_white_frames >= min_white_frames:
                    bookends.append(current_bookend)
                    logger.info(f"Detected white bookend at end: {current_bookend['start_time']:.3f}s - {current_bookend['end_time']:.3f}s " +
                              f"(brightness: {current_bookend.get('avg_brightness', 0):.1f}, stddev: {current_bookend.get('std_dev', 0):.1f})")
            
            # If we found at least 2 bookends, we're done
            if len(bookends) >= 2:
                logger.info(f"Found {len(bookends)} white bookend sections with threshold {adaptive_threshold}")
                break
                
            logger.warning(f"Found only {len(bookends)} white bookend sections with threshold {adaptive_threshold} (need at least 2)")
            # Continue to next threshold if we didn't find enough bookends
        
        cap.release()
        
        # IMPROVED: If we still don't have enough bookends, try a more aggressive approach
        if len(bookends) < 2:
            logger.warning("Insufficient bookends found with standard detection. Trying frame-by-frame scan...")
            bookends = self._detect_white_bookends_aggressive(video_path)
            
        if len(bookends) < 2:
            logger.warning(f"Still only found {len(bookends)} white bookend sections after aggressive scan (need at least 2)")
        
        return bookends
        
    except Exception as e:
        logger.error(f"Error detecting white bookends: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return None

    def _detect_white_bookends_aggressive(self, video_path):
        """
        More aggressive scan for white bookends when standard detection fails
        Scans the entire video with minimal sampling
        """
        try:
            logger.info("Starting aggressive white bookend detection")
            self.status_update.emit("Performing detailed scan for white frames...")
            
            bookends = []
            cap = cv2.VideoCapture(video_path)
            
            if not cap.isOpened():
                return None
                
            # Get video properties
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            # Use a more frequent sampling rate
            sample_rate = 1  # Check every frame
            
            # Use a lower whiteness threshold
            whiteness_threshold = 180  # Lower threshold
            
            # Shorter minimum for white bookends - just 2 frames
            min_white_frames = 2
            
            # Counters for white frame detection
            consecutive_white_frames = 0
            current_bookend = None
            
            # Scan entire video
            for frame_idx in range(0, frame_count, sample_rate):
                # Report progress
                if frame_idx % 100 == 0:
                    progress = int(70 + (frame_idx / frame_count) * 20)  # Scale to 70-90%
                    self.alignment_progress.emit(progress)
                    
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame = cap.read()
                
                if not ret:
                    break
                    
                # Calculate brightness and uniformity
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                avg_brightness = np.mean(gray)
                std_dev = np.std(gray)
                
                # More lenient white frame detection
                is_white_frame = (avg_brightness > whiteness_threshold and std_dev < 40)
                
                if is_white_frame:
                    consecutive_white_frames += 1
                    
                    # Start a new bookend if needed
                    if current_bookend is None:
                        frame_time = frame_idx / fps
                        current_bookend = {
                            'start_frame': frame_idx,
                            'start_time': frame_time,
                            'frame_count': 1
                        }
                else:
                    # Check if we just finished a bookend
                    if current_bookend is not None:
                        # Update end time
                        current_bookend['end_frame'] = frame_idx - sample_rate
                        current_bookend['end_time'] = current_bookend['end_frame'] / fps
                        current_bookend['frame_count'] = consecutive_white_frames
                        
                        # Add to bookends if long enough
                        if consecutive_white_frames >= min_white_frames:
                            bookends.append(current_bookend)
                            logger.info(f"Aggressive scan: Detected white bookend at {current_bookend['start_time']:.3f}s - {current_bookend['end_time']:.3f}s")
                            
                        # Reset for next bookend
                        current_bookend = None
                        consecutive_white_frames = 0
            
            # Check if we have an unfinished bookend at the end
            if current_bookend is not None and consecutive_white_frames >= min_white_frames:
                current_bookend['end_frame'] = frame_count - 1
                current_bookend['end_time'] = frame_count / fps
                current_bookend['frame_count'] = consecutive_white_frames
                bookends.append(current_bookend)
                logger.info(f"Aggressive scan: Detected white bookend at end: {current_bookend['start_time']:.3f}s - {current_bookend['end_time']:.3f}s")
            
            cap.release()
            
            logger.info(f"Aggressive scan completed, found {len(bookends)} white bookend sections")
            return bookends
            
        except Exception as e:
            logger.error(f"Error in aggressive white bookend detection: {str(e)}")
            return []
    
  
  
            
    def _create_aligned_videos_by_bookends(self, reference_path, captured_path, content_start_time, content_duration):
        """Create aligned videos based on bookend content timing"""
        try:
            # Create output paths
            aligned_reference = os.path.splitext(reference_path)[0] + "_aligned.mp4"
            aligned_captured = os.path.splitext(captured_path)[0] + "_aligned.mp4"
            
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

        except Exception as e:
            error_msg = f"Error in bookend alignment thread: {str(e)}"
            self.error_occurred.emit(error_msg)
            logger.error(error_msg)
            import traceback
            logger.error(traceback.format_exc())
            return
