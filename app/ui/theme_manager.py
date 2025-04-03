
import os
import logging
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QPalette, QColor

logger = logging.getLogger(__name__)

class ThemeManager:
    """Manages application themes and styling"""
    
    def __init__(self, parent, options_manager):
        self.parent = parent
        self.options_manager = options_manager
        
    def apply_current_theme(self):
        """Apply the current theme stored in settings to the application"""
        try:
            # Get theme settings
            theme_settings = self.options_manager.get_setting("theme", {})
            theme = theme_settings.get("selected_theme", "System")
            
            # Apply theme
            app = QApplication.instance()
            if app:
                if theme == "Light":
                    app.setStyleSheet("")
                    app.setPalette(app.style().standardPalette())
                elif theme == "Dark":
                    try:
                        import qdarkstyle
                        app.setStyleSheet(qdarkstyle.load_stylesheet_pyqt5())
                    except ImportError:
                        logger.warning("QDarkStyle not installed, using default theme")
                        app.setStyleSheet("")
                        app.setPalette(app.style().standardPalette())
                elif theme == "System":
                    # Use system theme (default)
                    app.setStyleSheet("")
                    app.setPalette(app.style().standardPalette())
                elif theme == "Custom":
                    # Use custom colors
                    palette = QPalette()
                    bg_color = theme_settings.get("bg_color", "#2D2D30")
                    text_color = theme_settings.get("text_color", "#FFFFFF")
                    accent_color = theme_settings.get("accent_color", "#007ACC")
                    
                    palette.setColor(QPalette.Window, QColor(bg_color))
                    palette.setColor(QPalette.WindowText, QColor(text_color))
                    palette.setColor(QPalette.Base, QColor(bg_color).lighter(110))
                    palette.setColor(QPalette.AlternateBase, QColor(bg_color))
                    palette.setColor(QPalette.ToolTipBase, QColor(text_color))
                    palette.setColor(QPalette.ToolTipText, QColor(text_color))
                    palette.setColor(QPalette.Text, QColor(text_color))
                    palette.setColor(QPalette.Button, QColor(bg_color).lighter(110))
                    palette.setColor(QPalette.ButtonText, QColor(text_color))
                    palette.setColor(QPalette.BrightText, QColor(text_color).lighter(150))
                    palette.setColor(QPalette.Highlight, QColor(accent_color))
                    palette.setColor(QPalette.HighlightedText, QColor(text_color).lighter(150))
                    
                    app.setPalette(palette)
                    
            logger.info(f"Applied theme: {theme}")
            
        except Exception as e:
            logger.error(f"Error applying theme: {str(e)}")
