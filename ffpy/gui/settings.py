"""Settings dialog with segmented controls for theme and language."""

import sys

from PySide6.QtCore import QProcess, QSettings, Qt, Signal
from PySide6.QtWidgets import (QApplication, QButtonGroup, QDialog, QMessageBox, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QVBoxLayout, QWidget)

from ffpy.gui.i18n import tr
from ffpy.gui.theme import get_palette, get_theme_mode, hex_color, set_theme_mode


class SegmentedControl(QFrame):
    """Segmented switch matching .ai/design styling."""
    valueChanged = Signal(str)

    def __init__(self, options, parent=None):
        super().__init__(parent)
        self.setProperty("segmented", True)
        self.options = options  # [(key, label), ...]
        self._buttons = {}
        self._current_value = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)

        self.btn_group = QButtonGroup(self)
        self.btn_group.setExclusive(True)

        for key, label in options:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            self.btn_group.addButton(btn)
            self._buttons[key] = btn
            layout.addWidget(btn)
            btn.clicked.connect(lambda checked, k=key: self._on_btn_clicked(k))

    def _on_btn_clicked(self, key):
        self._current_value = key
        btn = self._buttons.get(key)
        if btn is not None:
            btn.setChecked(True)
        self.valueChanged.emit(key)

    def set_value(self, key):
        self._current_value = key
        btn = self._buttons.get(key)
        if btn is not None:
            btn.setChecked(True)

    def value(self):
        return self._current_value


class SettingsDialog(QDialog):
    """Settings dialog: theme and language settings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Настройки"))
        self.resize(460, 260)
        self.settings = QSettings("ffpy", "ffpy-gui")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 24)
        layout.setSpacing(12)

        # Header
        hdr = QHBoxLayout()
        title_label = QLabel(tr("Настройки"))
        font = title_label.font()
        font.setPointSize(16)
        font.setBold(True)
        title_label.setFont(font)
        hdr.addWidget(title_label)
        hdr.addStretch(1)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        hdr.addWidget(close_btn)
        layout.addLayout(hdr)

        # Appearance section
        self.lbl_theme = QLabel(tr("ОФОРМЛЕНИЕ"))
        self.lbl_theme.setStyleSheet("font-size: 11px; font-weight: 600; letter-spacing: 0.8px;")
        layout.addWidget(self.lbl_theme)

        self.theme_seg = SegmentedControl([
            ("light", tr("Светлая")),
            ("dark", tr("Тёмная")),
            ("system", tr("Как в системе")),
        ])
        current_mode = self.settings.value("theme_mode", get_theme_mode() or "system")
        self.theme_seg.set_value(current_mode)
        self.theme_seg.valueChanged.connect(self._on_theme_changed)
        layout.addWidget(self.theme_seg)

        # Language section
        self.lbl_lang = QLabel(tr("ЯЗЫК"))
        self.lbl_lang.setStyleSheet("font-size: 11px; font-weight: 600; letter-spacing: 0.8px;")
        layout.addWidget(self.lbl_lang)

        self.lang_seg = SegmentedControl([
            ("ru", tr("Русский")),
            ("en", "English"),
        ])
        current_lang = self.settings.value("language", "ru")
        self.lang_seg.set_value(current_lang)
        self.lang_seg.valueChanged.connect(self._on_lang_changed)
        layout.addWidget(self.lang_seg)

        # System theme explanation hint
        self.hint = QLabel(tr("Режим «Как в системе» следует светлой или тёмной теме операционной системы."))
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("font-size: 12px;")
        layout.addWidget(self.hint)
        layout.addStretch(1)

        self._refresh_colors()

    def _refresh_colors(self):
        pal = get_palette()
        muted = pal["muted"]
        self.lbl_theme.setStyleSheet(f"font-size: 11px; font-weight: 600; letter-spacing: 0.8px; color: {muted};")
        self.lbl_lang.setStyleSheet(f"font-size: 11px; font-weight: 600; letter-spacing: 0.8px; color: {muted};")
        self.hint.setStyleSheet(f"font-size: 12px; color: {muted};")

    def _on_theme_changed(self, mode):
        self.settings.setValue("theme_mode", mode)
        set_theme_mode(mode)
        self._refresh_colors()

    def _on_lang_changed(self, lang):
        from ffpy.gui.i18n import language
        self.settings.setValue("language", lang)
        self.settings.sync()
        if lang == language():
            return
        ask = QMessageBox.question(self, tr("Язык интерфейса"),
                                   tr("Язык изменится после перезапуска ffpy. Перезапустить сейчас?"))
        if ask == QMessageBox.Yes:
            self._restart_app()

    def _restart_app(self):
        self.accept()
        main = self.parent()
        if main is None or main.close():
            if getattr(sys, "frozen", False):
                QProcess.startDetached(sys.executable, sys.argv[1:])
            else:
                QProcess.startDetached(sys.executable, ["-m", "ffpy.gui"] + sys.argv[1:])
            QApplication.quit()
