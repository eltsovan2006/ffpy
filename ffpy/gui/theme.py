"""Colors for syntax highlighting and status, picked for light or dark palettes."""

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

_LIGHT = {
    "group": "#1f4fbf", "key": "#7a3e9d", "number": "#0b7a75", "bool": "#b35900",
    "comment": "#6a737d", "atom": "#24292e", "string": "#24292e",
    "warning": "#b36b00", "error": "#c62828", "ok": "#2e7d32", "header": "#1f4fbf",
    "muted": "#8b949e", "accent": "#7a3e9d",
    "current_line": "#f3f6fb", "error_line": "#fde7e9", "line_number": "#9aa4af",
    "gutter": "#f6f8fa", "find": "#fff3b0",
}
_DARK = {
    "group": "#6ea8fe", "key": "#d2a8ff", "number": "#56d4bc", "bool": "#ffa657",
    "comment": "#8b949e", "atom": "#e6edf3", "string": "#e6edf3",
    "warning": "#e3b341", "error": "#ff7b72", "ok": "#56d364", "header": "#6ea8fe",
    "muted": "#7d8590", "accent": "#d2a8ff",
    "current_line": "#1c2330", "error_line": "#4a1d22", "line_number": "#6e7681",
    "gutter": "#161b22", "find": "#5a4a00",
}


def is_dark():
    app = QApplication.instance()
    if app is None:
        return False
    return app.palette().color(QPalette.Window).lightness() < 128


def color(name):
    return QColor((_DARK if is_dark() else _LIGHT)[name])


def hex_color(name):
    return (_DARK if is_dark() else _LIGHT)[name]
