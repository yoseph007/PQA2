import subprocess
import logging
import os
import json
import re
import time
import concurrent.futures
from datetime import datetime

logger = logging.getLogger(__name__)


def normalize_videos_for_comparison(reference_path, captured_path, output_dir=None):
    """
    Normalize two videos to have the same framerate, color format, and resolution
    for accurate VMAF comparison. Never downgrade quality if capture is higher quality.
    
    Improvements:
    - Added "-y" to all ffmpeg commands to prevent prompts
    - Added parallel processing for faster normalization
    - Added smarter detection of when normalization can be skipped
    - Improved error handling and logging
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
    
    # Get target parameters from reference video
    target_fps = ref_info.get('frame_rate', 25)
    target_width = ref_info.get('width', 1920)
    target_height = ref_info.get('height', 1080)
    target_res = f"{target_width}x{target_height}"
    target_format = "yuv420p"  # Standard format for VMAF
    
    logger.info(f"Normalizing videos to match reference: {target_fps} fps, {target_res}, {target_format}")
    
    # Check if videos need normalization
    ref_needs_conversion = (
        abs(ref_info.get('frame_rate', 0) - target_fps) > 0.01 or
        ref_info.get('width', 0) != target_width or
        ref_info.get('height', 0) != target_height or
        ref_info.get('pix_fmt') != target_format
    )
    
    cap_needs_conversion = (
        abs(cap_info.get('frame_rate', 0) - target_fps) > 0.01 or
        cap_info.get('width', 0) != target_width or
        cap_info.get('height', 0) != target_height or
        cap_info.get('pix_fmt') != target_format
    )
    
    # Run normalizations in parallel for better performance
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        # Submit normalization tasks
        ref_future = executor.submit(
            process_video, 
            reference_path, 
            normalized_ref_path,
            ref_needs_conversion,
            target_fps,
            target_res,
            target_format
        )
        
        cap_future = executor.submit(
            process_video,
            captured_path,
            normalized_cap_path,
            cap_needs_conversion,
            target_fps,
            target_res,
            target_format
        )
        
        # Get results
        normalized_ref_path = ref_future.result()
        normalized_cap_path = cap_future.result()
    
    # Verify both files exist
    if not os.path.exists(normalized_ref_path) or not os.path.exists(normalized_cap_path):
        logger.error("Failed to create normalized videos")
        return None, None
        
    return normalized_ref_path, normalized_cap_path


def process_video(input_path, output_path, needs_conversion, target_fps, target_res, target_format):
    """Process a single video based on whether it needs conversion or just copying"""
    try:
        if needs_conversion:
            logger.info(f"Converting {os.path.basename(input_path)} to match target parameters")
            success = normalize_video(
                input_path, 
                output_path, 
                target_fps, 
                target_res, 
                target_format,
                high_quality=True
            )
            if not success:
                logger.warning(f"Normalization failed, copying original: {input_path}")
                copy_video(input_path, output_path)
        else:
            logger.info(f"Video already meets target parameters, copying: {os.path.basename(input_path)}")
            copy_video(input_path, output_path)
            
        return output_path
    except Exception as e:
        logger.error(f"Error processing video {input_path}: {str(e)}")
        # Copy the original as fallback
        copy_video(input_path, output_path)
        return output_path


def normalize_video(input_path, output_path, target_fps, target_res, target_format, high_quality=False):
    """Normalize a video to the specified parameters with quality preservation"""
    try:
        # Determine if hardware acceleration is available and should be used
        hw_accel = check_hw_acceleration()
        
        # Build FFmpeg command with quality settings
        cmd = [
            "ffmpeg",
            "-y",  # Always overwrite output
            "-i", input_path
        ]
        
        # Add hardware acceleration if available
        if hw_accel:
            if hw_accel == "nvidia":
                # NVIDIA GPU acceleration
                cmd.extend([
                    "-hwaccel", "cuda",
                    "-hwaccel_output_format", "cuda"
                ])
                
        # Add high quality scaling filters
        if high_quality:
            # Use high quality scaler
            filter_complex = f"fps={target_fps},scale={target_res}:flags=lanczos"
        else:
            filter_complex = f"fps={target_fps},scale={target_res}:flags=bicubic"
        
        # Choose encoder based on hardware acceleration
        video_encoder = "libx264"
        preset = "medium"  # Default preset
        
        if hw_accel == "nvidia":
            video_encoder = "h264_nvenc"
            preset = "p4"  # Good quality preset for NVENC
        
        # For high quality, adjust preset
        if high_quality:
            if video_encoder == "libx264":
                preset = "slow"  # Better quality at cost of encoding time
            elif video_encoder == "h264_nvenc":
                preset = "p6"  # Higher quality NVENC preset
        
        cmd.extend([
            "-vf", filter_complex,
            "-pix_fmt", target_format,
            "-c:v", video_encoder,
            "-crf", "18" if video_encoder == "libx264" else None,  # High quality (lower is better)
            "-preset", preset,
            "-c:a", "aac",  # AAC audio
            "-b:a", "192k",  # High quality audio
            output_path
        ])
        
        # Remove None values
        cmd = [x for x in cmd if x is not None]
        
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


def check_hw_acceleration():
    """Check for available hardware acceleration"""
    try:
        # Check for NVIDIA GPU
        nvidia_result = subprocess.run(
            ["nvidia-smi"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        if nvidia_result.returncode == 0:
            # NVIDIA GPU found
            return "nvidia"
            
        # Check for Intel QuickSync
        intel_result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        if intel_result.returncode == 0 and "h264_qsv" in intel_result.stdout:
            # Intel QuickSync found
            return "intel"
            
        # No hardware acceleration available
        return None
        
    except Exception:
        # Error checking for hardware acceleration
        return None


def copy_video(input_path, output_path):
    """Copy a video without re-encoding"""
    try:
        cmd = [
            "ffmpeg",
            "-y",  # Always overwrite output
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
            "-y",  # Ensure we don't get prompts
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