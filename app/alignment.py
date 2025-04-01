import os
import logging
import subprocess
import json
import re
import time
from datetime import datetime
import cv2
import numpy as np
from PyQt5.QtCore import QObject, pyqtSignal, QThread

logger = logging.getLogger(__name__)

class VideoAligner(QObject):
    """Class for aligning captured video with reference video"""
    alignment_progress = pyqtSignal(int)  # 0-100%
    alignment_complete = pyqtSignal(dict)  # Results including offset
    error_occurred = pyqtSignal(str)
    status_update = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()

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


    # Update the _read_frame_timestamp function in alignment.py
    def _read_frame_timestamp(self, frame):
        """Read timestamp from frame using OCR (requires pytesseract)"""
        try:
            import pytesseract
            # Crop timestamp area (adjust coordinates based on overlay position)
            timestamp_roi = frame[40:100, 10:400]  # y:y+h, x:x+w
            
            # Apply multiple preprocessing techniques to improve OCR
            gray = cv2.cvtColor(timestamp_roi, cv2.COLOR_BGR2GRAY)
            
            # Try several binarization methods and pick the best result
            _, binary1 = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
            _, binary2 = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            adaptive = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
            
            # Apply slight blur to reduce noise before binarization
            blurred = cv2.GaussianBlur(gray, (3, 3), 0)
            _, binary3 = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            
            # Try multiple preprocessing methods and parse all results
            images_to_try = [binary1, binary2, adaptive, binary3]
            
            for idx, img in enumerate(images_to_try):
                # Apply dilation to make text thicker and clearer
                kernel = np.ones((2, 2), np.uint8)
                dilated = cv2.dilate(img, kernel, iterations=1)
                
                # Use tesseract with specific configuration for timestamps
                text = pytesseract.image_to_string(
                    dilated, 
                    config='--psm 7 -c tessedit_char_whitelist=0123456789:.'
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
            
            # Create output paths for videos with timestamps
            ref_base = os.path.splitext(os.path.basename(reference_path))[0]
            cap_base = os.path.splitext(os.path.basename(captured_path))[0]
            
            ref_ts_path = os.path.join(test_output_dir, f"{ref_base}_timestamps.mp4")
            cap_ts_path = os.path.join(test_output_dir, f"{cap_base}_timestamps.mp4")
                    
            # Add timestamps to videos
            self.status_update.emit("Adding timestamps to videos for alignment...")
            self._add_timestamps_to_video(reference_path, ref_ts_path)
            self._add_timestamps_to_video(captured_path, cap_ts_path)
            
            # Extract timestamps from both videos
            self.status_update.emit("Extracting timestamps from reference video...")
            ref_timestamps = self._extract_timestamps_from_video(ref_ts_path, sample_count=15)
            
            self.status_update.emit("Extracting timestamps from captured video...")
            cap_timestamps = self._extract_timestamps_from_video(cap_ts_path, sample_count=15)
            
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
            
            # Calculate confidence based on timestamp difference
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
            
            # Try timestamp-based alignment first
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
                # Fallback to SSIM-based alignment if timestamps failed
                # Conditional logging:
                if timestamp_alignment_successful:
                    logger.info(f"Using timestamp-based alignment (confidence: {ts_confidence:.2f})")
                else:
                    logger.warning(f"Timestamp alignment failed (confidence: {ts_confidence:.2f}), using SSIM alignment")

                self.status_update.emit("Timestamp alignment failed, using visual alignment...")
                
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
        Align videos using SSIM (Structural Similarity Index)
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
            
            # Sample frames from reference video
            ref_frames = []
            frame_positions = []
            
            ref_frame_count = int(ref_cap.get(cv2.CAP_PROP_FRAME_COUNT))
            sample_count = min(10, ref_frame_count)  # Sample up to 10 frames
            
            # Use frames from throughout the video, not just the beginning
            for i in range(sample_count):
                frame_pos = int(i * ref_frame_count / sample_count)
                frame_positions.append(frame_pos)
                ref_cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
                ret, frame = ref_cap.read()
                if ret:
                    # Resize for faster processing
                    frame_small = cv2.resize(frame, (320, 180))
                    gray = cv2.cvtColor(frame_small, cv2.COLOR_BGR2GRAY)
                    ref_frames.append(gray)
            
            if not ref_frames:
                logger.error("Could not extract frames from reference video")
                return 0, 0
                
            # Try different offsets
            best_offset = 0
            best_score = -1
            
            for offset in range(max_offset_frames + 1):
                # Report progress
                progress = (offset * 100) // total_comparisons
                self.alignment_progress.emit(progress)
                
                # Get frames from captured video at same positions + offset
                cap_frames = []
                for frame_pos in frame_positions:
                    adjusted_pos = frame_pos + offset
                    if adjusted_pos >= int(cap_cap.get(cv2.CAP_PROP_FRAME_COUNT)):
                        continue
                    cap_cap.set(cv2.CAP_PROP_POS_FRAMES, adjusted_pos)
                    ret, frame = cap_cap.read()
                    if ret:
                        frame_small = cv2.resize(frame, (320, 180))
                        gray = cv2.cvtColor(frame_small, cv2.COLOR_BGR2GRAY)
                        cap_frames.append(gray)
                
                # Skip if we couldn't get enough frames
                if len(cap_frames) < 5:
                    continue
                    
                # Calculate overall match score
                match_score = self._calculate_match_score(ref_frames[:len(cap_frames)], cap_frames)
                
                if match_score > best_score:
                    best_score = match_score
                    best_offset = offset
            
            # Clean up
            ref_cap.release()
            cap_cap.release()
            
            # Complete progress
            self.alignment_progress.emit(100)
            
            return best_offset, best_score
            
        except Exception as e:
            logger.error(f"Error in SSIM alignment: {str(e)}")
            return 0, 0
            
    def _get_video_info(self, video_path):
        """Get video information using FFprobe"""
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
                
            info = json.loads(result.stdout)
            
            # Find video stream
            video_stream = None
            for stream in info.get('streams', []):
                if stream.get('codec_type') == 'video':
                    video_stream = stream
                    break
                    
            if not video_stream:
                logger.error("No video stream found")
                return None
                
            # Extract key information
            format_info = info.get('format', {})
            duration = float(format_info.get('duration', 0))
            
            # Parse frame rate
            frame_rate_str = video_stream.get('avg_frame_rate', '0/0')
            frame_rate = self._parse_frame_rate(frame_rate_str)
            
            # Get dimensions
            width = int(video_stream.get('width', 0))
            height = int(video_stream.get('height', 0))
            
            # Get pixel format
            pix_fmt = video_stream.get('pix_fmt', 'unknown')
            
            return {
                'path': video_path,
                'duration': duration,
                'frame_rate': frame_rate,
                'width': width,
                'height': height,
                'pix_fmt': pix_fmt
            }
            
        except Exception as e:
            logger.error(f"Error getting video info: {str(e)}")
            return None
            
    def _parse_frame_rate(self, frame_rate_str):
        """Parse frame rate string (e.g., '30000/1001') to float"""
        try:
            if '/' in frame_rate_str:
                num, den = map(int, frame_rate_str.split('/'))
                if den == 0:
                    return 0
                return num / den
            else:
                return float(frame_rate_str)
        except (ValueError, ZeroDivisionError):
            return 0
            
    def _calculate_ssim(self, img1, img2):
        """Calculate SSIM between two grayscale images"""
        C1 = (0.01 * 255) ** 2
        C2 = (0.03 * 255) ** 2
        
        img1 = img1.astype(np.float64)
        img2 = img2.astype(np.float64)
        kernel = cv2.getGaussianKernel(11, 1.5)
        window = np.outer(kernel, kernel.transpose())
        
        mu1 = cv2.filter2D(img1, -1, window)[5:-5, 5:-5]
        mu2 = cv2.filter2D(img2, -1, window)[5:-5, 5:-5]
        mu1_sq = mu1 ** 2
        mu2_sq = mu2 ** 2
        mu1_mu2 = mu1 * mu2
        
        sigma1_sq = cv2.filter2D(img1 ** 2, -1, window)[5:-5, 5:-5] - mu1_sq
        sigma2_sq = cv2.filter2D(img2 ** 2, -1, window)[5:-5, 5:-5] - mu2_sq
        sigma12 = cv2.filter2D(img1 * img2, -1, window)[5:-5, 5:-5] - mu1_mu2
        
        ssim_map = ((2 * mu1_mu2 + C1) * (2 * sigma12 + C2)) / \
                  ((mu1_sq + mu2_sq + C1) * (sigma1_sq + sigma2_sq + C2))
                  
        return ssim_map.mean()
        
    def _calculate_match_score(self, ref_frames, cap_frames):
        """Calculate match score using multiple comparison methods"""
        frame_count = min(len(ref_frames), len(cap_frames))
        if frame_count == 0:
            return 0
            
        total_score = 0
        
        for i in range(frame_count):
            # SSIM comparison
            ssim_score = self._calculate_ssim(ref_frames[i], cap_frames[i])
            
            # Histogram comparison (color distribution)
            hist_score = self._calculate_histogram_similarity(ref_frames[i], cap_frames[i])
            
            # Combined score (weighted)
            frame_score = (0.7 * ssim_score) + (0.3 * hist_score)
            total_score += frame_score
            
        return total_score / frame_count

    def _calculate_histogram_similarity(self, img1, img2):
        """Calculate histogram similarity between two images"""
        hist1 = cv2.calcHist([img1], [0], None, [256], [0, 256])
        hist2 = cv2.calcHist([img2], [0], None, [256], [0, 256])
        
        # Normalize histograms
        cv2.normalize(hist1, hist1, 0, 1, cv2.NORM_MINMAX)
        cv2.normalize(hist2, hist2, 0, 1, cv2.NORM_MINMAX)
        
        # Compare using correlation
        return cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)
        
    def _create_aligned_videos_by_offset(self, reference_path, captured_path, offset_frames):
        """Create trimmed videos aligned to each other based on frame offset"""
        try:
            # Get directory for output
            output_dir = os.path.dirname(reference_path)
            
            # Base names for output files
            ref_base = os.path.splitext(os.path.basename(reference_path))[0]
            cap_base = os.path.splitext(os.path.basename(captured_path))[0]
            
            aligned_ref_path = os.path.join(output_dir, f"{ref_base}_aligned.mp4")
            aligned_cap_path = os.path.join(output_dir, f"{cap_base}_aligned.mp4")
            
            # Get video info
            ref_info = self._get_video_info(reference_path)
            cap_info = self._get_video_info(captured_path)
            
            if not ref_info or not cap_info:
                logger.error("Failed to get video information for alignment")
                return reference_path, captured_path  # Return originals on error
                
            # Determine which video starts later
            if offset_frames > 0:
                # Captured video starts later, trim beginning of reference
                self.status_update.emit(f"Trimming reference video by {offset_frames} frames...")
                
                # Calculate time offset in seconds
                offset_seconds = offset_frames / ref_info.get('frame_rate', 25)
                
                # Use FFmpeg to trim reference video
                cmd = [
                    "ffmpeg", "-y",
                    "-i", reference_path,
                    "-ss", str(offset_seconds),
                    "-c:v", "libx264",
                    "-crf", "18",
                    "-preset", "fast",
                    aligned_ref_path
                ]
                
                subprocess.run(cmd, capture_output=True, check=True)
                
                # Just copy captured video
                cmd = [
                    "ffmpeg", "-y",
                    "-i", captured_path,
                    "-c:v", "copy",
                    aligned_cap_path
                ]
                
                subprocess.run(cmd, capture_output=True, check=True)
                
            else:
                # Reference video starts later or at same time, trim captured
                offset_frames = abs(offset_frames)
                self.status_update.emit(f"Trimming captured video by {offset_frames} frames...")
                
                # Calculate time offset in seconds
                offset_seconds = offset_frames / cap_info.get('frame_rate', 25)
                
                # Use FFmpeg to trim captured video
                cmd = [
                    "ffmpeg", "-y",
                    "-i", captured_path,
                    "-ss", str(offset_seconds),
                    "-c:v", "libx264",
                    "-crf", "18",
                    "-preset", "fast",
                    aligned_cap_path
                ]
                
                subprocess.run(cmd, capture_output=True, check=True)
                
                # Just copy reference video
                cmd = [
                    "ffmpeg", "-y",
                    "-i", reference_path,
                    "-c:v", "copy",
                    aligned_ref_path
                ]
                
                subprocess.run(cmd, capture_output=True, check=True)
                
            # Verify files were created
            if not os.path.exists(aligned_ref_path) or not os.path.exists(aligned_cap_path):
                logger.error("Failed to create aligned videos")
                return reference_path, captured_path  # Return originals on error
                
            return aligned_ref_path, aligned_cap_path
            
        except Exception as e:
            logger.error(f"Error creating aligned videos: {str(e)}")
            return reference_path, captured_path  # Return originals on error



    # Update the _create_aligned_videos_by_trimming method in VideoAligner class
    def _create_aligned_videos_by_trimming(self, reference_path, captured_path, ref_start_trim, ref_end_trim, cap_start_trim, cap_end_trim):
        """
        Create trimmed videos aligned by precise timestamp matching
        """
        try:
            # Get directory for output - specifically use test_results
            script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            test_results_dir = os.path.join(script_dir, "tests", "test_results")
            
            # Create timestamped test folder
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            test_folder = f"alignment_{timestamp}"
            output_dir = os.path.join(test_results_dir, test_folder)
            os.makedirs(output_dir, exist_ok=True)
            
            # Base names for output files
            ref_base = os.path.splitext(os.path.basename(reference_path))[0]
            cap_base = os.path.splitext(os.path.basename(captured_path))[0]
            
            aligned_ref_path = os.path.join(output_dir, f"{ref_base}_aligned.mp4")
            aligned_cap_path = os.path.join(output_dir, f"{cap_base}_aligned.mp4")
            
            # Log the output paths
            logger.info(f"Saving aligned reference to: {aligned_ref_path}")
            logger.info(f"Saving aligned captured to: {aligned_cap_path}")
            
            # Process reference video - in most cases we won't trim the reference
            ref_duration = self._get_video_info(reference_path).get('duration', 0)
            
            # Force-disable reference trimming - only trim captured video
            ref_start_trim = 0
            ref_end_trim = 0
            
            # Just copy the reference
            cmd = [
                "ffmpeg", "-y",
                "-i", reference_path,
                "-c", "copy",
                aligned_ref_path
            ]
            subprocess.run(cmd, capture_output=True, check=True)
            
            # Process captured video - this is what we'll usually trim
            cap_duration = self._get_video_info(captured_path).get('duration', 0)
            
            # Ensure we're actually trimming the captured video
            if cap_start_trim <= 0 and cap_end_trim <= 0:
                logger.warning("No valid trim values for captured video, using SSIM alignment values")
                # Try to get better values using SSIM alignment
                offset_frames, confidence = self._align_ssim(reference_path, captured_path, 60)
                cap_fps = self._get_video_info(captured_path).get('frame_rate', 25)
                cap_start_trim = offset_frames / cap_fps if offset_frames > 0 else 0
                logger.info(f"Using SSIM-based start trim: {cap_start_trim:.3f}s")
            
            # Check if we need to trim captured (almost always true)
            if cap_start_trim > 0 or cap_end_trim > 0:
                self.status_update.emit(f"Trimming captured video by {cap_start_trim:.3f}s at start, {cap_end_trim:.3f}s at end...")
                
                trim_end = cap_duration - cap_end_trim if cap_end_trim > 0 else cap_duration
                duration = trim_end - cap_start_trim
                
                # Only trim if duration is positive
                if duration <= 0:
                    logger.warning(f"Invalid duration ({duration}s) after trimming, using full captured video")
                    cmd = [
                        "ffmpeg", "-y",
                        "-i", captured_path,
                        "-c", "copy",
                        aligned_cap_path
                    ]
                else:
                    # Clear log of trimming command
                    logger.info(f"Trimming captured video from {cap_start_trim:.3f}s to {trim_end:.3f}s (duration: {duration:.3f}s)")
                    
                    # Trim captured video
                    cmd = [
                        "ffmpeg", "-y",
                        "-i", captured_path,
                        "-ss", str(cap_start_trim)
                    ]
                    
                    # Add duration if we're trimming the end
                    if cap_end_trim > 0:
                        cmd.extend(["-t", str(duration)])
                    
                    cmd.extend([
                        "-c:v", "libx264",
                        "-crf", "18",
                        "-preset", "fast",
                        aligned_cap_path
                    ])
                    
                # Execute the command with clear logging
                logger.info(f"Running trim command: {' '.join(cmd)}")
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode != 0:
                    logger.error(f"FFmpeg trim error: {result.stderr}")
                    # Try backup approach with frame-accurate seeking
                    logger.info("Trying alternative trim approach")
                    cmd = [
                        "ffmpeg", "-y",
                        "-i", captured_path,
                        "-ss", str(cap_start_trim),
                        "-c:v", "libx264",
                        "-crf", "18",
                        "-preset", "fast",
                        aligned_cap_path
                    ]
                    subprocess.run(cmd, capture_output=True, check=True)
            else:
                # If no trimming needed for captured, just copy it
                logger.warning("No trimming values specified for captured video, just copying")
                cmd = [
                    "ffmpeg", "-y",
                    "-i", captured_path,
                    "-c", "copy",
                    aligned_cap_path
                ]
                subprocess.run(cmd, capture_output=True, check=True)
            
            # Verify files were created and have content
            if not os.path.exists(aligned_ref_path) or not os.path.exists(aligned_cap_path):
                logger.error("Failed to create aligned videos")
                return reference_path, captured_path  # Return originals on error
                
            if os.path.getsize(aligned_ref_path) == 0 or os.path.getsize(aligned_cap_path) == 0:
                logger.error("Aligned videos are empty")
                return reference_path, captured_path  # Return originals on error
                
            logger.info(f"Alignment complete. Files saved to {output_dir}")
            return aligned_ref_path, aligned_cap_path
            
        except Exception as e:
            logger.error(f"Error creating aligned videos by trimming: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return reference_path, captured_path  # Return originals on error




class AlignmentThread(QThread):
    """Thread for video alignment"""
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
        
        # Connect signals
        self.aligner.alignment_progress.connect(self.alignment_progress)
        self.aligner.alignment_complete.connect(self.alignment_complete)
        self.aligner.error_occurred.connect(self.error_occurred)
        self.aligner.status_update.connect(self.status_update)
        
    def run(self):
        """Run alignment in thread"""
        try:
            self.status_update.emit("Starting alignment process...")
            
            # Verify input files
            if not os.path.exists(self.reference_path):
                self.error_occurred.emit(f"Reference video not found: {self.reference_path}")
                return
                
            if not os.path.exists(self.captured_path):
                self.error_occurred.emit(f"Captured video not found: {self.captured_path}")
                return
            
            # Run alignment
            result = self.aligner.align_videos(
                self.reference_path,
                self.captured_path,
                self.max_offset_seconds
            )
            
            if result:
                self.alignment_complete.emit(result)
                self.status_update.emit("Alignment complete!")
            else:
                self.error_occurred.emit("Alignment failed")
                
        except Exception as e:
            error_msg = f"Error in alignment thread: {str(e)}"
            self.error_occurred.emit(error_msg)
            logger.error(error_msg)