
# VMAF Test App - Local Setup Guide

This guide will help you set up and run the VMAF Test App on your local machine.

## Prerequisites

- Python 3.8 or higher
- FFmpeg installed and available in your PATH
- PyQt5 and related dependencies

## Installation Steps

1. **Clone or download the repository to your local machine**

2. **Install required dependencies:**
   ```
   pip install -r requirements.txt
   ```

3. **Ensure FFmpeg is properly installed:**
   The application requires FFmpeg with libvmaf support for VMAF analysis. You can verify your FFmpeg installation by running:
   ```
   ffmpeg -version
   ```
   Look for "libvmaf" in the configuration options.

4. **Configure VMAF models:**
   The application comes with pre-configured VMAF models in the `models` directory. If you have custom VMAF models, you can place them in this directory.

5. **Run the application:**
   ```
   python main.py
   ```
   
   For headless mode (without GUI):
   ```
   python main.py --headless
   ```

## Using Capture Hardware

If you're using Blackmagic capture hardware:

1. Ensure the Blackmagic Desktop Video drivers are installed on your system
2. Connect your capture device
3. Configure the application to use your specific device through the Options tab

## Troubleshooting

If you encounter issues with:

1. **FFmpeg not found**: Ensure FFmpeg is in your system PATH
2. **PyQt5 errors**: Verify your PyQt5 installation with `pip install --upgrade PyQt5`
3. **VMAF model errors**: Check that the models directory contains the proper JSON model files
4. **Capture device not detected**: Verify the device drivers are properly installed

## Output Files

Analysis results will be saved to the configured output directory (default is a 'tests' folder in the application directory).
