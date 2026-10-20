"""Text editor widgets: code editor with line numbers, find/replace bar,
and FileTab, one open file (editable .inp or read-only log)."""

import os

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import (QAction, QFont, QFontDatabase, QKeySequence, QPainter,
                           QTextCursor, QTextDocument, QTextFormat)
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog, QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QTextEdit,
                               QToolButton, QVBoxLayout, QWidget)

from ffpy.gui.highlight import InpHighlighter, OutHighlighter
from ffpy.gui.theme import color

EDITABLE = {".inp", ".txt", ""}
LOG_LIKE = {".out", ".log"}


def editor_font(size=10):
    f = QFontDatabase.systemFont(QFontDatabase.FixedFont)
    for family in ("Cascadia Mono", "Consolas", "Courier New"):
        if family in QFontDatabase.families():
            f = QFont(family)
            break
    f.setPointSize(size)
    f.setStyleHint(QFont.Monospace)
    return f


class _Gutter(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.gutter_width(), 0)

    def paintEvent(self, event):
        self.editor.paint_gutter(event)


class CodeEditor(QPlainTextEdit):
    """QPlainTextEdit with line numbers, current-line and error-line marks."""

    def __init__(self, parent=None, read_only=False):
        super().__init__(parent)
        self._gutter = _Gutter(self)
        self._error_line = None
        self._find_selections = []
        self.setReadOnly(read_only)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setFont(editor_font())
        self.blockCountChanged.connect(self._update_gutter_width)
        self.updateRequest.connect(self._update_gutter)
        self.cursorPositionChanged.connect(self._refresh_selections)
        self._update_gutter_width()
        self._refresh_selections()

    def set_font_size(self, size):
        self.setFont(editor_font(size))
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))
        self._update_gutter_width()

    # line numbers
    def gutter_width(self):
        digits = max(3, len(str(self.blockCount())))
        return 12 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_gutter_width(self, *_):
        self.setViewportMargins(self.gutter_width(), 0, 0, 0)

    def _update_gutter(self, rect, dy):
        if dy:
            self._gutter.scroll(0, dy)
        else:
            self._gutter.update(0, rect.y(), self._gutter.width(), rect.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._gutter.setGeometry(QRect(cr.left(), cr.top(), self.gutter_width(), cr.height()))

    def paint_gutter(self, event):
        p = QPainter(self._gutter)
        p.fillRect(event.rect(), color("gutter"))
        block = self.firstVisibleBlock()
        num = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        cur = self.textCursor().blockNumber()
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                if self._error_line is not None and num + 1 == self._error_line:
                    p.setPen(color("error"))
                elif num == cur:
                    p.setPen(self.palette().text().color())
                else:
                    p.setPen(color("line_number"))
                p.drawText(0, top, self._gutter.width() - 6, self.fontMetrics().height(),
                           Qt.AlignRight, str(num + 1))
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            num += 1

    # extra selections
    def set_error_line(self, line):
        self._error_line = line
        self._refresh_selections()
        self._gutter.update()

    def set_find_selections(self, cursors):
        self._find_selections = cursors
        self._refresh_selections()

    def _refresh_selections(self):
        sels = []
        if self._error_line is not None:
            block = self.document().findBlockByNumber(self._error_line - 1)
            if block.isValid():
                s = QTextEdit.ExtraSelection()
                s.format.setBackground(color("error_line"))
                s.format.setProperty(QTextFormat.FullWidthSelection, True)
                s.cursor = QTextCursor(block)
                sels.append(s)
        if not self.isReadOnly() or self.hasFocus():
            s = QTextEdit.ExtraSelection()
            s.format.setBackground(color("current_line"))
            s.format.setProperty(QTextFormat.FullWidthSelection, True)
            s.cursor = self.textCursor()
            s.cursor.clearSelection()
            if not sels or sels[0].cursor.blockNumber() != s.cursor.blockNumber():
                sels.insert(0, s)
        for c in self._find_selections:
            s = QTextEdit.ExtraSelection()
            s.format.setBackground(color("find"))
            s.cursor = c
            sels.append(s)
        self.setExtraSelections(sels)

    def goto_line(self, line):
        block = self.document().findBlockByNumber(max(0, line - 1))
        cur = QTextCursor(block)
        self.setTextCursor(cur)
        self.centerCursor()
        self.setFocus()

    # editing helpers
    def toggle_comment(self):
        if self.isReadOnly():
            return
        cur = self.textCursor()
        doc = self.document()
        start = doc.findBlock(cur.selectionStart()).blockNumber()
        end = doc.findBlock(cur.selectionEnd()).blockNumber()
        if cur.hasSelection() and doc.findBlock(cur.selectionEnd()).position() == cur.selectionEnd() and end > start:
            end -= 1
        blocks = [doc.findBlockByNumber(i) for i in range(start, end + 1)]
        uncomment = all(b.text().lstrip().startswith("!") or not b.text().strip() for b in blocks)
        edit = QTextCursor(doc)
        edit.beginEditBlock()
        for b in blocks:
            t = b.text()
            if uncomment:
                i = t.find("!")
                if i >= 0:
                    edit.setPosition(b.position() + i)
                    n = 2 if t[i + 1:i + 2] == " " else 1
                    edit.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, n)
                    edit.removeSelectedText()
            elif t.strip():
                edit.setPosition(b.position())
                edit.insertText("! ")
        edit.endEditBlock()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Tab and not self.isReadOnly() and not event.modifiers():
            self.insertPlainText("    ")
            return
        super().keyPressEvent(event)

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self._refresh_selections()

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self._refresh_selections()


class FindBar(QWidget):
    """Ctrl+F / Ctrl+H bar under the editor."""

    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(4)
        row1 = QHBoxLayout()
        self.find_edit = QLineEdit()
        self.find_edit.setPlaceholderText("Найти…")
        self.find_edit.setClearButtonEnabled(True)
        self.case = QCheckBox("Aa")
        self.case.setToolTip("Учитывать регистр")
        self.count = QLabel("")
        prev_b, next_b, close_b = QToolButton(), QToolButton(), QToolButton()
        prev_b.setText("↑")
        prev_b.setToolTip("Предыдущее (Shift+Enter)")
        next_b.setText("↓")
        next_b.setToolTip("Следующее (Enter)")
        close_b.setText("✕")
        close_b.setToolTip("Закрыть (Esc)")
        prev_b.clicked.connect(lambda: self.find(backward=True))
        next_b.clicked.connect(lambda: self.find())
        close_b.clicked.connect(self.close_bar)
        for w in (self.find_edit, self.case, prev_b, next_b, self.count, close_b):
            row1.addWidget(w)
        row1.setStretch(0, 1)
        lay.addLayout(row1)
        self.replace_row = QWidget()
        row2 = QHBoxLayout(self.replace_row)
        row2.setContentsMargins(0, 0, 0, 0)
        self.replace_edit = QLineEdit()
        self.replace_edit.setPlaceholderText("Заменить на…")
        rep, rep_all = QToolButton(), QToolButton()
        rep.setText("Заменить")
        rep_all.setText("Заменить все")
        rep.clicked.connect(self.replace_one)
        rep_all.clicked.connect(self.replace_all)
        row2.addWidget(self.replace_edit, 1)
        row2.addWidget(rep)
        row2.addWidget(rep_all)
        lay.addWidget(self.replace_row)
        self.find_edit.textChanged.connect(self._mark_all)
        self.find_edit.returnPressed.connect(self._enter)
        self.case.toggled.connect(self._mark_all)
        self.hide()

    def open(self, replace=False):
        replace = replace and not self.editor.isReadOnly()
        self.replace_row.setVisible(replace)
        sel = self.editor.textCursor().selectedText()
        if sel and " " not in sel:
            self.find_edit.setText(sel)
        self.show()
        self.find_edit.setFocus()
        self.find_edit.selectAll()
        self._mark_all()

    def close_bar(self):
        self.hide()
        self.editor.set_find_selections([])
        self.editor.setFocus()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.close_bar()
            return
        super().keyPressEvent(e)

    def _enter(self):
        mods = QApplication.keyboardModifiers()
        self.find(backward=bool(mods & Qt.ShiftModifier))

    def _flags(self, backward=False):
        f = QTextDocument.FindFlag(0)
        if backward:
            f |= QTextDocument.FindBackward
        if self.case.isChecked():
            f |= QTextDocument.FindCaseSensitively
        return f

    def find(self, backward=False):
        text = self.find_edit.text()
        if not text:
            return False
        if self.editor.find(text, self._flags(backward)):
            return True
        cur = self.editor.textCursor()
        cur.movePosition(QTextCursor.End if backward else QTextCursor.Start)
        self.editor.setTextCursor(cur)
        return self.editor.find(text, self._flags(backward))

    def _mark_all(self, *_):
        text = self.find_edit.text()
        doc = self.editor.document()
        found = []
        if text:
            c = doc.find(text, 0, self._flags())
            while not c.isNull() and len(found) < 5000:
                found.append(c)
                c = doc.find(text, c, self._flags())
        self.editor.set_find_selections(found)
        self.count.setText("%d совп." % len(found) if text else "")

    def replace_one(self):
        cur = self.editor.textCursor()
        text = self.find_edit.text()
        same = (cur.selectedText() == text) if self.case.isChecked() else \
            (cur.selectedText().lower() == text.lower())
        if cur.hasSelection() and same:
            cur.insertText(self.replace_edit.text())
        self.find()
        self._mark_all()

    def replace_all(self):
        text = self.find_edit.text()
        if not text:
            return
        doc = self.editor.document()
        edit = QTextCursor(doc)
        edit.beginEditBlock()
        n = 0
        c = doc.find(text, 0, self._flags())
        while not c.isNull():
            c.insertText(self.replace_edit.text())
            n += 1
            c = doc.find(text, c, self._flags())
        edit.endEditBlock()
        self._mark_all()
        self.count.setText("заменено: %d" % n)


def section_headers(text):
    """(line number, title) of '----/TITLE/----' sections in an ffpy .out."""
    lines = text.splitlines()
    out = []
    for i in range(1, len(lines) - 1):
        a, t, b = lines[i - 1].strip(), lines[i].strip(), lines[i + 1].strip()
        if a and set(a) == {"-"} and b and set(b) == {"-"} and t:
            out.append((i + 1, t))
    return out


class FileTab(QWidget):
    """One open document. .inp files are editable; .out/.log/.dat/.xyz/.molden
    open read-only with copy/save-copy/outline tools."""

    modified_changed = Signal(bool)
    text_changed = Signal()

    def __init__(self, path=None, read_only=None, font_size=10):
        super().__init__()
        self.path = path
        ext = os.path.splitext(path)[1].lower() if path else ".inp"
        self.kind = "inp" if ext == ".inp" or path is None else ("out" if ext in LOG_LIKE else "text")
        if read_only is None:
            read_only = ext not in EDITABLE
        self.read_only = read_only
        self._mtime = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.editor = CodeEditor(read_only=read_only)
        self.editor.set_font_size(font_size)
        if self.kind == "inp":
            self.highlighter = InpHighlighter(self.editor.document())
        elif self.kind == "out":
            self.highlighter = OutHighlighter(self.editor.document())
        else:
            self.highlighter = None
        if read_only:
            lay.addWidget(self._make_toolbar())
        lay.addWidget(self.editor, 1)
        self.findbar = FindBar(self.editor)
        lay.addWidget(self.findbar)
        self.editor.document().modificationChanged.connect(self.modified_changed)
        self.editor.textChanged.connect(self.text_changed)
        if path:
            self.load()

    def _make_toolbar(self):
        bar = QWidget()
        h = QHBoxLayout(bar)
        h.setContentsMargins(6, 3, 6, 3)
        copy_b = QToolButton()
        copy_b.setText("Копировать всё")
        copy_b.setToolTip("Скопировать весь текст файла в буфер обмена (Ctrl+Shift+C)")
        copy_b.clicked.connect(self.copy_all)
        save_b = QToolButton()
        save_b.setText("Сохранить копию…")
        save_b.setToolTip("Сохранить копию файла в другое место")
        save_b.clicked.connect(self.save_copy)
        reload_b = QToolButton()
        reload_b.setText("Обновить")
        reload_b.clicked.connect(self.load)
        self.outline = QComboBox()
        self.outline.setMinimumWidth(260)
        self.outline.setToolTip("Перейти к разделу лога")
        self.outline.activated.connect(self._goto_section)
        self.info = QLabel("")
        for w in (copy_b, save_b, reload_b):
            h.addWidget(w)
        h.addSpacing(12)
        h.addWidget(QLabel("Раздел:"))
        h.addWidget(self.outline)
        h.addStretch(1)
        h.addWidget(self.info)
        act = QAction(self)
        act.setShortcut(QKeySequence("Ctrl+Shift+C"))
        act.triggered.connect(self.copy_all)
        self.addAction(act)
        return bar

    # file I/O
    def title(self):
        name = os.path.basename(self.path) if self.path else "Без имени.inp"
        return name + (" •" if self.is_modified() else "")

    def is_modified(self):
        return (not self.read_only) and self.editor.document().isModified()

    def load(self):
        if not self.path:
            return
        with open(self.path, "rb") as f:
            raw = f.read()
        for enc in ("utf-8-sig", "cp1251", "latin-1"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        bar = self.editor.verticalScrollBar()
        at_end = bar.value() >= bar.maximum() - 2
        pos = bar.value()
        self.editor.setPlainText(text)
        self.editor.document().setModified(False)
        if self.read_only:
            if at_end and self.kind == "out" and pos > 0:
                bar.setValue(bar.maximum())
            else:
                bar.setValue(min(pos, bar.maximum()))
            self._fill_outline(text)
            self.info.setText("%d строк, %.1f КБ" % (text.count("\n") + 1, len(raw) / 1024))
        self._mtime = os.path.getmtime(self.path)

    def changed_on_disk(self):
        return self.path and os.path.exists(self.path) and self._mtime is not None and \
            os.path.getmtime(self.path) != self._mtime

    def save(self, path=None):
        path = path or self.path
        text = self.editor.toPlainText()
        if not text.endswith("\n"):
            text += "\n"
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        self.path = path
        self.editor.document().setModified(False)
        self._mtime = os.path.getmtime(path)

    def copy_all(self):
        QApplication.clipboard().setText(self.editor.toPlainText())
        w = self.window()
        if hasattr(w, "statusBar"):
            w.statusBar().showMessage("Текст «%s» скопирован в буфер обмена"
                                      % os.path.basename(self.path or ""), 4000)

    def save_copy(self):
        if not self.path:
            return
        dest, _ = QFileDialog.getSaveFileName(self, "Сохранить копию", os.path.basename(self.path))
        if dest:
            import shutil
            try:
                shutil.copy2(self.path, dest)
            except OSError as e:
                QMessageBox.warning(self, "ffpy", "Не удалось скопировать файл:\n%s" % e)

    def _fill_outline(self, text):
        self.outline.clear()
        self._sections = section_headers(text) if self.kind == "out" else []
        self.outline.addItem("— в начало —", 1)
        for line, title in self._sections:
            self.outline.addItem(title.title(), line)
        if self.kind == "out":
            self.outline.addItem("— в конец —", -1)

    def _goto_section(self, idx):
        line = self.outline.itemData(idx)
        if line == -1:
            self.editor.goto_line(self.editor.blockCount())
        elif line:
            self.editor.goto_line(line)
