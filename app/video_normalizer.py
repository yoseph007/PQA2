import subprocess
import logging
import os
import json
import re
import time
from datetime import datetime

logger = logging.getLogger(__name__)


def normalize_videos_for_comparison(reference_path, captured_path, output_dir=None):
    """
    Normalize two videos to have the same framerate, color format, and resolution
    for accurate VMAF comparison. Never downgrade quality if capture is higher quality.
    """
    if output_dir is None:
        output_dir = os.path.dirname(reference_path)
        
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    # Get video information
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
    
    # KEY CHANGE: Always use reference video parameters as the target
    # This ensures we're evaluating the capture against the reference standard
    target_fps = ref_info.get('frame_rate', 25)
    target_width = ref_info.get('width', 1920)
    target_height = ref_info.get('height', 1080)
    target_res = f"{target_width}x{target_height}"
    target_format = "yuv420p"  # Standard format for VMAF
    
    logger.info(f"Normalizing videos to match reference: {target_fps} fps, {target_res}, {target_format}")
    
    # Copy reference video if it's already in the right format
    if ref_info.get('pix_fmt') == target_format:
        copy_video(reference_path, normalized_ref_path)
        logger.info("Reference video already in correct format, copying")
    else:
        # Just convert pixel format if needed
        normalize_video(
            reference_path, 
            normalized_ref_path, 
            target_fps, 
            target_res, 
            target_format,
            high_quality=True
        )
    
    # For captured video, use high quality settings to avoid degradation
    normalize_video(
        captured_path, 
        normalized_cap_path, 
        target_fps, 
        target_res, 
        target_format,
        high_quality=True
    )
    
    # Verify both files were created
    if not os.path.exists(normalized_ref_path) or not os.path.exists(normalized_cap_path):
        logger.error("Failed to create normalized videos")
        return None, None
        
    return normalized_ref_path, normalized_cap_path


def normalize_video(input_path, output_path, target_fps, target_res, target_format, high_quality=False):
    """Normalize a video to the specified parameters with quality preservation"""
    try:
        # Build FFmpeg command with quality settings
        cmd = [
            "ffmpeg",
            "-y",  # Overwrite output
            "-i", input_path
        ]
        
        # Add high quality scaling filters
        if high_quality:
            # Use high quality scaler
            filter_complex = f"fps={target_fps},scale={target_res}:flags=lanczos"
        else:
            filter_complex = f"fps={target_fps},scale={target_res}:flags=bicubic"
        
        cmd.extend([
            "-vf", filter_complex,
            "-pix_fmt", target_format,
            "-c:v", "libx264",
            "-crf", "18",  # High quality (lower is better, 18 is very high quality)
            "-preset", "slow" if high_quality else "medium",  # Better quality at cost of encoding time
            "-c:a", "aac",  # AAC audio
            "-b:a", "192k",  # High quality audio
            output_path
        ])
        
        logger.info(f"Running normalization: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        if result.returncode != 0:
            logger.error(f"Normalization failed: {result.stderr}")
            return False
            
        logger.info(f"Normalized video saved to {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"Error normalizing video: {str(e)}")
        return False

def copy_video(input_path, output_path):
    """Copy a video without re-encoding"""
    try:
        cmd = [
            "ffmpeg",
            "-y",  # Overwrite output
            "-i", input_path,
            "-c", "copy",  # Stream copy (no re-encode)
            output_path
        ]
        
        logger.info(f"Copying video: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        if result.returncode != 0:
            logger.error(f"Video copy failed: {result.stderr}")
            return False
            
        logger.info(f"Video copied to {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"Error copying video: {str(e)}")
        return False

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

def run_vmaf_analysis(reference_path, distorted_path, model_path="vmaf_v0.6.1.json", output_json=None):
    """Run VMAF analysis on normalized videos"""
    try:
        # Create output path for results if not specified
        if not output_json:
            output_dir = os.path.dirname(reference_path)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_json = os.path.join(output_dir, f"vmaf_results_{timestamp}.json")
            
        # Make sure model has .json extension
        if not model_path.endswith('.json'):
            model_path += '.json'
            
        # Build FFmpeg command
        cmd = [
            "ffmpeg",
            "-i", distorted_path,
            "-i", reference_path,
            "-lavfi", f"libvmaf=model_path={model_path}:log_path={output_json}:log_fmt=json:psnr=1:ssim=1",
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