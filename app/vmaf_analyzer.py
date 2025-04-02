import os
import subprocess
import logging
import json
import time
import shutil
from datetime import datetime
from PyQt5.QtCore import QObject, pyqtSignal, QThread

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







def run_vmaf_analysis(reference_path, distorted_path, output_dir, model_name=None, duration=None):
    """
    Run VMAF analysis on video files using a complex filter chain for better compatibility.

    Args:
        reference_path: Path to reference video
        distorted_path: Path to distorted/captured video
        output_dir: Directory to save output files
        model_name: VMAF model to use (ignored in this implementation)
        duration: Duration to analyze in seconds (None for full video)

    Returns:
        Dictionary with analysis results or None on failure
    """
    try:
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Generate output file paths
        vmaf_json = os.path.join(output_dir, "vmaf_log.json")
        vmaf_csv = os.path.join(output_dir, "vmaf_scores.csv")
        psnr_txt = os.path.join(output_dir, "psnr_log.txt")
        ssim_txt = os.path.join(output_dir, "ssim_log.txt")
        
        # Normalize paths to use forward slashes for FFmpeg
        reference_path = reference_path.replace('\\', '/')
        distorted_path = distorted_path.replace('\\', '/')
        vmaf_json = vmaf_json.replace('\\', '/')
        vmaf_csv = vmaf_csv.replace('\\', '/')
        psnr_txt = psnr_txt.replace('\\', '/')
        ssim_txt = ssim_txt.replace('\\', '/')
        
        # Log the paths being used
        logger.info(f"VMAF Reference: {reference_path}")
        logger.info(f"VMAF Distorted: {distorted_path}")
        
        # Build basic command
        cmd = [
            "ffmpeg",
            "-hide_banner",  # Reduce output noise
            "-nostats"       # Disable progress stats
        ]
        
        # Add duration limit if specified
        if duration:
            cmd.extend(["-t", str(duration)])
        
        # Add input files (include quotes for paths with spaces)
        cmd.extend([
            "-i", f'"{reference_path}"',
            "-i", f'"{distorted_path}"'
        ])
        
        # Build the complex filter chain using -filter_complex
        filter_chain = (
            "[0:v]setpts=PTS-STARTPTS,split=2[ref1][ref2];"
            "[1:v]setpts=PTS-STARTPTS,split=2[dist1][dist2];"
            "[ref1][dist1]libvmaf=log_path={0}:log_fmt=json;"
            "[ref2][dist2]libvmaf=log_path={1}:log_fmt=csv;"
            "[0:v][1:v]psnr=stats_file={2};"
            "[0:v][1:v]ssim=stats_file={3}"
        ).format(vmaf_json, vmaf_csv, psnr_txt, ssim_txt)
        
        # Add the filter_complex and output options
        cmd.extend([
            "-filter_complex", f"{filter_chain}",
            "-f", "null",
            "-"
        ])
        
        cmd_str = " ".join(cmd)
        logger.info(f"VMAF command: {cmd_str}")
        logger.info("VMAF subprocess started successfully")
        
        # Execute command
        result = subprocess.run(
            cmd_str,
            shell=True,     # Use shell=True to handle quotes in Windows
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Check for errors
        if result.returncode != 0:
            # Log the error with detailed stderr output
            logger.error(f"VMAF analysis failed with code {result.returncode}: {result.stderr}")
            
            # Try a simpler approach if the complex one fails
            logger.info("Trying simpler VMAF approach")
            
            # Simpler approach: just VMAF, no PSNR or SSIM
            simple_filter = f"libvmaf=log_path={vmaf_json}:log_fmt=json"
            
            simple_cmd = [
                "ffmpeg",
                "-hide_banner",
                "-i", f'"{reference_path}"',
                "-i", f'"{distorted_path}"',
                "-filter_complex", simple_filter,
                "-f", "null",
                "-"
            ]
            
            simple_cmd_str = " ".join(simple_cmd)
            logger.info(f"Simple VMAF command: {simple_cmd_str}")
            
            # Execute simple command
            simple_result = subprocess.run(
                simple_cmd_str,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            if simple_result.returncode != 0:
                logger.error(f"Simple VMAF command also failed: {simple_result.stderr}")
                return None
        
        # Check if result files exist
        if not os.path.exists(vmaf_json):
            logger.error(f"VMAF JSON output not found: {vmaf_json}")
            return None
        
        # Parse results
        try:
            # Read VMAF JSON file
            with open(vmaf_json, 'r') as f:
                vmaf_data = json.load(f)
            
            # Extract VMAF score
            vmaf_score = None
            if "pooled_metrics" in vmaf_data:
                # New format (libvmaf >= 2.0)
                pooled = vmaf_data.get("pooled_metrics", {})
                vmaf_score = pooled.get("vmaf", {}).get("mean", None)
            else:
                # Old format (libvmaf < 2.0)
                frames = vmaf_data.get("frames", [])
                if frames:
                    vmaf_values = [f.get("metrics", {}).get("vmaf", 0) for f in frames]
                    vmaf_score = sum(vmaf_values) / len(vmaf_values) if vmaf_values else None
            
            # Extract PSNR from text file
            psnr = None
            if os.path.exists(psnr_txt):
                with open(psnr_txt, 'r') as f:
                    lines = f.readlines()
                    for line in lines:
                        if "average" in line.lower():
                            parts = line.split()
                            for i, part in enumerate(parts):
                                if part == "average:":
                                    try:
                                        psnr = float(parts[i+1])
                                    except (IndexError, ValueError):
                                        pass
                                    break
            
            # Extract SSIM from text file
            ssim = None
            if os.path.exists(ssim_txt):
                with open(ssim_txt, 'r') as f:
                    lines = f.readlines()
                    for line in lines:
                        if "all" in line.lower() and ":" in line:
                            parts = line.split(":")
                            if len(parts) >= 2:
                                try:
                                    ssim = float(parts[1].strip())
                                except ValueError:
                                    pass
            
            # Log the results
            if vmaf_score is not None:
                logger.info(f"VMAF Score: {vmaf_score:.2f}")
            if psnr is not None:
                logger.info(f"PSNR: {psnr:.2f} dB")
            if ssim is not None:
                logger.info(f"SSIM: {ssim:.4f}")
            
            # Create result dictionary
            result = {
                "reference_path": reference_path,
                "distorted_path": distorted_path,
                "vmaf_score": vmaf_score,
                "psnr": psnr,
                "ssim": ssim,
                "json_path": vmaf_json,
                "csv_path": vmaf_csv,
                "model": model_name
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error parsing VMAF results: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None
            
    except Exception as e:
        logger.error(f"VMAF analysis error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return None







class VMAFAnalyzer(QObject):
    """VMAF analyzer with signals for UI integration"""
    analysis_progress = pyqtSignal(int)
    analysis_complete = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    status_update = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.current_thread = None
    
    def run_analysis(self, reference_path, distorted_path, model_name=None, duration=None):
        """Start VMAF analysis in a separate thread"""
        # Stop any existing thread
        if self.current_thread and self.current_thread.isRunning():
            self.current_thread.terminate()
            self.current_thread.wait()
            
        # Create output directory
        output_dir = os.path.join(
            os.path.dirname(reference_path), 
            f"vmaf_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        
        # Create and start new thread
        self.current_thread = VMAFAnalysisThread(
            reference_path,
            distorted_path,
            output_dir,
            model_name,
            duration
        )
        
        # Connect signals
        self.current_thread.analysis_progress.connect(self.analysis_progress)
        self.current_thread.analysis_complete.connect(self.analysis_complete)
        self.current_thread.error_occurred.connect(self.error_occurred)
        self.current_thread.status_update.connect(self.status_update)
        
        # Start thread
        self.current_thread.start()
        
    def stop_analysis(self):
        """Stop any running analysis"""
        if self.current_thread and self.current_thread.isRunning():
            self.current_thread.requestInterruption()
            self.current_thread.wait(1000)  # Wait for up to 1 second
            
            # Force termination if still running
            if self.current_thread.isRunning():
                self.current_thread.terminate()
                self.current_thread.wait()
                
            self.current_thread = None
            
class VMAFAnalysisThread(QThread):
    """Thread for running VMAF analysis with proper thread management"""
    analysis_progress = pyqtSignal(int)
    analysis_complete = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    status_update = pyqtSignal(str)
    
    def __init__(self, reference_path, distorted_path, output_dir, model_name=None, duration=None):
        super().__init__()
        self.reference_path = reference_path
        self.distorted_path = distorted_path
        self.output_dir = output_dir
        self.model_name = model_name
        self.duration = duration
        
    def run(self):
        """Run VMAF analysis in thread"""
        try:
            self.status_update.emit("Starting VMAF analysis...")
            self.analysis_progress.emit(10)
            
            # Check if paths exist
            if not os.path.exists(self.reference_path):
                self.error_occurred.emit(f"Reference video not found: {self.reference_path}")
                return
                
            if not os.path.exists(self.distorted_path):
                self.error_occurred.emit(f"Distorted video not found: {self.distorted_path}")
                return
                
            # Create output directory
            os.makedirs(self.output_dir, exist_ok=True)
            
            # Log info
            duration_info = f"Duration: {self.duration}s" if self.duration else "Duration: Full video"
            self.status_update.emit(f"Running VMAF analysis | {duration_info}")
            
            # Update progress
            self.analysis_progress.emit(20)
            
            # Get video info for progress calculation
            ref_info = get_video_info(self.reference_path)
            if ref_info:
                ref_duration = ref_info.get('duration', 0)
                self.status_update.emit(f"Reference duration: {ref_duration:.2f}s")
                
            # Run analysis with the new method (using complex filters)
            result = run_vmaf_analysis(
                self.reference_path,
                self.distorted_path,
                self.output_dir,
                self.model_name,
                self.duration
            )
            
            # Process results
            if result:
                vmaf_score = result.get('vmaf_score')
                if vmaf_score is not None:
                    self.status_update.emit(f"VMAF analysis complete! Score: {vmaf_score:.2f}")
                else:
                    self.status_update.emit("VMAF analysis complete! Score: N/A")
                    
                psnr = result.get('psnr')
                if psnr is not None:
                    self.status_update.emit(f"PSNR: {psnr:.2f} dB")
                    
                ssim = result.get('ssim')
                if ssim is not None:
                    self.status_update.emit(f"SSIM: {ssim:.4f}")
                    
                self.analysis_progress.emit(100)
                self.analysis_complete.emit(result)
            else:
                self.error_occurred.emit("VMAF analysis failed")
                
        except Exception as e:
            error_msg = f"Error in VMAF analysis thread: {str(e)}"
            self.error_occurred.emit(error_msg)
            logger.error(error_msg)
            import traceback
            logger.error(traceback.format_exc())