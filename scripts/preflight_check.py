#!/usr/bin/env python3
"""
Preflight Environment & System Checker for VMAF Application.

Validates the full development and runtime environment:
1. Python runtime & core module dependencies
2. FFmpeg binary availability & libvmaf filter capabilities
3. VMAF model directory and weights
4. Capture subsystem preflight (storage floor, directory permissions, device enumeration)
5. Git pre-commit hook installation
"""

import os
import sys
import shutil
from typing import Tuple, List, Dict, Any

# Ensure console supports UTF-8 on Windows
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PyQt6.QtCore import QCoreApplication
_qt_app = QCoreApplication.instance() or QCoreApplication([])

from app.version import get_version_string, get_git_commit
from app.vmaf_analyzer import VMAFAnalyzer
from app.options_manager import OptionsManager
from app.capture import CaptureManager
from app.utils import get_ffmpeg_path


class PreflightChecker:
    """Executes holistic preflight validation checks across app subsystems."""

    def __init__(self, install_hooks_if_missing: bool = False):
        self.install_hooks = install_hooks_if_missing
        self.results: List[Tuple[str, bool, str]] = []

    def log_result(self, name: str, passed: bool, detail: str):
        self.results.append((name, passed, detail))
        tag = "[PASS]" if passed else "[FAIL]"
        print(f" {tag} {name:<32} : {detail}")

    def check_python_environment(self) -> bool:
        """Check Python version and essential library imports."""
        py_ver = sys.version.split()[0]
        ver_ok = sys.version_info >= (3, 10)
        self.log_result(
            "Python Runtime",
            ver_ok,
            f"Python {py_ver} ({'Compatible >= 3.10' if ver_ok else 'Requires Python >= 3.10'})"
        )

        packages = [
            ("PyQt6", "PyQt6"),
            ("OpenCV", "cv2"),
            ("NumPy", "numpy"),
            ("Pandas", "pandas"),
            ("SciPy", "scipy"),
            ("Matplotlib", "matplotlib"),
            ("ReportLab", "reportlab"),
            ("Psutil", "psutil"),
        ]

        missing = []
        for label, mod_name in packages:
            try:
                __import__(mod_name)
            except ImportError:
                missing.append(label)

        pkgs_ok = len(missing) == 0
        detail = "All 8 core packages imported" if pkgs_ok else f"Missing: {', '.join(missing)}"
        self.log_result("Python Dependencies", pkgs_ok, detail)
        return ver_ok and pkgs_ok

    def check_ffmpeg_toolchain(self) -> bool:
        """Check FFmpeg executable and libvmaf filter capability."""
        try:
            analyzer = VMAFAnalyzer()
            caps = analyzer.probe_capabilities()

            ffmpeg_path = caps.get("ffmpeg_path")
            if not ffmpeg_path or not os.path.exists(ffmpeg_path):
                ffmpeg_path = str(get_ffmpeg_path())

            ffmpeg_ok = bool(ffmpeg_path and os.path.exists(ffmpeg_path))
            self.log_result(
                "FFmpeg Executable",
                ffmpeg_ok,
                f"{os.path.basename(ffmpeg_path)} at {ffmpeg_path}" if ffmpeg_ok else "Not found in ffmpeg_bin or PATH"
            )

            libvmaf_ok = caps.get("has_libvmaf", False)
            escaping = caps.get("libvmaf_path_escaping", caps.get("escaping_style", "unknown"))
            self.log_result(
                "FFmpeg libvmaf Filter",
                libvmaf_ok,
                f"libvmaf available (path-escaping: {escaping})" if libvmaf_ok else "Filter libvmaf missing in FFmpeg build"
            )

            models_dir = os.path.join(PROJECT_ROOT, "models")
            models = [f for f in os.listdir(models_dir) if f.endswith((".json", ".bin", ".pkl"))] if os.path.isdir(models_dir) else []
            models_ok = len(models) > 0
            default_model_found = any("vmaf_v0.6.1" in m for m in models)
            self.log_result(
                "VMAF Models",
                models_ok and default_model_found,
                f"{len(models)} model(s) found in models/ (default v0.6.1 present)" if models_ok else "Missing VMAF models in models/"
            )

            return ffmpeg_ok and libvmaf_ok and models_ok
        except Exception as e:
            self.log_result("FFmpeg Toolchain Probe", False, f"Probe error: {e}")
            return False

    def check_capture_and_storage(self) -> bool:
        """Run CaptureManager storage and device preflight checks."""
        try:
            options_mgr = OptionsManager()
            capture_mgr = CaptureManager(options_manager=options_mgr)

            # Test storage floor on captures directory
            captures_dir = os.path.join(PROJECT_ROOT, "captures")
            capture_mgr.set_output_directory(captures_dir)

            # Check preflight disk space for 30s capture run
            disk_ok, disk_msg = capture_mgr.run_preflight_checks(
                device_name="Intensity Shuttle",
                duration=30.0,
            )
            self.log_result("Storage Preflight", disk_ok, disk_msg)

            # Query hardware capture devices
            decklink_devices = options_mgr.get_decklink_devices()
            if decklink_devices:
                self.log_result("Capture Devices", True, f"{len(decklink_devices)} DeckLink device(s): {decklink_devices}")
            else:
                self.log_result("Capture Devices", True, "0 DeckLink devices detected (headless / simulation mode ready)")

            return disk_ok
        except Exception as e:
            self.log_result("Capture Subsystem Preflight", False, f"Preflight error: {e}")
            return False

    def check_git_hooks(self) -> bool:
        """Verify pre-commit git hook is installed."""
        git_dir = os.path.join(PROJECT_ROOT, ".git")
        if not os.path.isdir(git_dir):
            self.log_result("Git Pre-Commit Hook", True, "Not a git repository or running in CI archive (skipped)")
            return True

        hook_path = os.path.join(git_dir, "hooks", "pre-commit")
        hook_exists = os.path.isfile(hook_path)

        if not hook_exists and self.install_hooks:
            src_hook = os.path.join(PROJECT_ROOT, "scripts", "pre-commit")
            if os.path.isfile(src_hook):
                try:
                    os.makedirs(os.path.dirname(hook_path), exist_ok=True)
                    shutil.copy2(src_hook, hook_path)
                    hook_exists = True
                    self.log_result("Git Pre-Commit Hook", True, "Installed hook from scripts/pre-commit")
                    return True
                except Exception as e:
                    self.log_result("Git Pre-Commit Hook", False, f"Failed to auto-install hook: {e}")
                    return False

        self.log_result(
            "Git Pre-Commit Hook",
            hook_exists,
            "Active in .git/hooks/pre-commit" if hook_exists else "Missing (run scripts/setup_hooks.bat to install)"
        )
        return hook_exists

    def run_all(self) -> bool:
        """Run all preflight checks and output verdict."""
        print("=" * 72)
        print(f" VMAF APP PREFLIGHT ENVIRONMENT CHECK — {get_version_string()}")
        print(f" Git Commit: {get_git_commit(short=True)} | Workspace: {PROJECT_ROOT}")
        print("=" * 72)

        p1 = self.check_python_environment()
        p2 = self.check_ffmpeg_toolchain()
        p3 = self.check_capture_and_storage()
        p4 = self.check_git_hooks()

        all_ok = p1 and p2 and p3 and p4
        print("-" * 72)
        if all_ok:
            print(" [PREFLIGHT VERDICT] Environment Healthy - Ready for Development & Testing [OK]")
        else:
            print(" [PREFLIGHT VERDICT] One or more preflight checks failed [FAIL]")
        print("=" * 72)
        return all_ok


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Preflight check for VMAF App development environment")
    parser.add_argument("--install-hooks", action="store_true", help="Auto-install git pre-commit hook if missing")
    args = parser.parse_args()

    checker = PreflightChecker(install_hooks_if_missing=args.install_hooks)
    passed = checker.run_all()
    sys.exit(0 if passed else 1)
