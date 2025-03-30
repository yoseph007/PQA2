import os
import json
from datetime import datetime

def ensure_dir(path):
    """Ensure directory exists"""
    os.makedirs(path, exist_ok=True)

def timestamp():
    """Generate timestamp string"""
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def normalize_path(path, for_ffmpeg=False):
    """
    Normalize file path to use consistent separators
    
    Args:
        path: The path to normalize
        for_ffmpeg: If True, always use forward slashes for FFmpeg commands
    
    Returns:
        Normalized path string
    """
    if path is None:
        return None
        
    # First, convert to proper OS path with normalized separators
    normalized = os.path.normpath(path)
    
    # For FFmpeg, always use forward slashes regardless of platform
    if for_ffmpeg:
        normalized = normalized.replace('\\', '/')
        
    return normalized

def save_results(data, output_dir="results"):
    """Save analysis results to JSON"""
    ensure_dir(output_dir)
    filename = os.path.join(output_dir, f"results_{timestamp()}.json")
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)
    return filename