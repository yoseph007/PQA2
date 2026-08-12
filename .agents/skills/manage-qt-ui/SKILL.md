---
name: manage-qt-ui
description: Best practices for modifying or creating PyQt5 UI components in the VMAF application.
---

# Manage Qt UI Skill

## Context
The VMAF Test Application uses PyQt5 for its graphical interface. Because video capture and analysis are intensive blocking tasks, strict adherence to a multithreaded architecture is required.

## Instructions
When modifying or adding UI components (located in `app/ui/`):

1. **Thread Safety**: 
   - NEVER call blocking functions (e.g., `time.sleep`, `subprocess.run` without timeouts, or heavy OpenCV logic) directly in a Qt slot connected to a button click.
   - All intensive work MUST be delegated to a `QThread` subclass (e.g., `CaptureMonitor`, `VMAFAnalyzer`).
   
2. **Signal/Slot Communication**:
   - Use custom `pyqtSignal` definitions in your worker threads to pass data back to the UI.
   - Example: 
     ```python
     class Worker(QThread):
         progress = pyqtSignal(int)
         def run(self):
             # do work
             self.progress.emit(50)
     ```
   - Connect these signals to UI update functions in the `MainWindow` or specific widgets.

3. **Styling**:
   - Adhere to the existing layout structures (QVBoxLayout, QHBoxLayout).
   - Use the `ThemeManager` (`app/ui/theme_manager.py`) if dealing with explicit styling, rather than hardcoding colors directly in widgets.
