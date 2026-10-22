"""ffpy-gui main window."""

import os
import shutil
import sys

from PySide6.QtCore import QDir, QFile, QFileSystemWatcher, QSettings, QSize, Qt, QTimer, QUrl, qVersion
from PySide6.QtGui import (QAction, QColor, QDesktopServices, QIcon, QKeySequence, QPainter, QPen,
                           QPixmap)
from PySide6.QtWidgets import (QApplication, QDockWidget, QFileDialog, QFileSystemModel,
                               QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPushButton,
                               QSpinBox, QTabBar, QTabWidget, QToolButton, QTreeView,
                               QVBoxLayout, QWidget)

from ffpy import __version__
from ffpy.gui.builder import NewJobDialog
from ffpy.gui.editor import CodeEditor, FileTab
from ffpy.gui.highlight import OutHighlighter
from ffpy.gui.results import ResultsPanel, open_external
from ffpy.gui.runner import RunManager
from ffpy.gui.theme import hex_color
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


def app_icon():
    """A small water-molecule glyph; also used to make packaging/ffpy.ico."""
    pm = QPixmap(256, 256)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#1f4fbf"))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(8, 8, 240, 240, 48, 48)
    p.setPen(QPen(QColor("#ffffff"), 14))
    p.drawLine(128, 104, 66, 176)
    p.drawLine(128, 104, 190, 176)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#ff6b6b"))
    p.drawEllipse(88, 64, 80, 80)
    p.setBrush(QColor("#ffffff"))
    p.drawEllipse(38, 148, 56, 56)
    p.drawEllipse(162, 148, 56, 56)
    p.end()
    return QIcon(pm)


class MainWindow(QMainWindow):
    def __init__(self, files=()):
        super().__init__()
        self.settings = QSettings("ffpy", "ffpy-gui")
        self.font_size = int(self.settings.value("font_size", 10))
        self.setWindowTitle("ffpy %s" % __version__)
        self.setWindowIcon(app_icon())
        self.resize(1400, 860)
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
        self._build_actions()
        self._build_status()

        self.validate_timer = QTimer(self, singleShot=True, interval=400)
        self.validate_timer.timeout.connect(self._validate_current)
        self.run_timer = QTimer(self, interval=1000)
        self.run_timer.timeout.connect(self._update_run_state)

        geom = self.settings.value("geometry")
        if geom is not None:
            self.restoreGeometry(geom)
        state = self.settings.value("window_state")
        if state is not None:
            self.restoreState(state)
        folder = self.settings.value("folder") or self._default_folder()
        self.set_folder(folder)
        for f in files:
            self.open_path(os.path.abspath(f))
        self._update_actions()

    # ---------- layout ----------
    def _default_folder(self):
        if getattr(sys, "frozen", False):
            ex = os.path.join(os.path.dirname(sys.executable), "examples")
            if os.path.isdir(ex):
                return ex
        return os.path.expanduser("~")

    def _build_tabs(self):
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._tab_changed)
        self.welcome = self._make_welcome()
        self.setCentralWidget(self.tabs)
        self._show_welcome()

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
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(4, 4, 4, 4)
        row = QHBoxLayout()
        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText("Путь к папке...")
        self.folder_edit.returnPressed.connect(self._on_folder_edit_return)
        up = QToolButton()
        up.setText("↑")
        up.setToolTip("Папка выше")
        up.clicked.connect(lambda: self.set_folder(os.path.dirname(self.folder)))
        browse = QToolButton()
        browse.setText("…")
        browse.setToolTip("Выбрать папку")
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
        self.tree.setHeaderHidden(False)
        self.tree.setSelectionMode(QTreeView.ExtendedSelection)
        self.tree.setDragEnabled(True)
        self.tree.setDragDropMode(QTreeView.DragOnly)
        self.tree.setEditTriggers(QTreeView.EditKeyPressed)
        self.tree.doubleClicked.connect(self._tree_open)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._tree_menu)
        self.tree.header().resizeSection(0, 230)
        v.addWidget(self.tree, 1)
        dock.setWidget(w)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)
        self.files_dock = dock

    def _build_results_dock(self):
        dock = QDockWidget("Результаты", self)
        dock.setObjectName("results")
        self.results = ResultsPanel()
        self.results.open_file.connect(self.open_path)
        dock.setWidget(self.results)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)
        self.results_dock = dock

    def _build_log_dock(self):
        dock = QDockWidget("Журнал запуска", self)
        dock.setObjectName("log")
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(4, 2, 4, 4)
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
        self.log_view = CodeEditor(read_only=True)
        self.log_view.set_font_size(self.font_size - 1)
        self.log_view.setMaximumBlockCount(200000)
        OutHighlighter(self.log_view.document())
        v.addWidget(self.log_view, 1)
        dock.setWidget(w)
        self.addDockWidget(Qt.BottomDockWidgetArea, dock)
        self.log_dock = dock

        pdock = QDockWidget("Проверка входа", self)
        pdock.setObjectName("problems")
        self.problems = QListWidget()
        self.problems.itemActivated.connect(self._goto_problem)
        pdock.setWidget(self.problems)
        self.addDockWidget(Qt.BottomDockWidgetArea, pdock)
        self.tabifyDockWidget(dock, pdock)
        dock.raise_()
        self.problems_dock = pdock

    def _act(self, text, slot, shortcut=None, tip=None):
        a = QAction(text, self)
        a.triggered.connect(slot)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        if tip:
            a.setToolTip(tip)
            a.setStatusTip(tip)
        return a

    def _build_actions(self):
        A = self._act
        self.a_new_job = A("Новый расчёт…", self.new_job, "Ctrl+Shift+N", "Конструктор входного файла")
        self.a_new = A("Пустой .inp", self.new_empty, "Ctrl+N")
        self.a_open = A("Открыть…", self.open_dialog, "Ctrl+O")
        self.a_folder = A("Открыть папку…", self.choose_folder, "Ctrl+Shift+O")
        self.a_save = A("Сохранить", self.save_current, "Ctrl+S")
        self.a_save_as = A("Сохранить как…", self.save_as, "Ctrl+Shift+S")
        self.a_save_all = A("Сохранить все", self.save_all)
        self.a_close = A("Закрыть вкладку", lambda: self.close_tab(self.tabs.currentIndex()), "Ctrl+W")
        self.a_quit = A("Выход", self.close, "Ctrl+Q")
        self.a_run = A("▶  Запустить", self.run_current, "F5", "Сохранить и запустить текущий .inp (F5)")
        self.a_run_folder = A("Запустить все .inp в папке", self.run_folder)
        self.a_stop = A("■  Остановить", self.stop_run, "Shift+F5", "Остановить расчёт и очистить очередь")
        self.a_open_out = A("Открыть .out", self.open_out_of_current, "F6", "Открыть лог для текущего .inp")
        self.a_molden = A("Открыть .molden внешней программой", self.open_molden_of_current, "F7")
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

        mb = self.menuBar()
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

        m = mb.addMenu("&Справка")
        m.addAction(self.a_keywords)
        m.addAction(self.a_about)

        tb = self.addToolBar("Основное")
        tb.setObjectName("main_toolbar")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonTextOnly)
        for a in (self.a_new_job, self.a_open, self.a_save, None, self.a_run, self.a_stop, None,
                  self.a_open_out, self.a_molden):
            tb.addSeparator() if a is None else tb.addAction(a)
        tb.addSeparator()
        tb.addWidget(QLabel(" Потоки: "))
        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(1, max(1, os.cpu_count() or 1))
        self.threads_spin.setValue(self.runner.threads)
        self.threads_spin.setToolTip("Число потоков для расчёта (больше 8 обычно не ускоряет)")
        self.threads_spin.valueChanged.connect(self._set_threads)
        tb.addWidget(self.threads_spin)

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
        for a in (self.a_find, self.a_goto, self.a_copy_all, self.a_close):
            a.setEnabled(t is not None)
        self.a_open_out.setEnabled(bool(t and t.path and t.kind == "inp"))
        has_molden = bool(t and t.path and os.path.exists(os.path.splitext(t.path)[0] + ".molden"))
        self.a_molden.setEnabled(has_molden)
        self.a_run.setEnabled(inp)

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
            self.results_dock.raise_()
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
        else:
            self.run_label.setText("Нет запущенных расчётов")
            self.run_label.setStyleSheet("")
        self.a_stop.setEnabled(self.runner.is_running() or bool(q))

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
            self.recent_menu.addAction(p, lambda p=p: self.open_path(p))
        if not self._recent():
            self.recent_menu.addAction("(пусто)").setEnabled(False)

    def _fill_recent(self):
        self.recent_list.clear()
        for p in self._recent():
            if os.path.exists(p):
                it = QListWidgetItem(os.path.basename(p) + "   —   " + os.path.dirname(p))
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
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("window_state", self.saveState())
        e.accept()


def main(argv=None):
    argv = sys.argv if argv is None else argv
    app = QApplication(argv)
    app.setApplicationName("ffpy-gui")
    app.setOrganizationName("ffpy")
    app.setWindowIcon(app_icon())
    w = MainWindow(files=[a for a in argv[1:] if not a.startswith("-")])
    w.show()
    if "--smoke-test" in argv:     # used by packaging/build.ps1 on the frozen build
        QTimer.singleShot(1500, app.quit)
    return app.exec()
