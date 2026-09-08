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

from app.capture import CaptureManager, CaptureMonitor


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
        monitor.start_time = time.time() - 10.0

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


if __name__ == "__main__":
    unittest.main()
