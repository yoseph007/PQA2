import os
import subprocess
import cv2
import numpy as np
import logging
import time
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

def get_video_info(video_path):
    """
    Get detailed information about a video file using FFprobe
    
    Args:
        video_path: Path to the video file
        
    Returns:
        Dictionary with video information or None if there was an error
    """
    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format", 
            "-show_streams",
            "-count_frames",
            video_path
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        
        import json
        info = json.loads(result.stdout)
        
        # Find video stream
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
            'pix_fmt': pix_fmt
        }
            
    except Exception as e:
        logger.error(f"Error getting video info for {video_path}: {str(e)}")
        return None





def trim_video_frame_accurate(input_path, output_path, start_frame, frame_count, frame_rate):
    """
    Trim video with frame-perfect accuracy
    
    Args:
        input_path: Path to input video
        output_path: Path to output video
        start_frame: First frame to include
        frame_count: Number of frames to include
        frame_rate: Frame rate of the video
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Calculate precise start time in seconds
        start_time = start_frame / frame_rate
        
        # Calculate exact duration based on frame count
        duration = frame_count / frame_rate
        
        # Build FFmpeg command for frame-accurate trimming
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-vf", f"select='between(n,{start_frame},{start_frame+frame_count-1})'," 
                   f"setpts=N/{frame_rate}/TB",
            "-vsync", "0",
            "-c:v", "libx264",
            "-preset", "slow",
            "-crf", "18",
            output_path
        ]
        
        # Execute command
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        
        logger.debug(f"FFmpeg trim command complete for {output_path}")
        
        # Verify the output has the correct frame count
        output_info = get_video_info(output_path)
        if output_info and output_info.get('frame_count', 0) != frame_count:
            logger.warning(
                f"Trimmed video has {output_info.get('frame_count')} frames, " + 
                f"expected {frame_count}"
            )
        
        return True
        
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg trim failed: {e.stderr}")
        return False
    except Exception as e:
        logger.error(f"Error trimming video: {str(e)}")
        return False





def force_exact_frame_count(input_path, output_path, target_frames, frame_rate):
    """
    Force a video to have exactly the specified number of frames
    by re-encoding frame by frame
    
    Args:
        input_path: Path to input video
        output_path: Path to output video
        target_frames: Exact number of frames required
        frame_rate: Frame rate to use
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Check input video
        input_info = get_video_info(input_path)
        if not input_info:
            logger.error("Cannot get input video info")
            return False
            
        # Determine frames to extract
        input_frames = input_info.get('frame_count', 0)
        
        if input_frames < target_frames:
            logger.warning(f"Input has fewer frames ({input_frames}) than target ({target_frames})")
            # We'll need to duplicate some frames or adjust frame rate
            
        # Use FFmpeg to force exact frame count with a complex filter
        cmd = [
            "ffmpeg",
            "-y",
            "-i", input_path,
            "-an",                     # No audio
            "-c:v", "libx264",         # H.264 codec
            "-preset", "slow",         # Higher quality encoding
            "-crf", "18",              # High quality
            "-vf", f"select=1,setpts=N/({frame_rate}*TB)",  # Force consistent timing
            "-frames:v", str(target_frames),  # Exact frame count
            "-r", str(frame_rate),     # Force exact frame rate
            "-vsync", "0",             # Preserve frame timing
            output_path
        ]
        
        # Execute command
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        
        # Verify the output
        output_info = get_video_info(output_path)
        if output_info and output_info.get('frame_count', 0) != target_frames:
            logger.warning(
                f"Failed to force frame count: output has {output_info.get('frame_count')} frames, " + 
                f"expected {target_frames}"
            )
            return False
            
        return True
        
    except Exception as e:
        logger.error(f"Error forcing frame count: {str(e)}")
        return False

def extract_video_features(video_path, feature_type="orb", max_frames=10):
    """
    Extract features from video frames for matching
    
    Args:
        video_path: Path to video file
        feature_type: Type of features to extract ('orb', 'sift', 'phase')
        max_frames: Maximum number of frames to sample
        
    Returns:
        List of tuples (frame_idx, features) or None on error
    """
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            logger.error(f"Cannot open video: {video_path}")
            return None
            
        # Get video properties
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        # Determine frame sampling interval
        if frame_count <= max_frames:
            # Use all frames if there are fewer than max_frames
            sample_interval = 1
        else:
            sample_interval = max(1, frame_count // max_frames)
            
        # Create feature detector
        if feature_type == "orb":
            detector = cv2.ORB_create(nfeatures=1000)
        elif feature_type == "sift":
            detector = cv2.SIFT_create()
        else:
            detector = cv2.ORB_create()  # Default to ORB
        
        # Extract features from sampled frames
        frame_features = []
        
        for frame_idx in range(0, frame_count, sample_interval):
            # Set frame position
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            
            # Read frame
            ret, frame = cap.read()
            if not ret:
                continue
                
            # Convert to grayscale
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # Resize for faster processing
            resized = cv2.resize(gray, (640, 360))
            
            # Extract features
            if feature_type == "phase":
                # For phase correlation, just store the frame
                frame_features.append((frame_idx, resized))
            else:
                # For keypoint-based methods
                keypoints, descriptors = detector.detectAndCompute(resized, None)
                if descriptors is not None and len(descriptors) > 10:
                    frame_features.append((frame_idx, keypoints, descriptors))
        
        cap.release()
        
        if len(frame_features) == 0:
            logger.warning(f"No features extracted from {video_path}")
            return None
            
        return frame_features
        
    except Exception as e:
        logger.error(f"Error extracting features: {str(e)}")
        return None

def calculate_frame_offset_orb(ref_features, cap_features, max_offset=300):
    """
    Calculate frame offset using ORB features
    
    Args:
        ref_features: Features from reference video frames
        cap_features: Features from captured video frames
        max_offset: Maximum offset to consider
        
    Returns:
        (best_offset, confidence_score)
    """
    if not ref_features or not cap_features:
        return 0, 0
        
    # Create feature matcher
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    
    # Try different offsets
    best_offset = 0
    best_score = -1
    
    # Track progress
    total_tests = 2 * max_offset + 1
    progress_interval = max(1, total_tests // 10)
    
    for progress_idx, offset in enumerate(range(-max_offset, max_offset+1)):
        # Report progress occasionally
        if progress_idx % progress_interval == 0:
            logger.debug(f"Testing offset {offset}/{max_offset} ({100*progress_idx/total_tests:.1f}%)")
            
        # For each offset, match multiple frame pairs
        total_matches = 0
        valid_comparisons = 0
        
        for ref_idx, ref_kp, ref_desc in ref_features:
            # Calculate corresponding captured frame index
            cap_idx = ref_idx + offset
            
            # Find the closest captured frame index in our samples
            closest_cap_idx = None
            closest_cap_diff = float('inf')
            
            for c_idx, _, _ in cap_features:
                diff = abs(cap_idx - c_idx)
                if diff < closest_cap_diff:
                    closest_cap_diff = diff
                    closest_cap_idx = c_idx
            
            # Skip if we don't have a close match or it's too far away
            if closest_cap_idx is None or closest_cap_diff > 5:
                continue
                
            # Get the captured frame features
            cap_data = next((item for item in cap_features if item[0] == closest_cap_idx), None)
            if not cap_data:
                continue
                
            # Extract features
            _, cap_kp, cap_desc = cap_data
            
            # Match features
            matches = matcher.match(ref_desc, cap_desc)
            
            # Filter good matches
            good_matches = [m for m in matches if m.distance < 50]
            
            # Add to score
            total_matches += len(good_matches)
            valid_comparisons += 1
        
        # Calculate average match score for this offset
        if valid_comparisons > 0:
            avg_score = total_matches / valid_comparisons
            
            # Update best score
            if avg_score > best_score:
                best_score = avg_score
                best_offset = offset
                
    logger.info(f"Best frame offset: {best_offset} with score {best_score:.2f}")
    return best_offset, best_score

def calculate_frame_offset_phase(ref_features, cap_features, max_offset=300):
    """
    Calculate frame offset using phase correlation
    
    Args:
        ref_features: Frames from reference video
        cap_features: Frames from captured video
        max_offset: Maximum offset to consider
        
    Returns:
        (best_offset, confidence_score)
    """
    if not ref_features or not cap_features:
        return 0, 0
        
    # Extract just frames from features
    ref_frames = [frame for _, frame in ref_features]
    cap_frames = [frame for _, frame in cap_features]
    
    # Calculate phase correlation for each frame pair
    best_offset = 0
    best_score = -1
    
    # Try different offsets
    total_tests = 2 * max_offset + 1
    progress_interval = max(1, total_tests // 10)
    
    for progress_idx, offset in enumerate(range(-max_offset, max_offset+1)):
        # Report progress occasionally
        if progress_idx % progress_interval == 0:
            logger.debug(f"Testing offset {offset}/{max_offset} ({100*progress_idx/total_tests:.1f}%)")
            
        # For each offset, match multiple frame pairs
        total_score = 0
        valid_comparisons = 0
        
        for i, ref_frame in enumerate(ref_frames):
            # Calculate corresponding captured frame index with offset
            cap_idx = i + offset
            
            # Skip if outside bounds
            if cap_idx < 0 or cap_idx >= len(cap_frames):
                continue
                
            # Get captured frame
            cap_frame = cap_frames[cap_idx]
            
            # Calculate phase correlation
            # First make sure the frames are the same size
            if ref_frame.shape != cap_frame.shape:
                continue
                
            # Calculate cross-power spectrum
            ref_fft = np.fft.fft2(ref_frame)
            cap_fft = np.fft.fft2(cap_frame)
            cross_power = (ref_fft * np.conj(cap_fft)) / (np.abs(ref_fft) * np.abs(cap_fft) + 1e-10)
            
            # Inverse FFT and get correlation peak
            correlation = np.abs(np.fft.ifft2(cross_power))
            peak = np.max(correlation)
            
            # Add to score
            total_score += peak
            valid_comparisons += 1
        
        # Calculate average score for this offset
        if valid_comparisons > 0:
            avg_score = total_score / valid_comparisons
            
            # Update best score
            if avg_score > best_score:
                best_score = avg_score
                best_offset = offset
                
    logger.info(f"Best frame offset (phase): {best_offset} with score {best_score:.2f}")
    return best_offset, best_score

def find_precise_frame_offset(reference_path, captured_path, max_offset=300):
    """
    Find the precise frame offset between reference and captured videos
    using multiple methods and taking the most confident result
    
    Args:
        reference_path: Path to reference video
        captured_path: Path to captured video
        max_offset: Maximum frame offset to consider
        
    Returns:
        Best frame offset (positive if captured starts after reference)
    """
    logger.info(f"Finding precise frame offset between videos")
    start_time = time.time()
    
    # Extract features from both videos
    logger.debug("Extracting ORB features from reference video")
    ref_orb_features = extract_video_features(reference_path, feature_type="orb", max_frames=15)
    
    logger.debug("Extracting ORB features from captured video")
    cap_orb_features = extract_video_features(captured_path, feature_type="orb", max_frames=15)
    
    logger.debug("Extracting phase correlation frames from reference video")
    ref_phase_features = extract_video_features(reference_path, feature_type="phase", max_frames=10)
    
    logger.debug("Extracting phase correlation frames from captured video")
    cap_phase_features = extract_video_features(captured_path, feature_type="phase", max_frames=10)
    
    # Calculate offset using different methods
    offset_orb, score_orb = calculate_frame_offset_orb(
        ref_orb_features, cap_orb_features, max_offset=max_offset
    )
    
    offset_phase, score_phase = calculate_frame_offset_phase(
        ref_phase_features, cap_phase_features, max_offset=max_offset
    )
    
    # Determine the most reliable result
    logger.info(f"ORB offset: {offset_orb} (score: {score_orb:.2f})")
    logger.info(f"Phase offset: {offset_phase} (score: {score_phase:.2f})")
    
    # Choose the method with the highest confidence
    # For phase correlation, normalize the score
    normalized_phase_score = score_phase * 0.8  # Weight phase correlation slightly lower
    
    if score_orb > normalized_phase_score:
        best_offset = offset_orb
        logger.info(f"Selected ORB offset as more reliable")
    else:
        best_offset = offset_phase
        logger.info(f"Selected phase correlation offset as more reliable")
    
    elapsed = time.time() - start_time
    logger.info(f"Frame offset detection took {elapsed:.2f} seconds, result: {best_offset}")
    
    return best_offset

def align_videos_frame_perfect(reference_path, captured_path, target_duration=None, output_dir=None):
    """
    Create perfectly aligned videos with exact same frame count and duration
    
    Args:
        reference_path: Path to reference video
        captured_path: Path to captured video
        target_duration: Desired duration in seconds (or None for full video)
        output_dir: Output directory for aligned videos
        
    Returns:
        Tuple of (aligned_reference_path, aligned_captured_path) or (None, None) on error
    """
    try:
        logger.info(f"Starting frame-perfect alignment of videos")
        start_time = time.time()
        
        # Create temporary directory for processing
        import tempfile
        temp_dir = tempfile.mkdtemp()
        temp_files = []
        
        # Get video information
        ref_info = get_video_info(reference_path)
        cap_info = get_video_info(captured_path)
        
        if not ref_info or not cap_info:
            logger.error("Failed to get video information")
            return None, None
            
        # Get frame rate from reference
        frame_rate = ref_info.get('frame_rate', 25)
        
        # Calculate exact frame count for target duration
        if target_duration:
            target_frames = int(round(target_duration * frame_rate))
            logger.info(f"Target duration: {target_duration}s = {target_frames} frames")
        else:
            # For full video, use minimum of both videos
            ref_frames = ref_info.get('frame_count', int(ref_info.get('duration', 0) * frame_rate))
            cap_frames = cap_info.get('frame_count', int(cap_info.get('duration', 0) * frame_rate))
            target_frames = min(ref_frames, cap_frames)
            logger.info(f"Using full video duration: {target_frames} frames")
        
        # Determine precise frame offset using feature matching
        offset_frames = find_precise_frame_offset(reference_path, captured_path)
        logger.info(f"Detected precise frame offset: {offset_frames}")
        
        # Determine which video starts later
        if offset_frames > 0:
            # Captured starts later than reference
            ref_start_frame = offset_frames
            cap_start_frame = 0
            logger.info(f"Captured video starts {offset_frames} frames after reference")
        else:
            # Reference starts later than captured
            ref_start_frame = 0
            cap_start_frame = abs(offset_frames)
            logger.info(f"Reference video starts {abs(offset_frames)} frames after captured")
        
        # Create output filenames
        ref_basename = os.path.splitext(os.path.basename(reference_path))[0]
        cap_basename = os.path.splitext(os.path.basename(captured_path))[0]
        
        if output_dir is None:
            output_dir = os.path.dirname(reference_path)
            logger.debug(f"Using default output directory: {output_dir}")
        
        # Generate temporary file paths
        temp_ref_aligned = os.path.join(temp_dir, f"{ref_basename}_aligned_temp.mp4")
        temp_cap_aligned = os.path.join(temp_dir, f"{cap_basename}_aligned_temp.mp4")
        temp_files.extend([temp_ref_aligned, temp_cap_aligned])
        
        # Create aligned files with EXACT frame count
        logger.info(f"Trimming reference video: start={ref_start_frame}, frames={target_frames}")
        ref_success = trim_video_frame_accurate(
            reference_path,
            temp_ref_aligned,
            ref_start_frame,
            target_frames,
            frame_rate
        )
        
        logger.info(f"Trimming captured video: start={cap_start_frame}, frames={target_frames}")
        cap_success = trim_video_frame_accurate(
            captured_path,
            temp_cap_aligned,
            cap_start_frame,
            target_frames,
            frame_rate
        )
        
        if not ref_success or not cap_success:
            logger.error("Failed to trim videos accurately")
            return None, None
        
        # Verify both videos have identical frame counts and durations
        ref_aligned_info = get_video_info(temp_ref_aligned)
        cap_aligned_info = get_video_info(temp_cap_aligned)
        
        if not ref_aligned_info or not cap_aligned_info:
            logger.error("Failed to get info for aligned videos")
            return None, None
            
        logger.info(f"Aligned reference: {ref_aligned_info.get('frame_count')} frames, {ref_aligned_info.get('duration'):.2f}s")
        logger.info(f"Aligned captured: {cap_aligned_info.get('frame_count')} frames, {cap_aligned_info.get('duration'):.2f}s")
        
        # Check if we need to force exact frame count
        if ref_aligned_info.get('frame_count') != target_frames or cap_aligned_info.get('frame_count') != target_frames:
            logger.warning(f"Frame count mismatch. Target: {target_frames}, " +
                         f"Reference: {ref_aligned_info.get('frame_count')}, " +
                         f"Captured: {cap_aligned_info.get('frame_count')}")
            
            # Force exact frame count if needed
            if ref_aligned_info.get('frame_count') != target_frames:
                logger.info(f"Forcing exact frame count for reference video")
                temp_ref_fixed = os.path.join(temp_dir, f"{ref_basename}_fixed_temp.mp4")
                temp_files.append(temp_ref_fixed)
                
                force_exact_frame_count(temp_ref_aligned, temp_ref_fixed, target_frames, frame_rate)
                temp_ref_aligned = temp_ref_fixed
            
            if cap_aligned_info.get('frame_count') != target_frames:
                logger.info(f"Forcing exact frame count for captured video")
                temp_cap_fixed = os.path.join(temp_dir, f"{cap_basename}_fixed_temp.mp4")
                temp_files.append(temp_cap_fixed)
                
                force_exact_frame_count(temp_cap_aligned, temp_cap_fixed, target_frames, frame_rate)
                temp_cap_aligned = temp_cap_fixed
        
        # Create final output paths
        aligned_ref_path = os.path.join(output_dir, f"{ref_basename}_aligned.mp4")
        aligned_cap_path = os.path.join(output_dir, f"{cap_basename}_aligned.mp4")
        
        # Copy temporary files to final destination
        os.makedirs(output_dir, exist_ok=True)
        shutil.copy2(temp_ref_aligned, aligned_ref_path)
        shutil.copy2(temp_cap_aligned, aligned_cap_path)
        
        logger.info(f"Created aligned reference: {aligned_ref_path}")
        logger.info(f"Created aligned captured: {aligned_cap_path}")
        
        # Final verification
        final_ref_info = get_video_info(aligned_ref_path)
        final_cap_info = get_video_info(aligned_cap_path)
        
        if not final_ref_info or not final_cap_info:
            logger.error("Failed to verify final aligned videos")
        else:
            logger.info(f"Final aligned videos: {final_ref_info.get('frame_count')} frames, {final_ref_info.get('duration'):.2f}s")
        
        # Clean up temp files
        for file_path in temp_files:
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
        
        # Remove temporary directory
        try:
            shutil.rmtree(temp_dir)
        except:
            pass
            
        elapsed = time.time() - start_time
        logger.info(f"Frame-perfect alignment completed in {elapsed:.2f} seconds")
        
        return aligned_ref_path, aligned_cap_path
        
    except Exception as e:
        logger.error(f"Error in frame-perfect alignment: {str(e)}")
        return None, None
