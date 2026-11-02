"""Design system tokens, palettes, QSS generator, and theme mode handling."""

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPalette, Qt
from PySide6.QtWidgets import QApplication

LIGHT_PALETTE = {
    "bg": "#f4f6fb",
    "surface": "#ffffff",
    "border": "#dde2ef",
    "text": "#1b2440",
    "muted": "#7a84a3",
    "accent": "#2f5bd8",
    "onAccent": "#ffffff",
    "accentSoft": "#e8eefc",
    "accentText": "#1e3f9e",
    "rail": "#0f1b3d",
    "railActive": "#22346b",
    "railText": "#9fb0e0",
    "ok": "#0b7a55",
    "okSoft": "#e3f6ef",
    "err": "#c42a42",
    "errSoft": "#fde7ea",
    "gutter": "#f7f8fc",
    "hover": "#f1f5ff",
    "chip": "#eceff7",
    "kw": "#2f5bd8",
    "key": "#7b3fc4",
    "num": "#0f8a7a",
    "com": "#8a93b0",
}

DARK_PALETTE = {
    "bg": "#0b1226",
    "surface": "#121b36",
    "border": "#243158",
    "text": "#e6ebfa",
    "muted": "#8e9bc4",
    "accent": "#6f95ff",
    "onAccent": "#0b1226",
    "accentSoft": "#1d2c5c",
    "accentText": "#aac1ff",
    "rail": "#070d1f",
    "railActive": "#1f2e63",
    "railText": "#8fa2d8",
    "ok": "#4fd1a0",
    "okSoft": "#123a30",
    "err": "#ff7a8c",
    "errSoft": "#3d1a24",
    "gutter": "#0f1730",
    "hover": "#17224a",
    "chip": "#1c2748",
    "kw": "#7ea3ff",
    "key": "#c39bff",
    "num": "#4fd1b8",
    "com": "#7c88ad",
}

_ALIASES = {
    "group": "kw",
    "number": "num",
    "bool": "kw",
    "comment": "com",
    "atom": "text",
    "string": "text",
    "warning": "err",
    "error": "err",
    "header": "kw",
    "current_line": "hover",
    "error_line": "errSoft",
    "line_number": "muted",
    "find": "accentSoft",
}


def relative_luminance(hex_str):
    hex_str = hex_str.lstrip("#")
    r, g, b = [int(hex_str[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]

    def to_lin(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * to_lin(r) + 0.7152 * to_lin(g) + 0.0722 * to_lin(b)


def contrast_ratio(hex1, hex2):
    l1, l2 = relative_luminance(hex1), relative_luminance(hex2)
    return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)


class _ThemeBus(QObject):
    theme_changed = Signal()


_theme_bus = None
_theme_mode = "system"  # "system", "light", "dark"


def get_theme_bus():
    global _theme_bus
    if _theme_bus is None:
        _theme_bus = _ThemeBus()
        hints = QGuiApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(_on_system_scheme_changed)
    return _theme_bus


def _on_system_scheme_changed(*_):
    if _theme_mode == "system":
        if _theme_bus is not None:
            _theme_bus.theme_changed.emit()


def set_theme_mode(mode):
    global _theme_mode
    if mode not in ("light", "dark", "system"):
        mode = "system"
    _theme_mode = mode
    bus = get_theme_bus()
    bus.theme_changed.emit()


def get_theme_mode():
    return _theme_mode


def is_system_dark():
    hints = QGuiApplication.styleHints()
    if hasattr(hints, "colorScheme"):
        scheme = hints.colorScheme()
        if scheme == Qt.ColorScheme.Dark:
            return True
        elif scheme == Qt.ColorScheme.Light:
            return False
    app = QApplication.instance()
    if app is not None:
        return app.palette().color(QPalette.Window).lightness() < 128
    return False


def is_dark(mode=None):
    if mode is None:
        mode = _theme_mode
    if mode == "dark":
        return True
    elif mode == "light":
        return False
    return is_system_dark()


def get_palette(mode=None):
    return DARK_PALETTE if is_dark(mode) else LIGHT_PALETTE


def hex_color(name, mode=None):
    pal = get_palette(mode)
    if name in pal:
        return pal[name]
    if name in _ALIASES:
        alias = _ALIASES[name]
        if alias in pal:
            return pal[alias]
    return pal.get("text", "#000000")


def color(name, mode=None):
    return QColor(hex_color(name, mode))


def app_font(size=10):
    families = QFontDatabase.families()
    if "Inter" in families:
        f = QFont("Inter")
    else:
        f = QFontDatabase.systemFont(QFontDatabase.GeneralFont)
    f.setPointSize(size)
    return f


def build_qss(palette=None):
    if palette is None:
        palette = get_palette()
    p = palette

    return f"""
/* ffpy design system */
QWidget {{
    color: {p['text']};
    background-color: {p['bg']};
    selection-background-color: {p['accentSoft']};
    selection-color: {p['accentText']};
}}

QMainWindow {{
    background-color: {p['bg']};
}}

QToolBar#main_toolbar {{
    background-color: {p['surface']};
    border-bottom: 1px solid {p['border']};
    spacing: 8px;
    padding: 4px 10px;
}}

QMenuBar {{
    background-color: {p['surface']};
    color: {p['text']};
    border-bottom: 1px solid {p['border']};
    padding: 2px 4px;
}}

QMenuBar::item {{
    background: transparent;
    padding: 4px 8px;
    border-radius: 4px;
}}

QMenuBar::item:selected {{
    background-color: {p['hover']};
}}

QMenu {{
    background-color: {p['surface']};
    color: {p['text']};
    border: 1px solid {p['border']};
    border-radius: 8px;
    padding: 4px;
}}

QMenu::item {{
    padding: 6px 20px;
    border-radius: 4px;
}}

QMenu::item:selected {{
    background-color: {p['accentSoft']};
    color: {p['accentText']};
}}

QMenu::separator {{
    height: 1px;
    background-color: {p['border']};
    margin: 4px 8px;
}}

QDockWidget {{
    background-color: {p['surface']};
    color: {p['text']};
    border: 1px solid {p['border']};
}}

QDockWidget::title {{
    background-color: {p['surface']};
    border-bottom: 1px solid {p['border']};
    padding: 6px 10px;
    font-size: 11px;
    font-weight: 600;
    color: {p['muted']};
}}

QTabWidget::pane {{
    border: 1px solid {p['border']};
    background-color: {p['surface']};
    border-radius: 8px;
}}

QTabBar::tab {{
    background-color: transparent;
    color: {p['muted']};
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 500;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    margin-right: 2px;
}}

QTabBar::tab:selected {{
    background-color: {p['surface']};
    color: {p['text']};
    font-weight: 600;
    border: 1px solid {p['border']};
    border-bottom: none;
}}

QTabBar::tab:hover:!selected {{
    background-color: {p['hover']};
    color: {p['text']};
}}

QPushButton {{
    background-color: {p['surface']};
    color: {p['text']};
    border: 1px solid {p['border']};
    border-radius: 8px;
    padding: 4px 8px;
    font-size: 13px;
    font-weight: 500;
}}

QPushButton:hover {{
    background-color: {p['hover']};
}}

QPushButton:pressed {{
    background-color: {p['chip']};
}}

QPushButton:disabled {{
    color: {p['muted']};
    background-color: {p['bg']};
    border-color: {p['border']};
}}

QToolButton {{
    background-color: transparent;
    color: {p['text']};
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 4px 8px;
}}

QToolButton:hover {{
    background-color: {p['hover']};
    border-color: {p['border']};
}}

QToolButton:pressed {{
    background-color: {p['chip']};
}}

QStatusBar {{
    background-color: {p['surface']};
    color: {p['muted']};
    border-top: 1px solid {p['border']};
    font-size: 12px;
}}

QDialog {{
    background-color: {p['surface']};
    color: {p['text']};
}}

QLineEdit, QSpinBox, QComboBox {{
    background-color: {p['surface']};
    color: {p['text']};
    border: 1px solid {p['border']};
    border-radius: 6px;
    padding: 4px 8px;
}}

QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border-color: {p['accent']};
}}

QTreeView, QListView, QListWidget, QPlainTextEdit, QTextEdit, QTextBrowser {{
    background-color: {p['surface']};
    color: {p['text']};
    border: 1px solid {p['border']};
    border-radius: 6px;
}}

QTreeView::item:hover, QListView::item:hover, QListWidget::item:hover {{
    background-color: {p['hover']};
}}

QTreeView::item:selected, QListView::item:selected, QListWidget::item:selected {{
    background-color: {p['accentSoft']};
    color: {p['accentText']};
}}

QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 0px;
}}

QScrollBar::handle:vertical {{
    background: {p['border']};
    min-height: 20px;
    border-radius: 4px;
}}

QScrollBar::handle:vertical:hover {{
    background: {p['muted']};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 0px;
}}

QScrollBar::handle:horizontal {{
    background: {p['border']};
    min-width: 20px;
    border-radius: 4px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {p['muted']};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

QSplitter::handle {{
    background-color: {p['border']};
}}

/* Segmented control */
QFrame[segmented="true"] {{
    background-color: {p['chip']};
    border-radius: 9px;
    border: none;
}}

QFrame[segmented="true"] QPushButton {{
    border: none;
    background-color: transparent;
    padding: 6px 12px;
    border-radius: 7px;
    font-size: 13px;
    color: {p['muted']};
    font-weight: 500;
}}

QFrame[segmented="true"] QPushButton:checked {{
    background-color: {p['surface']};
    color: {p['text']};
    font-weight: 600;
}}

QFrame[segmented="true"] QPushButton:hover:!checked {{
    color: {p['text']};
}}
"""
