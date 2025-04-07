import json
import logging
import os
import platform
import re
import subprocess
import time
from typing import Dict, List, Any, Tuple, Optional

from PyQt5.QtCore import QObject, pyqtSignal

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

        # Default settings - DeckLink Intensity Shuttle specific settings
        self.default_settings = {
            "bookend": {
                "min_loops": 3,
                "max_loops": 10,
                "min_capture_time": 5,  # seconds
                "max_capture_time": 30,  # seconds
                "bookend_duration": 0.2,  # seconds
                "white_threshold": 200,  # 0-255 for white detection
                "frame_sampling_rate": 5,  # Added frame sampling rate
                "min_frame_sampling_rate": 1,  # Added minimum frame sampling rate
                "max_frame_sampling_rate": 30,  # Added maximum frame sampling rate
                "frame_offset": 3,  # Default frame offset (negative means go back)
                "adaptive_brightness": True,
                "motion_compensation": False,
                "fallback_to_full_video": True
            },
            # VMAF settings
            "vmaf": {
                "default_model": "vmaf_v0.6.1",
                "available_models": ["vmaf_v0.6.1", "vmaf_4k_v0.6.1", "vmaf_b_v0.6.3"],
                "subsample": 1,  # 1 = analyze every frame
                "threads": 0,    # 0 = auto
                "output_format": "json",
                "save_json": True,
                "save_plots": True,
                "pool_method": "mean",
                "feature_subsample": 1,
                "enable_motion_score": False,
                "enable_temporal_features": False,
                "psnr_enabled": True,
                "ssim_enabled": True,
                "tester_name": "",
                "test_location": ""
            },
            # Capture settings - Blackmagic Intensity Shuttle specific
            "capture": {
                "default_device": "Intensity Shuttle",
                "resolution": "1920x1080",
                "frame_rate": 29.97,  # Common default
                "pixel_format": "uyvy422",  # Standard for Intensity Shuttle
                "available_resolutions": ["1920x1080", "1280x720", "720x576", "720x486"],
                "available_frame_rates": [23.98, 24, 25, 29.97, 30, 50, 59.94, 60],
                "video_input": "hdmi",  # hdmi, sdi, component, composite, s-video
                "audio_input": "embedded",  # embedded, analog, aesebu
                "encoder": "libx264",
                "crf": 18,  # Higher quality for capture (lower value)
                "preset": "fast",  # Good balance of speed/quality for capture
                "disable_audio": False,
                "low_latency": True,
                "force_format": False,
                "format_code": "Hp29",  # Default format code for 1080p @ 29.97fps
                "width": 1920,
                "height": 1080,
                "scan_type": "p",  # progressive
                "is_interlaced": False,
                "retry_attempts": 3,  # Number of device connection retry attempts
                "retry_delay": 3,  # Seconds between retry attempts
                "recovery_timeout": 10  # Seconds to wait for device recovery
            },
            # Analysis settings
            "analysis": {
                "use_temp_files": True,
                "auto_alignment": True,
                "alignment_method": "Bookend Detection"
            },
            # Encoder settings
            "encoder": {
                "default_encoder": "libx264",
                "default_crf": 23,
                "default_preset": "medium"
            },
            # File paths
            "paths": {
                "default_output_dir": "",
                "reference_video_dir": "",
                "results_dir": "",
                "temp_dir": "",
                "models_dir": "",
                "ffmpeg_path": ""
            },
            # Debug settings
            "debug": {
                "log_level": "INFO",
                "save_logs": True,
                "show_commands": True,
                "suppress_ffmpeg_dialogs": True  # Suppress FFmpeg dialog windows
            },
            # Branding
            "branding": {
                "app_name": "VMAF Test App",
                "company_name": "Chroma",
                "enable_white_label": False,
                "footer_text": "© 2025 Chroma",
                "primary_color": "#4CAF50",
                "selected_theme": "System",
                "bg_color": "#2D2D30",
                "text_color": "#FFFFFF",
                "accent_color": "#007ACC",
                "logo_path": ""
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

    def load_settings(self) -> None:
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

    def _update_missing_settings(self) -> None:
        """Update settings with any missing keys from defaults"""
        updated = False

        # Recursively check for missing keys
        def update_dict(source: Dict, target: Dict) -> None:
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

    def save_settings(self) -> bool:
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

    def get_settings(self) -> Dict[str, Any]:
        """Get all settings"""
        return self.settings

    def get_setting(self, category: str, key: Optional[str] = None) -> Any:
        """Get a setting value by category and key"""
        if category not in self.settings:
            return self.default_settings.get(category, {})

        if key is None:
            return self.settings[category]

        default_value = None
        # Check if category exists in default settings and is a dictionary
        if category in self.default_settings and isinstance(self.default_settings[category], dict):
            # Now safely check if the key exists in the category dictionary
            if isinstance(key, str) and key in self.default_settings[category]:
                default_value = self.default_settings[category][key]
            # If key is a dictionary, we need to handle it differently
            elif not isinstance(key, str):
                # Return the default value for non-string keys
                return default_value

        # Check if the category is a dictionary before calling get()
        if isinstance(self.settings[category], dict):
            return self.settings[category].get(key, default_value)
        else:
            return default_value

    def update_setting(self, category: str, key: str, value: Any) -> bool:
        """Update a specific setting"""
        if category not in self.settings:
            self.settings[category] = {}

        self.settings[category][key] = value
        return self.save_settings()

    def set_setting(self, category: str, values: Dict[str, Any]) -> bool:
        """Set an entire category of settings (alias for update_category)"""
        return self.update_category(category, values)

    def update_category(self, category: str, values: Dict[str, Any]) -> bool:
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

    def reset_to_defaults(self) -> bool:
        """Reset all settings to defaults"""
        self.settings = self.default_settings.copy()
        return self.save_settings()

    def update_settings(self, settings: Dict[str, Any]) -> bool:
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

    def get_decklink_devices(self) -> List[str]:
        """Query available DeckLink devices using FFmpeg"""
        devices = []
        try:
            # Find FFmpeg path
            ffmpeg_path = self.get_ffmpeg_path()
            
            # Run FFmpeg command to list DeckLink devices with improved error handling
            cmd = [ffmpeg_path, "-f", "decklink", "-list_devices", "1", "-i", "dummy"]
            
            # Set up creation flags and startupinfo to suppress windows
            startupinfo = None
            creationflags = 0
            env = os.environ.copy()
            
            # Configure to suppress error dialogs on Windows
            if platform.system() == 'Windows':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0  # SW_HIDE
                if hasattr(subprocess, 'CREATE_NO_WINDOW'):
                    creationflags = subprocess.CREATE_NO_WINDOW
                # Add environment variables to suppress FFmpeg dialogs
                env.update({
                    "FFMPEG_HIDE_BANNER": "1",
                    "AV_LOG_FORCE_NOCOLOR": "1"
                })
            
            # Run command with configured startupinfo
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True,
                startupinfo=startupinfo,
                creationflags=creationflags,
                env=env,
                timeout=10  # Add timeout to prevent hanging
            )

            # Parse the error output (FFmpeg outputs device list to stderr)
            output = result.stderr or result.stdout  # Use stdout as fallback
            lines = output.split('\n')

            # Extract device names with improved parsing
            for line in lines:
                # Look for specific device mentions in the output
                if "'" in line and ("Decklink" in line or "Intensity" in line or "UltraStudio" in line):
                    try:
                        device_name = line.split("'")[1]
                        devices.append(device_name)
                    except:
                        pass

            # If no devices found with pattern matching, try alternate detection
            if not devices:
                # Also search for HDMI capture or similar phrasing
                for line in lines:
                    if "capture" in line.lower() and any(name in line for name in ["DeckLink", "Intensity", "Ultra", "Shuttle"]):
                        parts = line.split("'")
                        if len(parts) >= 2:
                            device_name = parts[1]
                            devices.append(device_name)

            # If still no devices detected, add default fallback options
            if not devices:
                logger.warning("No DeckLink devices detected, using default fallback options")
                devices = ["Intensity Shuttle", "DeckLink", "Intensity Pro", "UltraStudio"]

            logger.info(f"Found DeckLink devices: {devices}")
        except subprocess.TimeoutExpired:
            logger.error("Device detection timed out")
            # Add default device as fallback
            devices = ["Intensity Shuttle"]
        except Exception as e:
            logger.error(f"Error detecting DeckLink devices: {str(e)}")
            # Add default device as fallback
            devices = ["Intensity Shuttle"]

        return devices

    def get_decklink_formats(self, device: str) -> Dict[str, Any]:
        """Get available formats for a DeckLink device"""
        format_list = []
        format_map = {}  # Map of resolution -> list of frame rates

        try:
            # Check if the platform is Windows
            if platform.system() == 'Windows':
                # Try DirectShow approach first for Windows
                dshow_formats = self.get_decklink_formats_dshow(device)
                if dshow_formats.get("formats") or dshow_formats.get("format_map"):
                    logger.info("Successfully retrieved formats using DirectShow")
                    return dshow_formats

            # If DirectShow approach fails or not on Windows, use standard decklink approach
            # Check if ffmpeg is available
            ffmpeg_path = self.get_ffmpeg_path()
            if not ffmpeg_path:
                logger.warning("FFmpeg not found, unable to detect DeckLink formats")
                return {"formats": [], "format_map": {}}

            # Use ffmpeg to get available formats with improved error handling
            cmd = [ffmpeg_path, "-hide_banner", "-f", "decklink", "-list_formats", "1", "-i", device]
            logger.info(f"Getting formats for {device} using command: {' '.join(cmd)}")

            # Configure to suppress error dialogs on Windows
            startupinfo = None
            creationflags = 0
            env = os.environ.copy()
            
            if platform.system() == 'Windows':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0  # SW_HIDE
                if hasattr(subprocess, 'CREATE_NO_WINDOW'):
                    creationflags = subprocess.CREATE_NO_WINDOW
                # Add environment variables to suppress FFmpeg dialogs
                env.update({
                    "FFMPEG_HIDE_BANNER": "1",
                    "AV_LOG_FORCE_NOCOLOR": "1"
                })

            # Set a timeout to prevent hanging
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=True,
                startupinfo=startupinfo,
                creationflags=creationflags,
                env=env
            )
            
            try:
                stdout, stderr = process.communicate(timeout=10)  # 10 second timeout
            except subprocess.TimeoutExpired:
                process.kill()
                logger.warning(f"Timeout getting formats for {device}")
                # Return default formats for Intensity Shuttle if timeout
                return self._get_default_intensity_shuttle_formats()

            # Parse output to extract formats
            format_pattern = r'\s+([A-Za-z0-9]+)\s+([0-9]+x[0-9]+) at ([0-9]+(?:\/[0-9]+)?)'

            # Combine stdout and stderr for parsing as FFmpeg outputs to stderr
            output = stdout + stderr

            # Process all lines for format detection
            for line in output.splitlines():
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

                    # Check if this is interlaced (look for 'interlaced' in the line)
                    is_interlaced = 'interlaced' in line.lower()
                    scan_type = 'i' if is_interlaced else 'p'

                    format_item = {
                        "id": format_id,
                        "resolution": resolution,
                        "frame_rate": nice_rate,
                        "scan_type": scan_type,
                        "display": f"{resolution} @ {nice_rate} fps ({scan_type})"
                    }
                    format_list.append(format_item)

                    # Add to format map
                    if resolution not in format_map:
                        format_map[resolution] = []
                    if nice_rate not in format_map[resolution]:
                        format_map[resolution].append(nice_rate)

            # If no formats found, use default formats for Intensity Shuttle
            if not format_list:
                logger.info(f"No formats found for {device}, using default Intensity Shuttle formats")
                return self._get_default_intensity_shuttle_formats()

            # Sort frame rates within each resolution
            for res in format_map:
                format_map[res] = sorted(format_map[res])

            logger.info(f"Found formats for {device}: {len(format_list)} formats")
            return {
                "formats": format_list,
                "format_map": format_map
            }

        except Exception as e:
            logger.error(f"Error getting dshow formats: {str(e)}")
            return {"formats": [], "format_map": {}}

    def get_device_formats(self, device_name: str) -> List[Dict[str, Any]]:
        """Get available formats for the specified device directly from ffmpeg output"""
        try:
            logger.info(f"Getting formats for device: {device_name}")
            formats = []

            # First try using decklink with list_formats
            decklink_results = self.get_decklink_formats(device_name)
            if decklink_results and decklink_results.get("formats"):
                return decklink_results.get("formats", [])

            # If that fails, try using DirectShow on Windows
            if platform.system() == 'Windows':
                ffmpeg_path = self.get_ffmpeg_path()
                cmd = [ffmpeg_path, "-hide_banner", "-f", "dshow", "-list_options", "true", "-i", f"video=Decklink Video Capture"]
                logger.info(f"Getting formats using dshow command: {' '.join(cmd)}")

                # Configure subprocess to suppress dialogs
                startupinfo = None
                creationflags = 0
                env = os.environ.copy()
                
                if platform.system() == 'Windows':
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = 0  # SW_HIDE
                    if hasattr(subprocess, 'CREATE_NO_WINDOW'):
                        creationflags = subprocess.CREATE_NO_WINDOW
                    # Add environment variables to suppress FFmpeg dialogs
                    env.update({
                        "FFMPEG_HIDE_BANNER": "1",
                        "AV_LOG_FORCE_NOCOLOR": "1"
                    })

                process = subprocess.Popen(
                    cmd, 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE, 
                    text=True,
                    startupinfo=startupinfo,
                    creationflags=creationflags,
                    env=env
                )
                
                try:
                    stdout, stderr = process.communicate(timeout=10)  # 10 second timeout
                    combined_output = stdout + stderr
                except subprocess.TimeoutExpired:
                    process.kill()
                    logger.warning("Timeout getting dshow formats")
                    combined_output = ""

                # Parse the output to extract formats
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

            # If we found formats, return them
            if formats:
                logger.info(f"Found {len(formats)} formats for device {device_name}")
                return formats

            # If all methods failed, return default formats for Intensity Shuttle
            logger.warning("Failed to detect formats using direct methods, using defaults for Intensity Shuttle")
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

    def get_ffmpeg_path(self) -> str:
        """Find the path to ffmpeg"""
        try:
            # First check if we have a custom path stored in settings
            custom_path = self.get_setting("paths", "ffmpeg_path")
            if custom_path and os.path.exists(custom_path) and os.path.isfile(custom_path):
                return custom_path

            # Check if ffmpeg is in the path
            if platform.system() == 'Windows':
                try:
                    result = subprocess.run(["where", "ffmpeg"], capture_output=True, text=True)
                    if result.returncode == 0 and result.stdout.strip():
                        return result.stdout.strip().split('\n')[0]
                except:
                    pass  # Fall through to next method
            else:
                try:
                    result = subprocess.run(["which", "ffmpeg"], capture_output=True, text=True)
                    if result.returncode == 0 and result.stdout.strip():
                        return result.stdout.strip()
                except:
                    pass  # Fall through to next method

            # Look in common directories
            common_paths = []
            
            if platform.system() == 'Windows':
                # Windows common paths
                program_files = os.environ.get('ProgramFiles', 'C:\\Program Files')
                program_files_x86 = os.environ.get('ProgramFiles(x86)', 'C:\\Program Files (x86)')
                
                common_paths = [
                    os.path.join(program_files, "ffmpeg", "bin", "ffmpeg.exe"),
                    os.path.join(program_files_x86, "ffmpeg", "bin", "ffmpeg.exe"),
                    "C:\\ffmpeg\\bin\\ffmpeg.exe",
                    os.path.join(os.path.expanduser("~"), "ffmpeg", "bin", "ffmpeg.exe")
                ]
            else:
                # Linux/Mac common paths
                common_paths = [
                    "/usr/bin/ffmpeg",
                    "/usr/local/bin/ffmpeg",
                    "/opt/local/bin/ffmpeg",
                    "/opt/homebrew/bin/ffmpeg",
                    os.path.join(os.path.expanduser("~"), "bin", "ffmpeg")
                ]
                
            for path in common_paths:
                if os.path.exists(path) and os.path.isfile(path):
                    return path

            # Default fallback to command name
            return "ffmpeg"
        except Exception as e:
            logger.error(f"Error finding ffmpeg: {e}")
            return "ffmpeg"

    def get_capture_formats(self, device_name: str) -> List[str]:
        """Get available capture formats for a device using ffmpeg with decklink"""
        formats = []

        try:
            # Build ffmpeg command to list device options - using decklink format
            ffmpeg_path = self.get_ffmpeg_path()
            
            cmd = [
                ffmpeg_path,
                "-hide_banner",
                "-f", "decklink",
                "-list_formats", "1",
                "-i", device_name
            ]

            # Configure to suppress error dialogs
            startupinfo = None
            creationflags = 0
            env = os.environ.copy()
            
            if platform.system() == 'Windows':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0  # SW_HIDE
                if hasattr(subprocess, 'CREATE_NO_WINDOW'):
                    creationflags = subprocess.CREATE_NO_WINDOW
                # Add environment variables to suppress FFmpeg dialogs
                env.update({
                    "FFMPEG_HIDE_BANNER": "1",
                    "AV_LOG_FORCE_NOCOLOR": "1"
                })

            # Run the command and capture output
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                startupinfo=startupinfo,
                creationflags=creationflags,
                env=env
            )
            stdout, stderr = process.communicate(timeout=10)

            # Combine stdout and stderr as ffmpeg outputs to stderr
            output = stderr.decode() if stderr else stdout.decode()

            # Extract format lines
            format_pattern = r'\s+([A-Za-z0-9]+)\s+([0-9]+x[0-9]+) at ([0-9]+(?:\/[0-9]+)?)'
            matches = re.findall(format_pattern, output)
            
            # Process all matches to create format strings
            for format_code, resolution, frame_rate in matches:
                # Parse frame rate (handle both fractional and decimal)
                if '/' in frame_rate:
                    num, denom = frame_rate.split('/')
                    rate = float(num) / float(denom)
                else:
                    rate = float(frame_rate)

                # Format nicely
                if abs(rate - 23.976) < 0.01:
                    nice_rate = "23.98"
                elif abs(rate - 29.97) < 0.01:
                    nice_rate = "29.97"
                elif abs(rate - 59.94) < 0.01:
                    nice_rate = "59.94"
                else:
                    nice_rate = str(int(rate)) if rate == int(rate) else f"{rate:.2f}"

                format_str = f"{format_code} ({resolution} @ {nice_rate} fps)"
                formats.append(format_str)
                logger.info(f"Found format: {format_str}")
        except Exception as e:
            logger.error(f"Error getting capture formats: {e}")

        # If no formats found, use default formats
        if not formats:
            formats = [
                "Hp29 (1920x1080 @ 29.97 fps)",
                "Hp30 (1920x1080 @ 30 fps)",
                "Hp25 (1920x1080 @ 25 fps)",
                "hp59 (1280x720 @ 59.94 fps)",
                "hp60 (1280x720 @ 60 fps)",
                "hp50 (1280x720 @ 50 fps)"
            ]
            logger.info("Using default formats for Intensity Shuttle")

        return formats

    def test_device_connection(self, device_name: str) -> Tuple[bool, str]:
        """Test if a DeckLink device is properly connected and accessible"""
        try:
            ffmpeg_path = self.get_ffmpeg_path()
            
            # First try listing formats (lightweight test)
            cmd = [
                ffmpeg_path,
                "-hide_banner", 
                "-f", "decklink", 
                "-list_formats", "1", 
                "-i", device_name
            ]
            
            # Configure to suppress error dialogs
            startupinfo = None
            creationflags = 0
            env = os.environ.copy()
            
            if platform.system() == 'Windows':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0  # SW_HIDE
                if hasattr(subprocess, 'CREATE_NO_WINDOW'):
                    creationflags = subprocess.CREATE_NO_WINDOW
                # Add environment variables to suppress FFmpeg dialogs
                env.update({
                    "FFMPEG_HIDE_BANNER": "1",
                    "AV_LOG_FORCE_NOCOLOR": "1"
                })
            
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True,
                timeout=5,
                startupinfo=startupinfo,
                creationflags=creationflags,
                env=env
            )
            
            # If we get format information, device is connected
            if "Supported formats" in result.stderr or "Supported formats" in result.stdout:
                return True, "Device connected and responding"
                
            # If not, try a more thorough test - minimal capture
            cmd = [
                ffmpeg_path,
                "-hide_banner",
                "-f", "decklink",
                "-t", "0.1",  # Try for just 0.1 seconds
                "-i", device_name,
                "-f", "null",
                "-"
            ]
            
            try:
                result = subprocess.run(
                    cmd, 
                    capture_output=True, 
                    text=True,
                    timeout=5,
                    startupinfo=startupinfo,
                    creationflags=creationflags,
                    env=env
                )
                
                # Check for signs of successful capture
                output = result.stderr + result.stdout
                if "frame=" in output or "time=" in output:
                    return True, "Device successfully captured frames"
            except subprocess.TimeoutExpired:
                return False, "Capture test timed out"
                
            # If we get here, the device wasn't responsive
            return False, "Device not responding properly"
            
        except Exception as e:
            return False, f"Error testing device: {str(e)}"

        except Exception as e:
            logger.error(f"Error getting DeckLink formats: {str(e)}")
            # Return default formats for Intensity Shuttle in case of error
            return self._get_default_intensity_shuttle_formats()

    def _get_default_intensity_shuttle_formats(self) -> Dict[str, Any]:
        """Return default format specifications for Intensity Shuttle"""
        # These are the standard formats supported by Intensity Shuttle
        default_format_map = {
            "1920x1080": [23.98, 24, 25, 29.97, 30],
            "1280x720": [50, 59.94, 60],
            "720x576": [25, 50],  # PAL
            "720x480": [29.97, 59.94]  # NTSC
        }
        
        # Create format list with appropriate codes
        formats = [
            # 1080p formats
            {"id": "23ps", "resolution": "1920x1080", "frame_rate": 23.98, "scan_type": "p", 
             "display": "1920x1080 @ 23.98 fps (p)"},
            {"id": "24ps", "resolution": "1920x1080", "frame_rate": 24, "scan_type": "p", 
             "display": "1920x1080 @ 24 fps (p)"},
            {"id": "Hp25", "resolution": "1920x1080", "frame_rate": 25, "scan_type": "p", 
             "display": "1920x1080 @ 25 fps (p)"},
            {"id": "Hp29", "resolution": "1920x1080", "frame_rate": 29.97, "scan_type": "p", 
             "display": "1920x1080 @ 29.97 fps (p)"},
            {"id": "Hp30", "resolution": "1920x1080", "frame_rate": 30, "scan_type": "p", 
             "display": "1920x1080 @ 30 fps (p)"},
            
            # 1080i formats
            {"id": "Hi50", "resolution": "1920x1080", "frame_rate": 25, "scan_type": "i", 
             "display": "1920x1080 @ 25 fps (i)"},
            {"id": "Hi59", "resolution": "1920x1080", "frame_rate": 29.97, "scan_type": "i", 
             "display": "1920x1080 @ 29.97 fps (i)"},
            
            # 720p formats
            {"id": "hp50", "resolution": "1280x720", "frame_rate": 50, "scan_type": "p", 
             "display": "1280x720 @ 50 fps (p)"},
            {"id": "hp59", "resolution": "1280x720", "frame_rate": 59.94, "scan_type": "p", 
             "display": "1280x720 @ 59.94 fps (p)"},
            {"id": "hp60", "resolution": "1280x720", "frame_rate": 60, "scan_type": "p", 
             "display": "1280x720 @ 60 fps (p)"},
            
            # SD formats
            {"id": "pal", "resolution": "720x576", "frame_rate": 25, "scan_type": "i", 
             "display": "720x576 @ 25 fps (i)"},
            {"id": "ntsc", "resolution": "720x480", "frame_rate": 29.97, "scan_type": "i", 
             "display": "720x480 @ 29.97 fps (i)"}
        ]
        
        return {
            "formats": formats,
            "format_map": default_format_map
        }











    def get_decklink_formats_dshow(self, device: str) -> Dict[str, Any]:
        """Get available formats for a DeckLink device using DirectShow on Windows"""
        format_list = []
        format_map = {}  # Map of resolution -> list of frame rates

        try:
            # Use ffmpeg with DirectShow to get formats
            ffmpeg_path = self.get_ffmpeg_path()
            
            # Try multiple device name variations to maximize success chance
            # This is important as the DirectShow device name may not match the decklink name
            device_variations = [
                f"video=Decklink Video Capture",
                f"video={device}",
                f"video=Intensity Shuttle",
                f"video=Blackmagic",
                f"video=UltraStudio"
            ]
            
            logger.info(f"Attempting to detect formats using DirectShow for {device}")
            success = False
            output_combined = ""
            
            for device_name in device_variations:
                # Skip if we already got formats
                if success:
                    break
                    
                cmd = [ffmpeg_path, "-hide_banner", "-f", "dshow", "-list_options", "true", "-i", device_name]
                logger.info(f"Getting formats using dshow command: {' '.join(cmd)}")

                # Configure to suppress error dialogs
                startupinfo = None
                creationflags = 0
                env = os.environ.copy()
                
                if platform.system() == 'Windows':
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = 0  # SW_HIDE
                    if hasattr(subprocess, 'CREATE_NO_WINDOW'):
                        creationflags = subprocess.CREATE_NO_WINDOW
                    # Add environment variables to suppress FFmpeg dialogs
                    env.update({
                        "FFMPEG_HIDE_BANNER": "1",
                        "AV_LOG_FORCE_NOCOLOR": "1"
                    })

                try:
                    process = subprocess.Popen(
                        cmd, 
                        stdout=subprocess.PIPE, 
                        stderr=subprocess.PIPE, 
                        text=True,
                        startupinfo=startupinfo,
                        creationflags=creationflags,
                        env=env
                    )
                    
                    stdout, stderr = process.communicate(timeout=10)  # 10 second timeout
                    
                    # Combine output
                    output = stdout + stderr
                    output_combined += output  # Keep combined output for fallback parsing
                    
                    # Check if we got useful output
                    if "DirectShow video device options" in output or "pixel_format=" in output:
                        logger.info(f"Found DirectShow information using {device_name}")
                        success = True
                        
                        # Log some output for debugging
                        lines = output.splitlines()
                        for i, line in enumerate(lines[:10]):  # Log first 10 lines
                            logger.debug(f"DirectShow output line {i}: {line}")
                        
                        # Primary pattern for pixel format, resolution and frame rate
                        format_pattern = r'pixel_format=(\w+)\s+min\s+s=(\d+x\d+)\s+fps=(\d+(?:\.\d+)?)'
                        
                        # Alternative patterns to try if the primary one doesn't match
                        alt_patterns = [
                            r'vcodec=(\w+)\s+min\s+s=(\d+x\d+)\s+fps=(\d+(?:\.\d+)?)',  # vcodec format
                            r'min\s+s=(\d+x\d+)\s+fps=(\d+(?:\.\d+)?)'  # Just resolution and framerate
                        ]
                        
                        # First try the primary pattern
                        matches = re.findall(format_pattern, output)
                        if matches:
                            for pixel_format, resolution, fps_str in matches:
                                try:
                                    frame_rate = float(fps_str)
                                    
                                    # Format the rate nicely
                                    nice_rate = frame_rate
                                    if abs(frame_rate - 23.976) < 0.01:
                                        nice_rate = 23.98
                                    elif abs(frame_rate - 29.97) < 0.01:
                                        nice_rate = 29.97
                                    elif abs(frame_rate - 59.94) < 0.01:
                                        nice_rate = 59.94
                                    
                                    # Create unique format ID
                                    format_id = f"{resolution.replace('x', '_')}_{int(nice_rate * 100)}"
                                    
                                    # Create format item
                                    format_item = {
                                        "id": format_id,
                                        "resolution": resolution,
                                        "frame_rate": nice_rate,
                                        "pixel_format": pixel_format,
                                        "scan_type": "p",  # DirectShow typically reports progressive
                                        "display": f"{resolution} @ {nice_rate} fps ({pixel_format})"
                                    }
                                    
                                    # Parse width and height from resolution
                                    try:
                                        width, height = map(int, resolution.split('x'))
                                        format_item["width"] = width
                                        format_item["height"] = height
                                    except:
                                        # Use default values if parsing fails
                                        format_item["width"] = 1920
                                        format_item["height"] = 1080
                                    
                                    # Add to format list
                                    format_list.append(format_item)
                                    
                                    # Add to format map
                                    if resolution not in format_map:
                                        format_map[resolution] = []
                                    if nice_rate not in format_map[resolution]:
                                        format_map[resolution].append(nice_rate)
                                except Exception as format_err:
                                    logger.warning(f"Error parsing format: {format_err}")
                        
                        # If primary pattern didn't find anything, try alternative patterns
                        if not format_list:
                            for pattern in alt_patterns:
                                # Skip if we already found formats
                                if format_list:
                                    break
                                    
                                try:
                                    alt_matches = re.findall(pattern, output)
                                    if alt_matches:
                                        logger.info(f"Found matches using alternative pattern: {pattern}")
                                        
                                        # Handle different pattern outputs
                                        if pattern == alt_patterns[0]:  # vcodec pattern
                                            for vcodec, resolution, fps_str in alt_matches:
                                                frame_rate = float(fps_str)
                                                nice_rate = self._normalize_frame_rate(frame_rate)
                                                
                                                # Create format item
                                                format_id = f"{resolution.replace('x', '_')}_{int(nice_rate * 100)}"
                                                format_item = {
                                                    "id": format_id,
                                                    "resolution": resolution,
                                                    "frame_rate": nice_rate,
                                                    "vcodec": vcodec,
                                                    "scan_type": "p",
                                                    "display": f"{resolution} @ {nice_rate} fps ({vcodec})"
                                                }
                                                
                                                # Parse width and height
                                                try:
                                                    width, height = map(int, resolution.split('x'))
                                                    format_item["width"] = width
                                                    format_item["height"] = height
                                                except:
                                                    format_item["width"] = 1920
                                                    format_item["height"] = 1080
                                                
                                                # Add to results
                                                format_list.append(format_item)
                                                
                                                # Add to format map
                                                if resolution not in format_map:
                                                    format_map[resolution] = []
                                                if nice_rate not in format_map[resolution]:
                                                    format_map[resolution].append(nice_rate)
                                        
                                        elif pattern == alt_patterns[1]:  # Simple pattern
                                            for resolution, fps_str in alt_matches:
                                                frame_rate = float(fps_str)
                                                nice_rate = self._normalize_frame_rate(frame_rate)
                                                
                                                # Create format item
                                                format_id = f"{resolution.replace('x', '_')}_{int(nice_rate * 100)}"
                                                format_item = {
                                                    "id": format_id,
                                                    "resolution": resolution,
                                                    "frame_rate": nice_rate,
                                                    "pixel_format": "default",
                                                    "scan_type": "p",
                                                    "display": f"{resolution} @ {nice_rate} fps"
                                                }
                                                
                                                # Parse width and height
                                                try:
                                                    width, height = map(int, resolution.split('x'))
                                                    format_item["width"] = width
                                                    format_item["height"] = height
                                                except:
                                                    format_item["width"] = 1920
                                                    format_item["height"] = 1080
                                                
                                                # Add to results
                                                format_list.append(format_item)
                                                
                                                # Add to format map
                                                if resolution not in format_map:
                                                    format_map[resolution] = []
                                                if nice_rate not in format_map[resolution]:
                                                    format_map[resolution].append(nice_rate)
                                except Exception as alt_err:
                                    logger.warning(f"Error with alternative pattern: {alt_err}")
                    else:
                        # Try next variation
                        logger.debug(f"No DirectShow information found with {device_name}")
                        continue
                        
                except subprocess.TimeoutExpired:
                    process.kill()
                    logger.warning(f"Timeout getting dshow formats using {device_name}")
                    # Try next variation
                    continue
            
            # If we didn't get any formats but have output, try to parse resolutions and frame rates directly
            if not format_list and output_combined:
                logger.info("No formats found with standard patterns, trying to parse resolutions and framerates directly")
                
                # Look for resolutions (common formats: 1920x1080, 1280x720, etc.)
                res_pattern = r'(?<!\d)(\d{3,4}x\d{3,4})(?!\d)'
                res_matches = re.findall(res_pattern, output_combined)
                
                # Look for frame rates (23.98, 29.97, 30, 59.94, 60)
                fps_pattern = r'(?<!\d)((?:23\.98|24|25|29\.97|30|50|59\.94|60)(?:\d*)?)(?!\d)'
                fps_matches = re.findall(fps_pattern, output_combined)
                
                # If we found both resolutions and frame rates, create formats
                if res_matches and fps_matches:
                    logger.info(f"Found {len(res_matches)} resolutions and {len(fps_matches)} frame rates via direct parsing")
                    
                    # Get unique values
                    resolutions = list(set(res_matches))
                    frame_rates = [float(fps) for fps in set(fps_matches)]
                    
                    # Sort by resolution size
                    resolutions.sort(key=lambda r: int(r.split('x')[0]) * int(r.split('x')[1]), reverse=True)
                    frame_rates.sort()
                    
                    # Create a format for each combination (limit to reasonable combinations)
                    for resolution in resolutions[:3]:  # Limit to top 3 resolutions
                        width, height = map(int, resolution.split('x'))
                        
                        for fps in frame_rates[:4]:  # Limit to top 4 framerates
                            nice_rate = self._normalize_frame_rate(fps)
                            
                            # Create format ID
                            format_id = f"{resolution.replace('x', '_')}_{int(nice_rate * 100)}"
                            
                            # Create format item
                            format_item = {
                                "id": format_id,
                                "resolution": resolution,
                                "frame_rate": nice_rate,
                                "width": width,
                                "height": height,
                                "pixel_format": "default",
                                "scan_type": "p",
                                "display": f"{resolution} @ {nice_rate} fps"
                            }
                            
                            # Add to format list
                            format_list.append(format_item)
                            
                            # Add to format map
                            if resolution not in format_map:
                                format_map[resolution] = []
                            if nice_rate not in format_map[resolution]:
                                format_map[resolution].append(nice_rate)
            
            # Sort frame rates and ensure they're unique
            for res in format_map:
                format_map[res] = sorted(list(set(format_map[res])))

            logger.info(f"Found {len(format_list)} formats via DirectShow")
            return {
                "formats": format_list,
                "format_map": format_map
            }

        except Exception as e:
            logger.error(f"Error getting dshow formats: {str(e)}")
            return {"formats": [], "format_map": {}}

    def _normalize_frame_rate(self, rate: float) -> float:
        """Normalize frame rate to standard values"""
        if abs(rate - 23.976) < 0.01:
            return 23.98
        elif abs(rate - 29.97) < 0.01:
            return 29.97
        elif abs(rate - 59.94) < 0.01:
            return 59.94
        return rate










