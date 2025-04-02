import os
import json
import logging
import re
import time
from PyQt5.QtCore import QObject, pyqtSignal
import subprocess

logger = logging.getLogger(__name__)

class OptionsManager(QObject):
    """Manager for application settings and options"""

    # Signal when settings are updated
    settings_updated = pyqtSignal(dict)

    def __init__(self, settings_file=None):
        super().__init__()

        # Set up settings file in config directory
        if settings_file is None:
            # Create config directory if it doesn't exist
            config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
            os.makedirs(config_dir, exist_ok=True)
            self.settings_file = os.path.join(config_dir, "settings.json")
        else:
            self.settings_file = settings_file

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

        return self.settings[category].get(key, self.default_settings.get(category, {}).get(key))

    def update_setting(self, category, key, value):
        """Update a specific setting"""
        if category not in self.settings:
            self.settings[category] = {}

        self.settings[category][key] = value
        return self.save_settings()

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
        formats = []
        resolutions = []
        frame_rates = []

        try:
            # Check if ffmpeg is available
            ffmpeg_path = self._find_ffmpeg()
            if not ffmpeg_path:
                logger.warning("FFmpeg not found, unable to detect DeckLink formats")
                return {"formats": [], "resolutions": [], "frame_rates": []}

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
                return {
                    "formats": [],
                    "resolutions": ["1920x1080", "1280x720", "720x576", "720x480"],
                    "frame_rates": [23.98, 24, 25, 29.97, 30, 50, 59.94, 60]
                }

            # Parse output to extract formats
            format_pattern = r'\s+([A-Za-z0-9]+)\s+([0-9]+x[0-9]+) at ([0-9]+(?:\/[0-9]+)?)'

            # Combine stdout and stderr for parsing as FFmpeg outputs to stderr
            output = stdout + stderr

            # Log only the first few lines and last few lines to avoid log spam
            lines = output.splitlines()
            if len(lines) > 10:
                logger.info(f"Parsing format output for {device} (showing first 5 and last 5 of {len(lines)} lines):")
                for line in lines[:5]:
                    logger.info(f"Format line: {line}")
                logger.info("... [output truncated] ...")
                for line in lines[-5:]:
                    logger.info(f"Format line: {line}")
            else:
                logger.info(f"Parsing format output for {device}:")
                for line in lines:
                    logger.info(f"Format line: {line}")

            # Process all lines for format detection
            for line in lines:
                match = re.search(format_pattern, line)
                if match:
                    format_id, resolution, frame_rate = match.groups()
                    formats.append({
                        "id": format_id,
                        "resolution": resolution,
                        "frame_rate": frame_rate
                    })

                    # Add resolution if not already in list
                    if resolution not in resolutions:
                        resolutions.append(resolution)

                    # Parse frame rate (handle both fractional and decimal)
                    if '/' in frame_rate:
                        num, denom = frame_rate.split('/')
                        rate = float(num) / float(denom)
                    else:
                        rate = float(frame_rate)

                    # Add frame rate if not already in list
                    if rate not in frame_rates:
                        frame_rates.append(rate)

            # If no formats found, use default formats
            if not formats:
                logger.info(f"No formats found for {device}, using default formats")
                return {
                    "formats": [],
                    "resolutions": ["1920x1080", "1280x720", "720x576", "720x480"],
                    "frame_rates": [23.98, 24, 25, 29.97, 30, 50, 59.94, 60]
                }

            logger.info(f"Found formats for {device}: {len(formats)} formats")
            return {
                "formats": formats,
                "resolutions": sorted(resolutions, key=lambda r: int(r.split('x')[0]), reverse=True),
                "frame_rates": sorted(frame_rates)
            }

        except Exception as e:
            logger.error(f"Error getting DeckLink formats: {str(e)}")
            # Return default formats in case of error
            return {
                "formats": [],
                "resolutions": ["1920x1080", "1280x720", "720x576", "720x480"],
                "frame_rates": [23.98, 24, 25, 29.97, 30, 50, 59.94, 60]
            }

    def _find_ffmpeg(self):
        """Find the path to ffmpeg"""
        # Add your ffmpeg detection logic here if needed
        # For now, assume it's in the system PATH
        return "ffmpeg" # Replace with your actual ffmpeg path detection


    self.last_save_time = 0  # Track the last time settings were saved
    self.save_debounce_ms = 1000  # Minimum time between saves in milliseconds
    logger.info(f"Using settings file: {self.settings_file}")