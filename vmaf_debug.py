
#!/usr/bin/env python3
import os
import sys
import logging
import argparse
from datetime import datetime
from app.vmaf_analyzer import VMAFAnalyzer

def setup_logging():
    """Configure logging for the debug tool"""
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f'vmaf_debug_{timestamp}.log')
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file)
        ]
    )
    return logging.getLogger('vmaf_debug')

def main():
    """Debug tool main function"""
    logger = setup_logging()
    logger.info("Starting VMAF Debug Tool")
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='VMAF Debug Tool')
    parser.add_argument('-r', '--reference', required=True, help='Path to reference video file')
    parser.add_argument('-d', '--distorted', required=True, help='Path to distorted video file')
    parser.add_argument('-m', '--model', default='vmaf_v0.6.1', help='VMAF model to use (default: vmaf_v0.6.1)')
    parser.add_argument('-t', '--test-name', default=None, help='Test name for output organization')
    parser.add_argument('-o', '--output-dir', default=None, help='Output directory for results')
    parser.add_argument('-l', '--duration', type=float, default=None, help='Duration limit in seconds')
    
    args = parser.parse_args()
    
    # Verify reference and distorted files exist
    if not os.path.exists(args.reference):
        logger.error(f"Reference file not found: {args.reference}")
        return 1
    
    if not os.path.exists(args.distorted):
        logger.error(f"Distorted file not found: {args.distorted}")
        return 1
    
    logger.info(f"Reference: {args.reference}")
    logger.info(f"Distorted: {args.distorted}")
    logger.info(f"VMAF Model: {args.model}")
    
    # Set up output directory
    output_dir = args.output_dir
    if not output_dir:
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vmaf_debug_results')
    
    os.makedirs(output_dir, exist_ok=True)
    logger.info(f"Output directory: {output_dir}")
    
    # Create and configure VMAF analyzer
    analyzer = VMAFAnalyzer()
    analyzer.set_output_directory(output_dir)
    
    if args.test_name:
        analyzer.set_test_name(args.test_name)
    
    # Connect to basic console-based progress and status reporting
    analyzer.analysis_progress.connect(lambda p: print(f"Progress: {p}%", end='\r'))
    analyzer.status_update.connect(print)
    analyzer.error_occurred.connect(lambda e: logger.error(f"Error: {e}"))
    analyzer.analysis_complete.connect(lambda results: print_results(results, logger))
    
    # Run VMAF analysis
    try:
        logger.info("Starting VMAF analysis...")
        results = analyzer.analyze_videos(
            args.reference,
            args.distorted,
            args.model,
            args.duration
        )
        
        if not results:
            logger.error("VMAF analysis failed with no results")
            return 1
        
        logger.info("VMAF analysis completed successfully")
        return 0
    
    except Exception as e:
        logger.error(f"VMAF analysis failed: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return 1

def print_results(results, logger):
    """Print VMAF results in a readable format"""
    print("\n" + "="*50)
    print("VMAF ANALYSIS RESULTS")
    print("="*50)
    
    vmaf_score = results.get('vmaf_score')
    psnr = results.get('psnr')
    ssim = results.get('ssim')
    
    if vmaf_score is not None:
        print(f"VMAF Score: {vmaf_score:.2f}")
    else:
        print("VMAF Score: N/A")
    
    if psnr is not None:
        print(f"PSNR: {psnr:.2f} dB")
    else:
        print("PSNR: N/A")
    
    if ssim is not None:
        print(f"SSIM: {ssim:.4f}")
    else:
        print("SSIM: N/A")
    
    print("\nOutput Files:")
    print(f"JSON: {results.get('json_path', 'N/A')}")
    print(f"CSV: {results.get('csv_path', 'N/A')}")
    print(f"PSNR Log: {results.get('psnr_log', 'N/A')}")
    print(f"SSIM Log: {results.get('ssim_log', 'N/A')}")
    print("="*50)
    
    # Also log to file
    logger.info(f"VMAF Score: {vmaf_score}")
    logger.info(f"PSNR: {psnr}")
    logger.info(f"SSIM: {ssim}")

if __name__ == "__main__":
    sys.exit(main())
#!/usr/bin/env python
import os
import argparse
import json
import subprocess
import logging
import time
from datetime import datetime

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("vmaf_debug")

def get_ffmpeg_path():
    """Find FFmpeg executable path"""
    try:
        # First try with the standard PATH method
        result = subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if result.returncode == 0:
            logger.info("Found FFmpeg in PATH")
            return "ffmpeg"
    except Exception as e:
        logger.warning(f"FFmpeg not found in PATH: {e}")
    
    # Try with common installation paths
    common_paths = [
        os.path.join(os.getcwd(), "ffmpeg"),
        os.path.join(os.getcwd(), "bin", "ffmpeg"),
        "C:\\ffmpeg\\bin\\ffmpeg.exe",
        "/usr/bin/ffmpeg",
        "/usr/local/bin/ffmpeg"
    ]
    
    for path in common_paths:
        if os.path.exists(path):
            logger.info(f"Found FFmpeg at: {path}")
            return path
    
    # Default to just the command name and hope it's in PATH
    logger.warning("FFmpeg not found in common locations, using 'ffmpeg' command")
    return "ffmpeg"

def run_vmaf_analysis(reference_path, distorted_path, output_dir=None, model="vmaf_v0.6.1"):
    """Run VMAF analysis with separate processes for VMAF, PSNR, and SSIM"""
    logger.info(f"Running VMAF analysis comparing:")
    logger.info(f"Reference: {reference_path}")
    logger.info(f"Distorted: {distorted_path}")
    logger.info(f"Using VMAF model: {model}")
    
    if not os.path.exists(reference_path):
        logger.error(f"Reference file not found: {reference_path}")
        return None
    
    if not os.path.exists(distorted_path):
        logger.error(f"Distorted file not found: {distorted_path}")
        return None
    
    # Create output directory if not provided
    if not output_dir:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = os.path.join(os.getcwd(), f"vmaf_results_{timestamp}")
    
    os.makedirs(output_dir, exist_ok=True)
    logger.info(f"Output directory: {output_dir}")
    
    # Output filenames
    vmaf_json = os.path.join(output_dir, "vmaf_results.json").replace("\\", "/")
    vmaf_csv = os.path.join(output_dir, "vmaf_results.csv").replace("\\", "/")
    psnr_txt = os.path.join(output_dir, "psnr_results.txt").replace("\\", "/")
    ssim_txt = os.path.join(output_dir, "ssim_results.txt").replace("\\", "/")
    
    # Find FFmpeg
    ffmpeg_exe = get_ffmpeg_path()
    
    # Convert paths to forward slashes for FFmpeg
    ref_path = reference_path.replace("\\", "/")
    dist_path = distorted_path.replace("\\", "/")
    
    # Step 1: Run VMAF analysis
    logger.info("Running VMAF analysis...")
    vmaf_cmd = [
        ffmpeg_exe,
        "-hide_banner",
        "-i", dist_path,
        "-i", ref_path,
        "-lavfi", f"libvmaf=log_path={vmaf_json}:log_fmt=json",
        "-f", "null", "-"
    ]
    
    logger.info(f"VMAF command: {' '.join(vmaf_cmd)}")
    
    try:
        vmaf_process = subprocess.run(
            vmaf_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        if vmaf_process.returncode != 0:
            logger.error(f"VMAF analysis failed: {vmaf_process.stderr}")
            logger.info("Attempting simplified VMAF command...")
            
            # Try simplified version
            simple_vmaf_cmd = [
                ffmpeg_exe,
                "-i", dist_path,
                "-i", ref_path,
                "-filter_complex", f"libvmaf=log_path={vmaf_json}:log_fmt=json",
                "-f", "null", "-"
            ]
            
            vmaf_process = subprocess.run(
                simple_vmaf_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            if vmaf_process.returncode != 0:
                logger.error(f"Simplified VMAF analysis also failed: {vmaf_process.stderr}")
                return None
        
        logger.info("VMAF analysis completed successfully")
    except Exception as e:
        logger.error(f"Error running VMAF analysis: {e}")
        return None
    
    # Step 2: Run PSNR analysis
    logger.info("Running PSNR analysis...")
    psnr_cmd = [
        ffmpeg_exe,
        "-hide_banner",
        "-i", dist_path,
        "-i", ref_path,
        "-lavfi", f"psnr=stats_file={psnr_txt}",
        "-f", "null", "-"
    ]
    
    logger.info(f"PSNR command: {' '.join(psnr_cmd)}")
    
    try:
        psnr_process = subprocess.run(
            psnr_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        if psnr_process.returncode != 0:
            logger.warning(f"PSNR analysis failed: {psnr_process.stderr}")
        else:
            logger.info("PSNR analysis completed successfully")
    except Exception as e:
        logger.warning(f"Error running PSNR analysis: {e}")
    
    # Step 3: Run SSIM analysis
    logger.info("Running SSIM analysis...")
    ssim_cmd = [
        ffmpeg_exe,
        "-hide_banner",
        "-i", dist_path,
        "-i", ref_path,
        "-lavfi", f"ssim=stats_file={ssim_txt}",
        "-f", "null", "-"
    ]
    
    logger.info(f"SSIM command: {' '.join(ssim_cmd)}")
    
    try:
        ssim_process = subprocess.run(
            ssim_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        if ssim_process.returncode != 0:
            logger.warning(f"SSIM analysis failed: {ssim_process.stderr}")
        else:
            logger.info("SSIM analysis completed successfully")
    except Exception as e:
        logger.warning(f"Error running SSIM analysis: {e}")
    
    # Parse and return results
    results = parse_results(vmaf_json, psnr_txt, ssim_txt, reference_path, distorted_path)
    
    if results:
        # Print results summary
        logger.info(f"VMAF Score: {results.get('vmaf_score', 'N/A')}")
        logger.info(f"PSNR: {results.get('psnr', 'N/A')}")
        logger.info(f"SSIM: {results.get('ssim', 'N/A')}")
        
        # Save results as JSON
        results_json = os.path.join(output_dir, "complete_results.json").replace("\\", "/")
        with open(results_json, 'w') as f:
            json.dump(results, f, indent=4)
        
        logger.info(f"Complete results saved to: {results_json}")
    
    return results

def parse_results(vmaf_json_path, psnr_path, ssim_path, reference_path, distorted_path):
    """Parse results from output files"""
    results = {
        'reference_path': reference_path,
        'distorted_path': distorted_path,
        'json_path': vmaf_json_path,
        'psnr_log': psnr_path,
        'ssim_log': ssim_path
    }
    
    # Parse VMAF results from JSON
    try:
        if os.path.exists(vmaf_json_path):
            with open(vmaf_json_path, 'r') as f:
                vmaf_data = json.load(f)
            
            # Extract VMAF score
            if "pooled_metrics" in vmaf_data:
                # New format
                pool = vmaf_data["pooled_metrics"]
                if "vmaf" in pool:
                    results['vmaf_score'] = pool["vmaf"]["mean"]
                if "psnr" in pool:
                    results['psnr'] = pool["psnr"]["mean"]
                if "psnr_y" in pool:  # Sometimes it's labeled as psnr_y
                    results['psnr'] = pool["psnr_y"]["mean"]
                if "ssim" in pool:
                    results['ssim'] = pool["ssim"]["mean"]
                if "ssim_y" in pool:  # Sometimes it's labeled as ssim_y
                    results['ssim'] = pool["ssim_y"]["mean"]
            
            # Fallback to frames if pooled metrics don't exist
            elif "frames" in vmaf_data:
                frames = vmaf_data["frames"]
                if frames:
                    vmaf_values = []
                    psnr_values = []
                    ssim_values = []
                    
                    for frame in frames:
                        if "metrics" in frame:
                            metrics = frame["metrics"]
                            if "vmaf" in metrics:
                                vmaf_values.append(metrics["vmaf"])
                            if "psnr" in metrics or "psnr_y" in metrics:
                                psnr_values.append(metrics.get("psnr", metrics.get("psnr_y", 0)))
                            if "ssim" in metrics or "ssim_y" in metrics:
                                ssim_values.append(metrics.get("ssim", metrics.get("ssim_y", 0)))
                    
                    # Calculate averages
                    if vmaf_values:
                        results['vmaf_score'] = sum(vmaf_values) / len(vmaf_values)
                    if psnr_values:
                        results['psnr'] = sum(psnr_values) / len(psnr_values)
                    if ssim_values:
                        results['ssim'] = sum(ssim_values) / len(ssim_values)
            
            # Store raw results
            results['raw_vmaf'] = vmaf_data
        else:
            logger.warning(f"VMAF JSON file not found: {vmaf_json_path}")
    except Exception as e:
        logger.error(f"Error parsing VMAF results: {e}")
    
    # Parse PSNR from file if not already present in results
    if 'psnr' not in results:
        try:
            if os.path.exists(psnr_path):
                with open(psnr_path, 'r') as f:
                    psnr_data = f.read()
                
                # Try to extract average PSNR
                psnr_match = re.search(r'average:(\d+\.\d+)', psnr_data)
                if psnr_match:
                    results['psnr'] = float(psnr_match.group(1))
            else:
                logger.warning(f"PSNR file not found: {psnr_path}")
        except Exception as e:
            logger.error(f"Error parsing PSNR results: {e}")
    
    # Parse SSIM from file if not already present in results
    if 'ssim' not in results:
        try:
            if os.path.exists(ssim_path):
                with open(ssim_path, 'r') as f:
                    ssim_data = f.read()
                
                # Try to extract average SSIM
                ssim_match = re.search(r'All:(\d+\.\d+)', ssim_data)
                if ssim_match:
                    results['ssim'] = float(ssim_match.group(1))
            else:
                logger.warning(f"SSIM file not found: {ssim_path}")
        except Exception as e:
            logger.error(f"Error parsing SSIM results: {e}")
    
    return results

def main():
    """Main function for VMAF debug tool"""
    parser = argparse.ArgumentParser(description='VMAF Analysis Debug Tool')
    parser.add_argument('-r', '--reference', required=True, help='Path to reference video')
    parser.add_argument('-d', '--distorted', required=True, help='Path to distorted video')
    parser.add_argument('-o', '--output', help='Output directory')
    parser.add_argument('-m', '--model', default='vmaf_v0.6.1', help='VMAF model to use')
    
    args = parser.parse_args()
    
    # Run analysis
    start_time = time.time()
    results = run_vmaf_analysis(args.reference, args.distorted, args.output, args.model)
    end_time = time.time()
    
    if results:
        logger.info("Analysis completed successfully!")
        logger.info(f"Time taken: {end_time - start_time:.2f} seconds")
        return 0
    else:
        logger.error("Analysis failed!")
        return 1

if __name__ == "__main__":
    main()
