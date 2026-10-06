"""Application theming: light and dark palettes + a live color map C.

Widgets should read colors from C at paint/layout time and register a
restyle() callback so switching themes at runtime re-styles everything.
"""
from string import Template

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette

LIGHT = {
    "window": "#f5f6fa", "base": "#ffffff", "alt": "#f0f2f5",
    "card": "#ffffff", "card_edge": "#dfe4ea",
    "text": "#2c3e50", "text2": "#34495e", "subtext": "#7f8c8d",
    "faint": "#95a5a6", "disabled_bg": "#dfe4ea", "disabled_text": "#95a5a6",
    "btn_bg": "#ffffff", "btn_face": "#ecf0f1", "btn_hover": "#eef2f5",
    "border": "#cfd6dd", "field_bg": "#ffffff",
    "select": "#d6eaf8", "accent": "#3498db", "link": "#2980b9",
    "placeholder": "#95a5a6", "track": "#f4f6f8", "chunk": "#3498db",
    "video_bg": "#e9ecef", "sheet_bg": "#e5e8eb", "page_edge": "#d0d4d9",
    "arc": "#e5e8ec", "tick_major": "#7f8c8d", "tick_minor": "#c3cad1",
    "in_tune_card": "#eafaf1", "idle_note": "#bdc3c7", "trace": "#3498db",
    "dot_normal": "#d5dbe1", "dot_off_edge": "#b9c2cb",
    "dot_accent": "#f39c12", "dot_accent_edge": "#d68910",
    "dot_live": "#3498db", "dot_muted": "#e74c3c",
    "neutral": "#dfe4ea", "neutral_text": "#2c3e50",
    "green": "#27ae60", "red": "#c0392b", "amber": "#f39c12", "blue": "#3498db",
}

DARK = {
    "window": "#1b222c", "base": "#232c38", "alt": "#1f2733",
    "card": "#242e3b", "card_edge": "#38424f",
    "text": "#e8edf3", "text2": "#c9d3de", "subtext": "#8b98a8",
    "faint": "#6b7885", "disabled_bg": "#2a3441", "disabled_text": "#5d6b7a",
    "btn_bg": "#2c3644", "btn_face": "#2c3644", "btn_hover": "#364252",
    "border": "#425061", "field_bg": "#1e2731",
    "select": "#2e4f6d", "accent": "#3498db", "link": "#5dade2",
    "placeholder": "#6b7885", "track": "#2a3441", "chunk": "#3498db",
    "video_bg": "#202a35", "sheet_bg": "#1e2731", "page_edge": "#38424f",
    "arc": "#3a4452", "tick_major": "#8b98a8", "tick_minor": "#4a5563",
    "in_tune_card": "#1f3a2c", "idle_note": "#4a5563", "trace": "#5dade2",
    "dot_normal": "#3a4452", "dot_off_edge": "#4a5563",
    "dot_accent": "#f39c12", "dot_accent_edge": "#f39c12",
    "dot_live": "#3498db", "dot_muted": "#e74c3c",
    "neutral": "#2c3644", "neutral_text": "#c9d3de",
    "green": "#2ecc71", "red": "#e74c3c", "amber": "#f5b041", "blue": "#5dade2",
}

C = dict(LIGHT)
_name = "light"
_listeners = []


def theme_name():
    return _name


def qss(template):
    """Fill a $placeholder stylesheet template with the active colors."""
    return Template(template).safe_substitute(C)


def on_change(callback):
    """Call callback() after every theme change (e.g. widget.update)."""
    _listeners.append(callback)


def restyle(apply):
    """Run apply() now and after every theme change; survives deleted widgets."""
    def safe():
        try:
            apply()
        except RuntimeError:
            pass
    safe()
    _listeners.append(safe)


def apply_theme(app, name):
    global _name
    _name = "dark" if str(name).lower() == "dark" else "light"
    C.clear()
    C.update(DARK if _name == "dark" else LIGHT)
    app.styleHints().setColorScheme(
        Qt.ColorScheme.Dark if _name == "dark" else Qt.ColorScheme.Light)
    app.setStyle("Fusion")
    palette = QPalette()
    for role, key in [
        (QPalette.Window, "window"), (QPalette.WindowText, "text"),
        (QPalette.Base, "base"), (QPalette.AlternateBase, "alt"),
        (QPalette.Text, "text"), (QPalette.Button, "btn_face"),
        (QPalette.ButtonText, "text"), (QPalette.ToolTipBase, "base"),
        (QPalette.ToolTipText, "text"), (QPalette.PlaceholderText, "placeholder"),
        (QPalette.Highlight, "accent"), (QPalette.Link, "link"),
    ]:
        palette.setColor(role, QColor(C[key]))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        palette.setColor(QPalette.Disabled, role, QColor(C["disabled_text"]))
    app.setPalette(palette)
    for cb in list(_listeners):
        cb()
