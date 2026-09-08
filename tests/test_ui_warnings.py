import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from PyQt6.QtWidgets import QApplication, QMessageBox

app = QApplication.instance()
if not app:
    app = QApplication([])

from app.options_manager import OptionsManager
from app.ui.tabs.options_tab import OptionsTab
from app.ui.tabs.capture_tab import CaptureTab


class TestUIWarnings(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.settings_file = os.path.join(self.td.name, "settings.json")
        self.options_manager = OptionsManager(settings_file=self.settings_file)

        self.mock_parent = MagicMock()
        self.mock_parent.options_manager = self.options_manager
        # Prevent background timers and subprocess hardware probing in headless tests
        self.options_manager.test_device_connection = MagicMock(return_value=(True, "Mocked test device"))
        self.options_manager.get_decklink_devices = MagicMock(return_value=["Mocked Device"])
        self.options_manager.detect_formats = MagicMock(return_value={})
        self.options_manager.get_formats_for_device = MagicMock(return_value={})
        self._timer_patcher = patch("PyQt6.QtCore.QTimer.singleShot")
        self.mock_single_shot = self._timer_patcher.start()
        self._msg_patcher = patch.object(QMessageBox, "show")
        self.mock_msg_show = self._msg_patcher.start()

    def tearDown(self):
        self._msg_patcher.stop()
        self._timer_patcher.stop()
        self.td.cleanup()

    def test_options_tab_immediate_warning_dialog_is_non_blocking(self):
        options_tab = OptionsTab(self.mock_parent)
        immediate_idx = options_tab.combo_stop_mode.findData("immediate")
        options_tab.combo_stop_mode.setCurrentIndex(immediate_idx)

        # Dialog created, non-modal, and contains warning text
        dialog = getattr(options_tab, "_active_warning_box", None)
        self.assertIsNotNone(dialog)
        self.assertFalse(dialog.isModal())
        self.assertIn("Truncated", dialog.text())

    def test_options_tab_stop_mode_immediate_warning_and_persistence(self):
        options_tab = OptionsTab(self.mock_parent)
        capture_tab = CaptureTab(self.mock_parent)
        self.mock_parent.capture_tab = capture_tab

        # Initially graceful
        self.assertTrue(options_tab.lbl_stop_mode_warning.isHidden())

        # Switch to immediate
        immediate_idx = options_tab.combo_stop_mode.findData("immediate")
        options_tab.combo_stop_mode.setCurrentIndex(immediate_idx)

        # Amber warning visible and persisted
        self.assertFalse(options_tab.lbl_stop_mode_warning.isHidden())
        self.assertEqual(self.options_manager.get_setting("capture", "stop_mode"), "immediate")

    def test_options_tab_restart_restores_warning_state(self):
        self.options_manager.update_setting("capture", "stop_mode", "immediate")

        # Simulate fresh app startup / OptionsTab creation
        new_options_tab = OptionsTab(self.mock_parent)
        new_options_tab.load_capture_settings()

        # Amber label restored without popping up modal dialog
        self.assertFalse(new_options_tab.lbl_stop_mode_warning.isHidden())
        self.assertIsNone(getattr(new_options_tab, "_active_warning_box", None))

    def test_options_tab_graceful_revert_hides_warning(self):
        options_tab = OptionsTab(self.mock_parent)
        capture_tab = CaptureTab(self.mock_parent)
        self.mock_parent.capture_tab = capture_tab

        immediate_idx = options_tab.combo_stop_mode.findData("immediate")
        options_tab.combo_stop_mode.setCurrentIndex(immediate_idx)
        self.assertFalse(options_tab.lbl_stop_mode_warning.isHidden())

        # Revert to graceful
        graceful_idx = options_tab.combo_stop_mode.findData("graceful")
        options_tab.combo_stop_mode.setCurrentIndex(graceful_idx)

        self.assertTrue(options_tab.lbl_stop_mode_warning.isHidden())
        self.assertTrue(capture_tab.lbl_immediate_warning.isHidden())
        self.assertEqual(self.options_manager.get_setting("capture", "stop_mode"), "graceful")

    def test_capture_tab_warning_visibility(self):
        capture_tab = CaptureTab(self.mock_parent)
        self.assertTrue(capture_tab.lbl_immediate_warning.isHidden())

        capture_tab.update_stop_mode_warning("immediate")
        self.assertFalse(capture_tab.lbl_immediate_warning.isHidden())

        capture_tab.update_stop_mode_warning("graceful")
        self.assertTrue(capture_tab.lbl_immediate_warning.isHidden())

    def test_capture_tab_sync_with_options(self):
        options_tab = OptionsTab(self.mock_parent)
        capture_tab = CaptureTab(self.mock_parent)
        self.mock_parent.capture_tab = capture_tab

        self.assertTrue(capture_tab.lbl_immediate_warning.isHidden())

        # Changing options tab propagates to capture tab
        immediate_idx = options_tab.combo_stop_mode.findData("immediate")
        options_tab.combo_stop_mode.setCurrentIndex(immediate_idx)
        self.assertFalse(capture_tab.lbl_immediate_warning.isHidden())


if __name__ == "__main__":
    unittest.main()
