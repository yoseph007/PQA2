import subprocess
import re
import logging
from PyQt5.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)

class DeviceDetectionThread(QThread):
    finished = pyqtSignal(list)
 
 
    # Update the run method in DeviceDetectionThread
    def run(self):
        devices = []
        try:
            # Get the list of supported devices
            logger.info("Detecting DeckLink devices...")
            
            # Add a delay before detection to ensure device is ready
            import time
            time.sleep(1)
            
            # Method 1: Try direct specific Blackmagic Desktop 12.6 compatible approach
            try:
                result = subprocess.run(
                    ["ffmpeg", "-f", "decklink", "-list_formats", "1", "-i", "Intensity Shuttle"],
                    stderr=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    text=True,
                    timeout=5  # Reduced timeout
                )
                # If this succeeds without error, we know the device exists
                if result.returncode == 1 and "Intensity Shuttle" in (result.stderr + result.stdout):
                    devices.append({
                        "id": "Intensity Shuttle",
                        "name": "Intensity Shuttle (detected)",
                        "input": True
                    })
                    logger.info("Detected Intensity Shuttle via direct query")
            except Exception as e:
                logger.debug(f"Direct detection attempt failed: {e}")
            
            # Method 2: Traditional list_devices approach with improved timeout
            if not devices:
                try:
                    result = subprocess.run(
                        ["ffmpeg", "-f", "decklink", "-list_devices", "true", "-i", "dummy"],
                        stderr=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        text=True,
                        timeout=5  # Reduced timeout
                    )
                    output = result.stderr + result.stdout
                    
                    # Parse the device names
                    device_pattern = re.compile(r'\[decklink @ [^\]]+\]\s+\[(\d+)\]\s+(.+)')
                    for line in output.split('\n'):
                        match = device_pattern.search(line)
                        if match:
                            device_id = match.group(1)
                            device_name = match.group(2).strip()
                            devices.append({
                                "id": device_name,
                                "name": device_name,
                                "input": True
                            })
                            logger.info(f"Found DeckLink device: {device_name}")
                except Exception as e:
                    logger.debug(f"List devices attempt failed: {e}")
            
            # Method 3: Fallback to known names
            if not devices:
                logger.info("Falling back to known device names")
                devices.append({
                    "id": "Intensity Shuttle",
                    "name": "Intensity Shuttle (default)",
                    "input": True
                })
        except Exception as e:
            logger.error(f"Device detection error: {str(e)}")
        
        # Always ensure Intensity Shuttle is in the list for your setup
        if not any(d["id"] == "Intensity Shuttle" for d in devices):
            devices.append({
                "id": "Intensity Shuttle",
                "name": "Intensity Shuttle (forced)",
                "input": True
            })
            logger.info("Added forced Intensity Shuttle device")
            
        self.finished.emit(devices)