import os
import subprocess
import logging
import json
import time

logger = logging.getLogger(__name__)

def run_vmaf_analysis(reference_path, distorted_path, output_dir, model_name="vmaf_v0.6.1", duration=None):
    """
    Run VMAF analysis on video files using FFmpeg with improved parameters and error handling
    
    Args:
        reference_path: Path to reference video
        distorted_path: Path to distorted/captured video
        output_dir: Directory to save output files
        model_name: VMAF model to use ('vmaf_v0.6.1' or 'vmaf_4k_v0.6.1')
        duration: Duration to analyze in seconds (None for full video)
        
    Returns:
        Dictionary with analysis results or None on failure
    """
    try:
        logger.info(f"Starting VMAF analysis")
        
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Generate output file paths
        json_output = os.path.join(output_dir, "vmaf_log.json")
        psnr_output = os.path.join(output_dir, "psnr_log.txt")
        ssim_output = os.path.join(output_dir, "ssim_log.txt")
        csv_output = os.path.join(output_dir, "vmaf_scores.csv")
        
        # Normalize paths to use forward slashes for FFmpeg
        reference_path = reference_path.replace('\\', '/')
        distorted_path = distorted_path.replace('\\', '/')
        json_output = json_output.replace('\\', '/')
        
        # Ensure there are no spaces in paths or escape them
        if ' ' in json_output:
            json_output = f'"{json_output}"'
        
        # Build FFmpeg command with proper filter syntax
        cmd = [
            "ffmpeg",
            "-i", reference_path,
            "-i", distorted_path
        ]
        
        # Add duration limit if specified
        if duration:
            cmd.extend(["-t", str(duration)])
        
        # Build the libvmaf filter with proper escaping
        # The key fix is using '=' for parameters and ':' as separator
        filter_params = [
            f"log_path={json_output}",
            f"log_fmt=json",
            f"model={model_name}",
            "psnr=1",
            "ssim=1"
        ]
        
        filter_string = "libvmaf=" + ":".join(filter_params)
        
        # Complete the command
        cmd.extend([
            "-an",
            "-f", "null",
            "-"
        ])
        
        # Add filter complex parameter separately with proper escaping
        cmd_with_filter = cmd[:]
        cmd_with_filter.extend(["-filter_complex", filter_string])
        
        logger.info(f"Running FFmpeg with VMAF filter: {filter_string}")
        logger.debug(f"Full command: {' '.join(cmd_with_filter)}")
        
        # Execute command
        result = subprocess.run(
            cmd_with_filter,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Check for errors
        if result.returncode != 0:
            logger.error(f"VMAF analysis failed with code {result.returncode}: {result.stderr}")
            return None
        
        # Parse JSON results
        try:
            if os.path.exists(json_output):
                with open(json_output, 'r') as f:
                    vmaf_data = json.load(f)
                
                # Extract overall score
                overall_metrics = {}
                
                # Parse VMAF results differently based on FFmpeg version
                if "pooled_metrics" in vmaf_data:
                    # Newer FFmpeg/libvmaf output format
                    pooled = vmaf_data.get("pooled_metrics", {})
                    overall_metrics["vmaf_score"] = pooled.get("vmaf", {}).get("mean", None)
                    overall_metrics["psnr"] = pooled.get("psnr", {}).get("mean", None)
                    overall_metrics["ssim"] = pooled.get("ssim", {}).get("mean", None)
                else:
                    # Older FFmpeg/libvmaf output format
                    frames = vmaf_data.get("frames", [])
                    if frames:
                        vmaf_values = [f.get("metrics", {}).get("vmaf", 0) for f in frames]
                        psnr_values = [f.get("metrics", {}).get("psnr_y", 0) for f in frames]
                        ssim_values = [f.get("metrics", {}).get("ssim", 0) for f in frames]
                        
                        # Calculate averages
                        if vmaf_values:
                            overall_metrics["vmaf_score"] = sum(vmaf_values) / len(vmaf_values)
                        if psnr_values:
                            overall_metrics["psnr"] = sum(psnr_values) / len(psnr_values)
                        if ssim_values:
                            overall_metrics["ssim"] = sum(ssim_values) / len(ssim_values)
                
                # Write CSV with per-frame scores for graphing
                try:
                    frames = vmaf_data.get("frames", [])
                    if frames:
                        with open(csv_output, 'w') as csvfile:
                            # Write header
                            csvfile.write("frame,vmaf,psnr,ssim\n")
                            
                            # Write data
                            for i, frame in enumerate(frames):
                                metrics = frame.get("metrics", {})
                                vmaf = metrics.get("vmaf", "")
                                psnr = metrics.get("psnr_y", "")
                                ssim = metrics.get("ssim", "")
                                csvfile.write(f"{i},{vmaf},{psnr},{ssim}\n")
                except Exception as e:
                    logger.warning(f"Error writing CSV: {str(e)}")
                
                # Create result dictionary
                result = {
                    "reference_path": reference_path,
                    "distorted_path": distorted_path,
                    "vmaf_score": overall_metrics.get("vmaf_score"),
                    "psnr": overall_metrics.get("psnr"),
                    "ssim": overall_metrics.get("ssim"),
                    "json_path": json_output,
                    "csv_path": csv_output,
                    "psnr_log": psnr_output,
                    "ssim_log": ssim_output,
                    "model": model_name
                }
                
                logger.info(f"VMAF Score: {result.get('vmaf_score', 'N/A')}")
                logger.info(f"PSNR: {result.get('psnr', 'N/A')}")
                logger.info(f"SSIM: {result.get('ssim', 'N/A')}")
                
                return result
            else:
                logger.error(f"VMAF output file not found: {json_output}")
                return None
        except Exception as e:
            logger.error(f"Error parsing VMAF results: {str(e)}")
            return None
            
    except Exception as e:
        logger.error(f"VMAF analysis error: {str(e)}")
        return None


class VMAFAnalysisThread:
    """
    Thread class for running VMAF analysis
    """
    def __init__(self, reference_path, distorted_path, model_name="vmaf_v0.6.1", duration=None, output_dir=None):
        self.reference_path = reference_path
        self.distorted_path = distorted_path
        self.model_name = model_name
        self.duration = duration
        
        # Set default output directory if none provided
        if output_dir is None:
            output_dir = os.path.join(os.path.dirname(reference_path), f"vmaf_{time.strftime('%Y%m%d_%H%M%S')}")
        self.output_dir = output_dir
        
        # Initialize signals (these would be properly connected in a PyQt application)
        self.analysis_progress = lambda x: logger.info(f"Progress: {x}%")
        self.status_update = lambda x: logger.info(f"Status: {x}")
        self.error_occurred = lambda x: logger.error(f"Error: {x}")
        self.analysis_complete = lambda x: logger.info(f"Complete: {x}")
        
    def start(self):
        """Run the analysis in a thread"""
        try:
            self.status_update("Starting VMAF analysis...")
            self.analysis_progress(0)
            
            # Ensure paths exist
            if not os.path.exists(self.reference_path):
                self.error_occurred(f"Reference video not found: {self.reference_path}")
                return
                
            if not os.path.exists(self.distorted_path):
                self.error_occurred(f"Distorted video not found: {self.distorted_path}")
                return
                
            # Create output directory
            os.makedirs(self.output_dir, exist_ok=True)
            
            # Report status
            model_info = f"Model: {self.model_name}"
            duration_info = f"Duration: {self.duration}s" if self.duration else "Duration: Full video"
            self.status_update(f"Running VMAF analysis | {model_info} | {duration_info}")
            
            # Run analysis
            self.analysis_progress(10)
            result = run_vmaf_analysis(
                self.reference_path,
                self.distorted_path,
                self.output_dir,
                self.model_name,
                self.duration
            )
            
            # Process results
            if result:
                self.analysis_progress(100)
                self.status_update(f"VMAF analysis complete! Score: {result.get('vmaf_score', 'N/A')}")
                self.analysis_complete(result)
            else:
                self.error_occurred("VMAF analysis failed")
                
        except Exception as e:
            self.error_occurred(f"Error in VMAF analysis thread: {str(e)}")
