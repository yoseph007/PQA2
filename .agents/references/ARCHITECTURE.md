# VMAF Test Application Architecture

## Overview
This application is a PyQt5-based tool for capturing video (specifically utilizing Blackmagic capture devices via FFmpeg), aligning frames, and calculating VMAF (Video Multimethod Assessment Fusion) quality scores.

## Key Components

### 1. `CaptureManager` (`app.capture.CaptureManager`)
- **Role**: Manages the video capture process.
- **Mechanism**: Spawns `ffmpeg` subprocesses to capture video. It operates on a separate `QThread` (`CaptureMonitor`) to avoid blocking the main UI thread.
- **Important**: Uses state management (`CaptureState`) to track IDLE, INITIALIZING, CAPTURING, PROCESSING, COMPLETED, and ERROR states. 

### 2. `Bookend Alignment` (`app.bookend_alignment`)
- **Role**: Ensures frame-perfect alignment between reference and distorted videos.
- **Mechanism**: Utilizes OpenCV (`cv2`) to detect specific visual markers or barcodes injected into the video stream (the "bookends"). This ensures that VMAF analysis starts and stops on the exact same frame across both videos.
- **Thread Safety**: Runs on `QThread` with signals emitted for progress updates.

### 3. `VMAFAnalyzer` (`app.vmaf_analyzer.VMAFAnalyzer`)
- **Role**: Calculates the VMAF score comparing the aligned captured video to the reference.
- **Mechanism**: Executes `ffmpeg` with the `libvmaf` filter.
- **Configurability**: Supports varying threads, subsampling (e.g., analyzing every Nth frame), pooling methods (mean, harmonic_mean), and optional metrics like PSNR and SSIM via the `OptionsManager`.

### 4. `MainWindow` (`app.ui.main_window.MainWindow`)
- **Role**: The primary entry point for user interaction.
- **Mechanism**: Coordinates interactions between the `CaptureManager`, `FileManager`, and `OptionsManager`. 
- **Threading Model**: All long-running tasks (capture, alignment, VMAF) MUST run in background `QThread`s and communicate with the main window solely via PyQt signals and slots.

## Threading & Concurrency Rule
**NEVER block the main UI thread.** All subprocess calls to `ffmpeg`, `ffprobe`, or heavy OpenCV processing must be dispatched to a worker `QThread` and report status back to the main thread via signals (e.g., `progress_updated`, `error_occurred`).
