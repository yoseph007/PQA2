# VMAF Quality Assessment Application

Professional video quality assessment suite featuring Blackmagic capture hardware integration, frame-accurate bookend alignment, and VMAF / PSNR / SSIM metric calculation.

---

## Features
- **Blackmagic DeckLink / DirectShow Ingestion**: High-throughput live and buffered frame capture with hardware watchdog monitoring and stall escalation.
- **Bookend Frame Alignment**: Template matching and timestamp correlation for frame-perfect reference and distorted sequence alignment.
- **VMAF / PSNR / SSIM Analysis**: Integrated libvmaf pipeline with auto-detected path-escaping strategies and metric export.
- **Repeatability & Gage R&R Metrology**: Multi-pass repeatability campaigns with automated determinism assertions, JSONL drift tracking, and branded PDF reporting.
- **Modern PyQt6 GUI**: Responsive high-contrast interface supporting both dark and light modes with live capture telemetry.

---

## One-Command Developer Bootstrap

Bootstrap the full development environment (virtual environment, dependencies, preflight checks, git hooks, and test execution) with a single command:

### PowerShell:
```powershell
.\setup_dev.ps1
```
Optional flags:
- `.\setup_dev.ps1 -SkipTests` (fast setup skipping test suite)
- `.\setup_dev.ps1 -RecreateVenv` (clean rebuild of `.venv`)
- `.\setup_dev.ps1 -SkipHooks` (skip git pre-commit hook installation)

### Command Prompt / Explorer:
```cmd
setup_dev.bat
```

---

## Running the Application

### Launch GUI:
```cmd
run_app.bat
```
*(or from activated venv: `python main.py`)*

### Run Regression Test Suite:
```cmd
.\.venv\Scripts\python.exe run_tests.py
```
*(or: `.\.venv\Scripts\pytest.exe`)*

### Run Environment Preflight Check:
```cmd
.\.venv\Scripts\python.exe scripts\preflight_check.py --install-hooks
```

### Run Gage R&R Repeatability Baseline:
```cmd
.\.venv\Scripts\python.exe scripts\run_gage_rr_baseline.py --passes 5
```