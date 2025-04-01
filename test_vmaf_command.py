
#!/usr/bin/env python3
import os
import subprocess
import logging
import sys
import argparse

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('vmaf_test.log')
    ]
)

logger = logging.getLogger(__name__)

def test_vmaf_command(reference_path, distorted_path, output_dir="./vmaf_test"):
    """Test the VMAF command that's known to work"""
    try:
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        
        # Prepare paths with forward slashes
        reference_path_unix = reference_path.replace("\\", "/")
        distorted_path_unix = distorted_path.replace("\\", "/")
        
        # Prepare output paths
        json_path = os.path.join(output_dir, "vmaf_log.json").replace("\\", "/")
        csv_path = os.path.join(output_dir, "vmaf_log.csv").replace("\\", "/")
        psnr_log = os.path.join(output_dir, "psnr_log.txt").replace("\\", "/")
        ssim_log = os.path.join(output_dir, "ssim_log.txt").replace("\\", "/")
        
        # Build the filter_complex string exactly as in the working example
        filter_complex = (
            f"[0:v]setpts=PTS-STARTPTS,split=2[ref1][ref2];"
            f"[1:v]setpts=PTS-STARTPTS,split=2[dist1][dist2];"
            f"[ref1][dist1]libvmaf=log_path={json_path}:log_fmt=json:model=vmaf_v0.6.1;"
            f"[ref2][dist2]libvmaf=log_path={csv_path}:log_fmt=csv:model=vmaf_v0.6.1;"
            f"[0:v][1:v]psnr=stats_file={psnr_log};"
            f"[0:v][1:v]ssim=stats_file={ssim_log}"
        )
        
        # Build the full command
        cmd = [
            "ffmpeg", 
            "-hide_banner",
            "-i", reference_path_unix,
            "-i", distorted_path_unix,
            "-filter_complex", filter_complex,
            "-f", "null", "-"
        ]
        
        # Log the command
        cmd_str = ' '.join(cmd)
        logger.info(f"Running VMAF test command: {cmd_str}")
        
        # Also save to file for reference
        with open(os.path.join(output_dir, "test_vmaf_command.txt"), "w") as f:
            f.write(cmd_str)
        
        # Execute the command
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        
        # Log success and results
        logger.info("VMAF command executed successfully!")
        if os.path.exists(json_path):
            logger.info(f"VMAF results saved to: {json_path}")
            with open(json_path, "r") as f:
                import json
                results = json.load(f)
                if "pooled_metrics" in results:
                    vmaf_score = results["pooled_metrics"]["vmaf"]["mean"]
                    logger.info(f"VMAF Score: {vmaf_score:.2f}")
                else:
                    logger.warning("No pooled metrics found in VMAF results")
        else:
            logger.warning(f"VMAF results file not found: {json_path}")
        
        return True
    
    except subprocess.CalledProcessError as e:
        logger.error(f"Command execution failed: {e.stderr}")
        return False
    except Exception as e:
        logger.error(f"Error testing VMAF command: {str(e)}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test VMAF command")
    parser.add_argument("reference", help="Path to reference video")
    parser.add_argument("distorted", help="Path to distorted video")
    parser.add_argument("--output", help="Output directory", default="./vmaf_test")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.reference):
        logger.error(f"Reference video not found: {args.reference}")
        sys.exit(1)
    
    if not os.path.exists(args.distorted):
        logger.error(f"Distorted video not found: {args.distorted}")
        sys.exit(1)
    
    success = test_vmaf_command(args.reference, args.distorted, args.output)
    sys.exit(0 if success else 1)
