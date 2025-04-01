
import os
import sys
import logging
import argparse
from app.bookend_alignment import BookendAligner

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bookend_alignment_test.log')
    ]
)

logger = logging.getLogger(__name__)

def main():
    """Test the bookend alignment functionality"""
    parser = argparse.ArgumentParser(description='Test white bookend frame alignment')
    parser.add_argument('reference', help='Path to reference video')
    parser.add_argument('captured', help='Path to captured video with white bookends')
    
    args = parser.parse_args()
    
    # Verify files exist
    if not os.path.exists(args.reference):
        logger.error(f"Reference video not found: {args.reference}")
        return 1
        
    if not os.path.exists(args.captured):
        logger.error(f"Captured video not found: {args.captured}")
        return 1
    
    logger.info(f"Testing bookend alignment with:")
    logger.info(f"Reference: {args.reference}")
    logger.info(f"Captured:  {args.captured}")
    
    # Create bookend aligner
    aligner = BookendAligner()
    
    # Set up status callback
    def status_callback(message):
        logger.info(f"Status: {message}")
    aligner.status_update.connect(status_callback)
    
    # Set up progress callback
    def progress_callback(progress):
        logger.info(f"Progress: {progress}%")
    aligner.alignment_progress.connect(progress_callback)
    
    # Run alignment
    result = aligner.align_bookend_videos(args.reference, args.captured)
    
    if result:
        logger.info("Alignment completed successfully!")
        logger.info(f"Aligned reference: {result['aligned_reference']}")
        logger.info(f"Aligned captured: {result['aligned_captured']}")
        
        # Print bookend info
        logger.info("Bookend information:")
        for key, value in result['bookend_info'].items():
            if isinstance(value, dict):
                logger.info(f"  {key}:")
                for k, v in value.items():
                    logger.info(f"    {k}: {v}")
            else:
                logger.info(f"  {key}: {value}")
                
        return 0
    else:
        logger.error("Alignment failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
