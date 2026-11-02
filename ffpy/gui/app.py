"""ffpy-gui main window."""

import os
import shutil
import sys

from PySide6.QtCore import (QDir, QFile, QFileSystemWatcher, QPointF, QRect, QRectF,
                            QSettings, QSize, Qt, QTimer, QUrl, qVersion)
from PySide6.QtGui import (QAction, QBrush, QColor, QDesktopServices, QIcon, QImage,
                           QKeySequence, QLinearGradient, QPainter, QPainterPath,
                           QPen, QPixmap, QRadialGradient)
from PySide6.QtWidgets import (QApplication, QButtonGroup, QDockWidget, QFileDialog,
                               QFileSystemModel, QFrame, QHeaderView, QHBoxLayout,
                               QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QMainWindow, QMenu, QMessageBox, QPushButton, QSizePolicy,
                               QSpacerItem, QSpinBox, QStackedWidget, QStyle, QTabBar,
                               QTabWidget, QToolBar, QToolButton, QTreeView, QVBoxLayout,
                               QWidget)

from ffpy import __version__
from ffpy.gui.builder import NewJobDialog
from ffpy.gui.editor import CodeEditor, FileTab
from ffpy.gui.highlight import OutHighlighter
from ffpy.gui.results import ResultsPanel, open_external
from ffpy.gui.runner import RunManager
from ffpy.gui.settings import SettingsDialog
from ffpy.gui.theme import app_font, build_qss, get_theme_bus, hex_color, set_theme_mode
from ffpy.gui.validate import check_text

FILE_FILTERS = ["*.inp", "*.out", "*.molden", "*.dat", "*.xyz", "*.log", "*.txt"]
OPEN_FILTER = ("Файлы ffpy (*.inp *.out *.dat *.xyz *.log);;Входные файлы (*.inp);;"
               "Логи (*.out *.log);;Все файлы (*)")
EMPTY_INP = """! new input
 $CONTRL SCFTYP=RHF RUNTYP=ENERGY ICHARG=0 MULT=1 $END
 $BASIS  GBASIS=N31 NGAUSS=6 NDFUNC=1 $END
 $DATA
Title
C1
O  8.0   0.000   0.000   0.117
H  1.0   0.000   0.757  -0.467
H  1.0   0.000  -0.757  -0.467
 $END
"""


def compact_path_label(path):
    """Format path as 'filename   —   parent_dir' with fallback for root."""
    if not path:
        return ""
    norm = os.path.abspath(path)
    name = os.path.basename(norm)
    parent = os.path.basename(os.path.dirname(norm))
    if parent:
        return f"{name}   —   {parent}"
    return name


class LogEditor(CodeEditor):
    def minimumSizeHint(self):
        return QSize(80, 40)

    def sizeHint(self):
        return QSize(200, 70)


class ProblemsList(QListWidget):
    def minimumSizeHint(self):
        return QSize(80, 40)

    def sizeHint(self):
        return QSize(200, 70)


def render_app_image(size=1024):
    """Render high-resolution macOS-style squircle app icon with 3D quantum molecule."""
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)

    scale = size / 1024.0
    p.scale(scale, scale)

    # Multi-layered soft drop shadow (macOS style)
    shadow_layers = [(36, 18, 10), (28, 14, 15), (20, 10, 22), (14, 6, 30), (8, 2, 42)]
    p.setPen(Qt.NoPen)
    for dy, exp, alpha in shadow_layers:
        p.setBrush(QColor(0, 0, 0, alpha))
        p.drawRoundedRect(QRectF(100 - exp, 100 + dy - exp, 824 + 2 * exp, 824 + 2 * exp), 185 + exp, 185 + exp)

    # Squircle tile
    tile_rect = QRectF(100, 100, 824, 824)
    tile_path = QPainterPath()
    tile_path.addRoundedRect(tile_rect, 185, 185)

    bg_grad = QLinearGradient(100, 100, 924, 924)
    bg_grad.setColorAt(0.0, QColor("#1e3a8a"))
    bg_grad.setColorAt(0.45, QColor("#172554"))
    bg_grad.setColorAt(1.0, QColor("#090d16"))
    p.fillPath(tile_path, bg_grad)

    p.save()
    p.setClipPath(tile_path)

    # Ambient quantum glow
    glow = QRadialGradient(512, 500, 380)
    glow.setColorAt(0.0, QColor(56, 189, 248, 75))
    glow.setColorAt(0.4, QColor(99, 102, 241, 40))
    glow.setColorAt(1.0, QColor(15, 23, 42, 0))
    p.setBrush(glow)
    p.setPen(Qt.NoPen)
    p.drawEllipse(QPointF(512, 500), 380, 380)

    # Quantum orbital rings
    p.save()
    p.translate(512, 510)
    p.rotate(-25)
    p.setPen(QPen(QColor(56, 189, 248, 75), 5.0))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QPointF(0, 0), 330, 120)
    p.restore()

    p.save()
    p.translate(512, 510)
    p.rotate(35)
    p.setPen(QPen(QColor(168, 85, 247, 65), 4.5))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QPointF(0, 0), 310, 110)
    p.restore()

    # Glass specular rim highlight
    rim_grad = QLinearGradient(512, 100, 512, 350)
    rim_grad.setColorAt(0.0, QColor(255, 255, 255, 90))
    rim_grad.setColorAt(0.5, QColor(255, 255, 255, 25))
    rim_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setPen(QPen(QBrush(rim_grad), 3.0))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(QRectF(101.5, 101.5, 821, 821), 184, 184)
    p.restore()

    # Covalent bonds: shadow
    p.setPen(QPen(QColor(0, 0, 0, 80), 38.0, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(512 + 8, 425 + 16), QPointF(335 + 8, 635 + 16))
    p.drawLine(QPointF(512 + 8, 425 + 16), QPointF(689 + 8, 635 + 16))

    # Covalent bonds: 3D cylinder body
    p.setPen(QPen(QColor("#475569"), 30.0, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(512, 425), QPointF(335, 635))
    p.drawLine(QPointF(512, 425), QPointF(689, 635))

    # Covalent bonds: specular shine
    p.setPen(QPen(QColor(241, 245, 249, 190), 10.0, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(512 - 3, 425 - 3), QPointF(335 - 3, 635 - 3))
    p.drawLine(QPointF(512 + 3, 425 - 3), QPointF(689 + 3, 635 - 3))

    # Lone-pair orbital lobe above oxygen
    p.save()
    p.translate(512, 295)
    orb_path = QPainterPath()
    orb_path.addEllipse(QRectF(-48, -70, 96, 140))
    orb_grad = QLinearGradient(0, -70, 0, 70)
    orb_grad.setColorAt(0.0, QColor(56, 189, 248, 190))
    orb_grad.setColorAt(0.6, QColor(99, 102, 241, 150))
    orb_grad.setColorAt(1.0, QColor(244, 63, 94, 70))
    p.setBrush(orb_grad)
    p.setPen(QPen(QColor(224, 242, 254, 160), 2.5))
    p.drawPath(orb_path)
    core_grad = QRadialGradient(0, -25, 35)
    core_grad.setColorAt(0.0, QColor(255, 255, 255, 200))
    core_grad.setColorAt(1.0, QColor(56, 189, 248, 0))
    p.setBrush(core_grad)
    p.setPen(Qt.NoPen)
    p.drawEllipse(QPointF(0, -25), 35, 45)
    p.restore()

    # Atom drop shadows
    for cx, cy, r in [(335, 635, 74), (689, 635, 74), (512, 425, 118)]:
        sh_grad = QRadialGradient(cx + 8, cy + 20, r + 15)
        sh_grad.setColorAt(0.0, QColor(0, 0, 0, 90))
        sh_grad.setColorAt(0.7, QColor(0, 0, 0, 40))
        sh_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(sh_grad)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(cx + 8, cy + 20), r + 15, r + 15)

    def draw_h(cx, cy, r):
        h_grad = QRadialGradient(cx, cy, r, cx - r * 0.38, cy - r * 0.38)
        h_grad.setColorAt(0.0, QColor("#ffffff"))
        h_grad.setColorAt(0.2, QColor("#f8fafc"))
        h_grad.setColorAt(0.5, QColor("#cbd5e1"))
        h_grad.setColorAt(0.8, QColor("#64748b"))
        h_grad.setColorAt(1.0, QColor("#334155"))
        p.setBrush(h_grad)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(cx, cy), r, r)
        rim = QRadialGradient(cx, cy, r, cx + r * 0.5, cy + r * 0.5)
        rim.setColorAt(0.8, QColor(56, 189, 248, 0))
        rim.setColorAt(1.0, QColor(56, 189, 248, 80))
        p.setBrush(rim)
        p.drawEllipse(QPointF(cx, cy), r, r)

    draw_h(335, 635, 74)
    draw_h(689, 635, 74)

    ox, oy, orad = 512, 425, 118
    o_grad = QRadialGradient(ox, oy, orad, ox - orad * 0.36, oy - orad * 0.36)
    o_grad.setColorAt(0.0, QColor("#ffffff"))
    o_grad.setColorAt(0.12, QColor("#fda4af"))
    o_grad.setColorAt(0.42, QColor("#f43f5e"))
    o_grad.setColorAt(0.72, QColor("#be123c"))
    o_grad.setColorAt(0.92, QColor("#881337"))
    o_grad.setColorAt(1.0, QColor("#4c0519"))
    p.setBrush(o_grad)
    p.setPen(Qt.NoPen)
    p.drawEllipse(QPointF(ox, oy), orad, orad)

    o_rim = QRadialGradient(ox, oy, orad, ox + orad * 0.45, oy + orad * 0.45)
    o_rim.setColorAt(0.82, QColor(254, 205, 211, 0))
    o_rim.setColorAt(1.0, QColor(254, 205, 211, 85))
    p.setBrush(o_rim)
    p.drawEllipse(QPointF(ox, oy), orad, orad)

    p.end()
    return img


def app_icon():
    """Modern macOS-style squircle application icon with 3D quantum molecule."""
    icon = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(QPixmap.fromImage(render_app_image(s)))
    return icon


def make_logo_pixmap(size=26, radius=8):
    """Draw the ffpy logo matching mock: 26px tile with 8px radius and water molecule."""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing, True)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), radius, radius)
    p.setClipPath(path)
    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0.0, QColor("#2a4fb8"))
    grad.setColorAt(1.0, QColor("#0f1b3d"))
    p.fillPath(path, grad)
    s = size / 16.0
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#e5384f"))
    p.drawEllipse(QPointF(8.0 * s, 5.0 * s), 3.0 * s, 3.0 * s)
    p.setBrush(QColor("#e8eefc"))
    p.drawEllipse(QPointF(3.5 * s, 12.0 * s), 2.2 * s, 2.2 * s)
    p.drawEllipse(QPointF(12.5 * s, 12.0 * s), 2.2 * s, 2.2 * s)
    p.end()
    return pix


def make_stop_icon(mode=None):
    """Quiet stop icon: small rounded square of color --muted matching mock."""
    icon = QIcon()
    for s in (11, 16, 22):
        pix = QPixmap(s, s)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing, True)
        box = s * 0.72
        offset = (s - box) / 2.0
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(hex_color("muted", mode)))
        p.drawRoundedRect(QRectF(offset, offset, box, box), 2.0, 2.0)
        p.end()
        icon.addPixmap(pix)
    return icon


def make_gear_icon(size=24):
    """Draw a clean gear icon matching theme."""
    import math
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing, True)
    cx, cy = size / 2.0, size / 2.0
    r_out = size * 0.42
    r_in = size * 0.32
    r_hole = size * 0.16
    teeth = 8

    path = QPainterPath()
    for i in range(teeth):
        a0 = 2 * math.pi * i / teeth
        a1 = a0 + math.pi / teeth * 0.35
        a2 = a0 + math.pi / teeth * 0.65
        a3 = a0 + math.pi / teeth
        if i == 0:
            path.moveTo(cx + r_out * math.cos(a0), cy + r_out * math.sin(a0))
        else:
            path.lineTo(cx + r_out * math.cos(a0), cy + r_out * math.sin(a0))
        path.lineTo(cx + r_out * math.cos(a1), cy + r_out * math.sin(a1))
        path.lineTo(cx + r_in * math.cos(a2), cy + r_in * math.sin(a2))
        path.lineTo(cx + r_in * math.cos(a3), cy + r_in * math.sin(a3))
    path.closeSubpath()

    hole = QPainterPath()
    hole.addEllipse(QPointF(cx, cy), r_hole, r_hole)
    gear = path.subtracted(hole)

    p.setPen(Qt.NoPen)
    p.setBrush(QColor(hex_color("muted")))
    p.drawPath(gear)
    p.end()
    return QIcon(pix)


def make_dock_toggle_pixmap(side="left", checked=False, size=20, mode=None):
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing, True)

    fg_col = QColor(hex_color("text" if checked else "muted", mode))
    pen = QPen(fg_col, 1.6)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)

    s = size / 20.0
    rect = QRectF(2.5 * s, 4.0 * s, 15.0 * s, 12.0 * s)
    p.drawRoundedRect(rect, 3.0 * s, 3.0 * s)

    if side == "left":
        p.drawLine(QPointF(7.5 * s, 4.0 * s), QPointF(7.5 * s, 16.0 * s))
        if checked:
            p.setPen(Qt.NoPen)
            fill_col = QColor(fg_col)
            fill_col.setAlphaF(0.35)
            p.setBrush(fill_col)
            p.drawRoundedRect(QRectF(3.0 * s, 4.5 * s, 4.2 * s, 11.0 * s), 2.0 * s, 2.0 * s)
    else:
        p.drawLine(QPointF(12.5 * s, 4.0 * s), QPointF(12.5 * s, 16.0 * s))
        if checked:
            p.setPen(Qt.NoPen)
            fill_col = QColor(fg_col)
            fill_col.setAlphaF(0.35)
            p.setBrush(fill_col)
            p.drawRoundedRect(QRectF(12.8 * s, 4.5 * s, 4.2 * s, 11.0 * s), 2.0 * s, 2.0 * s)
    p.end()
    return pix


def make_sidebar_icon(side="left", mode=None):
    icon = QIcon()
    for s in (16, 20, 24, 32):
        pix_off = make_dock_toggle_pixmap(side=side, checked=False, size=s, mode=mode)
        pix_on = make_dock_toggle_pixmap(side=side, checked=True, size=s, mode=mode)
        icon.addPixmap(pix_off, QIcon.Normal, QIcon.Off)
        icon.addPixmap(pix_on, QIcon.Normal, QIcon.On)
    return icon


def make_rail_pixmap(mode_name, checked=False, size=20, mode=None):
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing, True)

    col = QColor("#ffffff" if checked else hex_color("railText", mode))
    pen = QPen(col, 1.6)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)

    s = size / 20.0
    if mode_name == "editor":
        path = QPainterPath()
        path.moveTo(4.0 * s, 16.0 * s)
        path.lineTo(5.0 * s, 12.0 * s)
        path.lineTo(13.0 * s, 4.0 * s)
        path.lineTo(16.0 * s, 7.0 * s)
        path.lineTo(8.0 * s, 15.0 * s)
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(QPointF(12.0 * s, 5.0 * s), QPointF(15.0 * s, 8.0 * s))
    elif mode_name == "results":
        p.drawLine(QPointF(3.0 * s, 16.0 * s), QPointF(3.0 * s, 4.0 * s))
        p.drawLine(QPointF(3.0 * s, 16.0 * s), QPointF(17.0 * s, 16.0 * s))
        path = QPainterPath()
        path.moveTo(6.0 * s, 12.0 * s)
        path.lineTo(9.0 * s, 8.0 * s)
        path.lineTo(12.0 * s, 10.0 * s)
        path.lineTo(16.0 * s, 4.0 * s)
        p.drawPath(path)
    elif mode_name == "3d":
        path = QPainterPath()
        path.moveTo(10.0 * s, 2.5 * s)
        path.lineTo(17.0 * s, 6.5 * s)
        path.lineTo(17.0 * s, 14.5 * s)
        path.lineTo(10.0 * s, 18.5 * s)
        path.lineTo(3.0 * s, 14.5 * s)
        path.lineTo(3.0 * s, 6.5 * s)
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(QPointF(10.0 * s, 10.5 * s), QPointF(17.0 * s, 6.5 * s))
        p.drawLine(QPointF(10.0 * s, 10.5 * s), QPointF(10.0 * s, 18.5 * s))
        p.drawLine(QPointF(10.0 * s, 10.5 * s), QPointF(3.0 * s, 6.5 * s))
    elif mode_name == "batch":
        p.drawRoundedRect(QRectF(3.0 * s, 4.0 * s, 14.0 * s, 4.0 * s), 1.0 * s, 1.0 * s)
        p.drawRoundedRect(QRectF(3.0 * s, 12.0 * s, 14.0 * s, 4.0 * s), 1.0 * s, 1.0 * s)
    elif mode_name == "settings":
        p.drawEllipse(QPointF(10.0 * s, 10.0 * s), 3.0 * s, 3.0 * s)
        p.drawLine(QPointF(10.0 * s, 2.0 * s), QPointF(10.0 * s, 5.0 * s))
        p.drawLine(QPointF(10.0 * s, 15.0 * s), QPointF(10.0 * s, 18.0 * s))
        p.drawLine(QPointF(2.0 * s, 10.0 * s), QPointF(5.0 * s, 10.0 * s))
        p.drawLine(QPointF(15.0 * s, 10.0 * s), QPointF(18.0 * s, 10.0 * s))
        p.drawLine(QPointF(4.5 * s, 4.5 * s), QPointF(6.5 * s, 6.5 * s))
        p.drawLine(QPointF(13.5 * s, 13.5 * s), QPointF(15.5 * s, 15.5 * s))
        p.drawLine(QPointF(15.5 * s, 4.5 * s), QPointF(13.5 * s, 6.5 * s))
        p.drawLine(QPointF(6.5 * s, 13.5 * s), QPointF(4.5 * s, 15.5 * s))
    p.end()
    return pix


def make_rail_icon(mode_name, mode=None):
    icon = QIcon()
    for s in (16, 20, 24, 32):
        pix_off = make_rail_pixmap(mode_name, checked=False, size=s, mode=mode)
        pix_on = make_rail_pixmap(mode_name, checked=True, size=s, mode=mode)
        icon.addPixmap(pix_off, QIcon.Normal, QIcon.Off)
        icon.addPixmap(pix_on, QIcon.Normal, QIcon.On)
    return icon


class MainWindow(QMainWindow):
    def __init__(self, files=()):
        super().__init__()
        self.settings = QSettings(QSettings.defaultFormat(), QSettings.UserScope, "ffpy", "ffpy-gui")
        self.font_size = int(self.settings.value("font_size", 10))
        theme_mode = self.settings.value("theme_mode", "system")
        set_theme_mode(theme_mode)

        app = QApplication.instance()
        if app is not None:
            app.setFont(app_font(self.font_size))
            app.setStyleSheet(build_qss())
        get_theme_bus().theme_changed.connect(self._on_theme_changed)

        self.setWindowTitle("ffpy %s" % __version__)
        self.setWindowIcon(app_icon())
        self.resize(1280, 800)
        self.setAcceptDrops(True)

        self.runner = RunManager(self)
        self.runner.threads = int(self.settings.value("threads", min(8, os.cpu_count() or 1)))
        self.runner.line.connect(self._on_run_line)
        self.runner.started.connect(self._on_run_started)
        self.runner.finished.connect(self._on_run_finished)
        self.runner.queue_changed.connect(lambda n: self._update_run_state())

        self.watcher = QFileSystemWatcher(self)
        self.watcher.fileChanged.connect(self._file_changed_on_disk)

        self._build_tabs()
        self._build_files_dock()
        self._build_results_dock()
        self._build_log_dock()
        self._build_rail()
        self._build_actions()
        self._build_status()

        self.validate_timer = QTimer(self, singleShot=True, interval=400)
        self.validate_timer.timeout.connect(self._validate_current)
        self.run_timer = QTimer(self, interval=1000)
        self.run_timer.timeout.connect(self._update_run_state)

        geom = self.settings.value("geometry")
        if geom is not None:
            self.restoreGeometry(geom)
            self.ensure_within_screen()
        else:
            self.set_default_geometry()
        state = self.settings.value("window_state")
        if state is not None:
            self.restoreState(state)
        else:
            self.apply_default_dock_sizes()

        # Restore visibility from settings if specified
        f_vis = self.settings.value("files_dock_visible")
        if f_vis is not None:
            v = f_vis in (True, "true", "True", 1, "1")
            self.files_dock.setVisible(v)
            self.btn_toggle_files.setChecked(v)
        r_vis = self.settings.value("results_dock_visible")
        if r_vis is not None:
            v = r_vis in (True, "true", "True", 1, "1")
            self.results_dock.setVisible(v)
            self.btn_toggle_results.setChecked(v)
        self._editor_docks_visibility = {
            "files": not self.files_dock.isHidden(),
            "results": not self.results_dock.isHidden(),
            "log": not self.log_dock.isHidden(),
            "problems": not self.problems_dock.isHidden(),
        }
        self._update_editor_centering()

        folder = self.settings.value("folder") or self._default_folder()
        self.set_folder(folder)
        for f in files:
            self.open_path(os.path.abspath(f))
        self._update_actions()

    def apply_default_dock_sizes(self):
        self.resizeDocks([self.files_dock, self.results_dock], [252, 340], Qt.Horizontal)
        self.resizeDocks([self.log_dock, self.problems_dock], [150, 150], Qt.Vertical)

    def showEvent(self, e):
        super().showEvent(e)
        if not getattr(self, "_dock_sizes_applied", False):
            self._dock_sizes_applied = True
            state = self.settings.value("window_state")
            if (state is None or self.files_dock.width() < 235 or self.files_dock.width() > 275
                    or self.results_dock.width() < 310 or self.results_dock.width() > 370
                    or self.log_dock.height() > 180):
                self.apply_default_dock_sizes()
        self._update_editor_centering()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._update_editor_centering()

    # ---------- layout ----------
    def _default_folder(self):
        if getattr(sys, "frozen", False):
            ex = os.path.join(os.path.dirname(sys.executable), "examples")
            if os.path.isdir(ex):
                return ex
        return os.path.expanduser("~")

    def set_default_geometry(self, avail=None):
        if avail is None:
            screen = self.screen() or QApplication.primaryScreen()
            avail = screen.availableGeometry() if screen else None
        if not avail or avail.isEmpty():
            self.resize(1280, 800)
            return
        margin_w = min(40, max(0, avail.width() - 200))
        margin_h = min(60, max(0, avail.height() - 200))
        w = min(1280, max(400, avail.width() - margin_w))
        h = min(800, max(300, avail.height() - margin_h))
        x = avail.x() + max(0, (avail.width() - w) // 2)
        y = avail.y() + max(0, (avail.height() - h) // 2)
        self.setGeometry(x, y, w, h)

    def ensure_within_screen(self, avail=None):
        if avail is None:
            screen = self.screen() or QApplication.primaryScreen()
            if not screen:
                return
            avail = screen.availableGeometry()
        if not avail or avail.isEmpty():
            return
        geo = self.geometry()
        margin_w = min(40, max(0, avail.width() - 200))
        margin_h = min(60, max(0, avail.height() - 200))
        max_w = max(300, avail.width() - margin_w)
        max_h = max(200, avail.height() - margin_h)

        w = min(geo.width(), max_w)
        h = min(geo.height(), max_h)

        x = max(avail.left(), min(geo.x(), avail.right() - w + 1))
        y = max(avail.top(), min(geo.y(), avail.bottom() - h + 1))

        if (x, y, w, h) != (geo.x(), geo.y(), geo.width(), geo.height()):
            self.setGeometry(x, y, w, h)

    def _make_stub_page(self, title, description):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setAlignment(Qt.AlignCenter)
        card = QWidget()
        card.setObjectName("stub_card")
        card.setStyleSheet(f"""
            QWidget#stub_card {{
                background-color: {hex_color('surface')};
                border: 1px solid {hex_color('border')};
                border-radius: 12px;
                padding: 36px 48px;
            }}
        """)
        cv = QVBoxLayout(card)
        cv.setAlignment(Qt.AlignCenter)
        cv.setSpacing(10)
        lbl_title = QLabel(f"<h2>{title}</h2>")
        lbl_title.setAlignment(Qt.AlignCenter)
        lbl_desc = QLabel(description)
        lbl_desc.setAlignment(Qt.AlignCenter)
        lbl_desc.setStyleSheet(f"color: {hex_color('muted')}; font-size: 13px;")
        cv.addWidget(lbl_title)
        cv.addWidget(lbl_desc)
        v.addWidget(card)
        return w

    def _build_tabs(self):
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._tab_changed)
        self.welcome = self._make_welcome()
        self._show_welcome()

        # Page 0: editor container with centering when docks are hidden
        self.editor_page = QWidget()
        self.editor_layout = QHBoxLayout(self.editor_page)
        self.editor_layout.setContentsMargins(16, 0, 16, 0)
        self.editor_layout.setSpacing(0)
        self.left_spacer = QSpacerItem(0, 0, QSizePolicy.Fixed, QSizePolicy.Minimum)
        self.right_spacer = QSpacerItem(0, 0, QSizePolicy.Fixed, QSizePolicy.Minimum)
        self.editor_layout.addItem(self.left_spacer)
        self.editor_layout.addWidget(self.tabs, 1)
        self.editor_layout.addItem(self.right_spacer)

        # Pages 1-3: stubs
        self.stub_results = self._make_stub_page("Итоги", "Сводная таблица и графики расчётов появятся здесь")
        self.stub_3d = self._make_stub_page("3D", "Интерактивная 3D-визуализация молекулярных структур")
        self.stub_batch = self._make_stub_page("Пакеты", "Пакетная обработка и управление очередью расчётов")

        self.stack = QStackedWidget(self)
        self.stack.addWidget(self.editor_page)
        self.stack.addWidget(self.stub_results)
        self.stack.addWidget(self.stub_3d)
        self.stack.addWidget(self.stub_batch)
        self.setCentralWidget(self.stack)

    def _build_rail(self):
        self.rail_widget = QWidget()
        self.rail_widget.setObjectName("rail_widget")
        self.rail_widget.setFixedWidth(68)
        layout = QVBoxLayout(self.rail_widget)
        layout.setContentsMargins(0, 12, 0, 12)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignHCenter)

        def make_btn(label, icon_name, is_check=True):
            b = QToolButton()
            b.setProperty("rail", "true")
            b.setFixedSize(68, 50)
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setCheckable(is_check)
            b.setText(label)
            b.setAccessibleName(label)
            b.setIcon(make_rail_icon(icon_name))
            b.setIconSize(QSize(20, 20))
            b.setCursor(Qt.PointingHandCursor)
            font = b.font()
            font.setPixelSize(10)
            b.setFont(font)
            return b

        self.btn_mode_editor = make_btn("Редактор", "editor")
        self.btn_mode_results = make_btn("Итоги", "results")
        self.btn_mode_3d = make_btn("3D", "3d")
        self.btn_mode_batch = make_btn("Пакеты", "batch")
        self.btn_mode_settings = make_btn("Настройки", "settings", is_check=False)
        self.btn_mode_settings.clicked.connect(self.open_settings)
        self.settings_btn = self.btn_mode_settings

        self.rail_group = QButtonGroup(self)
        self.rail_group.setExclusive(True)
        self.rail_group.addButton(self.btn_mode_editor, 0)
        self.rail_group.addButton(self.btn_mode_results, 1)
        self.rail_group.addButton(self.btn_mode_3d, 2)
        self.rail_group.addButton(self.btn_mode_batch, 3)
        self.btn_mode_editor.setChecked(True)
        self.rail_group.idClicked.connect(self.set_mode)

        layout.addWidget(self.btn_mode_editor)
        layout.addWidget(self.btn_mode_results)
        layout.addWidget(self.btn_mode_3d)
        layout.addWidget(self.btn_mode_batch)
        layout.addStretch(1)
        layout.addWidget(self.btn_mode_settings)

        self.rail_toolbar = QToolBar("Режимы", self)
        self.rail_toolbar.setObjectName("rail_toolbar")
        self.rail_toolbar.setMovable(False)
        self.rail_toolbar.setFloatable(False)
        self.rail_toolbar.setContextMenuPolicy(Qt.PreventContextMenu)
        self.rail_toolbar.setFixedWidth(68)
        self.rail_widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.rail_toolbar.addWidget(self.rail_widget)
        self.addToolBar(Qt.LeftToolBarArea, self.rail_toolbar)
        self.rail = self.rail_widget

    def set_mode(self, index):
        if self.stack.currentIndex() == index:
            return
        prev_index = self.stack.currentIndex()
        if prev_index == 0:
            self._editor_docks_visibility = {
                "files": not self.files_dock.isHidden(),
                "results": not self.results_dock.isHidden(),
                "log": not self.log_dock.isHidden(),
                "problems": not self.problems_dock.isHidden(),
            }
        self.stack.setCurrentIndex(index)
        btn = self.rail_group.button(index)
        if btn and not btn.isChecked():
            btn.setChecked(True)
        is_editor = (index == 0)
        if not is_editor:
            self.files_dock.hide()
            self.results_dock.hide()
            self.log_dock.hide()
            self.problems_dock.hide()
        else:
            vis = getattr(self, "_editor_docks_visibility", None)
            if vis is not None:
                self.files_dock.setVisible(vis.get("files", True))
                self.results_dock.setVisible(vis.get("results", True))
                self.log_dock.setVisible(vis.get("log", True))
                self.problems_dock.setVisible(vis.get("problems", False))
            else:
                self.files_dock.show()
                self.results_dock.show()
                self.log_dock.show()
            self._update_editor_centering()

    def _update_editor_centering(self):
        if not hasattr(self, "tabs") or not hasattr(self, "files_dock"):
            return
        t = self.tab()
        is_inp = (t is None or getattr(t, "kind", "inp") == "inp")
        docks_closed = (self.files_dock.isHidden() and self.results_dock.isHidden())
        if is_inp and docks_closed:
            self.tabs.setMaximumWidth(860)
            self.left_spacer.changeSize(1, 0, QSizePolicy.Expanding, QSizePolicy.Minimum)
            self.right_spacer.changeSize(1, 0, QSizePolicy.Expanding, QSizePolicy.Minimum)
            self.editor_layout.setContentsMargins(16, 0, 16, 0)
        else:
            self.tabs.setMaximumWidth(16777215)
            self.left_spacer.changeSize(0, 0, QSizePolicy.Fixed, QSizePolicy.Minimum)
            self.right_spacer.changeSize(0, 0, QSizePolicy.Fixed, QSizePolicy.Minimum)
            self.editor_layout.setContentsMargins(0, 0, 0, 0)
        self.editor_layout.invalidate()

    def _make_welcome(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.addStretch(1)
        t = QLabel("<h2>ffpy %s</h2><p>Входные файлы Firefly/GAMESS, расчёт через PySCF</p>" % __version__)
        t.setAlignment(Qt.AlignCenter)
        v.addWidget(t)
        row = QHBoxLayout()
        row.addStretch(1)
        for text, slot in (("Новый расчёт…", self.new_job), ("Открыть файл…", self.open_dialog),
                           ("Открыть папку…", self.choose_folder)):
            b = QPushButton(text)
            b.setMinimumSize(QSize(160, 36))
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)
        self.recent_list = QListWidget()
        self.recent_list.setMaximumWidth(620)
        self.recent_list.setMaximumHeight(220)
        self.recent_list.itemActivated.connect(lambda it: self.open_path(it.data(Qt.UserRole)))
        lab = QLabel("Недавние файлы:")
        lab.setAlignment(Qt.AlignCenter)
        v.addSpacing(16)
        v.addWidget(lab)
        v.addWidget(self.recent_list, 0, Qt.AlignHCenter)
        hint = QLabel("F5 — запустить расчёт · Ctrl+F — поиск · Ctrl+/ — закомментировать строки · "
                      "файлы можно перетаскивать в окно")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("color:%s" % hex_color("muted"))
        v.addSpacing(10)
        v.addWidget(hint)
        v.addStretch(2)
        return w

    def _show_welcome(self):
        if self.tabs.count() == 0:
            self._fill_recent()
            self.tabs.addTab(self.welcome, "Начало")
            for side in (QTabBar.RightSide, QTabBar.LeftSide):
                self.tabs.tabBar().setTabButton(0, side, None)

    def _hide_welcome(self):
        i = self.tabs.indexOf(self.welcome)
        if i >= 0:
            self.tabs.removeTab(i)

    def _build_files_dock(self):
        dock = QDockWidget("Файлы", self)
        dock.setObjectName("files")
        title_bar = QWidget()
        title_bar.setObjectName("files_dock_title")
        th = QHBoxLayout(title_bar)
        th.setContentsMargins(14, 10, 14, 4)
        th.setSpacing(8)
        lbl_files = QLabel("ФАЙЛЫ")
        lbl_files.setProperty("dock_label", "true")
        self.lbl_folder_name = QLabel()
        self.lbl_folder_name.setProperty("dock_sub", "true")
        th.addWidget(lbl_files)
        th.addStretch(1)
        th.addWidget(self.lbl_folder_name)
        dock.setTitleBarWidget(title_bar)

        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 4, 8, 8)
        v.setSpacing(6)
        row = QHBoxLayout()
        row.setSpacing(4)
        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText("Поиск по файлам или путь...")
        self.folder_edit.setFixedHeight(30)
        self.folder_edit.returnPressed.connect(self._on_folder_edit_return)
        up = QToolButton()
        up.setText("↑")
        up.setToolTip("Папка выше")
        up.setFixedSize(28, 30)
        up.clicked.connect(lambda: self.set_folder(os.path.dirname(self.folder)))
        browse = QToolButton()
        browse.setText("…")
        browse.setToolTip("Выбрать папку")
        browse.setFixedSize(28, 30)
        browse.clicked.connect(self.choose_folder)
        row.addWidget(self.folder_edit, 1)
        row.addWidget(up)
        row.addWidget(browse)
        v.addLayout(row)
        self.fs = QFileSystemModel(self)
        self.fs.setFilter(QDir.AllDirs | QDir.Files | QDir.NoDotAndDotDot)
        self.fs.setNameFilters(FILE_FILTERS)
        self.fs.setNameFilterDisables(False)
        self.fs.setReadOnly(False)
        self.tree = QTreeView()
        self.tree.setModel(self.fs)
        for col in (1, 2, 3):
            self.tree.setColumnHidden(col, True)
        self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(0, Qt.AscendingOrder)
        self.tree.setHeaderHidden(True)
        self.tree.setSelectionMode(QTreeView.ExtendedSelection)
        self.tree.setDragEnabled(True)
        self.tree.setDragDropMode(QTreeView.DragOnly)
        self.tree.setEditTriggers(QTreeView.EditKeyPressed)
        self.tree.doubleClicked.connect(self._tree_open)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._tree_menu)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.tree.header().setStretchLastSection(True)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        v.addWidget(self.tree, 1)
        w.setMinimumWidth(240)
        dock.setWidget(w)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)
        self.files_dock = dock

    def _build_results_dock(self):
        dock = QDockWidget("Результаты", self)
        dock.setObjectName("results")
        res_title = QWidget()
        res_title.setObjectName("results_dock_title")
        rh = QHBoxLayout(res_title)
        rh.setContentsMargins(14, 10, 14, 4)
        lbl_res = QLabel("РЕЗУЛЬТАТЫ")
        lbl_res.setProperty("dock_label", "true")
        rh.addWidget(lbl_res)
        rh.addStretch(1)
        dock.setTitleBarWidget(res_title)
        self.results = ResultsPanel()
        self.results.setMinimumWidth(260)
        self.results.open_file.connect(self.open_path)
        dock.setWidget(self.results)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)
        self.results_dock = dock

    def _build_log_dock(self):
        dock = QDockWidget("Журнал запуска", self)
        dock.setObjectName("log")
        dock.setTitleBarWidget(QWidget())
        w = QWidget()
        v = QVBoxLayout(cw := w)
        v.setContentsMargins(4, 2, 4, 2)
        v.setSpacing(2)
        row = QHBoxLayout()
        self.run_label = QLabel("Нет запущенных расчётов")
        b_copy = QToolButton()
        b_copy.setText("Копировать")
        b_copy.clicked.connect(lambda: QApplication.clipboard().setText(self.log_view.toPlainText()))
        b_clear = QToolButton()
        b_clear.setText("Очистить")
        b_clear.clicked.connect(lambda: self.log_view.clear())
        row.addWidget(self.run_label, 1)
        row.addWidget(b_copy)
        row.addWidget(b_clear)
        v.addLayout(row)
        self.log_view = LogEditor(read_only=True)
        self.log_view.set_font_size(self.font_size - 1)
        self.log_view.setMaximumBlockCount(200000)
        OutHighlighter(self.log_view.document())
        v.addWidget(self.log_view, 1)
        dock.setWidget(w)
        self.addDockWidget(Qt.BottomDockWidgetArea, dock)
        self.log_dock = dock

        pdock = QDockWidget("Проверка входа", self)
        pdock.setObjectName("problems")
        pdock.setTitleBarWidget(QWidget())
        self.problems = ProblemsList()
        self.problems.itemActivated.connect(self._goto_problem)
        pdock.setWidget(self.problems)
        self.addDockWidget(Qt.BottomDockWidgetArea, pdock)
        self.tabifyDockWidget(dock, pdock)
        dock.raise_()
        self.problems_dock = pdock

    def _act(self, text, slot, shortcut=None, tip=None, icon=None, icon_text=None):
        a = QAction(text, self)
        a.triggered.connect(slot)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        if tip:
            a.setToolTip(tip)
            a.setStatusTip(tip)
        if icon:
            a.setIcon(icon)
        if icon_text:
            a.setIconText(icon_text)
        return a

    def _build_actions(self):
        A = self._act
        st = self.style()
        self.a_new_job = A("Новый расчёт…", self.new_job, "Ctrl+Shift+N", "Конструктор входного файла",
                           st.standardIcon(QStyle.SP_FileIcon), "Новый…")
        self.a_new = A("Пустой .inp", self.new_empty, "Ctrl+N")
        self.a_open = A("Открыть…", self.open_dialog, "Ctrl+O", "Открыть файл",
                        st.standardIcon(QStyle.SP_DialogOpenButton), "Открыть")
        self.a_folder = A("Открыть папку…", self.choose_folder, "Ctrl+Shift+O")
        self.a_save = A("Сохранить", self.save_current, "Ctrl+S", "Сохранить файл",
                        st.standardIcon(QStyle.SP_DialogSaveButton), "Сохранить")
        self.a_save_as = A("Сохранить как…", self.save_as, "Ctrl+Shift+S")
        self.a_save_all = A("Сохранить все", self.save_all)
        self.a_close = A("Закрыть вкладку", lambda: self.close_tab(self.tabs.currentIndex()), "Ctrl+W")
        self.a_quit = A("Выход", self.close, "Ctrl+Q")
        self.a_run = A("▶  Запустить", self.run_current, "F5", "Сохранить и запустить текущий .inp (F5)",
                       st.standardIcon(QStyle.SP_MediaPlay), "Запуск")
        self.a_run_folder = A("Запустить все .inp в папке", self.run_folder)
        self.a_stop = A("■  Остановить", self.stop_run, "Shift+F5", "Остановить расчёт и очистить очередь",
                        st.standardIcon(QStyle.SP_MediaStop), "Стоп")
        self.a_open_out = A("Открыть .out", self.open_out_of_current, "F6", "Открыть лог для текущего .inp",
                            st.standardIcon(QStyle.SP_FileDialogContentsView), ".out")
        self.a_molden = A("Открыть .molden внешней программой", self.open_molden_of_current, "F7",
                          "Открыть .molden во внешней программе",
                          st.standardIcon(QStyle.SP_FileDialogInfoView), ".molden")
        self.a_find = A("Найти…", lambda: self._with_tab(lambda t: t.findbar.open()), "Ctrl+F")
        self.a_replace = A("Заменить…", lambda: self._with_tab(lambda t: t.findbar.open(True)), "Ctrl+H")
        self.a_goto = A("Перейти к строке…", self.goto_line, "Ctrl+G")
        self.a_comment = A("Закомментировать / раскомментировать", lambda: self._with_tab(
            lambda t: t.editor.toggle_comment()), "Ctrl+/")
        self.a_copy_all = A("Копировать весь текст", lambda: self._with_tab(lambda t: t.copy_all()),
                            "Ctrl+Shift+C")
        self.a_font_up = A("Крупнее шрифт", lambda: self.set_font_size(self.font_size + 1), "Ctrl+=")
        self.a_font_down = A("Мельче шрифт", lambda: self.set_font_size(self.font_size - 1), "Ctrl+-")
        self.a_keywords = A("Ключевые слова ffpy", self.show_keywords, "F1")
        self.a_about = A("О программе", self.about)
        self.a_settings = A("Настройки…", self.open_settings, "Ctrl+,", "Настройки оформления и языка",
                            make_gear_icon(), "Настройки")

        mb = self.menuBar()
        mb.setNativeMenuBar(True)
        m = mb.addMenu("&Файл")
        for a in (self.a_new_job, self.a_new, None, self.a_open, self.a_folder):
            m.addSeparator() if a is None else m.addAction(a)
        self.recent_menu = m.addMenu("Недавние")
        self.recent_menu.aboutToShow.connect(self._fill_recent_menu)
        for a in (None, self.a_save, self.a_save_as, self.a_save_all, None, self.a_close, None, self.a_quit):
            m.addSeparator() if a is None else m.addAction(a)

        m = mb.addMenu("&Правка")
        self.a_undo = A("Отменить", lambda: self._with_tab(lambda t: t.editor.undo()), QKeySequence.Undo)
        self.a_redo = A("Повторить", lambda: self._with_tab(lambda t: t.editor.redo()), QKeySequence.Redo)
        for a in (self.a_undo, self.a_redo, None, self.a_find, self.a_replace, self.a_goto, None,
                  self.a_comment, self.a_copy_all):
            m.addSeparator() if a is None else m.addAction(a)
        # undo/redo/copy shortcuts are handled by the editor itself
        self.a_undo.setShortcut(QKeySequence())
        self.a_redo.setShortcut(QKeySequence())

        m = mb.addMenu("&Расчёт")
        for a in (self.a_run, self.a_run_folder, self.a_stop, None, self.a_open_out, self.a_molden):
            m.addSeparator() if a is None else m.addAction(a)
        m.addSeparator()
        th = A("Число потоков…", self.ask_threads)
        m.addAction(th)

        m = mb.addMenu("&Вид")
        m.addAction(self.a_font_up)
        m.addAction(self.a_font_down)
        m.addSeparator()
        for d in (self.files_dock, self.results_dock, self.log_dock, self.problems_dock):
            m.addAction(d.toggleViewAction())

        m = mb.addMenu("&Настройки")
        m.addAction(self.a_settings)

        m = mb.addMenu("&Справка")
        m.addAction(self.a_keywords)
        m.addAction(self.a_about)

        tb = self.addToolBar("Основное")
        tb.setObjectName("main_toolbar")
        tb.setMovable(False)
        tb.setFloatable(False)
        tb.setContextMenuPolicy(Qt.PreventContextMenu)
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

        # 1. Logo with version
        logo_widget = QWidget()
        logo_widget.setObjectName("logo_widget")
        logo_widget.setStyleSheet("background: transparent;")
        h_logo = QHBoxLayout(logo_widget)
        h_logo.setContentsMargins(0, 0, 8, 0)
        h_logo.setSpacing(8)
        self.lbl_logo_icon = QLabel()
        self.lbl_logo_icon.setFixedSize(26, 26)
        self.lbl_logo_icon.setPixmap(make_logo_pixmap(26, 8))
        self.lbl_logo_title = QLabel("ffpy")
        self.lbl_logo_title.setStyleSheet("font-size: 15px; font-weight: 700; background: transparent;")
        self.lbl_logo_ver = QLabel(__version__)
        self.lbl_logo_ver.setStyleSheet("font-size: 12px; color: %s; background: transparent;" % hex_color("muted"))
        h_logo.addWidget(self.lbl_logo_icon)
        h_logo.addWidget(self.lbl_logo_title)
        h_logo.addWidget(self.lbl_logo_ver)
        tb.addWidget(logo_widget)

        # 2. Main actions
        def make_flat_tb_btn(text, slot, tip):
            b = QToolButton()
            b.setProperty("flat_btn", "true")
            b.setText(text)
            b.setToolButtonStyle(Qt.ToolButtonTextOnly)
            b.setFixedHeight(32)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            return b

        self.btn_new = make_flat_tb_btn("Новый расчёт", self.new_job, self.a_new_job.toolTip())
        tb.addWidget(self.btn_new)
        self.btn_open = make_flat_tb_btn("Открыть", self.open_dialog, self.a_open.toolTip())
        tb.addWidget(self.btn_open)
        self.btn_save = make_flat_tb_btn("Сохранить", self.save_current, self.a_save.toolTip())
        tb.addWidget(self.btn_save)

        # 3. Vertical separator
        sep = QFrame()
        sep.setProperty("vsep", "true")
        sep.setFrameShape(QFrame.NoFrame)
        sep.setFixedWidth(1)
        sep.setFixedHeight(22)
        tb.addWidget(sep)

        # 4. Primary Run button
        self.btn_run = QToolButton()
        self.btn_run.setObjectName("btn_run")
        self.btn_run.setText("▶  Запустить")
        self.btn_run.setFixedHeight(34)
        self.btn_run.setToolTip(self.a_run.toolTip())
        self.btn_run.setStatusTip(self.a_run.statusTip())
        self.btn_run.clicked.connect(self.run_current)
        tb.addWidget(self.btn_run)

        # 5. Quiet Stop button
        self.btn_stop = QToolButton()
        self.btn_stop.setObjectName("btn_stop")
        self.btn_stop.setText("Стоп")
        self.btn_stop.setIcon(make_stop_icon())
        self.btn_stop.setIconSize(QSize(11, 11))
        self.btn_stop.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.btn_stop.setFixedHeight(34)
        self.btn_stop.setToolTip(self.a_stop.toolTip())
        self.btn_stop.setStatusTip(self.a_stop.statusTip())
        self.btn_stop.clicked.connect(self.stop_run)
        tb.addWidget(self.btn_stop)

        # 6. Spacer
        spacer = QWidget()
        spacer.setObjectName("toolbar_spacer")
        spacer.setStyleSheet("background: transparent;")
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)

        # 7. Claude-style dock toggle buttons
        self.btn_toggle_files = QToolButton()
        self.btn_toggle_files.setProperty("icon_btn", "true")
        self.btn_toggle_files.setFixedSize(32, 32)
        self.btn_toggle_files.setCheckable(True)
        self.btn_toggle_files.setChecked(True)
        self.btn_toggle_files.setAccessibleName("Список файлов")
        self.btn_toggle_files.setToolTip("Список файлов")
        self.btn_toggle_files.setIcon(make_sidebar_icon("left"))
        self.btn_toggle_files.setIconSize(QSize(20, 20))
        self.btn_toggle_files.toggled.connect(self.files_dock.setVisible)
        self.files_dock.visibilityChanged.connect(self.btn_toggle_files.setChecked)
        self.files_dock.visibilityChanged.connect(lambda _: self._update_editor_centering())
        tb.addWidget(self.btn_toggle_files)

        self.btn_toggle_results = QToolButton()
        self.btn_toggle_results.setProperty("icon_btn", "true")
        self.btn_toggle_results.setFixedSize(32, 32)
        self.btn_toggle_results.setCheckable(True)
        self.btn_toggle_results.setChecked(True)
        self.btn_toggle_results.setAccessibleName("Результаты")
        self.btn_toggle_results.setToolTip("Результаты")
        self.btn_toggle_results.setIcon(make_sidebar_icon("right"))
        self.btn_toggle_results.setIconSize(QSize(20, 20))
        self.btn_toggle_results.toggled.connect(self.results_dock.setVisible)
        self.results_dock.visibilityChanged.connect(self.btn_toggle_results.setChecked)
        self.results_dock.visibilityChanged.connect(lambda _: self._update_editor_centering())
        tb.addWidget(self.btn_toggle_results)

        # Keep threads spinbox off-toolbar for ask_threads / tests
        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(1, max(1, os.cpu_count() or 1))
        self.threads_spin.setValue(self.runner.threads)
        self.threads_spin.valueChanged.connect(self._set_threads)

    def _build_status(self):
        self.check_label = QLabel("")
        self.check_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.pos_label = QLabel("")
        self.statusBar().addWidget(self.check_label, 1)
        self.statusBar().addPermanentWidget(self.pos_label)

    # ---------- tabs and files ----------
    def tab(self, i=None):
        w = self.tabs.widget(self.tabs.currentIndex() if i is None else i)
        return w if isinstance(w, FileTab) else None

    def _with_tab(self, fn):
        t = self.tab()
        if t:
            fn(t)

    def find_tab(self, path):
        norm = os.path.normcase(os.path.abspath(path))
        for i in range(self.tabs.count()):
            t = self.tab(i)
            if t and t.path and os.path.normcase(os.path.abspath(t.path)) == norm:
                return i
        return -1

    def add_tab(self, tab, focus=True):
        self._hide_welcome()
        i = self.tabs.addTab(tab, tab.title())
        self.tabs.setTabToolTip(i, tab.path or "")
        tab.modified_changed.connect(lambda _m, t=tab: self._refresh_tab_title(t))
        tab.text_changed.connect(lambda t=tab: self._on_text_changed(t))
        tab.editor.cursorPositionChanged.connect(self._update_pos)
        if tab.path:
            self.watcher.addPath(tab.path)
        if focus:
            self.tabs.setCurrentIndex(i)
        return i

    def open_path(self, path, focus=True):
        if not path:
            return
        if os.path.isdir(path):
            self.set_folder(path)
            return
        if not os.path.exists(path):
            QMessageBox.warning(self, "ffpy", "Файл не найден:\n%s" % path)
            self._remove_recent(path)
            return
        i = self.find_tab(path)
        if i >= 0:
            if focus:
                self.tabs.setCurrentIndex(i)
            return self.tab(i)
        if path.lower().endswith(".molden"):
            if QMessageBox.question(self, "ffpy", "Открыть .molden во внешней программе "
                                    "(Chemcraft, Avogadro…)?\n«Нет» — показать как текст.") == QMessageBox.Yes:
                open_external(path)
                return
        size = os.path.getsize(path)
        if size > 50 * 1024 * 1024:
            QMessageBox.warning(self, "ffpy", "Файл слишком большой для просмотра (%.0f МБ)" % (size / 2**20))
            return
        try:
            tab = FileTab(path, font_size=self.font_size)
        except OSError as e:
            QMessageBox.warning(self, "ffpy", "Не удалось открыть файл:\n%s" % e)
            return
        self.add_tab(tab, focus)
        self._add_recent(path)
        file_dir = os.path.dirname(os.path.abspath(path))
        if os.path.isdir(file_dir) and (not self.folder or os.path.abspath(self.folder) != file_dir):
            self.set_folder(file_dir)
        if tab.kind == "out" and focus:
            self.results.set_out(path)
        return tab

    def _on_folder_edit_return(self):
        text = self.folder_edit.text().strip()
        if text and os.path.isdir(text):
            self.set_folder(text)
        else:
            self.folder_edit.setText(self.folder)

    def new_empty(self, *args):
        tab = FileTab(None, font_size=self.font_size)
        tab.editor.setPlainText(EMPTY_INP)
        tab.editor.document().setModified(True)
        self.add_tab(tab)

    def new_job(self, *args):
        dlg = NewJobDialog(self, self.folder)
        if dlg.exec() != NewJobDialog.Accepted:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить входной файл",
                                              os.path.join(self.folder, dlg.suggested_name()),
                                              "Входные файлы (*.inp)")
        tab = FileTab(None, font_size=self.font_size)
        tab.editor.setPlainText(dlg.result_text)
        if path:
            if not path.lower().endswith(".inp"):
                path += ".inp"
            tab.save(path)
            self._add_recent(path)
        else:
            tab.editor.document().setModified(True)
        self.add_tab(tab)
        self._refresh_tab_title(tab)

    def open_dialog(self, *args):
        paths, _ = QFileDialog.getOpenFileNames(self, "Открыть", self.folder, OPEN_FILTER)
        for p in paths:
            self.open_path(p)

    def choose_folder(self, *args):
        d = QFileDialog.getExistingDirectory(self, "Папка с расчётами", self.folder)
        if d:
            self.set_folder(d)

    def set_folder(self, folder):
        if not folder or not os.path.isdir(folder):
            folder = os.path.expanduser("~")
        self.folder = os.path.abspath(folder)
        self.folder_edit.setText(self.folder)
        self.folder_edit.setCursorPosition(0)
        self.folder_edit.setToolTip(self.folder)
        if hasattr(self, "lbl_folder_name"):
            self.lbl_folder_name.setText(os.path.basename(self.folder) or self.folder)
        self.tree.setRootIndex(self.fs.setRootPath(self.folder))
        self.settings.setValue("folder", self.folder)

    def save_current(self):
        t = self.tab()
        return self.save_tab(t) if t else False

    def save_tab(self, t, ask_path=False):
        if t.read_only:
            return True
        if not t.path or ask_path:
            start = t.path or os.path.join(self.folder, "job.inp")
            path, _ = QFileDialog.getSaveFileName(self, "Сохранить как", start, "Входные файлы (*.inp);;Все файлы (*)")
            if not path:
                return False
            if not os.path.splitext(path)[1]:
                path += ".inp"
            old = t.path
            t.save(path)
            if old:
                self.watcher.removePath(old)
            self.watcher.addPath(path)
            self._add_recent(path)
        else:
            self.watcher.removePath(t.path)
            t.save()
            self.watcher.addPath(t.path)
        self._refresh_tab_title(t)
        self.statusBar().showMessage("Сохранено: %s" % t.path, 3000)
        return True

    def save_as(self):
        t = self.tab()
        if t and not t.read_only:
            self.save_tab(t, ask_path=True)

    def save_all(self):
        for i in range(self.tabs.count()):
            t = self.tab(i)
            if t and t.is_modified():
                self.save_tab(t)

    def close_tab(self, i):
        t = self.tab(i)
        if t is None:
            return
        if t.is_modified():
            r = QMessageBox.question(self, "ffpy", "Сохранить изменения в «%s»?" % t.title().rstrip(" •"),
                                     QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
            if r == QMessageBox.Cancel or (r == QMessageBox.Save and not self.save_tab(t)):
                return
        if t.path:
            self.watcher.removePath(t.path)
        self.tabs.removeTab(i)
        t.deleteLater()
        self._show_welcome()

    def _refresh_tab_title(self, t):
        i = self.tabs.indexOf(t)
        if i >= 0:
            self.tabs.setTabText(i, t.title())
            self.tabs.setTabToolTip(i, t.path or "")
        if t is self.tab():
            self._update_title()

    def _update_title(self):
        t = self.tab()
        name = (t.path or "Без имени") if t else ""
        self.setWindowTitle(("%s — " % name if name else "") + "ffpy %s" % __version__)

    def _tab_changed(self, _i):
        if not hasattr(self, "a_run"):      # the welcome tab is added before the actions exist
            return
        t = self.tab()
        self._update_title()
        self._update_actions()
        self._update_pos()
        self._update_editor_centering()
        if t and t.kind == "inp":
            self._validate_current()
        else:
            self.check_label.setText("")
            self.problems.clear()
        if t and t.kind == "out" and t.path:
            self.results.set_out(t.path)
        elif t and t.kind == "inp" and t.path:
            out = os.path.splitext(t.path)[0] + ".out"
            if os.path.exists(out):
                self.results.set_out(out)

    def _update_actions(self):
        t = self.tab()
        inp = bool(t and t.kind == "inp")
        editable = bool(t and not t.read_only)
        for a in (self.a_save, self.a_save_as, self.a_replace, self.a_comment, self.a_undo, self.a_redo):
            a.setEnabled(editable)
        if hasattr(self, "btn_save"):
            self.btn_save.setEnabled(editable)
        for a in (self.a_find, self.a_goto, self.a_copy_all, self.a_close):
            a.setEnabled(t is not None)
        self.a_open_out.setEnabled(bool(t and t.path and t.kind == "inp"))
        has_molden = bool(t and t.path and os.path.exists(os.path.splitext(t.path)[0] + ".molden"))
        self.a_molden.setEnabled(has_molden)
        self.a_run.setEnabled(inp)
        if hasattr(self, "btn_run"):
            self.btn_run.setEnabled(inp)

    def _update_pos(self):
        t = self.tab()
        if not t:
            self.pos_label.setText("")
            return
        c = t.editor.textCursor()
        self.pos_label.setText("Стр %d, кол %d   " % (c.blockNumber() + 1, c.positionInBlock() + 1))

    def _on_text_changed(self, t):
        if t is self.tab() and t.kind == "inp":
            self.validate_timer.start()

    def _file_changed_on_disk(self, path):
        i = self.find_tab(path)
        if i < 0:
            return
        t = self.tab(i)
        if not os.path.exists(path):
            return
        if t.read_only or not t.is_modified():
            QTimer.singleShot(150, t.load)
            if t.kind == "out" and t is self.tab():
                QTimer.singleShot(200, lambda: self.results.set_out(path))
        elif t.changed_on_disk():
            r = QMessageBox.question(self, "ffpy", "Файл «%s» изменён на диске. Загрузить новую версию "
                                     "и потерять правки в редакторе?" % os.path.basename(path))
            if r == QMessageBox.Yes:
                t.load()
        if path not in self.watcher.files():
            self.watcher.addPath(path)

    # ---------- validation ----------
    def _validate_current(self):
        t = self.tab()
        if not t or t.kind != "inp":
            return
        chk = check_text(t.editor.toPlainText())
        t.editor.set_error_line(chk.line)
        self.problems.clear()
        if chk.ok:
            self.check_label.setText("✔ " + chk.message)
            self.check_label.setStyleSheet("color:%s" % hex_color("ok"))
            it = QListWidgetItem("✔ Вход корректен: " + chk.message)
            it.setForeground(QColor(hex_color("ok")))
            self.problems.addItem(it)
        else:
            self.check_label.setText("✖ " + chk.message)
            self.check_label.setStyleSheet("color:%s" % hex_color("error"))
            it = QListWidgetItem("✖ " + chk.message)
            it.setForeground(QColor(hex_color("error")))
            it.setData(Qt.UserRole, chk.line)
            self.problems.addItem(it)
        for w in chk.warnings:
            it = QListWidgetItem("⚠ " + w)
            it.setForeground(QColor(hex_color("warning")))
            self.problems.addItem(it)
        self.problems_dock.setWindowTitle("Проверка входа" + ("" if chk.ok else " ✖"))

    def _goto_problem(self, item):
        line = item.data(Qt.UserRole)
        t = self.tab()
        if line and t:
            t.editor.goto_line(line)

    def goto_line(self):
        t = self.tab()
        if not t:
            return
        n, ok = QInputDialog.getInt(self, "Перейти к строке", "Номер строки:",
                                    t.editor.textCursor().blockNumber() + 1, 1, t.editor.blockCount())
        if ok:
            t.editor.goto_line(n)

    # ---------- running ----------
    def run_current(self):
        t = self.tab()
        if not t or t.kind != "inp":
            return
        if t.is_modified() or not t.path:
            if not self.save_tab(t):
                return
        chk = check_text(t.editor.toPlainText())
        if not chk.ok:
            r = QMessageBox.question(self, "ffpy", "Во входном файле ошибка:\n\n%s\n\nВсё равно запустить?"
                                     % chk.message)
            if r != QMessageBox.Yes:
                return
        self.results_dock.hide()
        self.run_paths([t.path])

    def run_paths(self, paths):
        paths = [p for p in paths if p.lower().endswith(".inp")]
        if not paths:
            return
        if self.runner.is_running():
            self.statusBar().showMessage("Добавлено в очередь: %d" % len(paths), 4000)
        self.runner.enqueue(paths)
        self.log_dock.raise_()
        self._update_run_state()

    def run_folder(self):
        paths = sorted(os.path.join(self.folder, f) for f in os.listdir(self.folder)
                       if f.lower().endswith(".inp"))
        if not paths:
            QMessageBox.information(self, "ffpy", "В папке нет файлов .inp")
            return
        if QMessageBox.question(self, "ffpy", "Запустить по очереди %d файлов .inp из папки\n%s?"
                                % (len(paths), self.folder)) == QMessageBox.Yes:
            self.run_paths(paths)

    def stop_run(self):
        if self.runner.is_running() or self.runner.queue:
            self.runner.stop()

    def _on_run_started(self, path):
        self.log_view.clear()
        self.log_view.appendPlainText(">>> %s" % path)
        self.run_timer.start()
        self._update_run_state()
        self.log_dock.raise_()
        target_h = max(240, int(self.height() * 0.35))
        self.resizeDocks([self.log_dock], [target_h], Qt.Vertical)

    def _on_run_line(self, line):
        self.log_view.appendPlainText(line)

    def _on_run_finished(self, path, code):
        self.run_timer.stop()
        out = os.path.splitext(path)[0] + ".out"
        if code == -1:
            msg = "Расчёт остановлен: %s" % os.path.basename(path)
        elif code == 0:
            msg = "Готово: %s" % os.path.basename(path)
        else:
            msg = "Расчёт %s завершился с ошибкой (код %d)" % (os.path.basename(path), code)
        self.log_view.appendPlainText("<<< " + msg)
        self.statusBar().showMessage(msg, 10000)
        if os.path.exists(out):
            i = self.find_tab(out)
            if i >= 0:
                self.tab(i).load()
            else:
                self.open_path(out, focus=False)
            self.results.set_out(out)
            if code == 0:
                self.results_dock.show()
                self.results_dock.raise_()
        elif code == 0:
            self.results_dock.show()
            self.results_dock.raise_()
        self.resizeDocks([self.log_dock, self.problems_dock], [150, 150], Qt.Vertical)
        self._update_run_state()
        self._update_actions()
        if not self.isActiveWindow():
            QApplication.alert(self)

    def _update_run_state(self):
        q = len(self.runner.queue)
        if self.runner.is_running():
            el = int(self.runner.elapsed())
            txt = "Идёт расчёт: %s  (%d:%02d)" % (os.path.basename(self.runner.current or ""), el // 60, el % 60)
            if q:
                txt += ", в очереди: %d" % q
            self.run_label.setText(txt)
            self.run_label.setStyleSheet("color:%s; font-weight:bold" % hex_color("accent"))
            if hasattr(self, "btn_run"):
                self.btn_run.setText("Расчёт…")
                self.btn_run.setProperty("busy", "true")
                self.btn_run.style().unpolish(self.btn_run)
                self.btn_run.style().polish(self.btn_run)
        else:
            self.run_label.setText("Нет запущенных расчётов")
            self.run_label.setStyleSheet("")
            if hasattr(self, "btn_run"):
                self.btn_run.setText("▶  Запустить")
                self.btn_run.setProperty("busy", "false")
                self.btn_run.style().unpolish(self.btn_run)
                self.btn_run.style().polish(self.btn_run)
        self.a_stop.setEnabled(self.runner.is_running() or bool(q))
        if hasattr(self, "btn_stop"):
            self.btn_stop.setEnabled(self.runner.is_running() or bool(q))

    def _set_threads(self, n):
        self.runner.threads = n
        self.settings.setValue("threads", n)

    def ask_threads(self):
        n, ok = QInputDialog.getInt(self, "Потоки", "Число потоков для расчёта:", self.runner.threads,
                                    1, max(1, os.cpu_count() or 1))
        if ok:
            self.threads_spin.setValue(n)

    def open_out_of_current(self):
        t = self.tab()
        if t and t.path:
            out = os.path.splitext(t.path)[0] + ".out"
            if os.path.exists(out):
                self.open_path(out)
            else:
                self.statusBar().showMessage("Лога ещё нет — запустите расчёт (F5)", 4000)

    def open_molden_of_current(self):
        t = self.tab()
        if t and t.path:
            m = os.path.splitext(t.path)[0] + ".molden"
            if os.path.exists(m):
                open_external(m)

    # ---------- file tree ----------
    def _tree_paths(self):
        rows = {i.row(): i for i in self.tree.selectionModel().selectedRows(0)}
        return [self.fs.filePath(i) for i in rows.values()]

    def _tree_open(self, index):
        path = self.fs.filePath(index)
        if os.path.isfile(path):
            self.open_path(path)

    def _tree_menu(self, pos):
        idx = self.tree.indexAt(pos)
        paths = self._tree_paths() if idx.isValid() else []
        m = QMenu(self)
        if paths:
            files = [p for p in paths if os.path.isfile(p)]
            inps = [p for p in files if p.lower().endswith(".inp")]
            if files:
                m.addAction("Открыть", lambda: [self.open_path(p) for p in files])
            if inps:
                m.addAction("▶ Запустить" + (" (%d)" % len(inps) if len(inps) > 1 else ""),
                            lambda: self._run_from_tree(inps))
            if len(paths) == 1:
                p = paths[0]
                if os.path.isdir(p):
                    m.addAction("Сделать корневой папкой", lambda: self.set_folder(p))
                m.addAction("Открыть внешней программой", lambda: open_external(p))
                m.addAction("Показать в проводнике", lambda: self._reveal(p))
            m.addSeparator()
            m.addAction("Копировать путь", lambda: QApplication.clipboard().setText("\n".join(paths)))
            if files:
                m.addAction("Копировать в папку…", lambda: self._copy_to(files))
            if len(paths) == 1:
                m.addAction("Дублировать", lambda: self._duplicate(paths[0]))
                m.addAction("Переименовать", lambda: self.tree.edit(idx))
            m.addAction("Удалить в корзину", lambda: self._trash(paths))
            m.addSeparator()
        m.addAction("Новый .inp здесь…", self._new_inp_in_folder)
        m.addAction("Новая папка…", self._new_folder)
        m.addAction("Обновить", lambda: self.set_folder(self.folder))
        m.exec(self.tree.viewport().mapToGlobal(pos))

    def _run_from_tree(self, paths):
        for p in paths:
            i = self.find_tab(p)
            if i >= 0 and self.tab(i).is_modified():
                self.save_tab(self.tab(i))
        self.run_paths(paths)

    def _reveal(self, path):
        if os.name == "nt":
            import subprocess
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path)))

    def _copy_to(self, files):
        d = QFileDialog.getExistingDirectory(self, "Копировать в папку", self.folder)
        if not d:
            return
        for f in files:
            dest = os.path.join(d, os.path.basename(f))
            if os.path.exists(dest) and QMessageBox.question(
                    self, "ffpy", "%s уже существует. Заменить?" % dest) != QMessageBox.Yes:
                continue
            try:
                shutil.copy2(f, dest)
            except OSError as e:
                QMessageBox.warning(self, "ffpy", "Не удалось скопировать %s:\n%s" % (f, e))
        self.statusBar().showMessage("Скопировано файлов: %d → %s" % (len(files), d), 5000)

    def _duplicate(self, path):
        base, ext = os.path.splitext(path)
        n = 1
        while os.path.exists("%s_copy%d%s" % (base, n, ext)):
            n += 1
        dest = "%s_copy%d%s" % (base, n, ext)
        try:
            if os.path.isdir(path):
                shutil.copytree(path, dest)
            else:
                shutil.copy2(path, dest)
        except OSError as e:
            QMessageBox.warning(self, "ffpy", str(e))

    def _trash(self, paths):
        names = "\n".join(os.path.basename(p) for p in paths[:10])
        if QMessageBox.question(self, "ffpy", "Переместить в корзину?\n\n%s" % names) != QMessageBox.Yes:
            return
        for p in paths:
            i = self.find_tab(p)
            if i >= 0:
                t = self.tab(i)
                t.editor.document().setModified(False)
                self.close_tab(i)
            if not QFile.moveToTrash(p):
                QMessageBox.warning(self, "ffpy", "Не удалось переместить в корзину:\n%s" % p)

    def _target_dir(self):
        idx = self.tree.currentIndex()
        if idx.isValid():
            p = self.fs.filePath(idx)
            return p if os.path.isdir(p) else os.path.dirname(p)
        return self.folder

    def _new_inp_in_folder(self):
        d = self._target_dir()
        name, ok = QInputDialog.getText(self, "Новый файл", "Имя файла:", text="job.inp")
        if not ok or not name.strip():
            return
        if not name.lower().endswith(".inp"):
            name += ".inp"
        path = os.path.join(d, name)
        if os.path.exists(path):
            QMessageBox.warning(self, "ffpy", "Файл уже существует")
            return
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(EMPTY_INP)
        self.open_path(path)

    def _new_folder(self):
        d = self._target_dir()
        name, ok = QInputDialog.getText(self, "Новая папка", "Имя папки:")
        if ok and name.strip():
            try:
                os.makedirs(os.path.join(d, name.strip()))
            except OSError as e:
                QMessageBox.warning(self, "ffpy", str(e))

    def open_settings(self):
        dlg = SettingsDialog(self)
        dlg.exec()

    def _on_theme_changed(self):
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(build_qss())
        if hasattr(self, "a_settings"):
            self.a_settings.setIcon(make_gear_icon())
        if hasattr(self, "btn_toggle_files"):
            self.btn_toggle_files.setIcon(make_sidebar_icon("left"))
            self.btn_toggle_results.setIcon(make_sidebar_icon("right"))
        if hasattr(self, "btn_stop"):
            self.btn_stop.setIcon(make_stop_icon())
        if hasattr(self, "lbl_logo_ver"):
            self.lbl_logo_ver.setStyleSheet("font-size: 12px; color: %s; background: transparent;" % hex_color("muted"))
        if hasattr(self, "btn_mode_editor"):
            self.btn_mode_editor.setIcon(make_rail_icon("editor"))
            self.btn_mode_results.setIcon(make_rail_icon("results"))
            self.btn_mode_3d.setIcon(make_rail_icon("3d"))
            self.btn_mode_batch.setIcon(make_rail_icon("batch"))
            self.btn_mode_settings.setIcon(make_rail_icon("settings"))
        self._refresh_theme()

    def _refresh_theme(self):
        for i in range(self.tabs.count()):
            t = self.tab(i)
            if t:
                if hasattr(t, "highlighter") and t.highlighter:
                    t.highlighter.refresh_colors()
                t.editor._refresh_selections()
                t.editor._gutter.update()
        if hasattr(self, "log_highlighter") and self.log_highlighter:
            self.log_highlighter.refresh_colors()
        if hasattr(self, "log_view"):
            self.log_view._refresh_selections()
            self.log_view._gutter.update()
        self._validate_current()
        if hasattr(self, "results"):
            if self.results.data and self.results.out_path:
                self.results.view.setHtml(self.results._html(self.results.data))
            else:
                self.results.clear()

    # ---------- recent files ----------
    def _recent(self):
        r = self.settings.value("recent") or []
        return [r] if isinstance(r, str) else list(r)

    def _add_recent(self, path):
        r = [p for p in self._recent() if os.path.normcase(p) != os.path.normcase(path)]
        self.settings.setValue("recent", [path] + r[:14])

    def _remove_recent(self, path):
        self.settings.setValue("recent", [p for p in self._recent() if p != path])

    def _fill_recent_menu(self):
        self.recent_menu.clear()
        for p in self._recent():
            label = compact_path_label(p)
            a = self.recent_menu.addAction(label, lambda p=p: self.open_path(p))
            a.setToolTip(p)
            a.setStatusTip(p)
        if not self._recent():
            self.recent_menu.addAction("(пусто)").setEnabled(False)

    def _fill_recent(self):
        self.recent_list.clear()
        for p in self._recent():
            if os.path.exists(p):
                it = QListWidgetItem(compact_path_label(p))
                it.setToolTip(p)
                it.setData(Qt.UserRole, p)
                self.recent_list.addItem(it)

    # ---------- misc ----------
    def set_font_size(self, size):
        size = max(7, min(28, size))
        self.font_size = size
        self.settings.setValue("font_size", size)
        for i in range(self.tabs.count()):
            t = self.tab(i)
            if t:
                t.editor.set_font_size(size)
        self.log_view.set_font_size(max(7, size - 1))

    def show_keywords(self):
        import contextlib
        import io

        from ffpy.cli import print_keywords
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_keywords()
        tab = FileTab(None, read_only=True, font_size=self.font_size)
        tab.editor.setPlainText(buf.getvalue())
        tab.title = lambda: "Ключевые слова"
        self.add_tab(tab)

    def about(self):
        QMessageBox.about(self, "О программе",
                          "<h3>ffpy %s</h3><p>Входные файлы в формате Firefly/GAMESS, расчёт через PySCF."
                          "</p><p>Редактор .inp с проверкой на лету, просмотр логов, запуск и очередь "
                          "расчётов.</p><p>Qt %s</p>" % (__version__, qVersion()))

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            if url.isLocalFile():
                self.open_path(url.toLocalFile())

    def closeEvent(self, e):
        for i in range(self.tabs.count()):
            t = self.tab(i)
            if t and t.is_modified():
                self.tabs.setCurrentIndex(i)
                r = QMessageBox.question(self, "ffpy", "Сохранить изменения в «%s»?" % t.title().rstrip(" •"),
                                         QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
                if r == QMessageBox.Cancel or (r == QMessageBox.Save and not self.save_tab(t)):
                    e.ignore()
                    return
        if self.runner.is_running():
            if QMessageBox.question(self, "ffpy", "Идёт расчёт. Остановить его и выйти?") != QMessageBox.Yes:
                e.ignore()
                return
            self.runner.stop()
        if self.isVisible():
            self.settings.setValue("geometry", self.saveGeometry())
            self.settings.setValue("window_state", self.saveState())
            if self.stack.currentIndex() == 0:
                self.settings.setValue("files_dock_visible", not self.files_dock.isHidden())
                self.settings.setValue("results_dock_visible", not self.results_dock.isHidden())
            elif hasattr(self, "_editor_docks_visibility"):
                self.settings.setValue("files_dock_visible", self._editor_docks_visibility.get("files", True))
                self.settings.setValue("results_dock_visible", self._editor_docks_visibility.get("results", True))
        e.accept()


def main(argv=None):
    argv = sys.argv if argv is None else argv
    app = QApplication(argv)
    app.setApplicationName("ffpy-gui")
    app.setOrganizationName("ffpy")
    app.setWindowIcon(app_icon())
    app.setFont(app_font())
    app.setStyleSheet(build_qss())
    w = MainWindow(files=[a for a in argv[1:] if not a.startswith("-")])
    w.show()
    if "--smoke-test" in argv:     # used by packaging/build.ps1 on the frozen build
        QTimer.singleShot(1500, app.quit)
    return app.exec()
