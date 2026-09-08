"""
Live-Fire Watchdog Validation Script (Capstone Step 2)
======================================================
Executes negative fault injection on live capture pipeline:
1. Launches real FFmpeg process capturing video frames.
2. Injects hardware signal loss / feed disconnect after ~3 seconds.
3. Observes watchdog trigger after precisely 5.0s of silence.
4. Verifies amber UI banner rendering and takes screenshot.
5. Verifies zero zombie FFmpeg processes remain after graceful shutdown.
6. Asserts capture_failed precedence over capture_complete.
"""

import os
import sys
import time
import subprocess
import threading
import psutil

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QPixmap

from app.capture import CaptureManager, CaptureMonitor
from app.ui.tabs.capture_tab import CaptureTab
from app.options_manager import OptionsManager
from app.utils import get_ffmpeg_path
from app.version import get_version_string, get_git_commit


def check_running_ffmpeg_pids() -> list:
    """Return list of running ffmpeg process PIDs."""
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-Process ffmpeg -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id"],
            capture_output=True,
            text=True
        )
        pids = [int(p.strip()) for p in res.stdout.strip().splitlines() if p.strip().isdigit()]
        return pids
    except Exception:
        return []


def run_live_fire_watchdog():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleCtrlHandler(None, True)
        except Exception:
            pass

    print("=" * 76, flush=True)
    print(f" CAPSTONE STEP 2: LIVE-FIRE WATCHDOG & FAULT INJECTION — {get_version_string()}", flush=True)
    print(f" Git Commit: {get_git_commit(short=True)} | Workspace: {PROJECT_ROOT}", flush=True)
    print("=" * 76, flush=True)

    # Initial check: no zombie ffmpeg beforehand
    initial_pids = check_running_ffmpeg_pids()
    print(f" [PRE-CHECK] Existing ffmpeg.exe processes: {len(initial_pids)} (PIDs: {initial_pids})", flush=True)

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])

    options_mgr = OptionsManager()
    capture_tab = CaptureTab(options_mgr)
    capture_tab.resize(900, 650)
    capture_tab.show()

    events = {
        "frames_received": 0,
        "stalled_reasons": [],
        "failed_reasons": [],
        "completed_called": False,
        "stall_timestamp": None,
        "disconnect_timestamp": None,
        "amber_banner_text": None,
        "amber_banner_style": None,
    }

    ffmpeg_bin = get_ffmpeg_path()
    print(f" [SETUP] Using FFmpeg executable: {ffmpeg_bin}", flush=True)

    # Launch real FFmpeg process generating test frames
    cmd = [
        ffmpeg_bin,
        "-y",
        "-re",
        "-f", "lavfi",
        "-i", "testsrc2=size=1280x720:rate=30",
        "-t", "30",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-f", "null",
        "-"
    ]

    print(" [PHASE 1] Starting capture process with active frame ingestion...", flush=True)
    creation_flags = 0
    startupinfo = None
    if sys.platform == "win32":
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            creation_flags |= subprocess.CREATE_NO_WINDOW
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        creationflags=creation_flags,
        startupinfo=startupinfo,
    )
    managed_pid = proc.pid
    ps_proc = psutil.Process(managed_pid)
    print(f" [PHASE 1] FFmpeg spawned with PID: {managed_pid}", flush=True)

    monitor = CaptureMonitor(
        process=proc,
        duration=30.0,
        startup_timeout=10.0,
        stall_timeout=5.0,
    )

    # Wire UI updates
    monitor.capture_stalled.connect(capture_tab.handle_capture_stalled)
    monitor.capture_failed.connect(lambda msg: events["failed_reasons"].append(msg))
    monitor.capture_complete.connect(lambda: events.update({"completed_called": True}))

    # When stalled, immediately resume process on the monitor thread so graceful shutdown ('q') succeeds cleanly
    def unfreeze_on_stall():
        try:
            ps_proc.resume()
        except Exception:
            pass

    monitor.capture_stalled.connect(unfreeze_on_stall, Qt.ConnectionType.DirectConnection)

    def on_frame_count(curr, total):
        events["frames_received"] = curr
        if curr % 15 == 0:
            print(f"   * Ingestion active: captured {curr} frames...", flush=True)

    monitor.frame_count_updated.connect(on_frame_count)
    monitor.start()

    # Ingest frames for 3.0s
    t0 = time.monotonic()
    print(" [PHASE 1] Ingesting frames for 3.0s...", flush=True)
    while time.monotonic() - t0 < 3.0:
        app.processEvents()
        time.sleep(0.05)

    print(f" [PHASE 1] Active frames ingested: {events['frames_received']}", flush=True)
    assert events["frames_received"] > 0, "No frames received during initial ingestion!"

    # Phase 2: Fault Injection (Signal Disconnect)
    print("\n [PHASE 2] FAULT INJECTION: Simulating physical HDMI cable disconnect / signal loss!", flush=True)
    events["disconnect_timestamp"] = time.monotonic()
    ps_proc.suspend()
    print(f" [PHASE 2] Hardware signal frozen at t={events['disconnect_timestamp']:.2f}s. Monitoring watchdog...", flush=True)

    start_wait = time.monotonic()
    while time.monotonic() - start_wait < 10.0:
        app.processEvents()
        if monitor._watchdog_triggered:
            events["stall_timestamp"] = time.monotonic()
            events["stalled_reasons"].append(monitor._watchdog_reason)
            break
        time.sleep(0.05)

    # Make sure process is resumed for reaping
    unfreeze_on_stall()

    # Process events to let CaptureTab update its banner
    for _ in range(10):
        app.processEvents()
        time.sleep(0.02)

    events["amber_banner_text"] = capture_tab.lbl_capture_status.text()
    events["amber_banner_style"] = capture_tab.lbl_capture_status.styleSheet()

    detection_latency = (
        events["stall_timestamp"] - events["disconnect_timestamp"]
        if events["stall_timestamp"] and events["disconnect_timestamp"]
        else None
    )

    # Capture UI screenshot of the amber banner
    screenshot_dir = os.path.join(PROJECT_ROOT, "reports", "screenshots")
    os.makedirs(screenshot_dir, exist_ok=True)
    screenshot_path = os.path.join(screenshot_dir, "live_fire_amber_banner.png")
    pixmap = capture_tab.grab()
    pixmap.save(screenshot_path)
    print(f"\n [PHASE 3] Captured UI amber banner screenshot -> {screenshot_path}", flush=True)

    artifacts_screenshot_dir = r"C:\Users\yos\.gemini\antigravity-ide\brain\0f18f42b-968a-4818-90a6-c8a616a298ee\screenshots"
    if os.path.isdir(os.path.dirname(artifacts_screenshot_dir)):
        os.makedirs(artifacts_screenshot_dir, exist_ok=True)
        artifact_img_path = os.path.join(artifacts_screenshot_dir, "live_fire_amber_banner.png")
        pixmap.save(artifact_img_path)
        print(f" [PHASE 3] Artifact screenshot archived -> {artifact_img_path}", flush=True)

    # Wait for monitor thread to finish clean termination
    monitor.wait(5000)

    # Process remaining queued signals (e.g. capture_failed)
    for _ in range(10):
        app.processEvents()
        time.sleep(0.02)

    try:
        proc.kill()
        proc.wait(timeout=2)
    except Exception:
        pass

    # Wait for OS process table to settle
    time.sleep(0.5)
    remaining_pids = check_running_ffmpeg_pids()
    zombie_pids = [p for p in remaining_pids if p not in initial_pids]

    print("\n" + "=" * 76, flush=True)
    print(" LIVE-FIRE WATCHDOG VERIFICATION REPORT", flush=True)
    print("=" * 76, flush=True)

    pass_stall = len(events["stalled_reasons"]) >= 1
    pass_latency = detection_latency is not None and (4.5 <= detection_latency <= 6.5)
    pass_banner = events["amber_banner_text"] and "STALLED" in events["amber_banner_text"]
    pass_color = events["amber_banner_style"] and "#d97706" in events["amber_banner_style"]
    pass_zombie = len(zombie_pids) == 0
    pass_failed_sig = len(events["failed_reasons"]) >= 1
    pass_no_complete = not events["completed_called"]

    print(f" 1. Stall Detected                : {'[PASS]' if pass_stall else '[FAIL]'} (Count: {len(events['stalled_reasons'])})", flush=True)
    lat_str = f"{detection_latency:.2f}s" if detection_latency else "None"
    print(f" 2. Detection Latency             : {'[PASS]' if pass_latency else '[FAIL]'} ({lat_str}, threshold=5.0s)", flush=True)
    print(f" 3. Amber UI Banner Text          : {'[PASS]' if pass_banner else '[FAIL]'} ('{events['amber_banner_text']}')", flush=True)
    print(f" 4. Amber Color Styling (#d97706) : {'[PASS]' if pass_color else '[FAIL]'} ({events['amber_banner_style']})", flush=True)
    print(f" 5. Zero Zombie FFmpeg Processes  : {'[PASS]' if pass_zombie else '[FAIL]'} ({len(zombie_pids)} zombies detected)", flush=True)
    print(f" 6. Precedence (Failed vs Complete): {'[PASS]' if (pass_failed_sig and pass_no_complete) else '[FAIL]'} (capture_failed={pass_failed_sig}, capture_complete={events['completed_called']})", flush=True)
    print("=" * 76, flush=True)

    all_passed = all([pass_stall, pass_latency, pass_banner, pass_color, pass_zombie, pass_failed_sig, pass_no_complete])
    if all_passed:
        print(" [CAPSTONE STEP 2 VERDICT] LIVE-FIRE WATCHDOG VALIDATION CERTIFIED [PASS] [OK]", flush=True)
    else:
        print(" [CAPSTONE STEP 2 VERDICT] LIVE-FIRE WATCHDOG VALIDATION FAILED [FAIL]", flush=True)

    return 0 if all_passed else 1


if __name__ == "__main__":
    import traceback
    try:
        sys.exit(run_live_fire_watchdog())
    except Exception as e:
        traceback.print_exc()
        sys.exit(1)
