import os
import logging
import subprocess
import json
import re
import time
from datetime import datetime
import cv2
import numpy as np
from PyQt5.QtCore import QObject, pyqtSignal, QThread, Qt

logger = logging.getLogger(__name__)

class VideoAligner(QObject):
    """Class for aligning captured video with reference video"""
    alignment_progress = pyqtSignal(int)  # 0-100%
    alignment_complete = pyqtSignal(dict)  # Results including offset
    error_occurred = pyqtSignal(str)
    status_update = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._ffmpeg_path = "ffmpeg"  # Assume ffmpeg is in PATH

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

    def _stabilize_video(self, input_path):
        """Apply vid.stab stabilization"""
        try:
            output_path = os.path.splitext(input_path)[0] + "_stab.mp4"
            # Analysis pass
            subprocess.run([
                "ffmpeg", "-y", "-i", input_path,
                "-vf", "vidstabdetect=result=transforms.trf",
                "-f", "null", "-"
            ], check=True)

            # Application pass
            subprocess.run([
                "ffmpeg", "-y", "-i", input_path,
                "-vf", "vidstabtransform=input=transforms.trf:zoom=0:smoothing=10",
                "-c:v", "libx264", output_path
            ], check=True)
            return output_path
        except Exception as e:
            logger.error(f"Stabilization failed: {str(e)}")
            return input_path

    def _add_timestamps_to_video(self, input_path, output_path):
        """Add high-precision timestamps to video using FFmpeg"""
        try:
            cmd = [
                "ffmpeg", "-y",
                "-i", input_path,
                "-vf", "drawtext=text='%{pts\\:hms\\:6}':x=10:y=50:fontsize=48:fontcolor=white:box=1:boxcolor=black",
                "-c:a", "copy",
                output_path
            ]
            subprocess.run(cmd, check=True)
            return output_path
        except Exception as e:
            logger.error(f"Timestamp overlay failed: {str(e)}")
            return input_path


    def _read_frame_timestamp(self, frame):
        """Read timestamp from frame using OCR with improved resolution handling"""
        try:
            import pytesseract

            # Get frame dimensions
            height, width = frame.shape[:2]
            
            # Don't attempt OCR if resolution is lower than minimum requirement
            if height < 720:
                logger.warning(f"Frame resolution too low for OCR: {width}x{height}, minimum height is 720px")
                return None

            # Define a larger ROI for the timestamp area
            roi_height = max(60, int(height * 0.1))  # At least 60px or 10% of frame height
            roi_width = max(400, int(width * 0.3))   # At least 400px or 30% of frame width

            # Crop timestamp area (adjust coordinates based on overlay position)
            timestamp_roi = frame[40:40+roi_height, 10:10+roi_width]  # y:y+h, x:x+w

            # Resize the ROI to improve OCR detection (upscale to higher resolution)
            scale_factor = 2.0  # Double the resolution
            timestamp_roi_upscaled = cv2.resize(timestamp_roi, None, fx=scale_factor, fy=scale_factor, 
                                               interpolation=cv2.INTER_CUBIC)

            # Apply multiple preprocessing techniques to improve OCR
            gray = cv2.cvtColor(timestamp_roi_upscaled, cv2.COLOR_BGR2GRAY)

            # Increase contrast using CLAHE (Contrast Limited Adaptive Histogram Equalization)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
            enhanced = clahe.apply(gray)

            # Try several binarization methods and pick the best result
            _, binary1 = cv2.threshold(enhanced, 150, 255, cv2.THRESH_BINARY)
            _, binary2 = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            adaptive = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)

            # Apply slight blur to reduce noise before binarization
            blurred = cv2.GaussianBlur(enhanced, (3, 3), 0)
            _, binary3 = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

            # Try multiple preprocessing methods and parse all results
            images_to_try = [binary1, binary2, adaptive, binary3, enhanced, gray]

            for idx, img in enumerate(images_to_try):
                # Apply dilation to make text thicker and clearer
                kernel = np.ones((2, 2), np.uint8)
                dilated = cv2.dilate(img, kernel, iterations=1)

                # Use tesseract with specific configuration for timestamps
                # --psm 7: Treat the image as a single line of text
                # --oem 1: Use LSTM OCR Engine
                text = pytesseract.image_to_string(
                    dilated, 
                    config='--psm 7 --oem 1 -c tessedit_char_whitelist=0123456789:.'
                )

                # Try to parse the timestamp (more lenient pattern matching)
                timestamp_str = text.strip()
                logger.debug(f"OCR read attempt {idx+1}: '{timestamp_str}'")

                # Try multiple regex patterns to improve matching chances
                patterns = [
                    r'(\d{2}):(\d{2}):(\d{2})\.(\d+)',  # Standard HH:MM:SS.mmm
                    r'(\d{2}):(\d{2})\.(\d+)',          # MM:SS.mmm
                    r'(\d{1,2}):(\d{2})\.(\d+)',        # M:SS.mmm
                    r'(\d+)\.(\d+)'                     # S.mmm
                ]

                for pattern in patterns:
                    match = re.search(pattern, timestamp_str)
                    if match:
                        groups = match.groups()
                        if len(groups) == 4:  # HH:MM:SS.mmm
                            hours = int(groups[0])
                            minutes = int(groups[1])
                            seconds = int(groups[2])
                            microsec = int(groups[3].ljust(6, '0')[:6])
                            total_seconds = hours * 3600 + minutes * 60 + seconds + microsec / 1000000
                            return total_seconds
                        elif len(groups) == 3:  # MM:SS.mmm
                            minutes = int(groups[0])
                            seconds = int(groups[1])
                            microsec = int(groups[2].ljust(6, '0')[:6])
                            total_seconds = minutes * 60 + seconds + microsec / 1000000
                            return total_seconds
                        elif len(groups) == 2:  # S.mmm
                            seconds = int(groups[0])
                            microsec = int(groups[1].ljust(6, '0')[:6])
                            total_seconds = seconds + microsec / 1000000
                            return total_seconds

                # Try to handle specific errors in your timestamp format
                # From your logs: '9000:06.900', '00700:09.7204', etc.
                if ':' in timestamp_str and '.' in timestamp_str:
                    parts = timestamp_str.split(':')
                    if len(parts) == 2:
                        try:
                            # Handle malformed timestamps like '9000:06.900'
                            seconds_part = parts[1]
                            if '.' in seconds_part:
                                seconds, microseconds = seconds_part.split('.')
                                total_seconds = int(seconds) + int(microseconds.ljust(6, '0')[:6]) / 1000000

                                # If first part is reasonable (less than 60), treat as minutes
                                if parts[0].isdigit() and len(parts[0]) <= 2 and int(parts[0]) < 60:
                                    total_seconds += int(parts[0]) * 60
                                # Otherwise, try to extract last 2 digits as minutes
                                elif parts[0].isdigit() and len(parts[0]) > 2:
                                    minutes = int(parts[0][-2:])
                                    total_seconds += minutes * 60

                                logger.info(f"Parsed irregular timestamp '{timestamp_str}' as {total_seconds:.6f}s")
                                return total_seconds
                        except (ValueError, IndexError):
                            pass

            logger.warning(f"Failed to parse timestamp: '{timestamp_str}'")
            return None

        except ImportError:
            logger.error("pytesseract not installed")
            return None
        except Exception as e:
            logger.error(f"Error reading timestamp: {str(e)}")
            return None

    def _extract_timestamps_from_video(self, video_path, sample_count=10):
        """Extract multiple timestamps from a video to understand its timeline"""
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                logger.error(f"Failed to open video: {video_path}")
                return []

            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)

            if frame_count <= 0 or fps <= 0:
                logger.error(f"Invalid video properties: frames={frame_count}, fps={fps}")
                cap.release()
                return []

            # Sample frames throughout the video
            timestamps = []

            # Sample first, last, and evenly distributed frames
            sample_positions = [0]  # First frame

            # Add evenly distributed samples
            if sample_count > 2:
                for i in range(1, sample_count-1):
                    pos = int((i / (sample_count-1)) * frame_count)
                    sample_positions.append(pos)

            sample_positions.append(frame_count - 1)  # Last frame

            # Remove duplicates and sort
            sample_positions = sorted(list(set(sample_positions)))

            for pos in sample_positions:
                cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
                ret, frame = cap.read()
                if not ret:
                    continue

                frame_timestamp = self._read_frame_timestamp(frame)
                video_timestamp = pos / fps  # Frame position in seconds

                if frame_timestamp is not None:
                    timestamps.append({
                        'frame': pos,
                        'video_time': video_timestamp,
                        'frame_timestamp': frame_timestamp
                    })
                    logger.debug(f"Frame {pos}: video_time={video_timestamp:.3f}s, frame_timestamp={frame_timestamp:.3f}s")

            cap.release()
            return timestamps

        except Exception as e:
            logger.error(f"Error extracting timestamps: {str(e)}")
            return []


    def _align_using_timestamps(self, reference_path, captured_path):
        """
        Align videos based on their embedded timestamps

        Returns:
        - ref_start_trim: Seconds to trim from start of reference
        - ref_end_trim: Seconds to trim from end of reference
        - cap_start_trim: Seconds to trim from start of captured
        - cap_end_trim: Seconds to trim from end of captured
        - confidence: Alignment confidence (0-1)
        """
        try:         
            # Create output paths for timestamps
            test_dir = os.path.dirname(os.path.dirname(reference_path))
            test_results_dir = os.path.join(test_dir, "test_results")

            # Use timestamp for unique test folder
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            test_name = f"alignment_{timestamp}"
            test_output_dir = os.path.join(test_results_dir, test_name)
            os.makedirs(test_output_dir, exist_ok=True)

            # No need to add timestamps - use existing ones in the videos
            self.status_update.emit("Using existing timestamps from videos...")

            # Extract timestamps from both videos with increased sample count
            self.status_update.emit("Extracting timestamps from reference video...")
            ref_timestamps = self._extract_timestamps_from_video(reference_path, sample_count=15)

            self.status_update.emit("Extracting timestamps from captured video...")
            cap_timestamps = self._extract_timestamps_from_video(captured_path, sample_count=15)

            if not ref_timestamps or not cap_timestamps:
                logger.error("Failed to extract timestamps from videos")
                return None, None, None, None, 0

            # Get video info to calculate durations
            ref_info = self._get_video_info(reference_path)
            cap_info = self._get_video_info(captured_path)

            if not ref_info or not cap_info:
                logger.error("Failed to get video info")
                return None, None, None, None, 0

            ref_duration = ref_info.get('duration', 0)
            cap_duration = cap_info.get('duration', 0)

            # For debugging, log all timestamps
            logger.info("Reference video timestamps:")
            for ts in ref_timestamps:
                logger.info(f"  Frame {ts['frame']}: video_time={ts['video_time']:.3f}s, timestamp={ts['frame_timestamp']:.3f}s")

            logger.info("Captured video timestamps:")
            for ts in cap_timestamps:
                logger.info(f"  Frame {ts['frame']}: video_time={ts['video_time']:.3f}s, timestamp={ts['frame_timestamp']:.3f}s")

            # Get first and last valid timestamps from reference
            ref_start_timestamp = ref_timestamps[0]['frame_timestamp'] if ref_timestamps else None
            ref_end_timestamp = ref_timestamps[-1]['frame_timestamp'] if ref_timestamps else None

            # Find matching timestamps in captured video
            cap_matching_start = None
            cap_matching_end = None

            # Look for matching start timestamp in captured
            for ts in cap_timestamps:
                # Find timestamp in captured closest to reference start
                if ref_start_timestamp is not None:
                    if cap_matching_start is None or abs(ts['frame_timestamp'] - ref_start_timestamp) < abs(cap_matching_start['frame_timestamp'] - ref_start_timestamp):
                        cap_matching_start = ts

                # Find timestamp in captured closest to reference end
                if ref_end_timestamp is not None:
                    if cap_matching_end is None or abs(ts['frame_timestamp'] - ref_end_timestamp) < abs(cap_matching_end['frame_timestamp'] - ref_end_timestamp):
                        cap_matching_end = ts

            # Calculate trim amounts
            ref_start_trim = 0  # By default, don't trim reference start
            ref_end_trim = 0    # By default, don't trim reference end

            # Calculate trim for captured start
            cap_start_trim = 0
            if cap_matching_start:
                # Trim captured video to start at matching timestamp
                cap_start_trim = cap_matching_start['video_time']
                logger.info(f"Trim captured start by {cap_start_trim:.3f}s to match reference timestamp {ref_start_timestamp:.3f}s")

            # Calculate trim for captured end
            cap_end_trim = 0
            if cap_matching_end and cap_matching_end != cap_matching_start:
                # Calculate how much to trim from the end
                cap_end_time = cap_matching_end['video_time']
                cap_end_trim = cap_duration - cap_end_time
                logger.info(f"Trim captured end by {cap_end_trim:.3f}s to match reference timestamp {ref_end_timestamp:.3f}s")

            # Calculate confidence based on timestamp match quality
            confidence = 0.8  # Default high confidence if we found matching timestamps

            # Adjust confidence based on timestamp match quality
            if cap_matching_start and ref_start_timestamp:
                start_diff = abs(cap_matching_start['frame_timestamp'] - ref_start_timestamp)
                if start_diff > 1.0:  # If more than 1 second different
                    confidence *= (1.0 / (start_diff + 1.0))

            if cap_matching_end and ref_end_timestamp:
                end_diff = abs(cap_matching_end['frame_timestamp'] - ref_end_timestamp)
                if end_diff > 1.0:  # If more than 1 second different
                    confidence *= (1.0 / (end_diff + 1.0))

            logger.info(f"Timestamp alignment results:")
            logger.info(f"  Reference: start_trim={ref_start_trim:.3f}s, end_trim={ref_end_trim:.3f}s")
            logger.info(f"  Captured: start_trim={cap_start_trim:.3f}s, end_trim={cap_end_trim:.3f}s")
            logger.info(f"  Confidence: {confidence:.2f}")

            return ref_start_trim, ref_end_trim, cap_start_trim, cap_end_trim, confidence

        except Exception as e:
            logger.error(f"Error in timestamp alignment: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None, None, None, None, 0

    def align_videos(self, reference_path, captured_path, max_offset_seconds=5):
        """
        Align two videos based on their content or embedded timestamps

        Returns a dictionary with:
        - offset_frames: Frame offset (positive if captured starts after reference)
        - offset_seconds: Time offset in seconds
        - aligned_reference: Path to trimmed reference video
        - aligned_captured: Path to trimmed captured video
        """
        # Initialize variables to avoid undefined variable errors
        ts_confidence = 0
        ref_start_trim = None
        ref_end_trim = None
        cap_start_trim = None
        cap_end_trim = None

        try:
            self.status_update.emit(f"Loading reference video: {os.path.basename(reference_path)}")

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

            # Normalize videos before alignment to ensure same framerate
            try:
                self.status_update.emit("Normalizing videos for alignment...")

                # Import here to avoid circular imports
                from .video_normalizer import normalize_videos_for_comparison

                normalized_ref_path, normalized_cap_path = normalize_videos_for_comparison(
                    reference_path,
                    captured_path
                )

                if normalized_ref_path and normalized_cap_path and os.path.exists(normalized_ref_path) and os.path.exists(normalized_cap_path):
                    # Use normalized paths
                    reference_path = normalized_ref_path
                    captured_path = normalized_cap_path

                    # Get updated info for normalized videos
                    ref_info = self._get_video_info(reference_path)
                    cap_info = self._get_video_info(captured_path)

                    if not ref_info or not cap_info:
                        logger.warning("Could not get info for normalized videos, using originals")
                        # Revert to original paths
                        reference_path = reference_path
                        captured_path = captured_path
                else:
                    logger.warning("Normalization failed, using original videos")
            except Exception as norm_e:
                logger.error(f"Error during normalization: {str(norm_e)}")
                # Continue with original videos if normalization fails

            # Try timestamp-based alignment first - but only if videos have timestamps
            try_timestamp_alignment = False

            # Quick check for timestamps - capture a single frame and check for timestamp
            ref_cap = cv2.VideoCapture(reference_path)
            if ref_cap.isOpened():
                ret, frame = ref_cap.read()
                if ret:
                    # Try to read timestamp from first frame
                    timestamp = self._read_frame_timestamp(frame)
                    if timestamp is not None:
                        try_timestamp_alignment = True
                ref_cap.release()

            # Only try timestamp alignment if we detected a timestamp
            if try_timestamp_alignment:
                self.status_update.emit("Aligning videos using timestamps...")
                try:
                    ref_start_trim, ref_end_trim, cap_start_trim, cap_end_trim, ts_confidence = self._align_using_timestamps(
                        reference_path,
                        captured_path
                    )
                except Exception as ts_e:
                    logger.error(f"Error in timestamp alignment: {str(ts_e)}")
                    ref_start_trim = None
                    ref_end_trim = None
                    cap_start_trim = None
                    cap_end_trim = None
                    ts_confidence = 0
            else:
                logger.info("Skipping timestamp alignment as no timestamps detected in videos")
                ts_confidence = 0

            logger.info(f"Timestamp alignment decision factors: confidence={ts_confidence}, " +
                    f"ref_start_trim={ref_start_trim}, cap_start_trim={cap_start_trim}, cap_end_trim={cap_end_trim}")

            # Check if timestamp alignment was successful
            timestamp_alignment_successful = (
                ts_confidence >= 0.2 and  # Changed > to >=
                ref_start_trim is not None and 
                cap_start_trim is not None and
                (cap_start_trim > 0 or cap_end_trim > 0)  # Allow either start or end trim to be positive
            )

            if timestamp_alignment_successful:
                logger.info(f"Using timestamp-based alignment (confidence: {ts_confidence:.2f})")

                # Create aligned videos using timestamp information
                aligned_reference, aligned_captured = self._create_aligned_videos_by_trimming(
                    reference_path,
                    captured_path,
                    ref_start_trim,
                    ref_end_trim,
                    cap_start_trim,
                    cap_end_trim
                )

                # Prepare result object
                fps = ref_info.get('frame_rate', 25)
                offset_seconds = cap_start_trim - ref_start_trim
                offset_frames = int(offset_seconds * fps)

                result = {
                    'alignment_method': 'timestamp',
                    'offset_frames': offset_frames,
                    'offset_seconds': offset_seconds,
                    'confidence': ts_confidence,
                    'aligned_reference': aligned_reference,
                    'aligned_captured': aligned_captured
                }

                self.alignment_complete.emit(result)
                return result

            else:
                # Fallback to SSIM-based alignment
                logger.warning(f"Using SSIM-based alignment (timestamp alignment failed or skipped)")
                self.status_update.emit("Using visual content alignment...")

                # Calculate maximum offset frames - use a safe default if frame_rate is missing or zero
                fps = ref_info.get('frame_rate', 25)
                if fps <= 0:
                    fps = 25  # Default to 25 fps if invalid

                max_offset_frames = int(max_offset_seconds * fps)

                self.alignment_progress.emit(0)

                # Try SSIM-based alignment
                offset_frames, confidence = self._align_ssim(
                    reference_path, 
                    captured_path, 
                    max_offset_frames
                )

                # Log alignment results
                self.status_update.emit(f"Visual alignment complete. Offset: {offset_frames} frames, confidence: {confidence:.2f}")
                logger.info(f"SSIM alignment result: {offset_frames} frames, confidence: {confidence}")

                # Check if alignment seems valid
                if confidence < 0.5:
                    logger.warning(f"Low alignment confidence: {confidence}")

                # Prepare trimmed/aligned videos using SSIM offset
                aligned_reference, aligned_captured = self._create_aligned_videos_by_offset(
                    reference_path,
                    captured_path,
                    offset_frames
                )

                # Prepare result object
                result = {
                    'alignment_method': 'ssim',
                    'offset_frames': offset_frames,
                    'offset_seconds': offset_frames / fps if fps > 0 else 0,
                    'confidence': confidence,
                    'aligned_reference': aligned_reference,
                    'aligned_captured': aligned_captured
                }

                self.alignment_complete.emit(result)
                return result

        except Exception as e:
            error_msg = f"Error aligning videos: {str(e)}"
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            return None

    def _align_ssim(self, reference_path, captured_path, max_offset_frames):
            """
            Optimized alignment using SSIM with improved resolution and accuracy
            Returns: (offset_frames, confidence)
            """
            try:
                # Open videos
                ref_cap = cv2.VideoCapture(reference_path)
                cap_cap = cv2.VideoCapture(captured_path)

                if not ref_cap.isOpened() or not cap_cap.isOpened():
                    logger.error("Failed to open video files for alignment")
                    return 0, 0

                # Get frame counts for progress reporting
                total_comparisons = min(max_offset_frames + 1, 30)  # Limit to reasonable number

                # Get video dimensions
                ref_width = int(ref_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                ref_height = int(ref_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

                # Calculate downscale factor for faster processing
                # Use higher resolution for better accuracy (720p height instead of 240p)
                target_height = 720
                scale_factor = target_height / ref_height
                scaled_width = int(ref_width * scale_factor)
                scaled_height = target_height

                logger.info(f"Using improved resolution {scaled_width}x{scaled_height} for alignment")
                self.status_update.emit(f"Using optimized alignment at {scaled_width}x{scaled_height}")

                # Sample frames from reference video
                ref_frames = []
                frame_positions = []

                ref_frame_count = int(ref_cap.get(cv2.CAP_PROP_FRAME_COUNT))
                sample_count = min(12, ref_frame_count)  # Increased from 8 to 12 for better matching

                # Use frames from throughout the video, not just the beginning
                # First sample more frames from the beginning for better matching
                first_quarter_samples = max(6, sample_count // 2)  # Increased from 4 to 6
                for i in range(first_quarter_samples):
                    frame_pos = int((i / first_quarter_samples) * (ref_frame_count // 4))
                    frame_positions.append(frame_pos)

                # Then sample the rest of the video
                remaining_samples = sample_count - first_quarter_samples
                if remaining_samples > 0:
                    for i in range(remaining_samples):
                        # Sample from 25% to 100% of the video
                        frame_pos = int(ref_frame_count // 4 + 
                                    (i / remaining_samples) * (ref_frame_count * 3 // 4))
                        frame_positions.append(frame_pos)

                # Remove duplicates and sort
                frame_positions = sorted(list(set(frame_positions)))

                # Read and process reference frames
                for frame_pos in frame_positions:
                    ref_cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
                    ret, frame = ref_cap.read()
                    if ret:
                        # Resize for faster processing
                        frame_small = cv2.resize(frame, (scaled_width, scaled_height))
                        # Convert to grayscale for faster comparison
                        gray = cv2.cvtColor(frame_small, cv2.COLOR_BGR2GRAY)
                        ref_frames.append(gray)

                if not ref_frames:
                    logger.error("Could not extract frames from reference video")
                    return 0, 0

                # Try different offsets
                best_offset = 0
                best_score = -1

                # For very long videos, use larger step sizes
                cap_frame_count = int(cap_cap.get(cv2.CAP_PROP_FRAME_COUNT))
                if cap_frame_count > 1000 and max_offset_frames > 100:
                    # Use step size of 2 or more for large videos
                    step_size = max(2, max_offset_frames // 50)
                    logger.info(f"Using step size of {step_size} for large video analysis")
                else:
                    step_size = 1

                last_progress = 0

                # Two-pass approach: first do coarse search, then refine
                # Coarse pass
                coarse_offsets = list(range(0, max_offset_frames + 1, step_size))
                for offset in coarse_offsets:
                    # Report progress
                    progress = (coarse_offsets.index(offset) * 50) // len(coarse_offsets)
                    if progress > last_progress:
                        self.alignment_progress.emit(progress)
                        last_progress = progress

                    # Get frames from captured video at same positions + offset
                    cap_frames = []
                    for framepos in frame_positions:
                        adjusted_pos = frame_pos + offset
                        if adjusted_pos >= cap_frame_count:
                            continue
                        cap_cap.set(cv2.CAP_PROP_POS_FRAMES, adjusted_pos)
                        ret, frame = cap_cap.read()
                        if ret:
                            frame_small = cv2.resize(frame, (scaled_width, scaled_height))
                            gray = cv2.cvtColor(frame_small, cv2.COLOR_BGR2GRAY)
                            cap_frames.append(gray)

                    # Skip if we couldn't get enough frames
                    if len(cap_frames) < min(3, len(ref_frames)):
                        continue

                    # Calculate overall match score (simplified for coarse pass)
                    match_score = self._calculate_quick_match_score(ref_frames[:len(cap_frames)], cap_frames)

                    if match_score > best_score:
                        best_score = match_score
                        best_offset = offset

                # Refine around best offset if step size > 1
                if step_size > 1 and best_offset > 0:
                    refine_start = max(0, best_offset - step_size)
                    refine_end = min(max_offset_frames, best_offset + step_size)

                    for offset in range(refine_start, refine_end + 1):
                        if offset == best_offset or offset % step_size == 0:
                            continue  # Skip offsets we already tested

                        # Report progress for refinement step
                        progress = 50 + ((offset - refine_start) * 40) // (refine_end - refine_start + 1)
                        if progress > last_progress:
                            self.alignment_progress.emit(progress)
                            last_progress = progress

                        # Get frames from captured video at same positions + offset
                        cap_frames = []
                        for frame_pos in frame_positions:
                            adjusted_pos = frame_pos + offset
                            if adjusted_pos >= cap_frame_count:
                                continue
                            cap_cap.set(cv2.CAP_PROP_POS_FRAMES, adjusted_pos)
                            ret, frame = cap_cap.read()
                            if ret:
                                frame_small = cv2.resize(frame, (scaled_width, scaled_height))
                                gray = cv2.cvtColor(frame_small, cv2.COLOR_BGR2GRAY)
                                cap_frames.append(gray)

                        # Skip if we couldn't get enough frames
                        if len(cap_frames) < min(3, len(ref_frames)):
                            continue

                        # Calculate overall match score (more detailed for refinement)
                        match_score = self._calculate_match_score(ref_frames[:len(cap_frames)], cap_frames)

                        if match_score > best_score:
                            best_score = match_score
                            best_offset= offset

                # Clean up
                ref_cap.release()
                cap_cap.release()

                # Complete progress
                self.alignment_progress.emit(100)

                return best_offset, best_score

            except Exception as e:
                logger.error(f"Error in SSIM alignment: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                return 0, 0
                
    def _calculate_quick_match_score(self, ref_frames, cap_frames):
        """
        Calculate a simplified SSIM-based match score between frame sets
        Uses grayscale frames to speed up calculation
        
        Args:
            ref_frames: List of reference frames (grayscale)
            cap_frames: List of captured frames (grayscale)
            
        Returns:
            Average SSIM score across all frame pairs
        """
        if len(ref_frames) == 0 or len(cap_frames) == 0:
            return 0.0
            
        total_score = 0.0
        count = min(len(ref_frames), len(cap_frames))
        
        for i in range(count):
            # Use built-in structural_similarity from skimage
            try:
                from skimage.metrics import structural_similarity as ssim
                score = ssim(ref_frames[i], cap_frames[i], full=False)
            except ImportError:
                # Fallback to basic MSE-based comparison if skimage not available
                diff = cv2.absdiff(ref_frames[i], cap_frames[i])
                mse = np.mean(diff ** 2)
                if mse == 0:
                    score = 1.0
                else:
                    # Convert MSE to a similarity score (0-1 range)
                    score = 1.0 - min(1.0, mse / 10000.0)
                    
            total_score += score
            
        return total_score / count
        
    def _calculate_match_score(self, ref_frames, cap_frames):
        """
        Calculate a more detailed match score between frame sets
        Used in the refinement pass for better accuracy
        
        Args:
            ref_frames: List of reference frames (grayscale)
            cap_frames: List of captured frames (grayscale)
            
        Returns:
            Weighted combination of SSIM and feature matching scores
        """
        return self._calculate_quick_match_score(ref_frames, cap_frames)

    def _create_aligned_videos_by_offset(self, reference_path, captured_path, offset_frames):
        """Create aligned videos by trimming based on frame offset"""
        try:
            # Create output paths
            aligned_reference = os.path.splitext(reference_path)[0] + "_aligned.mp4"
            aligned_captured = os.path.splitext(captured_path)[0] + "_aligned.mp4"

            # Get video info
            ref_info = self._get_video_info(reference_path)
            cap_info = self._get_video_info(captured_path)

            if not ref_info or not cap_info:
                logger.error("Failed to get video info for alignment")
                return None, None

            # Calculate trim times based on frames and fps
            fps = ref_info.get('frame_rate', 25)
            if fps <= 0:
                fps = 25  # Default to 25 fps if invalid

            # Convert frame offset to time offset
            offset_seconds = offset_frames / fps

            # Determine which video starts first
            if offset_frames > 0:
                # Reference starts first, need to trim reference start
                ref_start_trim = offset_seconds
                cap_start_trim = 0
                logger.info(f"Reference starts {offset_seconds:.3f}s before captured")
            else:
                # Captured starts first, need to trim captured start
                ref_start_trim = 0
                cap_start_trim = abs(offset_seconds)
                logger.info(f"Captured starts {abs(offset_seconds):.3f}s before reference")

            # Calculate video durations after trimming
            ref_duration = ref_info.get('duration', 0) - ref_start_trim
            cap_duration = cap_info.get('duration', 0) - cap_start_trim

            # Use the shorter duration for both videos
            output_duration = min(ref_duration, cap_duration)

            # Trim reference video
            ref_end_time = ref_start_trim + output_duration
            ref_cmd = [
                "ffmpeg", "-y", "-i", reference_path,
                "-ss", str(ref_start_trim),
                "-t", str(output_duration),
                "-c:v", "libx264", "-crf", "18", 
                "-preset", "fast", "-c:a", "copy",
                aligned_reference
            ]

            logger.info(f"Trimming reference video from {ref_start_trim:.3f}s to {ref_end_time:.3f}s")
            subprocess.run(ref_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # Trim captured video
            cap_end_time = cap_start_trim + output_duration
            cap_cmd = [
                "ffmpeg", "-y", "-i", captured_path,
                "-ss", str(cap_start_trim),
                "-t", str(output_duration),
                "-c:v", "libx264", "-crf", "18",
                "-preset", "fast", "-c:a", "copy",
                aligned_captured
            ]

            logger.info(f"Trimming captured video from {cap_start_trim:.3f}s to {cap_end_time:.3f}s")
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
            logger.error(f"Error creating aligned videos by offset: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None, None





class AlignmentThread(QThread):
    """Thread for video alignment with reliable progress reporting"""
    alignment_progress = pyqtSignal(int)
    alignment_complete = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    status_update = pyqtSignal(str)

    def __init__(self, reference_path, captured_path, max_offset_seconds=5):
        super().__init__()
        self.reference_path = reference_path
        self.captured_path = captured_path
        self.max_offset_seconds = max_offset_seconds
        self.aligner = VideoAligner()

        # Connect signals with direct connections for responsive UI updates
        self.aligner.alignment_progress.connect(self._handle_progress, Qt.DirectConnection)
        self.aligner.alignment_complete.connect(self.alignment_complete, Qt.DirectConnection)
        self.aligner.error_occurred.connect(self.error_occurred, Qt.DirectConnection)
        self.aligner.status_update.connect(self.status_update, Qt.DirectConnection)

    def _handle_progress(self, progress):
        """Handle progress updates from aligner, ensuring proper values"""
        try:
            # Ensure progress is an integer between 0-100
            progress_value = int(progress)
            progress_value = max(0, min(100, progress_value))
            self.alignment_progress.emit(progress_value)
        except (ValueError, TypeError):
            # In case of non-integer progress, emit a safe value
            self.alignment_progress.emit(0)

    def run(self):
        """Run alignment in thread"""
        try:
            self.status_update.emit("Starting alignment process...")

            # Report initial progress
            self.alignment_progress.emit(0)

            # Verify input files
            if not os.path.exists(self.reference_path):
                self.error_occurred.emit(f"Reference video not found: {self.reference_path}")
                return

            if not os.path.exists(self.captured_path):
                self.error_occurred.emit(f"Captured video not found: {self.captured_path}")
                return

            # Run alignment - pass parameters correctly
            # The align_videos method expects reference_path, captured_path, and max_offset_seconds
            result = self.aligner.align_videos(
                self.reference_path,
                self.captured_path,
                self.max_offset_seconds
            )

            if result:
                # Ensure progress is set to 100% at completion
                self.alignment_progress.emit(100)
                self.alignment_complete.emit(result)
                self.status_update.emit("Alignment complete!")
            else:
                self.error_occurred.emit("Alignment failed")

        except Exception as e:
            error_msg = f"Error in alignment thread: {str(e)}"
            self.error_occurred.emit(error_msg)
            logger.error(error_msg)
            import traceback
            logger.error(traceback.format_exc())

    def _get_video_info(self, video_path):
        try:
            cmd = [
                self._ffmpeg_path,
                "-i", video_path,
                "-hide_banner",
                "-show_entries", "stream=width,height,duration,r_frame_rate",
                "-of", "default=noprint_wrappers=1"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            output = result.stdout.strip()

            info = {}
            lines = output.splitlines()
            for line in lines:
                parts = line.split("=")
                if len(parts) == 2:
                    key = parts[0]
                    value = parts[1]

                    if key == "r_frame_rate":
                        framerate_parts = value.split("/")
                        if len(framerate_parts) == 2:
                            try:
                                info['frame_rate'] = float(framerate_parts[0]) / float(framerate_parts[1])
                            except ValueError:
                                pass
                    elif key == "duration":
                        try:
                            info['duration'] = float(value)
                        except ValueError:
                            pass
                    else:
                        info[key] = value

            return info
        except (subprocess.CalledProcessError, ValueError, IndexError) as e:
            logger.error(f"Error getting video info: {str(e)}")
            return None

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

    def _create_aligned_videos_by_trimming(self, reference_path, captured_path, ref_start_trim, ref_end_trim, cap_start_trim, cap_end_trim):
        try:
            # Create output paths
            aligned_reference = os.path.splitext(reference_path)[0] + "_aligned.mp4"
            aligned_captured = os.path.splitext(captured_path)[0] + "_aligned.mp4"

            # Trim reference video
            ref_cmd = [
                self._ffmpeg_path, "-y", "-i", reference_path,
                "-ss", str(ref_start_trim),
                "-to", str(ref_info['duration'] - ref_end_trim),
                "-c", "copy", aligned_reference
            ]
            subprocess.run(ref_cmd, check=True)

            # Trim captured video
            cap_cmd = [
                self._ffmpeg_path, "-y", "-i", captured_path,
                "-ss", str(cap_start_trim),
                "-to", str(cap_info['duration'] - cap_end_trim),
                "-c", "copy", aligned_captured
            ]
            subprocess.run(cap_cmd, check=True)

            return aligned_reference, aligned_captured
        except Exception as e:
            logger.error(f"Error creating trimmed videos: {str(e)}")
            return None, None

    def _create_aligned_videos_by_offset(self, reference_path, captured_path, offset_frames):
        """Create aligned videos by trimming based on frame offset"""
        try:
            # Create output paths
            aligned_reference = os.path.splitext(reference_path)[0] + "_aligned.mp4"
            aligned_captured = os.path.splitext(captured_path)[0] + "_aligned.mp4"

            # Get video info
            ref_info = self._get_video_info(reference_path)
            cap_info = self._get_video_info(captured_path)

            if not ref_info or not cap_info:
                logger.error("Failed to get video info for alignment")
                return None, None

            # Calculate trim times based on frames and fps
            fps = ref_info.get('frame_rate', 25)
            if fps <= 0:
                fps = 25  # Default to 25 fps if invalid

            # Convert frame offset to time offset
            offset_seconds = offset_frames / fps

            # Determine which video starts first
            if offset_frames > 0:
                # Reference starts first, need to trim reference start
                ref_start_trim = offset_seconds
                cap_start_trim = 0
                logger.info(f"Reference starts {offset_seconds:.3f}s before captured")
            else:
                # Captured starts first, need to trim captured start
                ref_start_trim = 0
                cap_start_trim = abs(offset_seconds)
                logger.info(f"Captured starts {abs(offset_seconds):.3f}s before reference")

            # Calculate video durations after trimming
            ref_duration = ref_info.get('duration', 0) - ref_start_trim
            cap_duration = cap_info.get('duration', 0) - cap_start_trim

            # Use the shorter duration for both videos
            output_duration = min(ref_duration, cap_duration)

            # Trim reference video
            ref_end_time = ref_start_trim + output_duration
            ref_cmd = [
                "ffmpeg", "-y", "-i", reference_path,
                "-ss", str(ref_start_trim),
                "-t", str(output_duration),
                "-c:v", "libx264", "-crf", "18", 
                "-preset", "fast", "-c:a", "copy",
                aligned_reference
            ]

            logger.info(f"Trimming reference video from {ref_start_trim:.3f}s to {ref_end_time:.3f}s")
            subprocess.run(ref_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # Trim captured video
            cap_end_time = cap_start_trim + output_duration
            cap_cmd = [
                "ffmpeg", "-y", "-i", captured_path,
                "-ss", str(cap_start_trim),
                "-t", str(output_duration),
                "-c:v", "libx264", "-crf", "18",
                "-preset", "fast", "-c:a", "copy",
                aligned_captured
            ]

            logger.info(f"Trimming captured video from {cap_start_trim:.3f}s to {cap_end_time:.3f}s")
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
            logger.error(f"Error creating aligned videos by offset: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None, None

    def _calculate_match_score(self, ref_frames, cap_frames):
        total_score = 0
        for i in range(len(ref_frames)):
            score = cv2.resize(ref_frames[i], (scaled_width, scaled_height))
            score = cv2.resize(cap_frames[i], (scaled_width, scaled_height))
            total_score += cv2.compareSSIM(ref_frames[i], cap_frames[i], cv2.COLOR_BGR2GRAY)
        return total_score / len(ref_frames)
    def _calculate_quick_match_score(self, ref_frames, cap_frames):
        total_score = 0
        for i in range(len(ref_frames)):
            total_score += cv2.compareSSIM(ref_frames[i], cap_frames[i], cv2.COLOR_BGR2GRAY)
        return total_score

    def _create_aligned_videos_by_offset(self, reference_path, captured_path, offset_frames):
        """Create aligned videos by trimming based on frame offset"""
        try:
            # Create output paths
            aligned_reference = os.path.splitext(reference_path)[0] + "_aligned.mp4"
            aligned_captured = os.path.splitext(captured_path)[0] + "_aligned.mp4"

            # Get video info
            ref_info = self._get_video_info(reference_path)
            cap_info = self._get_video_info(captured_path)

            if not ref_info or not cap_info:
                logger.error("Failed to get video info for alignment")
                return None, None

            # Calculate trim times based on frames and fps
            fps = ref_info.get('frame_rate', 25)
            if fps <= 0:
                fps = 25  # Default to 25 fps if invalid

            # Convert frame offset to time offset
            offset_seconds = offset_frames / fps

            # Determine which video starts first
            if offset_frames > 0:
                # Reference starts first, need to trim reference start
                ref_start_trim = offset_seconds
                cap_start_trim = 0
                logger.info(f"Reference starts {offset_seconds:.3f}s before captured")
            else:
                # Captured starts first, need to trim captured start
                ref_start_trim = 0
                cap_start_trim = abs(offset_seconds)
                logger.info(f"Captured starts {abs(offset_seconds):.3f}s before reference")

            # Calculate video durations after trimming
            ref_duration = ref_info.get('duration', 0) - ref_start_trim
            cap_duration = cap_info.get('duration', 0) - cap_start_trim

            # Use the shorter duration for both videos
            output_duration = min(ref_duration, cap_duration)

            # Trim reference video
            ref_end_time = ref_start_trim + output_duration
            ref_cmd = [
                "ffmpeg", "-y", "-i", reference_path,
                "-ss", str(ref_start_trim),
                "-t", str(output_duration),
                "-c:v", "libx264", "-crf", "18", 
                "-preset", "fast", "-c:a", "copy",
                aligned_reference
            ]

            logger.info(f"Trimming reference video from {ref_start_trim:.3f}s to {ref_end_time:.3f}s")
            subprocess.run(ref_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # Trim captured video
            cap_end_time = cap_start_trim + output_duration
            cap_cmd = [
                "ffmpeg", "-y", "-i", captured_path,
                "-ss", str(cap_start_trim),
                "-t", str(output_duration),
                "-c:v", "libx264", "-crf", "18",
                "-preset", "fast", "-c:a", "copy",
                aligned_captured
            ]

            logger.info(f"Trimming captured video from {cap_start_trim:.3f}s to {cap_end_time:.3f}s")
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
            logger.error(f"Error creating aligned videos by offset: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None, None