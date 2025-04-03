import os
import json
import logging
import re
import time
import platform
from PyQt5.QtCore import QObject, pyqtSignal
import subprocess

logger = logging.getLogger(__name__)

class OptionsManager(QObject):
    """Manager for application settings and options"""

    # Signal when settings are updated
    settings_updated = pyqtSignal(dict)

    def __init__(self, settings_file=None):
        super().__init__()

        # Initialize timing variables for debouncing
        self.last_save_time = 0  # Track the last time settings were saved
        self.save_debounce_ms = 1000  # Minimum time between saves in milliseconds

        # Set up settings file in config directory
        if settings_file is None:
            # Create config directory if it doesn't exist
            config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
            os.makedirs(config_dir, exist_ok=True)
            self.settings_file = os.path.join(config_dir, "settings.json")
        else:
            self.settings_file = settings_file

        logger.info(f"Using settings file: {self.settings_file}")

        # Default settings
        self.default_settings = {
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
                "results_dir": "",
                "temp_dir": ""
            },
            # Theme and branding settings
            "theme": {
                "selected_theme": "System",
                "bg_color": "#2D2D30",
                "text_color": "#FFFFFF",
                "accent_color": "#007ACC",
                "logo_path": ""
            },
            # White-label branding
            "branding": {
                "app_name": "VMAF Test App",
                "company_name": "Chroma",
                "enable_white_label": False,
                "footer_text": "© 2025 Chroma",
                "primary_color": "#4CAF50"
            }
        }

        # Handle migration from old settings file
        old_settings_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "settings.json")
        if os.path.exists(old_settings_file) and not os.path.exists(self.settings_file):
            try:
                logger.info(f"Migrating settings from {old_settings_file} to {self.settings_file}")
                # Read old settings
                with open(old_settings_file, 'r') as f:
                    old_settings = json.load(f)
                # Write to new location
                with open(self.settings_file, 'w') as f:
                    json.dump(old_settings, f, indent=4)
            except Exception as e:
                logger.error(f"Error migrating settings: {str(e)}")

        self.settings = self.default_settings.copy()
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
        """Save current settings to file with debouncing to prevent rapid saves"""
        current_time = time.time() * 1000  # Current time in milliseconds

        # Check if enough time has passed since the last save
        if (current_time - self.last_save_time) < self.save_debounce_ms:
            logger.debug("Skipping save due to debounce timer")
            return True

        try:
            # Make sure the config directory exists
            os.makedirs(os.path.dirname(self.settings_file), exist_ok=True)

            with open(self.settings_file, 'w') as f:
                json.dump(self.settings, f, indent=4)
            logger.info(f"Settings saved to {self.settings_file}")

            # Update last save time
            self.last_save_time = current_time

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

        default_value = None
        if category in self.default_settings and key in self.default_settings[category]:
            default_value = self.default_settings[category][key]

        return self.settings[category].get(key, default_value)
        
    def get_settings(self):
        """Get all settings"""
        return self.settings
        
    # Alias for get_settings to maintain compatibility
    def get_setting(self, category, key=None):
        """Get a setting value by category and key"""
        if category not in self.settings:
            return self.default_settings.get(category, {})

        if key is None:
            return self.settings[category]

        default_value = None
        if category in self.default_settings and key in self.default_settings[category]:
            default_value = self.default_settings[category][key]

        return self.settings[category].get(key, default_value)

    def update_setting(self, category, key, value):
        """Update a specific setting"""
        if category not in self.settings:
            self.settings[category] = {}

        self.settings[category][key] = value
        return self.save_settings()

    def set_setting(self, category, values):
        """Set an entire category of settings (alias for update_category)"""
        return self.update_category(category, values)

    def update_category(self, category, values):
        """Update an entire category of settings"""
        # Special handling for capture settings to preserve available options
        if category == "capture" and category in self.settings:
            # If we're updating capture settings, preserve available_resolutions and available_frame_rates
            # when they're empty in the new values but present in existing settings
            if (not values.get("available_resolutions") and 
                self.settings[category].get("available_resolutions")):
                values["available_resolutions"] = self.settings[category]["available_resolutions"]

            if (not values.get("available_frame_rates") and 
                self.settings[category].get("available_frame_rates")):
                values["available_frame_rates"] = self.settings[category]["available_frame_rates"]

        self.settings[category] = values
        return self.save_settings()

    def reset_to_defaults(self):
        """Reset all settings to defaults"""
        self.settings = self.default_settings.copy()
        return self.save_settings()
        
    def update_settings(self, settings):
        """Update multiple settings at once"""
        # Update each category with provided values
        for key, value in settings.items():
            if key in self.settings:
                # If this is a dict and the target is a dict, update recursively
                if isinstance(value, dict) and isinstance(self.settings[key], dict):
                    self.settings[key].update(value)
                else:
                    # Otherwise just replace the value
                    self.settings[key] = value
            else:
                # Add new setting category
                self.settings[key] = value
                
        # Save the updated settings
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

    def get_decklink_formats(self, device):
        """Get available formats for a DeckLink device"""
        format_list = []
        format_map = {}  # Map of resolution -> list of frame rates

        try:
            # Try using dshow for Windows first for more detailed format information
            if platform.system() == 'Windows':
                return self.get_decklink_formats_dshow(device)

            # Use regular decklink format if dshow fails or on other platforms
            # Check if ffmpeg is available
            ffmpeg_path = self._find_ffmpeg()
            if not ffmpeg_path:
                logger.warning("FFmpeg not found, unable to detect DeckLink formats")
                return {"formats": [], "format_map": {}}

            # Use ffmpeg to get available formats
            cmd = [ffmpeg_path, "-f", "decklink", "-list_formats", "1", "-i", device]
            logger.info(f"Getting formats for {device} using command: {' '.join(cmd)}")

            # Set a timeout to prevent hanging
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                stdout, stderr = process.communicate(timeout=5)  # 5 second timeout
            except subprocess.TimeoutExpired:
                process.kill()
                logger.warning(f"Timeout getting formats for {device}")
                # Return default formats if timeout
                default_format_map = {
                    "1920x1080": [23.98, 24, 25, 29.97, 30],
                    "1280x720": [50, 59.94, 60],
                    "720x576": [25, 50],
                    "720x480": [29.97, 59.94]
                }
                return {
                    "formats": [],
                    "format_map": default_format_map
                }

            # Parse output to extract formats
            format_pattern = r'\s+([A-Za-z0-9]+)\s+([0-9]+x[0-9]+) at ([0-9]+(?:\/[0-9]+)?)'

            # Combine stdout and stderr for parsing as FFmpeg outputs to stderr
            output = stdout + stderr

            # Log output for debugging
            lines = output.splitlines()
            for line in lines[:10]:  # Log first 10 lines
                logger.info(f"Format line: {line}")

            # Process all lines for format detection
            for line in lines:
                match = re.search(format_pattern, line)
                if match:
                    format_id, resolution, frame_rate = match.groups()

                    # Parse frame rate (handle both fractional and decimal)
                    if '/' in frame_rate:
                        num, denom = frame_rate.split('/')
                        rate = float(num) / float(denom)
                    else:
                        rate = float(frame_rate)

                    # Format the rate nicely
                    nice_rate = rate
                    if abs(rate - 23.976) < 0.01:
                        nice_rate = 23.98
                    elif abs(rate - 29.97) < 0.01:
                        nice_rate = 29.97
                    elif abs(rate - 59.94) < 0.01:
                        nice_rate = 59.94

                    format_item = {
                        "id": format_id,
                        "resolution": resolution,
                        "frame_rate": nice_rate,
                        "display": f"{resolution} @ {nice_rate} fps"
                    }
                    format_list.append(format_item)

                    # Add to format map
                    if resolution not in format_map:
                        format_map[resolution] = []
                    if nice_rate not in format_map[resolution]:
                        format_map[resolution].append(nice_rate)

            # If no formats found, use default formats
            if not format_list:
                logger.info(f"No formats found for {device}, using default formats")
                default_format_map = {
                    "1920x1080": [23.98, 24, 25, 29.97, 30],
                    "1280x720": [50, 59.94, 60],
                    "720x576": [25, 50],
                    "720x480": [29.97, 59.94]
                }
                return {
                    "formats": [],
                    "format_map": default_format_map
                }

            # Sort frame rates within each resolution
            for res in format_map:
                format_map[res] = sorted(format_map[res])

            logger.info(f"Found formats for {device}: {len(format_list)} formats")
            return {
                "formats": format_list,
                "format_map": format_map
            }

        except Exception as e:
            logger.error(f"Error getting DeckLink formats: {str(e)}")
            # Return default formats in case of error
            default_format_map = {
                "1920x1080": [23.98, 24, 25, 29.97, 30],
                "1280x720": [50, 59.94, 60],
                "720x576": [25, 50],
                "720x480": [29.97, 59.94]
            }
            return {
                "formats": [],
                "format_map": default_format_map
            }

    def get_decklink_formats_dshow(self, device):
        """Get available formats for a DeckLink device using DirectShow on Windows"""
        format_list = []
        format_map = {}  # Map of resolution -> list of frame rates

        try:
            # Use ffmpeg to get available formats using dshow
            cmd = ["ffmpeg", "-hide_banner", "-f", "dshow", "-list_options", "true", "-i", f"video=Decklink Video Capture"]
            logger.info(f"Getting formats using dshow: {' '.join(cmd)}")

            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                stdout, stderr = process.communicate(timeout=10)  # 10 second timeout
            except subprocess.TimeoutExpired:
                process.kill()
                logger.warning("Timeout getting dshow formats")
                return {"formats": [], "format_map": {}}

            # Combine output
            output = stdout + stderr
            lines = output.splitlines()

            # Log output for debugging
            for line in lines[:15]:  # Log first 15 lines
                logger.info(f"Format line: {line}")

            # Format pattern for dshow output
            format_pattern = r'pixel_format=(\w+)\s+min\s+s=(\d+x\d+)\s+fps=(\d+(?:\.\d+)?)\s+max\s+s=(\d+x\d+)\s+fps=(\d+(?:\.\d+)?)'

            for line in lines:
                match = re.search(format_pattern, line)
                if match:
                    pixel_format, min_res, min_fps, max_res, max_fps = match.groups()
                    resolution = min_res  # Assuming min and max are the same
                    frame_rate = float(min_fps)

                    # Format the rate nicely
                    nice_rate = frame_rate
                    if abs(frame_rate - 23.976) < 0.01:
                        nice_rate = 23.98
                    elif abs(frame_rate - 29.97) < 0.01:
                        nice_rate = 29.97
                    elif abs(frame_rate - 59.94) < 0.01:
                        nice_rate = 59.94

                    format_item = {
                        "id": f"{resolution}_{nice_rate}",
                        "resolution": resolution,
                        "frame_rate": nice_rate,
                        "pixel_format": pixel_format,
                        "display": f"{resolution} @ {nice_rate} fps"
                    }
                    format_list.append(format_item)

                    # Add to format map
                    if resolution not in format_map:
                        format_map[resolution] = []
                    if nice_rate not in format_map[resolution]:
                        format_map[resolution].append(nice_rate)

            # If no formats found, return empty
            if not format_list:
                logger.warning("No formats found via dshow")
                return {"formats": [], "format_map": {}}

            # Sort frame rates within each resolution
            for res in format_map:
                format_map[res] = sorted(format_map[res])

            logger.info(f"Found formats via dshow: {len(format_list)} formats")
            return {
                "formats": format_list,
                "format_map": format_map
            }

        except Exception as e:
            logger.error(f"Error getting dshow formats: {str(e)}")
            return {"formats": [], "format_map": {}}
            
    def get_device_formats(self, device):
        """Get available formats for the specified device directly from ffmpeg output"""
        try:
            logger.info(f"Getting formats for device: {device}")
            
            # Use DirectShow to get actual device formats on Windows
            cmd = ["ffmpeg", "-hide_banner", "-f", "dshow", "-list_options", "true", "-i", f"video=Decklink Video Capture"]
            logger.info(f"Getting formats using dshow command: {' '.join(cmd)}")
            
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                stdout, stderr = process.communicate(timeout=10)  # 10 second timeout
                combined_output = stdout + stderr
            except subprocess.TimeoutExpired:
                process.kill()
                logger.warning("Timeout getting dshow formats")
                combined_output = ""
            
            # Parse the output to extract formats
            formats = []
            format_id = 1
            
            # Parse format using regex pattern that matches ffmpeg output format
            format_pattern = r'pixel_format=(\w+)\s+min\s+s=(\d+x\d+)\s+fps=(\d+(?:\.\d+)?)'
            
            # Also look for v210 codec formats
            vcodec_pattern = r'vcodec=(\w+)\s+min\s+s=(\d+x\d+)\s+fps=(\d+(?:\.\d+)?)'
            
            for line in combined_output.splitlines():
                # Try pixel_format pattern first
                match = re.search(format_pattern, line)
                if match:
                    pixel_format, resolution, fps = match.groups()
                    fps_float = float(fps)
                    
                    # Format the rate nicely
                    if abs(fps_float - 23.976) < 0.01:
                        nice_rate = 23.98
                    elif abs(fps_float - 29.97) < 0.01:
                        nice_rate = 29.97
                    elif abs(fps_float - 59.94) < 0.01:
                        nice_rate = 59.94
                    else:
                        nice_rate = round(fps_float, 2)
                    
                    format_item = {
                        "id": f"fmt{format_id}",
                        "resolution": resolution,
                        "frame_rate": nice_rate,
                        "pixel_format": pixel_format,
                        "display": f"{resolution} @ {nice_rate} fps ({pixel_format})"
                    }
                    formats.append(format_item)
                    format_id += 1
                    continue
                
                # Try vcodec pattern if pixel_format didn't match
                match = re.search(vcodec_pattern, line)
                if match:
                    vcodec, resolution, fps = match.groups()
                    fps_float = float(fps)
                    
                    # Format the rate nicely
                    if abs(fps_float - 23.976) < 0.01:
                        nice_rate = 23.98
                    elif abs(fps_float - 29.97) < 0.01:
                        nice_rate = 29.97
                    elif abs(fps_float - 59.94) < 0.01:
                        nice_rate = 59.94
                    else:
                        nice_rate = round(fps_float, 2)
                    
                    format_item = {
                        "id": f"fmt{format_id}",
                        "resolution": resolution,
                        "frame_rate": nice_rate,
                        "vcodec": vcodec,
                        "display": f"{resolution} @ {nice_rate} fps ({vcodec})"
                    }
                    formats.append(format_item)
                    format_id += 1
            
            if formats:
                logger.info(f"Found {len(formats)} formats for device {device}")
                return formats
            
            # If no formats found or parsing failed, use default formats
            logger.warning("Failed to parse formats from ffmpeg output, using defaults")
            default_formats = [
                {"id": "fmt1", "resolution": "1920x1080", "frame_rate": 29.97, "pixel_format": "uyvy422", "display": "1920x1080 @ 29.97 fps (uyvy422)"},
                {"id": "fmt2", "resolution": "1920x1080", "frame_rate": 25, "pixel_format": "uyvy422", "display": "1920x1080 @ 25 fps (uyvy422)"},
                {"id": "fmt3", "resolution": "1920x1080", "frame_rate": 30, "pixel_format": "uyvy422", "display": "1920x1080 @ 30 fps (uyvy422)"},
                {"id": "fmt4", "resolution": "1280x720", "frame_rate": 59.94, "pixel_format": "uyvy422", "display": "1280x720 @ 59.94 fps (uyvy422)"},
                {"id": "fmt5", "resolution": "1280x720", "frame_rate": 50, "pixel_format": "uyvy422", "display": "1280x720 @ 50 fps (uyvy422)"},
                {"id": "fmt6", "resolution": "720x576", "frame_rate": 25, "pixel_format": "uyvy422", "display": "720x576 @ 25 fps (uyvy422)"},
                {"id": "fmt7", "resolution": "720x486", "frame_rate": 29.97, "pixel_format": "uyvy422", "display": "720x486 @ 29.97 fps (uyvy422)"}
            ]
            
            return default_formats
                
        except Exception as e:
            logger.error(f"Error in get_device_formats: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            # Return some default formats as fallback
            return [
                {"id": "fmt1", "resolution": "1920x1080", "frame_rate": 29.97, "pixel_format": "uyvy422", "display": "1920x1080 @ 29.97 fps (uyvy422)"},
                {"id": "fmt2", "resolution": "1280x720", "frame_rate": 59.94, "pixel_format": "uyvy422", "display": "1280x720 @ 59.94 fps (uyvy422)"}
            ]

    def _find_ffmpeg(self):
        """Find the path to ffmpeg"""
        # Add your ffmpeg detection logic here if needed
        # For now, assume it's in the system PATH
        return "ffmpeg" # Replace with your actual ffmpeg path detection