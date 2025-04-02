
import os
import json
import logging
from PyQt5.QtCore import QObject, pyqtSignal
import subprocess

logger = logging.getLogger(__name__)

class OptionsManager(QObject):
    """Manager for application settings and options"""
    
    # Signal when settings are updated
    settings_updated = pyqtSignal(dict)
    
    def __init__(self, settings_file="settings.json"):
        super().__init__()
        self.settings_file = settings_file
        
        # Default settings
        self.default_settings = {
            # Bookend settings
            "bookend": {
                "min_loops": 3,
                "max_capture_time": 120,  # seconds
                "bookend_duration": 0.5,  # seconds
                "white_threshold": 240    # 0-255 for white detection
            },
            # VMAF settings
            "vmaf": {
                "default_model": "vmaf_v0.6.1",
                "available_models": ["vmaf_v0.6.1", "vmaf_4k_v0.6.1", "vmaf_b_v0.6.3"],
                "subsample": 1,  # 1 = analyze every frame
                "threads": 0,    # 0 = auto
                "output_format": "json"
            },
            # Capture settings
            "capture": {
                "default_device": "Intensity Shuttle",
                "resolution": "1080p",
                "frame_rate": 30,
                "pixel_format": "uyvy422",
                "available_resolutions": ["1080p", "720p", "576p", "480p"],
                "available_frame_rates": [23.98, 24, 25, 29.97, 30, 50, 59.94, 60]
            },
            # File paths
            "paths": {
                "default_output_dir": "",
                "reference_video_dir": "",
                "results_dir": ""
            }
        }
        
        # Current settings (will be loaded from file or defaults)
        self.settings = {}
        
        # Load settings from file or create with defaults
        self.load_settings()
    
    def load_settings(self):
        """Load settings from file, or create with defaults if file doesn't exist"""
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r') as f:
                    self.settings = json.load(f)
                logger.info(f"Settings loaded from {self.settings_file}")
                
                # Update default settings with any missing keys from newer versions
                self._update_missing_settings()
            else:
                logger.info(f"Settings file not found, creating with defaults")
                self.settings = self.default_settings.copy()
                self.save_settings()
        except Exception as e:
            logger.error(f"Error loading settings: {str(e)}")
            self.settings = self.default_settings.copy()
    
    def _update_missing_settings(self):
        """Update settings with any missing keys from defaults"""
        updated = False
        
        # Recursively check for missing keys
        def update_dict(source, target):
            nonlocal updated
            for key, value in source.items():
                if key not in target:
                    target[key] = value
                    updated = True
                elif isinstance(value, dict) and isinstance(target[key], dict):
                    update_dict(value, target[key])
        
        update_dict(self.default_settings, self.settings)
        
        if updated:
            logger.info("Settings updated with new default values")
            self.save_settings()
    
    def save_settings(self):
        """Save current settings to file"""
        try:
            with open(self.settings_file, 'w') as f:
                json.dump(self.settings, f, indent=4)
            logger.info(f"Settings saved to {self.settings_file}")
            
            # Emit signal that settings were updated
            self.settings_updated.emit(self.settings)
            return True
        except Exception as e:
            logger.error(f"Error saving settings: {str(e)}")
            return False
    
    def get_setting(self, category, key=None):
        """Get a setting value by category and key"""
        if category not in self.settings:
            return self.default_settings.get(category, {})
        
        if key is None:
            return self.settings[category]
        
        return self.settings[category].get(key, self.default_settings.get(category, {}).get(key))
    
    def update_setting(self, category, key, value):
        """Update a specific setting"""
        if category not in self.settings:
            self.settings[category] = {}
        
        self.settings[category][key] = value
        return self.save_settings()
    
    def update_category(self, category, values):
        """Update an entire category of settings"""
        self.settings[category] = values
        return self.save_settings()
    
    def reset_to_defaults(self):
        """Reset all settings to defaults"""
        self.settings = self.default_settings.copy()
        return self.save_settings()
    
    def get_decklink_devices(self):
        """Query available DeckLink devices using FFmpeg"""
        devices = []
        try:
            # Run FFmpeg command to list DeckLink devices
            cmd = ["ffmpeg", "-f", "decklink", "-list_devices", "1", "-i", "dummy"]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            # Parse the error output (FFmpeg outputs device list to stderr)
            output = result.stderr
            lines = output.split('\n')
            
            # Extract device names
            for line in lines:
                if "'" in line and "Decklink" in line:
                    try:
                        device_name = line.split("'")[1]
                        devices.append(device_name)
                    except:
                        pass
            
            if not devices:
                # Add default device as fallback
                devices = ["Intensity Shuttle"]
                
            logger.info(f"Found DeckLink devices: {devices}")
        except Exception as e:
            logger.error(f"Error getting DeckLink devices: {str(e)}")
            # Add default device as fallback
            devices = ["Intensity Shuttle"]
        
        return devices
    
    def get_decklink_formats(self, device_name):
        """Query available formats for a DeckLink device"""
        formats = []
        resolutions = []
        frame_rates = []
        
        try:
            # Run FFmpeg command to list formats for device
            cmd = ["ffmpeg", "-f", "decklink", "-list_formats", "1", "-i", device_name]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            # Parse the error output
            output = result.stderr
            lines = output.split('\n')
            
            # Extract format information
            for line in lines:
                if "fps" in line and "format" in line:
                    formats.append(line.strip())
                    
                    # Try to extract resolution
                    if "x" in line:
                        parts = line.split()
                        for part in parts:
                            if "x" in part and part[0].isdigit():
                                resolutions.append(part)
                                break
                    
                    # Try to extract frame rate
                    if "fps" in line:
                        parts = line.split()
                        for i, part in enumerate(parts):
                            if part == "fps" and i > 0:
                                try:
                                    rate = float(parts[i-1])
                                    if rate not in frame_rates:
                                        frame_rates.append(rate)
                                except:
                                    pass
            
            # Deduplicate and sort
            resolutions = sorted(list(set(resolutions)))
            frame_rates = sorted(list(set(frame_rates)))
            
            logger.info(f"Found formats for {device_name}: {len(formats)} formats")
        except Exception as e:
            logger.error(f"Error getting formats for {device_name}: {str(e)}")
            # Return default formats as fallback
            resolutions = ["1920x1080", "1280x720", "720x576", "720x480"]
            frame_rates = [23.98, 24, 25, 29.97, 30, 50, 59.94, 60]
        
        return {
            "formats": formats,
            "resolutions": resolutions,
            "frame_rates": frame_rates
        }
