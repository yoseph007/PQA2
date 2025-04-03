# VMAF Test Application

## Features
- Blackmagic capture device support
- Frame-perfect video alignment
- VMAF quality analysis
- Cross-platform GUI
- Automated video analysis with PSNR and SSIM metrics

## Installation & Usage

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