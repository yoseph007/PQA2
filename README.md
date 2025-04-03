# VMAF Test Application

⚠️ **NOTE: This application requires local hardware (Blackmagic capture device) and is designed to run on your local machine, not in cloud environments like Replit.**

## Features
- Blackmagic capture device support (requires local hardware connection)
- Frame-perfect video alignment
- VMAF quality analysis
- Cross-platform GUI
- Automated video analysis with PSNR and SSIM metrics

## Installation & Usage (Local Machine Only)

### Quick Start
```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py
```

### Local Development
See [LOCAL_SETUP.md](./LOCAL_SETUP.md) for detailed setup instructions.

### Windows Users
Run the included batch file:
```
run_vmaf_app.bat
```

### Command Line Options
```
python main.py --headless  # Run without GUI (for automation)