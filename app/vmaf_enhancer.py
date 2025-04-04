
import json
import logging
import os
import subprocess
from pathlib import Path
import platform


logger = logging.getLogger(__name__)

class VMAFEnhancer:
    """
    Enhanced VMAF processing based on easyVmaf techniques
    for more consistent and accurate video quality measurement
    """
    
    def __init__(self):
        self.temp_dir = None
        self.models_dir = None
        self.initialize_paths()
        
    def initialize_paths(self):
        """Initialize paths for models and temporary files"""
        # Get the current directory (assumed to be app)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Check if we're in the app directory or at the root
        if os.path.basename(current_dir) == "app":
            root_dir = os.path.dirname(current_dir)  # Go up one level if in app directory
        else:
            root_dir = current_dir  # We're already at root
        
        # Set paths
        self.models_dir = os.path.join(root_dir, "models")
        
        # Create temporary directory if needed
        self.temp_dir = os.path.join(root_dir, "temp")
        os.makedirs(self.temp_dir, exist_ok=True)
        
        logger.info(f"VMAF Enhancer initialized. Models dir: {self.models_dir}, Temp dir: {self.temp_dir}")
    
    def get_video_metadata(self, video_path, ffprobe_path=None):
        """
        Extract comprehensive video metadata using FFprobe
        This provides more details than the current implementation
        """
        try:
            # Use provided ffprobe path or default to "ffprobe"
            ffprobe = ffprobe_path or "ffprobe"
            
            # Ensure path uses forward slashes
            video_path_norm = video_path.replace("\\", "/")
            
            # Get detailed video information
            cmd = [
                ffprobe,
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                video_path_norm
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            info = json.loads(result.stdout)
            
            # Find video stream
            video_stream = next((s for s in info.get('streams', []) if s.get('codec_type') == 'video'), None)
            if not video_stream:
                logger.error(f"No video stream found in {video_path}")
                return None
                
            # Parse frame rate
            fr_str = video_stream.get('avg_frame_rate', '0/0')
            if '/' in fr_str:
                num, den = map(int, fr_str.split('/'))
                frame_rate = num / den if den else 0
            else:
                frame_rate = float(fr_str) if fr_str else 0
                
            # Get more detailed metadata
            metadata = {
                'path': video_path,
                'duration': float(info.get('format', {}).get('duration', 0)),
                'frame_rate': frame_rate,
                'width': int(video_stream.get('width', 0)),
                'height': int(video_stream.get('height', 0)),
                'pix_fmt': video_stream.get('pix_fmt', 'unknown'),
                'codec_name': video_stream.get('codec_name', 'unknown'),
                'bit_rate': int(info.get('format', {}).get('bit_rate', 0)),
                'nb_frames': int(video_stream.get('nb_frames', 0)),
                'display_aspect_ratio': video_stream.get('display_aspect_ratio', 'unknown'),
                'sample_aspect_ratio': video_stream.get('sample_aspect_ratio', 'unknown')
            }
            
            logger.info(f"Video metadata extracted: {metadata['width']}x{metadata['height']} @ {metadata['frame_rate']}fps")
            return metadata
            
        except Exception as e:
            logger.error(f"Error extracting video metadata: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def preprocess_videos(self, reference_path, distorted_path, ffmpeg_path=None, match_framerate=True, match_resolution=True):
        """
        Preprocess videos to ensure consistent comparison:
        - Match frame rates if different
        - Match resolutions if different
        - Ensure compatible pixel formats
        """
        try:
            # Use provided ffmpeg path or default to "ffmpeg"
            ffmpeg = ffmpeg_path or "ffmpeg"
            
            # Get metadata for both videos
            ref_meta = self.get_video_metadata(reference_path)
            dist_meta = self.get_video_metadata(distorted_path)
            
            if not ref_meta or not dist_meta:
                logger.error("Could not extract metadata from videos")
                return None, None
                
            logger.info(f"Reference: {ref_meta['width']}x{ref_meta['height']} @ {ref_meta['frame_rate']}fps, {ref_meta['pix_fmt']}")
            logger.info(f"Distorted: {dist_meta['width']}x{dist_meta['height']} @ {dist_meta['frame_rate']}fps, {dist_meta['pix_fmt']}")
            
            # Check if preprocessing is needed
            
            # Check frame rate
            frame_rate_mismatch = abs(ref_meta['frame_rate'] - dist_meta['frame_rate']) > 0.01
            resolution_mismatch = ref_meta['width'] != dist_meta['width'] or ref_meta['height'] != dist_meta['height']
            pixel_format_mismatch = ref_meta['pix_fmt'] != dist_meta['pix_fmt']
            
            if not (frame_rate_mismatch and match_framerate) and not (resolution_mismatch and match_resolution) and not pixel_format_mismatch:
                logger.info("No preprocessing needed, videos have compatible parameters")
                return reference_path, distorted_path
                
            # Create filenames for preprocessed videos
            ref_filename = os.path.basename(reference_path)
            dist_filename = os.path.basename(distorted_path)
            
            ref_processed_path = os.path.join(self.temp_dir, f"ref_processed_{ref_filename}")
            dist_processed_path = os.path.join(self.temp_dir, f"dist_processed_{dist_filename}")
            
            # Process reference video if needed
            if pixel_format_mismatch:
                # Always standardize pixel format to yuv420p for VMAF
                ref_pix_fmt = "yuv420p"
                logger.info(f"Converting reference pixel format to {ref_pix_fmt}")
            else:
                ref_pix_fmt = ref_meta['pix_fmt']
                
            # Process distorted video
            # Match frame rate and resolution to reference if required
            target_frame_rate = ref_meta['frame_rate'] if match_framerate and frame_rate_mismatch else dist_meta['frame_rate']
            target_width = ref_meta['width'] if match_resolution and resolution_mismatch else dist_meta['width']
            target_height = ref_meta['height'] if match_resolution and resolution_mismatch else dist_meta['height']
            target_pix_fmt = ref_pix_fmt
            
            # Only process videos if needed
            if frame_rate_mismatch and match_framerate or resolution_mismatch and match_resolution or pixel_format_mismatch:
                # Process reference video if needed
                if pixel_format_mismatch:
                    logger.info(f"Processing reference video to {ref_pix_fmt}")
                    ref_cmd = [
                        ffmpeg,
                        "-hide_banner",
                        "-i", reference_path,
                        "-c:v", "libx264",
                        "-pix_fmt", ref_pix_fmt,
                        "-y", ref_processed_path
                    ]
                    subprocess.run(ref_cmd, check=True, capture_output=True)
                    reference_path = ref_processed_path
                
                # Process distorted video
                if frame_rate_mismatch and match_framerate or resolution_mismatch and match_resolution or pixel_format_mismatch:
                    logger.info(f"Processing distorted video to match {target_width}x{target_height} @ {target_frame_rate}fps, {target_pix_fmt}")
                    
                    dist_cmd = [
                        ffmpeg,
                        "-hide_banner",
                        "-i", distorted_path
                    ]
                    
                    # Add video filter options
                    filter_parts = []
                    
                    # Add scale filter if needed
                    if resolution_mismatch and match_resolution:
                        filter_parts.append(f"scale={target_width}:{target_height}")
                    
                    # Add fps filter if needed
                    if frame_rate_mismatch and match_framerate:
                        filter_parts.append(f"fps={target_frame_rate}")
                        
                    # Combine filters if any
                    if filter_parts:
                        dist_cmd.extend(["-vf", ",".join(filter_parts)])
                    
                    # Add pixel format
                    if pixel_format_mismatch:
                        dist_cmd.extend(["-pix_fmt", target_pix_fmt])
                    
                    # Add output path
                    dist_cmd.extend(["-c:v", "libx264", "-y", dist_processed_path])
                    
                    subprocess.run(dist_cmd, check=True, capture_output=True)
                    distorted_path = dist_processed_path
            
            return reference_path, distorted_path
            
        except Exception as e:
            logger.error(f"Error preprocessing videos: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return reference_path, distorted_path
    
    def validate_vmaf_model(self, model_name):
        """Validate and locate VMAF model file"""
        # If model_name already ends with .json, use as is
        if model_name.endswith('.json'):
            model_basename = model_name
        else:
            model_basename = f"{model_name}.json"
            
        # Look for model in models directory
        model_path = os.path.join(self.models_dir, model_basename)
        
        if os.path.exists(model_path):
            logger.info(f"Found VMAF model at: {model_path}")
            return model_path
        
        # Check for built-in FFmpeg models (don't return path)
        if model_name in ["vmaf", "vmaf_v0.6.1", "vmaf_4k"]:
            logger.info(f"Using built-in FFmpeg VMAF model: {model_name}")
            return None
            
        logger.warning(f"VMAF model '{model_name}' not found, will use default")
        return None
 
 
    def normalize_path_for_ffmpeg(path):
        """Normalize path for FFmpeg use, properly escaping special characters"""
        # Convert to Path object and resolve
        path_obj = Path(path).resolve()
        
        if platform.system() == 'Windows':
            # For Windows, escape colons with backslash and use forward slashes
            return str(path_obj).replace('\\', '/').replace(':', '\\:')
        else:
            # For Unix systems, just use forward slashes
            return str(path_obj)
 
 
    
    def get_optimal_command(self, reference_path, distorted_path, model_name="vmaf_v0.6.1", output_path=None, ffmpeg_path=None):
        """
        Generate a simplified reliable VMAF command that works consistently
        Avoids complex options that can cause path parsing issues
        """
        try:
            # Use provided ffmpeg path or default to "ffmpeg"
            ffmpeg = ffmpeg_path or "ffmpeg"
            
            # Validate and locate model - but don't use model_path parameter which causes issues
            self.validate_vmaf_model(model_name)
            
            # Ensure paths use forward slashes
            reference_path_ffmpeg = reference_path.replace("\\", "/")
            distorted_path_ffmpeg = distorted_path.replace("\\", "/")
            
            # Create output path if not provided
            if not output_path:
                output_dir = os.path.dirname(distorted_path)
                timestamp = Path(distorted_path).stem
                output_path = os.path.join(output_dir, f"{timestamp}_vmaf.json")
            
            output_path_ffmpeg = output_path.replace("\\", "/")
            
            # Build a simple, reliable command - avoid complex parameters
            # Just use model name instead of model_path which causes issues
            cmd = [
                ffmpeg,
                "-hide_banner",
                "-i", distorted_path_ffmpeg,
                "-i", reference_path_ffmpeg,
                "-lavfi", f"libvmaf=log_path={output_path_ffmpeg.replace(':', '\\:')}:log_fmt=json",
                "-f", "null", "-"
            ]
            
            logger.info(f"Generated simplified VMAF command: {' '.join(cmd)}")
            return cmd, output_path
            
        except Exception as e:
            logger.error(f"Error generating VMAF command: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None, None
    
    def run_vmaf_analysis(self, reference_path, distorted_path, model_name="vmaf_v0.6.1", preprocess=True, 
                          match_framerate=True, match_resolution=True, ffmpeg_path=None):
        """
        Run simplified VMAF analysis with reliable command format
        """
        try:
            # Get FFmpeg path
            from .utils import get_ffmpeg_path
            ffmpeg_exe, ffprobe_exe, ffplay_exe = get_ffmpeg_path()
            ffmpeg = ffmpeg_path or ffmpeg_exe
            
            logger.info(f"Starting simplified VMAF analysis between {os.path.basename(reference_path)} and {os.path.basename(distorted_path)}")
            
            # Preprocess videos if needed
            if preprocess:
                logger.info("Preprocessing videos for consistent comparison")
                ref_processed, dist_processed = self.preprocess_videos(
                    reference_path, distorted_path, ffmpeg, 
                    match_framerate=match_framerate, 
                    match_resolution=match_resolution
                )
                
                if not ref_processed or not dist_processed:
                    logger.error("Video preprocessing failed")
                    return None
                    
                # Use processed videos
                reference_path = ref_processed
                distorted_path = dist_processed
            
            # Create output directory
            output_dir = os.path.dirname(distorted_path)
            timestamp = Path(distorted_path).stem
            output_path = os.path.join(output_dir, f"{timestamp}_vmaf.json")
            
            # Use the simplified command format directly
            # This is the command that has been working most consistently
            output_path_ffmpeg = output_path.replace("\\", "/")
            distorted_path_ffmpeg = distorted_path.replace("\\", "/")
            reference_path_ffmpeg = reference_path.replace("\\", "/")
            
            cmd = [
                ffmpeg,
                "-hide_banner",
                "-i", distorted_path_ffmpeg,
                "-i", reference_path_ffmpeg,
                "-lavfi", f"libvmaf=log_path={output_path_ffmpeg}:log_fmt=json",
                "-f", "null", "-"
            ]
            
            logger.info(f"Running simplified VMAF command: {' '.join(cmd)}")
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Capture output for progress monitoring
            stdout, stderr = process.communicate()
            
            # Check if command was successful
            if process.returncode != 0:
                logger.error(f"VMAF analysis failed: {stderr}")
                return None
                
            logger.info(f"VMAF analysis completed successfully, parsing results from {output_path}")
            
            # Parse results
            try:
                with open(output_path, 'r') as f:
                    vmaf_data = json.load(f)
                    
                # Extract scores
                results = self.parse_vmaf_json(vmaf_data, reference_path, distorted_path, output_path)
                
                logger.info(f"VMAF Score: {results['vmaf_score']:.2f}, PSNR: {results.get('psnr', 0):.2f}, SSIM: {results.get('ssim', 0):.2f}")
                return results
                
            except Exception as e:
                logger.error(f"Error parsing VMAF results: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                return None
                
        except Exception as e:
            logger.error(f"Error in VMAF analysis: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None
            
    def parse_vmaf_json(self, vmaf_data, reference_path, distorted_path, json_path):
        """Parse VMAF JSON results and return comprehensive scores"""
        try:
            # Extract scores
            vmaf_score = None
            psnr_score = None
            ssim_score = None
            ms_ssim_score = None
            
            # Check for pooled metrics (preferred)
            if "pooled_metrics" in vmaf_data:
                pool = vmaf_data["pooled_metrics"]
                if "vmaf" in pool:
                    vmaf_score = pool["vmaf"]["mean"]
                if "psnr" in pool:
                    psnr_score = pool["psnr"]["mean"]
                elif "psnr_y" in pool:  # Sometimes labeled as psnr_y
                    psnr_score = pool["psnr_y"]["mean"]
                if "ssim" in pool:
                    ssim_score = pool["ssim"]["mean"]
                elif "ssim_y" in pool:  # Sometimes labeled as ssim_y
                    ssim_score = pool["ssim_y"]["mean"]
                if "ms_ssim" in pool:
                    ms_ssim_score = pool["ms_ssim"]["mean"]
            
            # Fallback to frames if pooled metrics don't exist
            elif "frames" in vmaf_data:
                frames = vmaf_data["frames"]
                if frames:
                    vmaf_values = []
                    psnr_values = []
                    ssim_values = []
                    ms_ssim_values = []
                    
                    for frame in frames:
                        if "metrics" in frame:
                            metrics = frame["metrics"]
                            if "vmaf" in metrics:
                                vmaf_values.append(metrics["vmaf"])
                            if "psnr" in metrics or "psnr_y" in metrics:
                                psnr_values.append(metrics.get("psnr", metrics.get("psnr_y", 0)))
                            if "ssim" in metrics or "ssim_y" in metrics:
                                ssim_values.append(metrics.get("ssim", metrics.get("ssim_y", 0)))
                            if "ms_ssim" in metrics:
                                ms_ssim_values.append(metrics["ms_ssim"])
                    
                    # Calculate averages
                    if vmaf_values:
                        vmaf_score = sum(vmaf_values) / len(vmaf_values)
                    if psnr_values:
                        psnr_score = sum(psnr_values) / len(psnr_values)
                    if ssim_values:
                        ssim_score = sum(ssim_values) / len(ssim_values)
                    if ms_ssim_values:
                        ms_ssim_score = sum(ms_ssim_values) / len(ms_ssim_values)
            
            # Create comprehensive results
            results = {
                'vmaf_score': vmaf_score,
                'psnr': psnr_score,
                'ssim': ssim_score,
                'ms_ssim': ms_ssim_score,
                'json_path': json_path,
                'reference_path': reference_path,
                'distorted_path': distorted_path,
                'raw_results': vmaf_data
            }
            
            # Add frame analysis
            if "frames" in vmaf_data:
                frame_count = len(vmaf_data["frames"])
                results['frame_count'] = frame_count
                
                # Calculate per-frame statistics
                if frame_count > 0:
                    vmaf_per_frame = [frame["metrics"].get("vmaf", 0) for frame in vmaf_data["frames"] if "metrics" in frame]
                    if vmaf_per_frame:
                        results['min_vmaf'] = min(vmaf_per_frame)
                        results['max_vmaf'] = max(vmaf_per_frame)
                        
                        # Identify problem segments (frames with low VMAF scores)
                        threshold = 70  # VMAF below this is considered problematic
                        problem_frames = [i for i, score in enumerate(vmaf_per_frame) if score < threshold]
                        
                        if problem_frames:
                            # Group consecutive frames into segments
                            segments = []
                            current_segment = [problem_frames[0]]
                            
                            for frame in problem_frames[1:]:
                                if frame == current_segment[-1] + 1:
                                    current_segment.append(frame)
                                else:
                                    segments.append(current_segment)
                                    current_segment = [frame]
                            
                            segments.append(current_segment)
                            
                            # Format segments for reporting
                            problem_segments = []
                            for segment in segments:
                                start_frame = segment[0]
                                end_frame = segment[-1]
                                avg_vmaf = sum(vmaf_per_frame[i] for i in segment) / len(segment)
                                problem_segments.append({
                                    'start_frame': start_frame,
                                    'end_frame': end_frame,
                                    'length': end_frame - start_frame + 1,
                                    'avg_vmaf': avg_vmaf
                                })
                            
                            results['problem_segments'] = problem_segments
            
            return results
            
        except Exception as e:
            logger.error(f"Error parsing VMAF results: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            # Return basic results even if parsing failed
            return {
                'vmaf_score': None,
                'psnr': None,
                'ssim': None,
                'ms_ssim': None,
                'json_path': json_path,
                'reference_path': reference_path,
                'distorted_path': distorted_path,
                'error': str(e)
            }
