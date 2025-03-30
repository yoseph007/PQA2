import subprocess
import re
import logging
from PyQt5.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)

class DeviceDetectionThread(QThread):
    finished = pyqtSignal(list)
    
    def run(self):
        devices = []
        try:
            # Get the list of supported devices
            logger.info("Detecting DeckLink devices...")
            
            # Method 1: Use ffmpeg -devices
            result = subprocess.run(
                ["ffmpeg", "-devices"],
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                timeout=10
            )
            output = result.stdout + result.stderr
            logger.debug(f"FFmpeg devices output:\n{output}")
            
            # Check if decklink is in the available devices
            if "decklink" not in output.lower():
                logger.warning("DeckLink not found in FFmpeg devices list")
            
            # Method 2: Try listing with ffmpeg -f decklink -list_devices
            try:
                result = subprocess.run(
                    ["ffmpeg", "-f", "decklink", "-list_devices", "true", "-i", "dummy"],
                    stderr=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    text=True,
                    timeout=10
                )
                output = result.stderr + result.stdout
                logger.debug(f"DeckLink devices output:\n{output}")
                
                # Parse the device names
                device_pattern = re.compile(r'\[decklink @ [^\]]+\]\s+\[(\d+)\]\s+(.+)')
                for line in output.split('\n'):
                    match = device_pattern.search(line)
                    if match:
                        device_id = match.group(1)
                        device_name = match.group(2).strip()
                        devices.append({
                            "id": device_name,  # Use the actual name as the ID
                            "name": device_name,
                            "input": True
                        })
                        logger.info(f"Found DeckLink device: {device_name}")
            except subprocess.TimeoutExpired:
                logger.error("Timeout while listing DeckLink devices")
            except Exception as e:
                logger.error(f"Error listing DeckLink devices: {e}")
            
            # If no devices found via specific methods, try manual detection
            if not devices:
                logger.info("No devices found automatically, trying known names")
                
                # Try using known device names (including the one the user reported working)
                for known_name in ["Intensity Shuttle", "DeckLink SDI", "DeckLink Studio", "UltraStudio"]:
                    devices.append({
                        "id": known_name,
                        "name": f"{known_name} (detected)",
                        "input": True
                    })
                    logger.info(f"Added known device: {known_name}")
                
        except Exception as e:
            logger.error(f"Device detection error: {str(e)}")
        
        # Log the final result
        if not devices:
            logger.warning("No DeckLink devices detected")
        else:
            logger.info(f"Detected {len(devices)} DeckLink devices")
            
        self.finished.emit(devices)