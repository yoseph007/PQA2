import os
import logging
import argparse
from datetime import datetime
import subprocess
import json
import re
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('vmaf_workflow.log')
    ]
)

logger = logging.getLogger(__name__)

def setup_paths():
    """Set up the project paths"""
    # Get the script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Create test results directory
    test_results_dir = os.path.join(script_dir, "tests", "test_results")
    os.makedirs(test_results_dir, exist_ok=True)
    
    return {
        'script_dir': script_dir,
        'test_results_dir': test_results_dir
    }

def create_test_directory(test_name=None):
    """Create a timestamped test directory"""
    paths = setup_paths()
    
    # Generate test name with timestamp if not provided
    if not test_name:
        test_name = "vmaf_test"
    
    # Sanitize test name
    safe_test_name = test_name.replace('/', '_').replace('\\', '_')
    
    # Add timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    test_dir_name = f"{safe_test_name}_{timestamp}"
    
    # Create full path
    test_dir = os.path.join(paths['test_results_dir'], test_dir_name)
    os.makedirs(test_dir, exist_ok=True)
    
    logger.info(f"Created test directory: {test_dir}")
    return test_dir

def extract_timestamps_from_video(video_path, sample_count=10):
    """Extract timestamps from a video to understand its timeline"""
    try:
        import cv2
        import pytesseract
        import numpy as np
        
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
                
            # Crop timestamp area (adjust coordinates based on overlay position)
            timestamp_roi = frame[40:100, 10:400]  # y:y+h, x:x+w
            
            # Convert to grayscale
            gray = cv2.cvtColor(timestamp_roi, cv2.COLOR_BGR2GRAY)
            
            # Apply threshold to make text clearer for OCR
            _, binary = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
            
            # Apply dilation to make text thicker and clearer
            kernel = np.ones((2, 2), np.uint8)
            dilated = cv2.dilate(binary, kernel, iterations=1)
            
            # Use tesseract with specific configuration for timestamps
            text = pytesseract.image_to_string(
                dilated, 
                config='--psm 7 -c tessedit_char_whitelist=0123456789:.'
            )
            
            # Try to parse the timestamp format (HH:MM:SS.microseconds)
            timestamp_str = text.strip()
            
            # Parse timestamp
            match = re.search(r'(\d{2}):(\d{2}):(\d{2})\.(\d+)', timestamp_str)
            if match:
                hours = int(match.group(1))
                minutes = int(match.group(2))
                seconds = int(match.group(3))
                microsec = int(match.group(4).ljust(6, '0')[:6])  # Pad to 6 digits
                total_seconds = hours * 3600 + minutes * 60 + seconds + microsec / 1000000
                
                timestamps.append({
                    'frame': pos,
                    'video_time': pos / fps,
                    'timestamp': total_seconds,
                    'timestamp_str': timestamp_str
                })
                logger.info(f"Frame {pos}: video_time={pos/fps:.3f}s, timestamp={total_seconds:.3f}s ({timestamp_str})")
        
        cap.release()
        return timestamps
        
    except Exception as e:
        logger.error(f"Error extracting timestamps: {str(e)}")
        return []

def add_timestamps_to_video(input_path, output_path):
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

def get_video_info(video_path):
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
        frame_rate = parse_frame_rate(frame_rate_str)
        
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

def parse_frame_rate(frame_rate_str):
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

def normalize_videos(reference_path, captured_path, output_dir):
    """Normalize videos to have the same format/resolution"""
    try:
        # Get video info
        ref_info = get_video_info(reference_path)
        cap_info = get_video_info(captured_path)
        
        if not ref_info or not cap_info:
            logger.error("Failed to get video information")
            return None, None
        
        # Create output paths
        ref_name = os.path.splitext(os.path.basename(reference_path))[0]
        cap_name = os.path.splitext(os.path.basename(captured_path))[0]
        
        normalized_ref_path = os.path.join(output_dir, f"{ref_name}_normalized.mp4")
        normalized_cap_path = os.path.join(output_dir, f"{cap_name}_normalized.mp4")
        
        # Get target parameters from reference video
        target_fps = ref_info.get('frame_rate', 25)
        target_width = ref_info.get('width', 1920)
        target_height = ref_info.get('height', 1080)
        target_res = f"{target_width}x{target_height}"
        target_format = "yuv420p"  # Standard format for VMAF
        
        logger.info(f"Normalizing videos to: {target_fps} fps, {target_res}, {target_format}")
        
        # Normalize reference video (usually just copy)
        cmd = [
            "ffmpeg", "-y",
            "-i", reference_path,
            "-vf", f"fps={target_fps},scale={target_res}:flags=lanczos",
            "-pix_fmt", target_format,
            "-c:v", "libx264",
            "-crf", "18",
            "-preset", "fast",
            normalized_ref_path
        ]
        
        subprocess.run(cmd, check=True)
        
        # Normalize captured video
        cmd = [
            "ffmpeg", "-y",
            "-i", captured_path,
            "-vf", f"fps={target_fps},scale={target_res}:flags=lanczos",
            "-pix_fmt", target_format,
            "-c:v", "libx264",
            "-crf", "18",
            "-preset", "fast",
            normalized_cap_path
        ]
        
        subprocess.run(cmd, check=True)
        
        return normalized_ref_path, normalized_cap_path
        
    except Exception as e:
        logger.error(f"Error normalizing videos: {str(e)}")
        return None, None

def align_videos_by_timestamps(reference_path, captured_path, output_dir):
    """
    Align videos by extracting and matching timestamps
    
    This method is tailored for scenarios with captured videos twice the length of reference videos
    """
    try:
        # First create timestamped versions if they don't already have timestamps
        ref_ts_path = os.path.join(output_dir, "ref_with_ts.mp4")
        cap_ts_path = os.path.join(output_dir, "cap_with_ts.mp4")
        
        # Add timestamps if they don't already exist
        add_timestamps_to_video(reference_path, ref_ts_path)
        add_timestamps_to_video(captured_path, cap_ts_path)
        
        # Extract timestamps from both videos
        logger.info("Extracting timestamps from reference video...")
        ref_timestamps = extract_timestamps_from_video(ref_ts_path, sample_count=15)
        
        logger.info("Extracting timestamps from captured video...")
        cap_timestamps = extract_timestamps_from_video(cap_ts_path, sample_count=30)
        
        if not ref_timestamps or not cap_timestamps:
            logger.error("Failed to extract timestamps from videos")
            return None, None
        
        # Get video info
        ref_info = get_video_info(reference_path)
        cap_info = get_video_info(captured_path)
        
        if not ref_info or not cap_info:
            logger.error("Failed to get video info")
            return None, None
            
        ref_duration = ref_info.get('duration', 0)
        cap_duration = cap_info.get('duration', 0)
        
        # For debugging, log all timestamps
        logger.info("Reference video timestamps:")
        for ts in ref_timestamps:
            logger.info(f"  Frame {ts['frame']}: video_time={ts['video_time']:.3f}s, timestamp={ts['timestamp']:.3f}s")
            
        logger.info("Captured video timestamps:")
        for ts in cap_timestamps:
            logger.info(f"  Frame {ts['frame']}: video_time={ts['video_time']:.3f}s, timestamp={ts['timestamp']:.3f}s")
        
        # Get first and last valid timestamps from reference
        ref_start_timestamp = ref_timestamps[0]['timestamp'] if ref_timestamps else None
        ref_end_timestamp = ref_timestamps[-1]['timestamp'] if ref_timestamps else None
        
        # Find matching timestamps in captured video
        cap_matching_start = None
        cap_matching_end = None
        
        # Since captured video is twice as long as reference, we need to be careful with matching
        for ts in cap_timestamps:
            # Find timestamp in captured closest to reference start
            if ref_start_timestamp is not None:
                if cap_matching_start is None or abs(ts['timestamp'] - ref_start_timestamp) < abs(cap_matching_start['timestamp'] - ref_start_timestamp):
                    cap_matching_start = ts
                    
            # Find timestamp in captured closest to reference end
            if ref_end_timestamp is not None:
                if cap_matching_end is None or abs(ts['timestamp'] - ref_end_timestamp) < abs(cap_matching_end['timestamp'] - ref_end_timestamp):
                    cap_matching_end = ts
        
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
            cap_end_trim = cap_duration - cap_end_time - 0.1  # Add small buffer
            logger.info(f"Trim captured end by {cap_end_trim:.3f}s to match reference timestamp {ref_end_timestamp:.3f}s")
        
        # Create output paths for aligned videos
        ref_name = os.path.splitext(os.path.basename(reference_path))[0]
        cap_name = os.path.splitext(os.path.basename(captured_path))[0]
        
        aligned_ref_path = os.path.join(output_dir, f"{ref_name}_aligned.mp4")
        aligned_cap_path = os.path.join(output_dir, f"{cap_name}_aligned.mp4")
        
        # Copy reference video (we don't trim it in this scenario)
        cmd = [
            "ffmpeg", "-y",
            "-i", reference_path,
            "-c", "copy",
            aligned_ref_path
        ]
        subprocess.run(cmd, check=True)
        
        # Trim captured video to match reference
        trim_end = cap_duration - cap_end_trim if cap_end_trim > 0 else cap_duration
        duration = trim_end - cap_start_trim
        
        # Ensure positive duration
        if duration <= 0:
            logger.warning("Invalid captured trim values, using original captured")
            # Just copy the captured
            cmd = [
                "ffmpeg", "-y",
                "-i", captured_path,
                "-c", "copy",
                aligned_cap_path
            ]
            subprocess.run(cmd, check=True)
        else:
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
            
            subprocess.run(cmd, check=True)
        
        return aligned_ref_path, aligned_cap_path
        
    except Exception as e:
        logger.error(f"Error aligning videos by timestamps: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return None, None

def run_vmaf_analysis(reference_path, distorted_path, output_json):
    """Run VMAF analysis on aligned videos"""
    try:
        # Build FFmpeg command
        cmd = [
            "ffmpeg", "-y",
            "-i", distorted_path,
            "-i", reference_path,
            "-lavfi", f"libvmaf=model_path=vmaf_v0.6.1.json:log_path={output_json}:log_fmt=json:psnr=1:ssim=1",
            "-f", "null",
            "-"
        ]
        
        logger.info(f"Running VMAF analysis: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        if result.returncode != 0:
            logger.error(f"VMAF analysis failed: {result.stderr}")
            return None
            
        # Extract VMAF score from output
        vmaf_score = None
        match = re.search(r'VMAF score: (\d+\.\d+)', result.stderr)
        if match:
            vmaf_score = float(match.group(1))
            
        # Load and parse results file
        if os.path.exists(output_json):
            with open(output_json, 'r') as f:
                results = json.load(f)
                
            logger.info(f"VMAF analysis complete, score: {vmaf_score}")
            return results
        else:
            logger.error(f"VMAF results file not found: {output_json}")
            return None
            
    except Exception as e:
        logger.error(f"Error in VMAF analysis: {str(e)}")
        return None

def main():
    """Main function to run the VMAF workflow"""
    parser = argparse.ArgumentParser(description='VMAF Workflow for twice-as-long captured videos')
    parser.add_argument('reference', help='Path to reference video')
    parser.add_argument('captured', help='Path to captured video (double length)')
    parser.add_argument('--test-name', help='Optional test name for results')
    
    args = parser.parse_args()
    
    # Check if files exist
    if not os.path.exists(args.reference):
        logger.error(f"Reference video not found: {args.reference}")
        return 1
        
    if not os.path.exists(args.captured):
        logger.error(f"Captured video not found: {args.captured}")
        return 1
    
    # Create test directory
    test_dir = create_test_directory(args.test_name)
    
    # Copy original files to test directory
    ref_name = os.path.basename(args.reference)
    cap_name = os.path.basename(args.captured)
    
    ref_copy_path = os.path.join(test_dir, ref_name)
    cap_copy_path = os.path.join(test_dir, cap_name)
    
    # Copy files
    import shutil
    shutil.copy2(args.reference, ref_copy_path)
    shutil.copy2(args.captured, cap_copy_path)
    
    logger.info(f"Copied original files to test directory")
    
    # Normalize videos
    logger.info("Normalizing videos...")
    norm_ref_path, norm_cap_path = normalize_videos(
        ref_copy_path,
        cap_copy_path,
        test_dir
    )
    
    if not norm_ref_path or not norm_cap_path:
        logger.error("Normalization failed")
        return 1
    
    # Align videos based on timestamps
    logger.info("Aligning videos by timestamps...")
    aligned_ref_path, aligned_cap_path = align_videos_by_timestamps(
        norm_ref_path,
        norm_cap_path,
        test_dir
    )
    
    if not aligned_ref_path or not aligned_cap_path:
        logger.error("Alignment failed")
        return 1
    
    # Run VMAF analysis
    logger.info("Running VMAF analysis...")
    vmaf_output = os.path.join(test_dir, "vmaf_results.json")
    
    results = run_vmaf_analysis(
        aligned_ref_path,
        aligned_cap_path,
        vmaf_output
    )
    
    if not results:
        logger.error("VMAF analysis failed")
        return 1
    
    # Extract and display VMAF score
    if 'pooled_metrics' in results:
        vmaf_score = results['pooled_metrics'].get('vmaf', {}).get('mean', 0)
        logger.info(f"==================================")
        logger.info(f"VMAF Score: {vmaf_score:.2f}")
        logger.info(f"==================================")
        
        # Save a summary file
        summary_path = os.path.join(test_dir, "summary.txt")
        with open(summary_path, 'w') as f:
            f.write(f"Reference video: {ref_name}\n")
            f.write(f"Captured video: {cap_name}\n")
            f.write(f"VMAF Score: {vmaf_score:.2f}\n")
            
            # Add timestamp details
            f.write("\nAlignment Details:\n")
            ref_info = get_video_info(aligned_ref_path)
            cap_info = get_video_info(aligned_cap_path)
            
            if ref_info and cap_info:
                f.write(f"Aligned reference duration: {ref_info['duration']:.2f} seconds\n")
                f.write(f"Aligned captured duration: {cap_info['duration']:.2f} seconds\n")
                
                # Extract timestamps from aligned videos for verification
                ref_ts_path = os.path.join(test_dir, "aligned_ref_with_ts.mp4")
                cap_ts_path = os.path.join(test_dir, "aligned_cap_with_ts.mp4")
                
                add_timestamps_to_video(aligned_ref_path, ref_ts_path)
                add_timestamps_to_video(aligned_cap_path, cap_ts_path)
                
                ref_timestamps = extract_timestamps_from_video(ref_ts_path, sample_count=5)
                cap_timestamps = extract_timestamps_from_video(cap_ts_path, sample_count=5)
                
                if ref_timestamps and cap_timestamps:
                    f.write("\nTimestamp Comparison:\n")
                    f.write("Reference video timestamps:\n")
                    for ts in ref_timestamps:
                        f.write(f"  Frame {ts['frame']}: video_time={ts['video_time']:.3f}s, timestamp={ts['timestamp']:.3f}s\n")
                    
                    f.write("\nCaptured video timestamps:\n")
                    for ts in cap_timestamps:
                        f.write(f"  Frame {ts['frame']}: video_time={ts['video_time']:.3f}s, timestamp={ts['timestamp']:.3f}s\n")
        
        logger.info(f"Results saved to: {test_dir}")
        return 0
    else:
        logger.error("Invalid VMAF results format")
        return 1

if __name__ == "__main__":
    sys.exit(main())