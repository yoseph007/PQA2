# VMAF Test App Quick Start Guide

## Installation

1. **Install Requirements**
   ```bash
   pip install -r requirements.txt
   ```

2. **Make sure FFmpeg is installed** and available in your system PATH
   - VMAF Test App uses FFmpeg with DeckLink support
   - Your FFmpeg build must have `decklink` support enabled

3. **Install Blackmagic Drivers**
   - Download Desktop Video drivers from [Blackmagic Design](https://www.blackmagicdesign.com/support/family/capture-and-playback)
   - Install according to your operating system instructions

## Running the Application

Start the application using:
```bash
python -m app.main
```

## Capture Process

1. **Select Capture Device**
   - Choose your "Intensity Shuttle" from the dropdown
   - Click "Refresh Devices" if your device isn't listed

2. **Configure Capture Settings**
   - Check "Auto-detect trigger" if you want to use the white frame trigger
   - Set the trigger delay if needed

3. **Start Capture**
   - Click "Start Capture"
   - Select the output file location
   - The application will start recording from your Intensity Shuttle

4. **Stop Capture**
   - Click "Stop Capture" to end recording
   - The video will be saved to your specified location

## Analysis Process

1. **Select Reference Video**
   - Click "Browse..." to select your reference video file

2. **Configure Analysis Settings**
   - Choose the VMAF model from the dropdown
   - Select the analysis duration

3. **Run Analysis**
   - Click "Run VMAF Analysis" 
   - The application will calculate VMAF scores between the captured and reference videos

4. **Export Results**
   - When analysis is complete, click "Export PDF Report"
   - Choose where to save the PDF certificate

## Troubleshooting

### Capture Errors

- **"Cannot access the DeckLink device"**
  - Ensure the device is properly connected
  - Check that Blackmagic drivers are installed
  - Make sure no other application is using the device

- **FFmpeg Command Line Test**
  - If you have issues with the app, try this command that we know works:
  ```
  ffmpeg -f decklink -i "Intensity Shuttle" -c:v libx264 -preset fast -crf 23 test_output.mp4
  ```

### Analysis Errors

- **VMAF Analysis Fails**
  - Ensure both videos have the same resolution
  - Check that FFmpeg has libvmaf support
  - Verify the VMAF model files exist in your system

## Mode Selection

- **Normal Mode** - Uses actual Blackmagic hardware
- **Dummy Mode** - Uses simulated devices for testing without hardware

## Additional Help

See the complete documentation in `/docs/MANUAL.md` for detailed information.