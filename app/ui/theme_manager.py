import logging
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

logger = logging.getLogger(__name__)


class ThemeManager:
    """Manages application themes and unified styling across all platforms."""

    def __init__(self, parent, options_manager):
        self.parent = parent
        self.options_manager = options_manager

    def set_theme(self, theme_name):
        """Set theme, persist to options settings, and apply immediately."""
        if hasattr(self.options_manager, 'update_setting'):
            # Update the theme setting in branding
            if isinstance(self.options_manager.get_setting("branding"), dict):
                self.options_manager.update_setting("branding", "selected_theme", theme_name)
            else:
                self.options_manager.set_setting("branding", {"selected_theme": theme_name})

            # Also update the theme block if it exists
            if isinstance(self.options_manager.get_setting("theme"), dict):
                self.options_manager.update_setting("theme", "selected_theme", theme_name)

            if hasattr(self.options_manager, 'save_settings'):
                try:
                    self.options_manager.save_settings()
                except Exception as e:
                    logger.warning(f"Could not save settings file after theme change: {e}")

            # Apply the new theme
            self.apply_current_theme()

    def get_current_theme_name(self):
        """Get the currently selected theme name from settings."""
        branding_settings = self.options_manager.get_setting("branding") if self.options_manager else None
        theme = "Dark"  # Modern dark default

        if isinstance(branding_settings, dict):
            theme = branding_settings.get("selected_theme", "Dark")
        elif isinstance(branding_settings, str):
            theme = branding_settings
        elif self.options_manager:
            theme_settings = self.options_manager.get_setting("theme")
            if isinstance(theme_settings, dict):
                theme = theme_settings.get("selected_theme", "Dark")

        return theme

    def apply_current_theme(self):
        """Apply the current theme stored in settings to the application."""
        try:
            theme = self.get_current_theme_name()
            app = QApplication.instance()
            if not app:
                return

            branding_settings = self.options_manager.get_setting("branding") if self.options_manager else {}
            if not isinstance(branding_settings, dict):
                branding_settings = {}

            if theme == "Light":
                app.setStyleSheet(self._get_light_stylesheet())
                self._apply_light_palette(app)
            elif theme == "System":
                app.setStyleSheet("")
                app.setPalette(app.style().standardPalette())
            elif theme == "Custom":
                # User-configured custom palette + stylesheet
                bg_color = branding_settings.get("bg_color", "#1e1e24")
                text_color = branding_settings.get("text_color", "#ffffff")
                accent_color = branding_settings.get("accent_color", "#3b82f6")
                app.setStyleSheet(self._get_custom_stylesheet(bg_color, text_color, accent_color))
                self._apply_dark_palette(app, bg_color=bg_color, text_color=text_color, accent_color=accent_color)
            else:
                # Default: Modern Dark
                app.setStyleSheet(self._get_dark_stylesheet())
                self._apply_dark_palette(app)

            # If help_tab is loaded, refresh its HTML documentation to match current theme
            if hasattr(self.parent, 'help_tab') and hasattr(self.parent.help_tab, 'reload_content'):
                self.parent.help_tab.reload_content(theme)

            logger.info(f"Applied theme: {theme}")

        except Exception as e:
            logger.error(f"Error applying theme: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            # Fallback to system palette
            app = QApplication.instance()
            if app:
                app.setStyleSheet("")
                app.setPalette(app.style().standardPalette())

    def _apply_dark_palette(self, app, bg_color="#18181b", text_color="#f4f4f5", accent_color="#3b82f6"):
        """Apply dark QPalette roles to ensure dialogs and non-styled elements stay readable."""
        palette = QPalette()
        base_bg = QColor(bg_color)
        base_text = QColor(text_color)
        accent = QColor(accent_color)
        panel_bg = QColor("#242429")

        palette.setColor(QPalette.ColorRole.Window, base_bg)
        palette.setColor(QPalette.ColorRole.WindowText, base_text)
        palette.setColor(QPalette.ColorRole.Base, QColor("#121316"))
        palette.setColor(QPalette.ColorRole.AlternateBase, panel_bg)
        palette.setColor(QPalette.ColorRole.ToolTipBase, base_bg)
        palette.setColor(QPalette.ColorRole.ToolTipText, base_text)
        palette.setColor(QPalette.ColorRole.Text, base_text)
        palette.setColor(QPalette.ColorRole.Button, panel_bg)
        palette.setColor(QPalette.ColorRole.ButtonText, base_text)
        palette.setColor(QPalette.ColorRole.BrightText, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.Highlight, accent)
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))

        # Disabled states
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor("#71717a"))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#71717a"))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#71717a"))

        app.setPalette(palette)

    def _apply_light_palette(self, app):
        """Apply light QPalette roles."""
        app.setPalette(app.style().standardPalette())

    def _get_dark_stylesheet(self):
        """Generate high-contrast, modern dark theme QSS stylesheet."""
        return """
        /* === Global Window & Base Widgets === */
        QWidget {
            background-color: #18181b;
            color: #f4f4f5;
            font-size: 9.5pt;
        }

        QMainWindow {
            background-color: #121316;
        }

        /* === Tabs & Tab Widget === */
        QTabWidget::pane {
            border: 1px solid #27272a;
            background-color: #18181b;
            border-radius: 6px;
            top: -1px;
        }

        QTabBar::tab {
            background-color: #121316;
            color: #a1a1aa;
            border: 1px solid #27272a;
            border-bottom: none;
            padding: 8px 18px;
            margin-right: 2px;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
            font-weight: 500;
        }

        QTabBar::tab:hover {
            background-color: #27272a;
            color: #f4f4f5;
        }

        QTabBar::tab:selected {
            background-color: #18181b;
            color: #ffffff;
            border: 1px solid #3f3f46;
            border-top: 2px solid #3b82f6;
            border-bottom: 1px solid #18181b;
            font-weight: bold;
        }

        /* === Group Boxes === */
        QGroupBox {
            background-color: #1e1e24;
            border: 1px solid #33333d;
            border-radius: 8px;
            margin-top: 18px;
            padding-top: 14px;
            padding-bottom: 10px;
            padding-left: 10px;
            padding-right: 10px;
            font-weight: bold;
            color: #f4f4f5;
        }

        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 12px;
            padding: 0 6px;
            color: #38bdf8;
            background-color: #1e1e24;
            border-radius: 3px;
        }

        /* === Inputs, Dropdowns, Spin Boxes === */
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
            background-color: #131418;
            color: #ffffff;
            border: 1px solid #3f3f46;
            border-radius: 5px;
            padding: 5px 8px;
            selection-background-color: #2563eb;
            selection-color: #ffffff;
            min-height: 22px;
        }

        QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
            border: 1.5px solid #3b82f6;
            background-color: #171920;
        }

        QLineEdit:read-only {
            background-color: #1c1d22;
            color: #d4d4d8;
            border: 1px solid #2e3038;
        }

        QLineEdit::placeholder {
            color: #71717a;
        }

        QComboBox::drop-down {
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 22px;
            border-left: 1px solid #3f3f46;
            border-top-right-radius: 5px;
            border-bottom-right-radius: 5px;
        }

        QComboBox QAbstractItemView {
            background-color: #1e1e24;
            color: #ffffff;
            border: 1px solid #3f3f46;
            selection-background-color: #2563eb;
            selection-color: #ffffff;
            padding: 4px;
        }

        /* === Buttons === */
        QPushButton {
            background-color: #2d3139;
            color: #ffffff;
            border: 1px solid #454a57;
            border-radius: 5px;
            padding: 6px 14px;
            font-weight: 500;
            min-height: 20px;
        }

        QPushButton:hover {
            background-color: #3b414f;
            border: 1px solid #555c6d;
        }

        QPushButton:pressed {
            background-color: #20232b;
        }

        QPushButton:disabled {
            background-color: #1a1c22;
            color: #606674;
            border: 1px solid #262932;
        }

        /* Primary Action Buttons */
        QPushButton#primaryButton, QPushButton[primary="true"] {
            background-color: #2563eb;
            color: #ffffff;
            border: 1px solid #3b82f6;
            font-weight: bold;
        }

        QPushButton#primaryButton:hover, QPushButton[primary="true"]:hover {
            background-color: #1d4ed8;
            border: 1px solid #60a5fa;
        }

        QPushButton#primaryButton:pressed, QPushButton[primary="true"]:pressed {
            background-color: #1e40af;
        }

        QPushButton#primaryButton:disabled, QPushButton[primary="true"]:disabled {
            background-color: #1e293b;
            color: #64748b;
            border: 1px solid #334155;
        }

        /* === Summary Cards === */
        QLabel#summaryCard {
            background-color: #1e293b;
            border: 1px solid #334155;
            border-left: 4px solid #38bdf8;
            color: #f1f5f9;
            font-size: 10pt;
            font-weight: 500;
            padding: 10px 14px;
            border-radius: 6px;
        }

        /* === Muted / Secondary Labels === */
        QLabel#mutedLabel, QLabel[muted="true"] {
            color: #a1a1aa;
            font-size: 9pt;
        }

        /* === Warning Banners === */
        QLabel#warningBanner, QLabel[warning="true"] {
            color: #fde047;
            background-color: #422006;
            border: 1px solid #ca8a04;
            border-radius: 5px;
            padding: 6px 10px;
            font-weight: bold;
        }

        /* === Log / Console Terminal TextEdits === */
        QTextEdit, QTextEdit#logConsole {
            background-color: #0d0f12;
            color: #e2e8f0;
            border: 1px solid #2d3139;
            border-radius: 6px;
            padding: 6px;
            font-family: Consolas;
            font-size: 9.5pt;
            selection-background-color: #2563eb;
            selection-color: #ffffff;
        }

        /* === Progress Bar === */
        QProgressBar {
            background-color: #131418;
            border: 1px solid #3f3f46;
            border-radius: 4px;
            text-align: center;
            color: #ffffff;
            font-weight: bold;
        }

        QProgressBar::chunk {
            background-color: #2563eb;
            border-radius: 3px;
        }

        /* === Status Bar === */
        QStatusBar {
            background-color: #121316;
            color: #cbd5e1;
            border-top: 1px solid #27272a;
        }

        QStatusBar::item {
            border: none;
        }

        /* === Scrollbars === */
        QScrollBar:vertical {
            background-color: #121316;
            width: 10px;
            margin: 0px;
        }

        QScrollBar::handle:vertical {
            background-color: #333842;
            min-height: 20px;
            border-radius: 4px;
        }

        QScrollBar::handle:vertical:hover {
            background-color: #4b5261;
        }

        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }

        QScrollBar:horizontal {
            background-color: #121316;
            height: 10px;
            margin: 0px;
        }

        QScrollBar::handle:horizontal {
            background-color: #333842;
            min-width: 20px;
            border-radius: 4px;
        }

        QScrollBar::handle:horizontal:hover {
            background-color: #4b5261;
        }

        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
            width: 0px;
        }

        /* === Video Preview Container === */
        #previewContainer, QLabel#previewLabel {
            background-color: #0d0f12;
            border: 1px solid #2d3139;
            border-radius: 6px;
            color: #a1a1aa;
        }

        /* === Checkboxes & Radio Buttons === */
        QCheckBox, QRadioButton {
            color: #f4f4f5;
            spacing: 6px;
        }

        QCheckBox::indicator, QRadioButton::indicator {
            width: 16px;
            height: 16px;
            background-color: #131418;
            border: 1px solid #3f3f46;
            border-radius: 3px;
        }

        QRadioButton::indicator {
            border-radius: 8px;
        }

        QCheckBox::indicator:checked, QRadioButton::indicator:checked {
            background-color: #2563eb;
            border-color: #3b82f6;
        }

        /* === Slider === */
        QSlider::groove:horizontal {
            height: 6px;
            background: #27272a;
            border-radius: 3px;
        }

        QSlider::sub-page:horizontal {
            background: #2563eb;
            border-radius: 3px;
        }

        QSlider::handle:horizontal {
            background: #ffffff;
            border: 1px solid #3b82f6;
            width: 14px;
            margin-top: -4px;
            margin-bottom: -4px;
            border-radius: 7px;
        }

        /* === Tables & Tree Views === */
        QTableWidget, QTableView, QTreeView, QListView {
            background-color: #121316;
            alternate-background-color: #1a1c22;
            color: #f4f4f5;
            border: 1px solid #27272a;
            border-radius: 6px;
            gridline-color: #27272a;
            selection-background-color: #2563eb;
            selection-color: #ffffff;
        }

        QTableWidget::item, QTableView::item {
            padding: 6px 8px;
            border: none;
        }

        QTableWidget::item:selected, QTableView::item:selected {
            background-color: #2563eb;
            color: #ffffff;
        }

        QHeaderView::section {
            background-color: #1e1e24;
            color: #38bdf8;
            font-weight: 600;
            padding: 6px 8px;
            border: 1px solid #27272a;
            border-top: none;
            border-left: none;
        }

        QHeaderView::section:checked {
            background-color: #2563eb;
            color: #ffffff;
        }

        QTableCornerButton::section {
            background-color: #1e1e24;
            border: 1px solid #27272a;
        }

        /* === Text Browsers & Documentation === */
        QTextBrowser {
            background-color: #18181b;
            color: #f4f4f5;
            border: 1px solid #27272a;
            border-radius: 6px;
            padding: 8px;
            selection-background-color: #2563eb;
            selection-color: #ffffff;
        }

        /* === ToolTips === */
        QToolTip {
            background-color: #27272a;
            color: #f4f4f5;
            border: 1px solid #3f3f46;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 9pt;
        }

        /* === List Widgets === */
        QListWidget {
            background-color: #131418;
            color: #f4f4f5;
            border: 1px solid #27272a;
            border-radius: 6px;
            padding: 4px;
        }

        QListWidget::item {
            padding: 6px 8px;
            border-radius: 4px;
        }

        QListWidget::item:hover {
            background-color: #1e1e24;
        }

        QListWidget::item:selected {
            background-color: #2563eb;
            color: #ffffff;
        }

        /* === Splitter === */
        QSplitter::handle {
            background-color: #27272a;
        }

        QSplitter::handle:hover {
            background-color: #3b82f6;
        }

        /* === Menus === */
        QMenu {
            background-color: #1e1e24;
            color: #f4f4f5;
            border: 1px solid #3f3f46;
            border-radius: 6px;
            padding: 4px;
        }

        QMenu::item {
            padding: 6px 24px;
            border-radius: 4px;
        }

        QMenu::item:selected {
            background-color: #2563eb;
            color: #ffffff;
        }

        QMenu::separator {
            height: 1px;
            background-color: #27272a;
            margin: 4px 8px;
        }
        """

    def _get_light_stylesheet(self):
        """Generate clean, high-contrast daylight theme QSS stylesheet."""
        return """
        /* === Global Window & Base Widgets === */
        QWidget {
            background-color: #f8fafc;
            color: #0f172a;
            font-size: 9.5pt;
        }

        QMainWindow {
            background-color: #f1f5f9;
        }

        /* === Tabs & Tab Widget === */
        QTabWidget::pane {
            border: 1px solid #e2e8f0;
            background-color: #ffffff;
            border-radius: 6px;
            top: -1px;
        }

        QTabBar::tab {
            background-color: #f1f5f9;
            color: #64748b;
            border: 1px solid #e2e8f0;
            border-bottom: none;
            padding: 8px 18px;
            margin-right: 2px;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
            font-weight: 500;
        }

        QTabBar::tab:hover {
            background-color: #e2e8f0;
            color: #0f172a;
        }

        QTabBar::tab:selected {
            background-color: #ffffff;
            color: #0f172a;
            border: 1px solid #cbd5e1;
            border-top: 2px solid #2563eb;
            border-bottom: 1px solid #ffffff;
            font-weight: bold;
        }

        /* === Group Boxes === */
        QGroupBox {
            background-color: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            margin-top: 18px;
            padding-top: 14px;
            padding-bottom: 10px;
            padding-left: 10px;
            padding-right: 10px;
            font-weight: bold;
            color: #0f172a;
        }

        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 12px;
            padding: 0 6px;
            color: #0284c7;
            background-color: #ffffff;
            border-radius: 3px;
        }

        /* === Inputs, Dropdowns, Spin Boxes === */
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
            background-color: #ffffff;
            color: #0f172a;
            border: 1px solid #cbd5e1;
            border-radius: 5px;
            padding: 5px 8px;
            selection-background-color: #2563eb;
            selection-color: #ffffff;
            min-height: 22px;
        }

        QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
            border: 1.5px solid #2563eb;
            background-color: #ffffff;
        }

        QLineEdit:read-only {
            background-color: #f1f5f9;
            color: #475569;
            border: 1px solid #e2e8f0;
        }

        QLineEdit::placeholder {
            color: #94a3b8;
        }

        QComboBox::drop-down {
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 22px;
            border-left: 1px solid #cbd5e1;
            border-top-right-radius: 5px;
            border-bottom-right-radius: 5px;
        }

        QComboBox QAbstractItemView {
            background-color: #ffffff;
            color: #0f172a;
            border: 1px solid #cbd5e1;
            selection-background-color: #2563eb;
            selection-color: #ffffff;
            padding: 4px;
        }

        /* === Buttons === */
        QPushButton {
            background-color: #f1f5f9;
            color: #0f172a;
            border: 1px solid #cbd5e1;
            border-radius: 5px;
            padding: 6px 14px;
            font-weight: 500;
            min-height: 20px;
        }

        QPushButton:hover {
            background-color: #e2e8f0;
            border: 1px solid #94a3b8;
        }

        QPushButton:pressed {
            background-color: #cbd5e1;
        }

        QPushButton:disabled {
            background-color: #f8fafc;
            color: #94a3b8;
            border: 1px solid #e2e8f0;
        }

        /* Primary Action Buttons */
        QPushButton#primaryButton, QPushButton[primary="true"] {
            background-color: #2563eb;
            color: #ffffff;
            border: 1px solid #1d4ed8;
            font-weight: bold;
        }

        QPushButton#primaryButton:hover, QPushButton[primary="true"]:hover {
            background-color: #1d4ed8;
        }

        QPushButton#primaryButton:pressed, QPushButton[primary="true"]:pressed {
            background-color: #1e40af;
        }

        QPushButton#primaryButton:disabled, QPushButton[primary="true"]:disabled {
            background-color: #93c5fd;
            color: #ffffff;
            border: 1px solid #bfdbfe;
        }

        /* === Summary Cards === */
        QLabel#summaryCard {
            background-color: #f0f9ff;
            border: 1px solid #bae6fd;
            border-left: 4px solid #0284c7;
            color: #0369a1;
            font-size: 10pt;
            font-weight: 500;
            padding: 10px 14px;
            border-radius: 6px;
        }

        /* === Muted / Secondary Labels === */
        QLabel#mutedLabel, QLabel[muted="true"] {
            color: #64748b;
            font-size: 9pt;
        }

        /* === Warning Banners === */
        QLabel#warningBanner, QLabel[warning="true"] {
            color: #b45309;
            background-color: #fef3c7;
            border: 1px solid #f59e0b;
            border-radius: 5px;
            padding: 6px 10px;
            font-weight: bold;
        }

        /* === Log / Console Terminal TextEdits === */
        QTextEdit, QTextEdit#logConsole {
            background-color: #ffffff;
            color: #0f172a;
            border: 1px solid #cbd5e1;
            border-radius: 6px;
            padding: 6px;
            font-family: Consolas;
            font-size: 9.5pt;
            selection-background-color: #2563eb;
            selection-color: #ffffff;
        }

        /* === Progress Bar === */
        QProgressBar {
            background-color: #f1f5f9;
            border: 1px solid #cbd5e1;
            border-radius: 4px;
            text-align: center;
            color: #0f172a;
            font-weight: bold;
        }

        QProgressBar::chunk {
            background-color: #2563eb;
            border-radius: 3px;
        }

        /* === Status Bar === */
        QStatusBar {
            background-color: #f1f5f9;
            color: #475569;
            border-top: 1px solid #e2e8f0;
        }

        QStatusBar::item {
            border: none;
        }

        /* === Scrollbars === */
        QScrollBar:vertical {
            background-color: #f1f5f9;
            width: 10px;
            margin: 0px;
        }

        QScrollBar::handle:vertical {
            background-color: #cbd5e1;
            min-height: 20px;
            border-radius: 4px;
        }

        QScrollBar::handle:vertical:hover {
            background-color: #94a3b8;
        }

        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }

        QScrollBar:horizontal {
            background-color: #f1f5f9;
            height: 10px;
            margin: 0px;
        }

        QScrollBar::handle:horizontal {
            background-color: #cbd5e1;
            min-width: 20px;
            border-radius: 4px;
        }

        QScrollBar::handle:horizontal:hover {
            background-color: #94a3b8;
        }

        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
            width: 0px;
        }

        /* === Video Preview Container === */
        #previewContainer, QLabel#previewLabel {
            background-color: #f1f5f9;
            border: 1px solid #cbd5e1;
            border-radius: 6px;
            color: #64748b;
        }

        /* === Checkboxes & Radio Buttons === */
        QCheckBox, QRadioButton {
            color: #0f172a;
            spacing: 6px;
        }

        QCheckBox::indicator, QRadioButton::indicator {
            width: 16px;
            height: 16px;
            background-color: #ffffff;
            border: 1px solid #cbd5e1;
            border-radius: 3px;
        }

        QRadioButton::indicator {
            border-radius: 8px;
        }

        QCheckBox::indicator:checked, QRadioButton::indicator:checked {
            background-color: #2563eb;
            border-color: #1d4ed8;
        }

        /* === Slider === */
        QSlider::groove:horizontal {
            height: 6px;
            background: #e2e8f0;
            border-radius: 3px;
        }

        QSlider::sub-page:horizontal {
            background: #2563eb;
            border-radius: 3px;
        }

        QSlider::handle:horizontal {
            background: #ffffff;
            border: 1px solid #2563eb;
            width: 14px;
            margin-top: -4px;
            margin-bottom: -4px;
            border-radius: 7px;
        }

        /* === Tables & Tree Views === */
        QTableWidget, QTableView, QTreeView, QListView {
            background-color: #ffffff;
            alternate-background-color: #f8fafc;
            color: #0f172a;
            border: 1px solid #cbd5e1;
            border-radius: 6px;
            gridline-color: #e2e8f0;
            selection-background-color: #2563eb;
            selection-color: #ffffff;
        }

        QTableWidget::item, QTableView::item {
            padding: 6px 8px;
            border: none;
        }

        QTableWidget::item:selected, QTableView::item:selected {
            background-color: #2563eb;
            color: #ffffff;
        }

        QHeaderView::section {
            background-color: #f1f5f9;
            color: #0284c7;
            font-weight: 600;
            padding: 6px 8px;
            border: 1px solid #cbd5e1;
            border-top: none;
            border-left: none;
        }

        QHeaderView::section:checked {
            background-color: #2563eb;
            color: #ffffff;
        }

        QTableCornerButton::section {
            background-color: #f1f5f9;
            border: 1px solid #cbd5e1;
        }

        /* === Text Browsers & Documentation === */
        QTextBrowser {
            background-color: #ffffff;
            color: #0f172a;
            border: 1px solid #cbd5e1;
            border-radius: 6px;
            padding: 8px;
            selection-background-color: #2563eb;
            selection-color: #ffffff;
        }

        /* === ToolTips === */
        QToolTip {
            background-color: #0f172a;
            color: #ffffff;
            border: 1px solid #334155;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 9pt;
        }

        /* === List Widgets === */
        QListWidget {
            background-color: #ffffff;
            color: #0f172a;
            border: 1px solid #cbd5e1;
            border-radius: 6px;
            padding: 4px;
        }

        QListWidget::item {
            padding: 6px 8px;
            border-radius: 4px;
        }

        QListWidget::item:hover {
            background-color: #f1f5f9;
        }

        QListWidget::item:selected {
            background-color: #2563eb;
            color: #ffffff;
        }

        /* === Splitter === */
        QSplitter::handle {
            background-color: #e2e8f0;
        }

        QSplitter::handle:hover {
            background-color: #2563eb;
        }

        /* === Menus === */
        QMenu {
            background-color: #ffffff;
            color: #0f172a;
            border: 1px solid #cbd5e1;
            border-radius: 6px;
            padding: 4px;
        }

        QMenu::item {
            padding: 6px 24px;
            border-radius: 4px;
        }

        QMenu::item:selected {
            background-color: #2563eb;
            color: #ffffff;
        }

        QMenu::separator {
            height: 1px;
            background-color: #e2e8f0;
            margin: 4px 8px;
        }
        """

    def _get_custom_stylesheet(self, bg_color, text_color, accent_color):
        """Generate custom theme stylesheet respecting user colors."""
        # Fallback to dark stylesheet base with customized accent and panel colors
        return self._get_dark_stylesheet().replace("#3b82f6", accent_color).replace("#2563eb", accent_color)
