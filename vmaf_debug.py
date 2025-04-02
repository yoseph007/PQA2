
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
