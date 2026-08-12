# Workspace Customizations

This file (`.agents/AGENTS.md`) is used to provide project-specific instructions and rules for Antigravity agents working in this workspace.

## Master Knowledge
Before modifying core architecture, refer to the following documents:
- [ARCHITECTURE.md](references/ARCHITECTURE.md): Details on `CaptureManager`, `VMAFAnalyzer`, Bookend alignment, and the PyQt5 threading model.
- [FFMPEG_GUIDELINES.md](references/FFMPEG_GUIDELINES.md): Rules for invoking `ffmpeg` and `ffprobe` as subprocesses.

## General Rules
- **Thread Safety**: Never block the main UI thread. Use `QThread` and signals for long-running operations. See `manage-qt-ui` skill.
- **Testing**: Always run tests before making significant commits. See `run-vmaf-tests` skill.
- **Code Style**: Follow the existing code style (Python) and use clear, descriptive names for PyQt signals.
- **Dependencies**: Document new dependencies in `requirements.txt`.

## Hooks and Workflow
- Ensure you have run `scripts/setup_hooks.bat` to install the pre-commit hook that enforces test execution before commits.
