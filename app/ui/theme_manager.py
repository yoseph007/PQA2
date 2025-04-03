
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
        
    def set_theme(self, theme_name):
        """Set theme and update settings"""
        if hasattr(self.options_manager, 'update_setting'):
            # Update the theme setting in branding
            if isinstance(self.options_manager.get_setting("branding"), dict):
                # If branding is stored as a dict, update the selected_theme key
                self.options_manager.update_setting("branding", "selected_theme", theme_name)
            else:
                # If branding is stored as a string or not defined, create it
                branding_settings = {"selected_theme": theme_name}
                self.options_manager.set_setting("branding", branding_settings)
            
            # Apply the new theme
            self.apply_current_theme()
        
    def apply_current_theme(self):
        """Apply the current theme stored in settings to the application"""
        try:
            # Get theme settings from branding
            branding_settings = self.options_manager.get_setting("branding")
            # Handle both dictionary and string theme settings
            theme = "System"  # Default
            
            if isinstance(branding_settings, dict):
                theme = branding_settings.get("selected_theme", "System")
            elif isinstance(branding_settings, str):
                # If theme_settings is a string, it's the theme name
                theme = branding_settings
            
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
                    # Use custom colors with safety checks
                    palette = QPalette()
                    
                    # Default colors
                    bg_color = "#2D2D30"
                    text_color = "#FFFFFF"
                    accent_color = "#007ACC"
                    
                    # Try to get colors from branding settings with fallbacks
                    if isinstance(branding_settings, dict):
                        bg_color = branding_settings.get("bg_color", bg_color)
                        text_color = branding_settings.get("text_color", text_color)
                        accent_color = branding_settings.get("accent_color", accent_color)
                    
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
            import traceback
            logger.error(traceback.format_exc())
            # Apply default theme as fallback
            app = QApplication.instance()
            if app:
                app.setStyleSheet("")
                app.setPalette(app.style().standardPalette())
