"""Batch processing view: table of jobs, counters, delta E comparison, export."""

from collections import Counter
import csv
import os
from typing import Dict, List, Optional

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ffpy.gui.i18n import tr
from ffpy.gui.theme import get_theme_bus, hex_color
from ffpy.job import build_job
from ffpy.outparse import parse_out
from ffpy.parser import parse_input


def _format_formula(symbols: List[str]) -> str:
    """Produce a standard Hill-like chemical formula string."""
    if not symbols:
        return "—"
    counts = Counter(symbols)
    # Hill system: C first, H second, then alphabetical
    order = []
    if "C" in counts:
        order.append("C")
    if "H" in counts:
        order.append("H")
    for s in sorted(counts.keys()):
        if s not in order:
            order.append(s)
    parts = []
    for s in order:
        c = counts[s]
        parts.append(f"{s}{c if c > 1 else ''}")
    return "".join(parts)


def parse_job_from_inp(path: str) -> Dict:
    """Parse .inp file to extract method, basis, formula, and title."""
    res = {
        "path": os.path.abspath(path),
        "name": os.path.basename(path),
        "method": "—",
        "basis": "—",
        "formula": "—",
        "title": "",
        "valid": False,
    }
    if not os.path.isfile(path):
        return res
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        deck = parse_input(text)
        job = build_job(deck)
        res["valid"] = True
        res["title"] = job.title or ""
        res["formula"] = _format_formula(job.symbols)
        if job.xc:
            res["method"] = job.dfttyp or "DFT"
        elif job.method == "MP2":
            res["method"] = "MP2"
        elif job.method == "CASSCF":
            res["method"] = "CASSCF"
        elif job.method in ("TDDFT", "TDHF"):
            res["method"] = job.method
        else:
            res["method"] = job.scftyp or "HF"
        res["basis"] = str(job.basis).upper()
    except Exception as e:
        res["error"] = str(e)
    return res


class StatusChip(QLabel):
    """Pill chip representing job execution status."""

    def __init__(self, status: str, text: str):
        super().__init__(text)
        self.setAlignment(Qt.AlignCenter)
        self.update_style(status)

    def update_style(self, status: str):
        if status == "done":
            bg = hex_color("okSoft")
            fg = hex_color("ok")
        elif status == "running":
            bg = hex_color("accentSoft")
            fg = hex_color("accent")
        elif status == "error":
            bg = hex_color("errSoft")
            fg = hex_color("err")
        else:  # idle / in queue
            bg = hex_color("chip")
            fg = hex_color("muted")

        self.setStyleSheet(f"""
            QLabel {{
                background-color: {bg};
                color: {fg};
                border-radius: 6px;
                padding: 3px 10px;
                font-size: 11px;
                font-weight: 600;
            }}
        """)


class BatchView(QWidget):
    """Batch calculation view with cards, table, delta E comparison, and export."""

    open_in_editor = Signal(str)
    open_in_3d = Signal(str)

    def __init__(self, parent=None, runner=None):
        super().__init__(parent)
        self.runner = runner
        self.items: List[Dict] = []
        self._row_by_path: Dict[str, int] = {}

        self.setAcceptDrops(True)
        self._build_ui()

        if self.runner is not None:
            self.runner.started.connect(self._on_runner_started)
            self.runner.finished.connect(self._on_runner_finished)

        get_theme_bus().theme_changed.connect(self._on_theme_changed)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(14)

        # 1. Top action bar
        bar = QHBoxLayout()
        bar.setSpacing(10)

        lbl_title = QLabel(tr("Пакет расчётов"))
        lbl_title.setStyleSheet("font-size: 15px; font-weight: 700;")
        bar.addWidget(lbl_title)

        self.lbl_subtitle = QLabel(tr("· 0 заданий"))
        self.lbl_subtitle.setStyleSheet(f"background: transparent; color: {hex_color('muted')}; font-size: 12px;")
        bar.addWidget(self.lbl_subtitle)

        bar.addStretch(1)

        # "Добавить .inp" button with dropdown menu
        self.btn_add = QToolButton()
        self.btn_add.setText(tr("Добавить .inp"))
        self.btn_add.setProperty("flat_btn", "true")
        self.btn_add.setPopupMode(QToolButton.InstantPopup)
        menu_add = QMenu(self.btn_add)
        act_files = menu_add.addAction(tr("Выбрать файлы .inp..."))
        act_files.triggered.connect(self._on_pick_files)
        act_folder = menu_add.addAction(tr("Выбрать папку с .inp..."))
        act_folder.triggered.connect(self._on_pick_folder)
        self.btn_add.setMenu(menu_add)
        bar.addWidget(self.btn_add)

        # "Экспорт таблицы" button with menu
        self.btn_export = QToolButton()
        self.btn_export.setText(tr("Экспорт таблицы"))
        self.btn_export.setProperty("flat_btn", "true")
        self.btn_export.setPopupMode(QToolButton.InstantPopup)
        menu_exp = QMenu(self.btn_export)
        act_csv = menu_exp.addAction(tr("Экспорт в CSV (.csv)..."))
        act_csv.triggered.connect(self._on_export_csv_dialog)
        act_docx = menu_exp.addAction(tr("Экспорт в Word (.docx)..."))
        act_docx.triggered.connect(self._on_export_docx_dialog)
        self.btn_export.setMenu(menu_exp)
        bar.addWidget(self.btn_export)

        self.btn_retry = QPushButton(tr("Повторить запуск"))
        self.btn_retry.setProperty("flat_btn", "true")
        self.btn_retry.setToolTip(tr("Повторить выполнение выбранных заданий"))
        self.btn_retry.clicked.connect(self.retry_selected)
        bar.addWidget(self.btn_retry)

        self.btn_remove = QPushButton(tr("Удалить"))
        self.btn_remove.setProperty("flat_btn", "true")
        self.btn_remove.setToolTip(tr("Удалить выбранные задания из пакета"))
        self.btn_remove.clicked.connect(self.remove_selected)
        bar.addWidget(self.btn_remove)

        self.btn_run_all = QPushButton(tr("Запустить всё"))
        self.btn_run_all.setObjectName("btn_run_all")
        self._apply_run_button_style()
        self.btn_run_all.clicked.connect(self.run_all)
        bar.addWidget(self.btn_run_all)

        root.addLayout(bar)

        # 2. Four counter cards
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(12)

        self.card_total = self._create_counter_card(tr("Всего"), "0", hex_color("text"))
        self.card_done = self._create_counter_card(tr("Готово"), "0", hex_color("ok"))
        self.card_running = self._create_counter_card(tr("В работе"), "0", hex_color("accent"))
        self.card_error = self._create_counter_card(tr("Ошибки"), "0", hex_color("err"))

        cards_layout.addWidget(self.card_total["frame"])
        cards_layout.addWidget(self.card_done["frame"])
        cards_layout.addWidget(self.card_running["frame"])
        cards_layout.addWidget(self.card_error["frame"])
        root.addLayout(cards_layout)

        # 3. Main table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([tr("ЗАДАНИЕ"), tr("МЕТОД"), tr("БАЗИС"), tr("ЭНЕРГИЯ, Eh"), tr("СТАТУС"), tr("ВРЕМЯ")])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.itemDoubleClicked.connect(self._on_table_double_clicked)
        self._apply_table_style()
        root.addWidget(self.table, 1)

        # 4. Delta E comparison block
        self.comp_card = QFrame()
        self.comp_card.setObjectName("batch_comp_card")
        self._apply_comp_card_style()
        comp_lay = QHBoxLayout(self.comp_card)
        comp_lay.setContentsMargins(20, 14, 20, 14)
        comp_lay.setSpacing(18)

        self.lbl_comp_title = QLabel(tr("Сравнение методов:"))
        self.lbl_comp_title.setStyleSheet("font-size: 13px; font-weight: 600;")
        comp_lay.addWidget(self.lbl_comp_title)

        self.lbl_comp_diffs = QLabel(tr("Выберите 2 или более завершённых расчёта для сравнения"))
        self.lbl_comp_diffs.setStyleSheet(f"background: transparent; color: {hex_color('muted')}; font-size: 12.5px;")
        comp_lay.addWidget(self.lbl_comp_diffs, 1)

        root.addWidget(self.comp_card)

    def minimumSizeHint(self):
        return QSize(200, 200)

    def _create_counter_card(self, title: str, init_val: str, val_color: str) -> Dict:
        card = QFrame()
        card.setObjectName("batch_counter_card")
        card.setStyleSheet(f"""
            QFrame#batch_counter_card {{
                background-color: {hex_color('surface')};
                border: 1px solid {hex_color('border')};
                border-radius: 12px;
                padding: 12px 16px;
            }}
        """)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(4)

        lbl_t = QLabel(title)
        lbl_t.setStyleSheet(f"background: transparent; color: {hex_color('muted')}; font-size: 12px; font-weight: 500;")
        lbl_v = QLabel(init_val)
        lbl_v.setStyleSheet(f"background: transparent; color: {val_color}; font-size: 26px; font-weight: 700;")

        lay.addWidget(lbl_t)
        lay.addWidget(lbl_v)
        return {"frame": card, "title_label": lbl_t, "val_label": lbl_v, "color": val_color}

    def _apply_run_button_style(self):
        self.btn_run_all.setStyleSheet(f"""
            QPushButton#btn_run_all {{
                background-color: {hex_color('accent')};
                color: {hex_color('onAccent')};
                font-weight: 600;
                font-size: 13px;
                border: none;
                border-radius: 8px;
                padding: 6px 16px;
                height: 20px;
            }}
            QPushButton#btn_run_all:hover {{
                background-color: {hex_color('accentText')};
            }}
            QPushButton#btn_run_all:disabled {{
                background-color: {hex_color('accentSoft')};
                color: {hex_color('muted')};
            }}
        """)

    def _apply_comp_card_style(self):
        self.comp_card.setStyleSheet(f"""
            QFrame#batch_comp_card {{
                background-color: {hex_color('surface')};
                border: 1px solid {hex_color('border')};
                border-radius: 14px;
            }}
        """)

    def _apply_table_style(self):
        p_surf = hex_color("surface")
        p_bord = hex_color("border")
        p_hover = hex_color("hover")
        p_text = hex_color("text")
        p_muted = hex_color("muted")

        self.table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {p_surf};
                border: 1px solid {p_bord};
                border-radius: 12px;
                gridline-color: transparent;
                selection-background-color: {hex_color('accentSoft')};
                selection-color: {p_text};
                outline: none;
            }}
            QHeaderView::section {{
                background-color: {p_surf};
                color: {p_muted};
                font-size: 11px;
                font-weight: 600;
                border: none;
                border-bottom: 1px solid {p_bord};
                padding: 10px 14px;
                text-align: left;
            }}
            QTableWidget::item {{
                border-bottom: 1px solid {p_bord};
                padding: 8px 12px;
                color: {p_text};
            }}
            QTableWidget::item:hover {{
                background-color: {p_hover};
            }}
        """)

    def _on_theme_changed(self):
        self._apply_run_button_style()
        self._apply_comp_card_style()
        self._apply_table_style()
        self.card_total["frame"].setStyleSheet(f"""
            QFrame#batch_counter_card {{
                background-color: {hex_color('surface')};
                border: 1px solid {hex_color('border')};
                border-radius: 12px;
            }}
        """)
        self.card_total["val_label"].setStyleSheet(f"background: transparent; color: {hex_color('text')}; font-size: 26px; font-weight: 700;")
        self.card_done["val_label"].setStyleSheet(f"background: transparent; color: {hex_color('ok')}; font-size: 26px; font-weight: 700;")
        self.card_running["val_label"].setStyleSheet(f"background: transparent; color: {hex_color('accent')}; font-size: 26px; font-weight: 700;")
        self.card_error["val_label"].setStyleSheet(f"background: transparent; color: {hex_color('err')}; font-size: 26px; font-weight: 700;")
        self.update_all_rows()
        self.update_comparison()

    # -------------------------------------------------------------------------
    # Drag and drop support
    # -------------------------------------------------------------------------
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = []
        for url in event.mimeData().urls():
            lp = url.toLocalFile()
            if os.path.isfile(lp) and lp.lower().endswith(".inp"):
                paths.append(lp)
            elif os.path.isdir(lp):
                self.add_folder(lp)
        if paths:
            self.add_files(paths)

    # -------------------------------------------------------------------------
    # Adding and managing jobs
    # -------------------------------------------------------------------------
    def item_count(self) -> int:
        return len(self.items)

    def get_item(self, index: int) -> Dict:
        return self.items[index]

    def add_files(self, paths: List[str]):
        new_items = []
        for p in paths:
            norm_p = os.path.abspath(p)
            if any(item["path"] == norm_p for item in self.items):
                continue
            item = parse_job_from_inp(norm_p)
            item["energy"] = None
            item["energy_str"] = "—"
            item["status"] = "idle"
            item["status_text"] = tr("В очереди")
            item["wall_time"] = None
            item["exit_code"] = None

            # Check if .out already exists
            out_p = os.path.splitext(norm_p)[0] + ".out"
            item["out_path"] = out_p
            if os.path.isfile(out_p):
                self._enrich_from_out(item, out_p)

            new_items.append(item)

        if not new_items:
            return

        for item in new_items:
            row = len(self.items)
            self.items.append(item)
            self._row_by_path[item["path"]] = row
            self.table.insertRow(row)
            self._fill_row(row, item)

        self.update_counters()
        self.update_comparison()

    def add_folder(self, folder_path: str):
        if not os.path.isdir(folder_path):
            return
        found = []
        for root_dir, _, files in os.walk(folder_path):
            for f in sorted(files):
                if f.lower().endswith(".inp"):
                    found.append(os.path.join(root_dir, f))
        if found:
            self.add_files(found)

    def _enrich_from_out(self, item: Dict, out_p: str):
        try:
            d = parse_out(out_p)
            item["wall_time"] = d.get("wall_time")
            if d.get("normal") and d.get("energy") is not None:
                item["energy"] = d["energy"]
                item["energy_str"] = f"{d['energy']:.6f}"
                item["status"] = "done"
                item["status_text"] = tr("Готово")
            elif d.get("exit_code") is not None:
                code = d["exit_code"]
                item["exit_code"] = code
                item["status"] = "error"
                item["status_text"] = tr("Ошибка {code}").format(code=code)
                item["energy_str"] = d.get("error") or tr("Ошибка")
        except Exception:
            pass

    def _fill_row(self, row: int, item: Dict):
        # 0: Name (bold)
        it_name = QTableWidgetItem(item["name"])
        f = it_name.font()
        f.setBold(True)
        it_name.setFont(f)
        it_name.setToolTip(item["path"])
        it_name.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        self.table.setItem(row, 0, it_name)

        # 1: Method
        it_m = QTableWidgetItem(item["method"])
        it_m.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        self.table.setItem(row, 1, it_m)

        # 2: Basis
        it_b = QTableWidgetItem(item["basis"])
        it_b.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        self.table.setItem(row, 2, it_b)

        # 3: Energy (mono)
        it_e = QTableWidgetItem(item["energy_str"])
        mono_f = QFont("JetBrains Mono")
        mono_f.setPointSize(11)
        it_e.setFont(mono_f)
        it_e.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        self.table.setItem(row, 3, it_e)

        # 4: Status chip
        chip = StatusChip(item["status"], item["status_text"])
        self.table.setCellWidget(row, 4, chip)

        # 5: Time (right aligned, muted)
        t_str = tr("{t:.1f} с").format(t=item["wall_time"]) if item["wall_time"] is not None else "—"
        it_t = QTableWidgetItem(t_str)
        it_t.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        it_t.setForeground(QColor(hex_color("muted")))
        it_t.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        self.table.setItem(row, 5, it_t)

    def update_all_rows(self):
        for r, item in enumerate(self.items):
            self._fill_row(r, item)

    def update_counters(self) -> Dict[str, int]:
        total = len(self.items)
        done = sum(1 for it in self.items if it["status"] == "done")
        running = sum(1 for it in self.items if it["status"] == "running")
        error = sum(1 for it in self.items if it["status"] == "error")

        self.card_total["val_label"].setText(str(total))
        self.card_done["val_label"].setText(str(done))
        self.card_running["val_label"].setText(str(running))
        self.card_error["val_label"].setText(str(error))

        self.lbl_subtitle.setText(tr("· {n} заданий").format(n=total))
        return {"total": total, "done": done, "running": running, "error": error}

    def get_counters(self) -> Dict[str, int]:
        return self.update_counters()

    # -------------------------------------------------------------------------
    # Runner signal callbacks
    # -------------------------------------------------------------------------
    def _on_runner_started(self, path: str):
        norm_p = os.path.abspath(path)
        for r, it in enumerate(self.items):
            if it["path"] == norm_p:
                it["status"] = "running"
                it["status_text"] = tr("Считается")
                it["energy_str"] = "…"
                self._fill_row(r, it)
                break
        self.update_counters()

    def _on_runner_finished(self, path: str, code: int):
        norm_p = os.path.abspath(path)
        for r, it in enumerate(self.items):
            if it["path"] == norm_p:
                out_p = it.get("out_path") or (os.path.splitext(norm_p)[0] + ".out")
                if code == 0 and os.path.isfile(out_p):
                    self._enrich_from_out(it, out_p)
                elif code == -1:
                    it["status"] = "idle"
                    it["status_text"] = tr("Остановлен")
                else:
                    it["exit_code"] = code
                    it["status"] = "error"
                    it["status_text"] = tr("Ошибка {code}").format(code=code)
                    if os.path.isfile(out_p):
                        self._enrich_from_out(it, out_p)
                    else:
                        it["energy_str"] = tr("Код {code}").format(code=code)
                self._fill_row(r, it)
                break
        self.update_counters()
        self.update_comparison()

    # -------------------------------------------------------------------------
    # UI actions (Run, Retry, Remove, Export)
    # -------------------------------------------------------------------------
    def run_all(self):
        if not self.runner:
            return
        paths_to_run = [it["path"] for it in self.items if it["status"] in ("idle", "error")]
        if not paths_to_run:
            paths_to_run = [it["path"] for it in self.items]
        if paths_to_run:
            self.runner.enqueue(paths_to_run)

    def retry_selected(self):
        selected_rows = sorted(set(idx.row() for idx in self.table.selectedIndexes()))
        if not selected_rows:
            return
        paths_to_retry = []
        for r in selected_rows:
            item = self.items[r]
            item["status"] = "idle"
            item["status_text"] = tr("В очереди")
            item["energy"] = None
            item["energy_str"] = "—"
            item["wall_time"] = None
            self._fill_row(r, item)
            paths_to_retry.append(item["path"])
        self.update_counters()
        if self.runner and paths_to_retry:
            self.runner.enqueue(paths_to_retry)

    def remove_selected(self):
        selected_rows = sorted(set(idx.row() for idx in self.table.selectedIndexes()), reverse=True)
        if not selected_rows:
            return
        for r in selected_rows:
            self.table.removeRow(r)
            del self.items[r]
        self._row_by_path.clear()
        for idx, it in enumerate(self.items):
            self._row_by_path[it["path"]] = idx
        self.update_counters()
        self.update_comparison()

    def _on_pick_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, tr("Добавить входные файлы .inp"), "", "Firefly input files (*.inp *.in);;All files (*)"
        )
        if paths:
            self.add_files(paths)

    def _on_pick_folder(self):
        folder = QFileDialog.getExistingDirectory(self, tr("Выбрать папку с файлами .inp"))
        if folder:
            self.add_folder(folder)

    def _on_export_csv_dialog(self):
        dest, _ = QFileDialog.getSaveFileName(
            self, tr("Экспорт таблицы пакета в CSV"), "batch_results.csv", "CSV files (*.csv)"
        )
        if dest:
            self.export_csv(dest)

    def _on_export_docx_dialog(self):
        dest, _ = QFileDialog.getSaveFileName(
            self, tr("Экспорт таблицы пакета в Word"), "batch_results.docx", "Word documents (*.docx)"
        )
        if dest:
            self.export_docx(dest)

    def export_csv(self, file_path: str):
        with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow([tr("ЗАДАНИЕ"), tr("МЕТОД"), tr("БАЗИС"), tr("ЭНЕРГИЯ (Eh)"), tr("СТАТУС"), tr("ВРЕМЯ (с)"), tr("ПУТЬ")])
            for it in self.items:
                e_val = f"{it['energy']:.8f}" if it["energy"] is not None else it["energy_str"]
                t_val = f"{it['wall_time']:.1f}" if it["wall_time"] is not None else "—"
                writer.writerow([it["name"], it["method"], it["basis"], e_val, it["status_text"], t_val, it["path"]])

    def export_docx(self, file_path: str):
        try:
            import docx
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            from docx.shared import Inches, Pt, RGBColor
        except ImportError:
            QMessageBox.warning(
                self, tr("Экспорт в .docx"), tr("Библиотека python-docx не найдена. Установите её: pip install python-docx")
            )
            return

        doc = docx.Document()
        title_p = doc.add_paragraph()
        r = title_p.add_run(tr("Сводная таблица пакета расчётов ffpy"))
        r.font.size = Pt(16)
        r.font.bold = True

        cnt = self.get_counters()
        stat_p = doc.add_paragraph()
        stat_p.add_run(tr("Всего заданий: {total}  |  Готово: {done}  |  В работе: {running}  |  Ошибки: {error}").format(**cnt))

        tbl = doc.add_table(rows=1, cols=6)
        tbl.style = "Table Grid"
        hdr_cells = tbl.rows[0].cells
        hdr_titles = [tr("ЗАДАНИЕ"), tr("МЕТОД"), tr("БАЗИС"), tr("ЭНЕРГИЯ, Eh"), tr("СТАТУС"), tr("ВРЕМЯ")]
        for i, t in enumerate(hdr_titles):
            hdr_cells[i].text = t
            for p in hdr_cells[i].paragraphs:
                for run in p.runs:
                    run.font.bold = True

        for it in self.items:
            row_cells = tbl.add_row().cells
            row_cells[0].text = it["name"]
            row_cells[1].text = it["method"]
            row_cells[2].text = it["basis"]
            e_str = f"{it['energy']:.8f}" if it["energy"] is not None else it["energy_str"]
            row_cells[3].text = e_str
            row_cells[4].text = it["status_text"]
            t_str = tr("{t:.1f} с").format(t=it["wall_time"]) if it["wall_time"] is not None else "—"
            row_cells[5].text = t_str

        # Add delta E block if comparison available
        comp = self.compute_comparison()
        if comp and comp.get("diffs"):
            doc.add_paragraph()
            cp = doc.add_paragraph()
            cr = cp.add_run(tr("Сравнение: {m}").format(m=", ".join(comp["methods"])))
            cr.font.bold = True
            for d in comp["diffs"]:
                dp = doc.add_paragraph(
                    tr("ΔE ({m} − {r}) = {eh:+.6f} Eh  ({kc:+.2f} ккал/моль)").format(
                        m=d["method"], r=comp["ref_method"], eh=d["delta_eh"], kc=d["delta_kcal"])
                )
                dp.paragraph_format.left_indent = Inches(0.2)

        doc.save(file_path)

    # -------------------------------------------------------------------------
    # Delta E comparison logic
    # -------------------------------------------------------------------------
    def compute_comparison(self, row_indices: Optional[List[int]] = None) -> Optional[Dict]:
        """Compute delta E between selected or group calculations in Eh and kcal/mol."""
        candidates = []
        if row_indices is not None:
            candidates = [self.items[i] for i in row_indices if i < len(self.items)]
        else:
            selected_rows = sorted(set(idx.row() for idx in self.table.selectedIndexes()))
            if len(selected_rows) >= 2:
                candidates = [self.items[r] for r in selected_rows]
            else:
                # Automatic: find first formula group with >= 2 done calculations
                formula_groups: Dict[str, List[Dict]] = {}
                for it in self.items:
                    if it["status"] == "done" and it["energy"] is not None:
                        formula_groups.setdefault(it["formula"], []).append(it)
                for f, grp in formula_groups.items():
                    if len(grp) >= 2:
                        candidates = grp
                        break

        done_candidates = [it for it in candidates if it["energy"] is not None]
        if len(done_candidates) < 2:
            return None

        # Reference job: choose RHF/HF if present, otherwise first
        ref_job = done_candidates[0]
        for it in done_candidates:
            if it["method"] in ("RHF", "HF"):
                ref_job = it
                break

        ref_e = ref_job["energy"]
        ref_m = ref_job["method"]
        methods = [ref_m]
        diffs = []

        for it in done_candidates:
            if it is ref_job:
                continue
            methods.append(it["method"])
            delta_eh = it["energy"] - ref_e
            delta_kcal = delta_eh * 627.5095
            diffs.append({
                "method": it["method"],
                "delta_eh": delta_eh,
                "delta_kcal": delta_kcal,
            })

        return {
            "ref_method": ref_m,
            "ref_energy": ref_e,
            "methods": methods,
            "diffs": diffs,
        }

    def update_comparison(self):
        comp = self.compute_comparison()
        if not comp or not comp["diffs"]:
            self.lbl_comp_title.setText(tr("Сравнение методов:"))
            self.lbl_comp_diffs.setText(tr("Выберите 2 или более завершённых расчёта для сравнения"))
            return

        methods_str = ", ".join(comp["methods"])
        self.lbl_comp_title.setText(tr("Сравнение: {m}").format(m=methods_str))

        parts = []
        for d in comp["diffs"]:
            sign_eh = f"{d['delta_eh']:+.6f}"
            sign_kcal = f"{d['delta_kcal']:+.2f}"
            parts.append(
                tr("ΔE ({m} − {r}) = <b style='color:{c1}'>{eh} Eh</b> <span style='color:{c2}'>({kc} ккал/моль)</span>").format(
                    m=d["method"], r=comp["ref_method"], c1=hex_color("text"), eh=sign_eh,
                    c2=hex_color("muted"), kc=sign_kcal)
            )

        self.lbl_comp_diffs.setText("&nbsp;&nbsp;·&nbsp;&nbsp;".join(parts))

    def _on_selection_changed(self):
        self.update_comparison()

    def _on_table_double_clicked(self, item: QTableWidgetItem):
        row = item.row()
        if row < len(self.items):
            it = self.items[row]
            if it["status"] == "done" and os.path.isfile(it["out_path"]):
                self.open_in_3d.emit(it["out_path"])
            else:
                self.open_in_editor.emit(it["path"])
