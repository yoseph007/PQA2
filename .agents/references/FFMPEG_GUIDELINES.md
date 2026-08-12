# FFmpeg & Subprocess Guidelines

## Overview
The VMAF Test Application relies heavily on `ffmpeg` for video capture and `libvmaf` filtering, and `ffprobe` for validation. Modifying these subprocess commands can easily introduce subtle regressions.

## Rules for FFmpeg Invocations

1. **Subprocess Management**:
   - Always use `subprocess.run` or `subprocess.Popen`.
   - When using `Popen`, ensure standard output/error are captured and properly drained to prevent deadlocks (e.g., using `stderr=subprocess.PIPE` and reading in a thread).

2. **Error Handling & Validation**:
   - Before operating on a video file, validate its integrity using `ffprobe` (as seen in `validate_video_file`).
   - Check the `returncode` of all `ffmpeg` subprocesses. `0` indicates success.

3. **VMAF Filter Construction**:
   - When constructing the `libvmaf` filter string in `VMAFAnalyzer`, parameters must be formatted exactly as required by the FFmpeg version in use.
   - Example template: `libvmaf=model=path/to/model:n_threads=4:feature=name=psnr`

4. **Moov Atom Issues (Faststart)**:
   - Captured videos can sometimes lack a proper moov atom if the capture is interrupted. Use the `repair_video_file` function (which applies `-movflags faststart`) if a file fails validation before throwing a fatal error.

5. **Paths**:
   - Always wrap file paths in quotes or use proper array structures in `subprocess` to handle spaces in Windows paths.
