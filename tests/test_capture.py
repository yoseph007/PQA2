import collections
import queue
import time
import unittest
from unittest.mock import MagicMock, patch

from PyQt6.QtWidgets import QApplication

# Ensure QApplication exists for QThread/QObject
app = QApplication.instance()
if not app:
    app = QApplication([])

from app.capture import CaptureManager, CaptureMonitor, CaptureState


class TestCapture(unittest.TestCase):
    def test_stderr_pump_terminates_on_eof(self):
        mock_proc = MagicMock()
        lines = ["frame=   10 fps=10.0\n", "frame=   20 fps=10.0\n", ""]
        mock_proc.stderr.readline.side_effect = lines

        monitor = CaptureMonitor(process=mock_proc, duration=5.0)
        monitor._stderr_pump()

        q_items = []
        while not monitor._stderr_queue.empty():
            q_items.append(monitor._stderr_queue.get_nowait())

        self.assertIn("frame=   10 fps=10.0\n", q_items)
        self.assertIn("frame=   20 fps=10.0\n", q_items)
        self.assertIsNone(q_items[-1])
        self.assertIn("frame=   10 fps=10.0\n", monitor.error_output)

    def test_stop_uses_graceful_path(self):
        mock_proc = MagicMock()
        mock_proc.poll.side_effect = [None, 0]
        mock_stdin = MagicMock()
        mock_proc.stdin = mock_stdin

        monitor = CaptureMonitor(process=mock_proc, stop_mode="graceful")
        with patch.object(monitor, "_verify_output_and_emit_metadata"):
            monitor._graceful_shutdown()

        mock_stdin.write.assert_called_with('q\n')
        mock_stdin.flush.assert_called_once()
        self.assertFalse(monitor.escalation_used)
        mock_proc.terminate.assert_not_called()
        mock_proc.kill.assert_not_called()

    def test_escalation_after_deadline(self):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_stdin = MagicMock()
        mock_proc.stdin = mock_stdin

        monitor = CaptureMonitor(process=mock_proc, stop_mode="graceful")
        with patch("time.sleep", return_value=None):
            with patch.object(monitor, "_verify_output_and_emit_metadata"):
                monitor._graceful_shutdown()

        self.assertTrue(monitor.escalation_used)
        mock_proc.terminate.assert_called()
        mock_proc.kill.assert_called()
        self.assertTrue(monitor.capture_truncated_flag)

    def test_gap_detection_flags_mismatch(self):
        mock_proc = MagicMock()
        monitor = CaptureMonitor(process=mock_proc, duration=10.0, total_frames=300)
        monitor.start_time = monitor._clock() - 10.0

        # Frame 200 captured at t=10s with fps=30 => expected 300 frames (delta 100 > 2%)
        line = "frame=  200 fps= 30.0 q=20.0 size= 1024kB time=00:00:06.66 bitrate=1258.3kbits/s speed=1.0x\n"
        monitor._stderr_queue.put(line)

        poll_calls = [0]

        def fake_poll():
            poll_calls[0] += 1
            if poll_calls[0] > 2:
                return 0
            return None

        mock_proc.poll = fake_poll
        mock_proc.returncode = 0

        with patch.object(monitor, "_verify_output_and_emit_metadata"):
            with patch.object(monitor, "_stderr_pump"):
                monitor._pump_thread = MagicMock()
                monitor.run()

        self.assertTrue(monitor.gaps_detected)


    def test_pid_scoped_kill(self):
        manager = CaptureManager()
        target_pid = 99999
        unrelated_pid = 88888
        manager._spawned_pids = {target_pid}

        mock_proc = MagicMock()
        mock_proc.name.return_value = "ffmpeg.exe"

        with patch("psutil.pid_exists", side_effect=lambda pid: pid in (target_pid, unrelated_pid)):
            with patch("psutil.Process", return_value=mock_proc) as mock_psutil_proc:
                manager._kill_all_ffmpeg()

        mock_psutil_proc.assert_called_once_with(target_pid)
        mock_proc.kill.assert_called_once()
        self.assertEqual(len(manager._spawned_pids), 0)

    def test_immediate_stop_mode(self):
        mock_proc = MagicMock()
        mock_proc.poll.side_effect = [None, 0]
        monitor = CaptureMonitor(process=mock_proc, stop_mode="immediate")
        with patch.object(monitor, "_verify_output_and_emit_metadata"):
            monitor._graceful_shutdown()
        mock_proc.terminate.assert_called_once()
        self.assertTrue(monitor.escalation_used)

    # -------------------------------------------------------------------------
    # Roadmap #3: Watchdog & Preflight Validation Tests (Annotations 1-5)
    # -------------------------------------------------------------------------

    def test_watchdog_startup_stall_clock_boundary(self):
        """Roadmap #3: Test watchdog triggers when no video frames arrive within startup timeout (boundary test)."""
        clock = FakeClock(1000.0)
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdin = MagicMock()

        monitor = CaptureMonitor(
            process=mock_proc,
            duration=30.0,
            startup_timeout=10.0,
            stall_timeout=5.0,
            clock=clock,
        )

        stalled_reasons = []
        failed_reasons = []
        completed_flags = []

        monitor.capture_stalled.connect(lambda reason: stalled_reasons.append(reason))
        monitor.capture_failed.connect(lambda reason: failed_reasons.append(reason))
        monitor.capture_complete.connect(lambda: completed_flags.append(True))

        # Iteration 1: elapsed 9.9s (below threshold) -> does NOT fire
        # Iteration 2: elapsed 10.1s (above threshold) -> watchdog fires, shuts down, exits run()
        clock_ticks = [1000.0, 1009.9, 1010.1]

        def fake_clock_advancer():
            if clock_ticks:
                clock.current_time = clock_ticks.pop(0)
            return clock.current_time

        monitor._clock = fake_clock_advancer
        mock_proc.poll.return_value = None

        with patch.object(monitor, "_verify_output_and_emit_metadata"):
            with patch.object(monitor, "_stderr_pump"):
                monitor._pump_thread = MagicMock()
                monitor.run()

        self.assertEqual(len(stalled_reasons), 1)
        self.assertIn("initialization", stalled_reasons[0])
        self.assertEqual(len(failed_reasons), 1)
        self.assertEqual(len(completed_flags), 0, "Failed stall run must NEVER emit capture_complete (Annot 1)")
        self.assertTrue(monitor._watchdog_triggered)

    def test_watchdog_frame_ingestion_stall_clock_boundary(self):
        """Roadmap #3: Test watchdog detects stream stall when frames freeze mid-capture (boundary test)."""
        clock = FakeClock(1000.0)
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdin = MagicMock()

        monitor = CaptureMonitor(
            process=mock_proc,
            duration=30.0,
            startup_timeout=10.0,
            stall_timeout=5.0,
            clock=clock,
        )

        stalled_reasons = []
        failed_reasons = []
        completed_flags = []

        monitor.capture_stalled.connect(lambda reason: stalled_reasons.append(reason))
        monitor.capture_failed.connect(lambda reason: failed_reasons.append(reason))
        monitor.capture_complete.connect(lambda: completed_flags.append(True))

        # Feed 1 frame line at t=1000.0
        monitor._stderr_queue.put("frame=   50 fps=30.0 time=00:00:01.66\n")

        # Iteration 1: t=1000.0 receives frame, last_frame_rx_time becomes 1000.0
        # Iteration 2: t=1004.9 (elapsed 4.9s < 5.0s) -> no stall fired
        # Iteration 3: t=1005.1 (elapsed 5.1s > 5.0s) -> stall fires!
        clock_ticks = [1000.0, 1000.0, 1004.9, 1005.1]

        def fake_clock_advancer():
            if clock_ticks:
                clock.current_time = clock_ticks.pop(0)
            return clock.current_time

        monitor._clock = fake_clock_advancer
        mock_proc.poll.return_value = None

        with patch.object(monitor, "_verify_output_and_emit_metadata"):
            with patch.object(monitor, "_stderr_pump"):
                monitor._pump_thread = MagicMock()
                monitor.run()

        self.assertTrue(monitor.frames_received)
        self.assertEqual(len(stalled_reasons), 1)
        self.assertIn("video stream frozen", stalled_reasons[0])
        self.assertEqual(len(failed_reasons), 1)
        self.assertEqual(len(completed_flags), 0, "Failed stall run must NEVER emit capture_complete (Annot 1)")
        self.assertTrue(monitor._watchdog_triggered)

    def test_watchdog_silent_during_deliberate_stop(self):
        """Annotation 1: Watchdog must NOT fire when capture is deliberately stopped."""
        clock = FakeClock(1000.0)
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()

        monitor = CaptureMonitor(
            process=mock_proc,
            duration=30.0,
            startup_timeout=10.0,
            stall_timeout=5.0,
            clock=clock,
        )

        stalled_reasons = []
        failed_reasons = []
        completed_flags = []

        monitor.capture_stalled.connect(lambda reason: stalled_reasons.append(reason))
        monitor.capture_failed.connect(lambda reason: failed_reasons.append(reason))
        monitor.capture_complete.connect(lambda: completed_flags.append(True))

        # Simulate deliberate user stop
        monitor.stop()
        self.assertTrue(monitor._stopping)
        self.assertFalse(monitor._running)

        # Advance clock way past stall timeouts
        clock.advance(50.0)

        # Process exits
        mock_proc.poll.return_value = 0
        with patch.object(monitor, "_verify_output_and_emit_metadata"):
            with patch.object(monitor, "_stderr_pump"):
                monitor._pump_thread = MagicMock()
                monitor.run()

        self.assertEqual(len(stalled_reasons), 0, "Watchdog fired spuriously on deliberate stop!")
        self.assertEqual(len(failed_reasons), 0, "Deliberate stop must not emit capture_failed!")
        self.assertEqual(len(completed_flags), 0)

    def test_watchdog_healthy_capture(self):
        """Annotation 4: Healthy capture with steady frame progress across multi-window duration has zero watchdog emissions."""
        clock = FakeClock(1000.0)
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdin = MagicMock()

        monitor = CaptureMonitor(
            process=mock_proc,
            duration=15.0,
            startup_timeout=10.0,
            stall_timeout=5.0,
            clock=clock,
        )

        stalled_reasons = []
        failed_reasons = []
        completed_flags = []

        monitor.capture_stalled.connect(lambda reason: stalled_reasons.append(reason))
        monitor.capture_failed.connect(lambda reason: failed_reasons.append(reason))
        monitor.capture_complete.connect(lambda: completed_flags.append(True))

        # Feed 20 frames spaced 0.75s apart (total 15s elapsed, spanning 3x the 5s stall timeout)
        for i in range(1, 21):
            monitor._stderr_queue.put(f"frame=   {i * 15} fps=30.0 time=00:00:{i:02d}.00\n")

        # Process returns None while frames are in queue, then returns 0
        def fake_poll():
            if not monitor._stderr_queue.empty():
                clock.advance(0.75)  # Steady frame pace
                return None
            return 0

        mock_proc.poll = fake_poll

        with patch.object(monitor, "_verify_output_and_emit_metadata"):
            with patch.object(monitor, "_stderr_pump"):
                monitor._pump_thread = MagicMock()
                monitor.run()

        self.assertEqual(len(stalled_reasons), 0)
        self.assertEqual(len(failed_reasons), 0)
        self.assertEqual(len(completed_flags), 1)
        self.assertTrue(monitor.frames_received)
        self.assertEqual(monitor.last_frame_count, 300)

    def test_preflight_sufficient_disk_space(self):
        """Annotation 5: Preflight check passes when disk space exceeds required estimate + buffer."""
        manager = CaptureManager()
        # Mock disk usage to 50 GB free
        with patch("shutil.disk_usage", return_value=(100 * 1024**3, 50 * 1024**3, 50 * 1024**3)):
            ok, msg = manager.run_preflight_checks("Intensity Shuttle", duration=30.0)
            self.assertTrue(ok)
            self.assertIn("Preflight passed", msg)

    def test_preflight_insufficient_disk_space(self):
        """Annotation 5: Preflight check fails fast when disk space is below required buffer."""
        manager = CaptureManager()
        # Mock disk usage to 500 MB free (< 2048 MB buffer)
        with patch("shutil.disk_usage", return_value=(100 * 1024**3, 99 * 1024**3, 500 * 1024**2)):
            ok, msg = manager.run_preflight_checks("Intensity Shuttle", duration=30.0)
            self.assertFalse(ok)
            self.assertIn("Insufficient disk space", msg)
            self.assertIn("Requires ~", msg)
            self.assertIn("found 500 MB free", msg)

    def test_preflight_invalid_or_missing_device(self):
        """Annotation 5: Preflight validates device enumeration only and rejects unknown devices."""
        mock_opts = MagicMock()
        mock_opts.get_decklink_devices.return_value = ["DeckLink Duo (1)", "DeckLink Duo (2)"]
        manager = CaptureManager(options_manager=mock_opts)

        with patch("shutil.disk_usage", return_value=(100 * 1024**3, 50 * 1024**3, 50 * 1024**3)):
            # Known device passes
            ok_valid, msg_valid = manager.run_preflight_checks("DeckLink Duo (1)", duration=10.0)
            self.assertTrue(ok_valid)

            # Unknown device fails fast
            ok_missing, msg_missing = manager.run_preflight_checks("Nonexistent Grabber", duration=10.0)
            self.assertFalse(ok_missing)
            self.assertIn("Capture device 'Nonexistent Grabber' not found", msg_missing)

    def test_preflight_fails_fast_in_start_bookend_capture(self):
        """Verify start_bookend_capture terminates early if preflight fails without spawning FFmpeg."""
        manager = CaptureManager()
        manager.reference_info = {"path": "dummy_ref.mp4", "duration": 10.0, "frame_rate": 30.0}

        finished_signals = []
        manager.capture_finished.connect(lambda success, msg: finished_signals.append((success, msg)))

        with patch.object(manager, "run_preflight_checks", return_value=(False, "Preflight failed: Disk full")):
            started = manager.start_bookend_capture("Intensity Shuttle")

        self.assertFalse(started)
        self.assertEqual(manager.state, CaptureState.ERROR)
        self.assertEqual(len(finished_signals), 1)
        self.assertFalse(finished_signals[0][0])
        self.assertIn("Disk full", finished_signals[0][1])
        self.assertIsNone(manager.ffmpeg_process)


class FakeClock:
    """Deterministic advancing monotonic clock for test timing injection (Annotation 4)."""
    def __init__(self, initial_time: float = 1000.0):
        self.current_time = initial_time

    def __call__(self) -> float:
        return self.current_time

    def advance(self, seconds: float):
        self.current_time += seconds


if __name__ == "__main__":
    unittest.main()
