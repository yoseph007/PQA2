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
                "-vf", "drawtext=text='%{pts\\:hms\\:6}':x=10:y=50:fontsize=36:fontcolor=white:box=1:boxcolor=black",
                "-c:a", "copy",
                output_path
            ]
            subprocess.run(cmd, check=True)
            return output_path
        except Exception as e:
            logger.error(f"Timestamp overlay failed: {str(e)}")
            return input_path

    def _read_frame_timestamp(self, frame):
        """Read timestamp from frame using OCR (requires pytesseract)"""
        try:
            import pytesseract
            # Crop timestamp area (adjust coordinates based on overlay position)
            timestamp_roi = frame[40:80, 10:400]  # y:y+h, x:x+w
            gray = cv2.cvtColor(timestamp_roi, cv2.COLOR_BGR2GRAY)
            # Apply threshold to make text clearer for OCR
            _, binary = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
            text = pytesseract.image_to_string(binary, config='--psm 7 -c tessedit_char_whitelist=0123456789:.')
            # Extract time in seconds from format like 00:00:12.500000
            parts = text.strip().split(':')
            if len(parts) == 3:
                try:
                    hours = int(parts[0])
                    minutes = int(parts[1])
                    seconds = float(parts[2])
                    total_seconds = hours * 3600 + minutes * 60 + seconds
                    return total_seconds
                except ValueError:
                    pass
            return None
        except ImportError:
            logger.error("pytesseract not installed")
            return None
        except Exception as e:
            logger.error(f"Error reading timestamp: {str(e)}")
            return None

    def _align_ssim(self, reference_path, captured_path, max_offset_frames):
        """
        Align videos using SSIM (Structural Similarity Index) with timestamp verification
        Returns: (offset_frames, confidence)
        """
        try:
            # First create timestamped versions for verification
            timestamp_dir = os.path.dirname(reference_path)
            ref_ts_path = os.path.join(timestamp_dir, "ref_with_ts.mp4")
            cap_ts_path = os.path.join(timestamp_dir, "cap_with_ts.mp4")
            
            self._add_timestamps_to_video(reference_path, ref_ts_path)
            self._add_timestamps_to_video(captured_path, cap_ts_path)
            
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
            
            # Verify and refine using timestamps if OCR is available
            try:
                # Only proceed with timestamp verification if we found a reasonable match
                if best_score > 0.5:
                    logger.info(f"Initial alignment: {best_offset} frames, score: {best_score:.3f}")
                    logger.info("Verifying with timestamps...")
                    refined_offset = self._verify_with_timestamps(ref_ts_path, cap_ts_path, best_offset)
                    if refined_offset is not None:
                        logger.info(f"Refined alignment using timestamps: {refined_offset} frames")
                        best_offset = refined_offset
            except Exception as e:
                logger.warning(f"Timestamp verification failed: {str(e)}")
                # Continue with SSIM-based offset if timestamp verification fails
            
            # Clean up
            ref_cap.release()
            cap_cap.release()
            
            # Complete progress
            self.alignment_progress.emit(100)
            
            return best_offset, best_score
            
        except Exception as e:
            logger.error(f"Error in SSIM alignment: {str(e)}")
            return 0, 0

    def _verify_with_timestamps(self, ref_path, cap_path, initial_offset):
        """Improve offset accuracy using timestamp OCR"""
        import pytesseract
        try:
            ref_cap = cv2.VideoCapture(ref_path)
            cap_cap = cv2.VideoCapture(cap_path)
            
            if not ref_cap.isOpened() or not cap_cap.isOpened():
                logger.error("Failed to open timestamped videos for verification")
                return initial_offset
            
            # Get frame rates to convert between frame offsets and time offsets
            ref_fps = ref_cap.get(cv2.CAP_PROP_FPS)
            cap_fps = cap_cap.get(cv2.CAP_PROP_FPS)
            
            if ref_fps <= 0 or cap_fps <= 0:
                logger.warning("Invalid frame rates, using default of 25 fps")
                ref_fps = cap_fps = 25
            
            # Sample middle frames for better reliability
            sample_points = [0.25, 0.5, 0.75]  # Sample at 25%, 50%, and 75% of the video
            timestamp_offsets = []
            
            # Convert initial frame offset to time offset (in seconds)
            initial_time_offset = initial_offset / ref_fps
            
            ref_frame_count = int(ref_cap.get(cv2.CAP_PROP_FRAME_COUNT))
            cap_frame_count = int(cap_cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            for point in sample_points:
                # Calculate frame indices
                ref_frame_idx = int(ref_frame_count * point)
                # Calculate where we expect the captured frame to be based on initial offset
                cap_frame_idx = int(ref_frame_idx + initial_offset)
                
                # Skip if out of range
                if cap_frame_idx >= cap_frame_count:
                    continue
                
                # Read reference frame and its timestamp
                ref_cap.set(cv2.CAP_PROP_POS_FRAMES, ref_frame_idx)
                ret_ref, ref_frame = ref_cap.read()
                if not ret_ref:
                    continue
                
                # Read captured frame and its timestamp
                cap_cap.set(cv2.CAP_PROP_POS_FRAMES, cap_frame_idx)
                ret_cap, cap_frame = cap_cap.read()
                if not ret_cap:
                    continue
                
                # Extract timestamps using OCR
                ref_ts = self._read_frame_timestamp(ref_frame)
                cap_ts = self._read_frame_timestamp(cap_frame)
                
                # If both timestamps were read successfully
                if ref_ts is not None and cap_ts is not None:
                    # Calculate time offset
                    time_offset = cap_ts - ref_ts
                    # Convert time offset to frame offset
                    frame_offset = int(time_offset * ref_fps)
                    timestamp_offsets.append(frame_offset)
                    logger.info(f"Sample point {point:.2f}: Ref TS={ref_ts:.6f}, Cap TS={cap_ts:.6f}, Offset={frame_offset} frames")
            
            # If we have at least one valid timestamp offset
            if timestamp_offsets:
                # Use median to avoid outliers
                refined_offset = int(np.median(timestamp_offsets))
                logger.info(f"Timestamp offsets (frames): {timestamp_offsets}")
                logger.info(f"Median timestamp offset: {refined_offset} frames")
                return refined_offset
            else:
                logger.warning("No valid timestamp pairs found, using SSIM-based offset")
                return initial_offset
                
        except ImportError:
            logger.warning("pytesseract not installed, timestamp verification skipped")
            return initial_offset
        except Exception as e:
            logger.error(f"Error in timestamp verification: {str(e)}")
            return initial_offset
        finally:
            # Clean up
            if 'ref_cap' in locals():
                ref_cap.release()
            if 'cap_cap' in locals():
                cap_cap.release()

    def align_videos(self, reference_path, captured_path, max_offset_seconds=5):
        """
        Align two videos and return the frame offset
        
        Returns a dictionary with:
        - offset_frames: Frame offset (positive if captured starts after reference)
        - offset_seconds: Time offset in seconds
        - aligned_reference: Path to trimmed reference video
        - aligned_captured: Path to trimmed captured video
        """
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
                    
            # Calculate maximum offset frames - use a safe default if frame_rate is missing or zero
            fps = ref_info.get('frame_rate', 25)
            if fps <= 0:
                fps = 25  # Default to 25 fps if invalid
                
            max_offset_frames = int(max_offset_seconds * fps)
            
            self.status_update.emit(f"Aligning videos (max offset: {max_offset_frames} frames)...")
            self.alignment_progress.emit(0)
            
            # Try SSIM-based alignment with timestamp verification
            offset_frames, confidence = self._align_ssim(
                reference_path, 
                captured_path, 
                max_offset_frames
            )
            
            # Log alignment results
            self.status_update.emit(f"Alignment complete. Offset: {offset_frames} frames, confidence: {confidence:.2f}")
            logger.info(f"Alignment result: {offset_frames} frames, confidence: {confidence}")
            
            # Check if alignment seems valid
            if confidence < 0.5:
                logger.warning(f"Low alignment confidence: {confidence}")
                
            # Prepare trimmed/aligned videos
            aligned_reference, aligned_captured = self._create_aligned_videos(
                reference_path,
                captured_path,
                offset_frames
            )
            
            # Prepare result object
            result = {
                'offset_frames': offset_frames,
                'offset_seconds': offset_frames / fps if fps > 0 else 0,
                'confidence': confidence,
                'aligned_reference': aligned_reference,
                'aligned_captured': aligned_captured
            }
            
            self.alignment_complete.emit(result)
            return result
            
        except IndexError as e:
            # Handle index errors explicitly
            error_msg = f"Index error during alignment: {str(e)}"
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            return None
        except Exception as e:
            error_msg = f"Error aligning videos: {str(e)}"
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            return None
            
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
        
    def _create_aligned_videos(self, reference_path, captured_path, offset_frames):
        """Create trimmed videos aligned to each other"""
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