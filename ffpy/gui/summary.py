"""Summary view: history of completed calculations and detailed results card."""

import html
import os
from typing import Dict, List, Optional

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ffpy.gui.i18n import tr
from ffpy.errors import EXIT_CODES
from ffpy.gui.theme import get_theme_bus, hex_color
from ffpy.outparse import parse_out


def _open_external(path: str):
    return QDesktopServices.openUrl(QUrl.fromLocalFile(path))


class SummaryView(QWidget):
    """Full-featured Summary view with job history list and styled results cards."""

    open_in_3d = Signal(str)
    open_in_editor = Signal(str)

    def __init__(self, parent=None, runner=None):
        super().__init__(parent)
        self.runner = runner
        self.out_files: List[str] = []
        self.current_path: Optional[str] = None
        self.current_data: Optional[Dict] = None

        self._build_ui()

        if self.runner is not None:
            self.runner.finished.connect(self._on_runner_finished)

        get_theme_bus().theme_changed.connect(self._on_theme_changed)

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(14)

        splitter = QSplitter(Qt.Horizontal, self)
        splitter.setHandleWidth(8)

        # ---------------------------------------------------------------------
        # Left side: list of completed runs
        # ---------------------------------------------------------------------
        left_panel = QWidget()
        left_lay = QVBoxLayout(left_panel)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(10)

        left_hdr = QHBoxLayout()
        lbl_history = QLabel(tr("Завершённые расчёты"))
        lbl_history.setStyleSheet("font-size: 14px; font-weight: 700;")
        left_hdr.addWidget(lbl_history)
        left_hdr.addStretch(1)

        btn_add = QPushButton(tr("Открыть .out"))
        btn_add.setProperty("flat_btn", "true")
        btn_add.clicked.connect(self._on_browse_out)
        left_hdr.addWidget(btn_add)
        left_lay.addLayout(left_hdr)

        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self._on_item_selected)
        self._apply_list_style()
        left_lay.addWidget(self.list_widget, 1)

        splitter.addWidget(left_panel)

        # ---------------------------------------------------------------------
        # Right side: detailed card (Results styled)
        # ---------------------------------------------------------------------
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.NoFrame)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.detail_widget = QWidget()
        self.detail_lay = QVBoxLayout(self.detail_widget)
        self.detail_lay.setContentsMargins(10, 0, 10, 10)
        self.detail_lay.setSpacing(12)

        # 1. Energy and status card
        self.card_energy = QFrame()
        self.card_energy.setObjectName("summary_card_energy")
        self._apply_card_style(self.card_energy)
        ce_lay = QVBoxLayout(self.card_energy)
        ce_lay.setContentsMargins(20, 18, 20, 18)
        ce_lay.setSpacing(8)

        self.lbl_file_title = QLabel(tr("Выберите расчёт из списка"))
        self.lbl_file_title.setStyleSheet(f"color: {hex_color('muted')}; font-size: 13px; font-weight: 500;")
        ce_lay.addWidget(self.lbl_file_title)

        lbl_e_sub = QLabel(tr("Полная энергия, Eh"))
        lbl_e_sub.setStyleSheet(f"color: {hex_color('muted')}; font-size: 12px;")
        ce_lay.addWidget(lbl_e_sub)

        self.lbl_energy_val = QLabel("—")
        mono_f = QFont("JetBrains Mono")
        mono_f.setPointSize(22)
        mono_f.setBold(True)
        self.lbl_energy_val.setFont(mono_f)
        ce_lay.addWidget(self.lbl_energy_val)

        # Chips row
        self.chips_lay = QHBoxLayout()
        self.chips_lay.setSpacing(8)
        self.chips_lay.addStretch(1)
        ce_lay.addLayout(self.chips_lay)

        self.detail_lay.addWidget(self.card_energy)

        # 2. Geometry & properties card
        self.card_geom = QFrame()
        self.card_geom.setObjectName("summary_card_geom")
        self._apply_card_style(self.card_geom)
        cg_lay = QVBoxLayout(self.card_geom)
        cg_lay.setContentsMargins(20, 16, 20, 16)
        cg_lay.setSpacing(10)

        lbl_geom_hdr = QLabel(tr("Геометрия и свойства"))
        lbl_geom_hdr.setStyleSheet("font-size: 13px; font-weight: 600;")
        cg_lay.addWidget(lbl_geom_hdr)

        self.grid_geom = QGridLayout()
        self.grid_geom.setSpacing(8)
        cg_lay.addLayout(self.grid_geom)

        self.detail_lay.addWidget(self.card_geom)

        # 3. Parameters card
        self.card_params = QFrame()
        self.card_params.setObjectName("summary_card_params")
        self._apply_card_style(self.card_params)
        cp_lay = QVBoxLayout(self.card_params)
        cp_lay.setContentsMargins(20, 16, 20, 16)
        cp_lay.setSpacing(10)

        lbl_par_hdr = QLabel(tr("Параметры расчёта"))
        lbl_par_hdr.setStyleSheet("font-size: 13px; font-weight: 600;")
        cp_lay.addWidget(lbl_par_hdr)

        self.grid_params = QGridLayout()
        self.grid_params.setSpacing(8)
        cp_lay.addLayout(self.grid_params)

        self.detail_lay.addWidget(self.card_params)

        # 4. Action buttons
        act_grid = QGridLayout()
        act_grid.setSpacing(10)

        self.b_3d = QPushButton(tr("Открыть в 3D"))
        self.b_3d.setProperty("flat_btn", "true")
        self.b_3d.clicked.connect(self._on_open_in_3d)

        self.b_copy = QPushButton(tr("Копировать энергию"))
        self.b_copy.setProperty("flat_btn", "true")
        self.b_copy.clicked.connect(self._copy_energy)

        self.b_docx = QPushButton(tr("Отчёт .docx"))
        self.b_docx.setProperty("flat_btn", "true")
        self.b_docx.clicked.connect(self._export_docx)

        self.b_molden = QPushButton(tr("Открыть .molden"))
        self.b_molden.setProperty("flat_btn", "true")
        self.b_molden.clicked.connect(self._open_molden)

        self.b_folder = QPushButton(tr("Папка"))
        self.b_folder.setProperty("flat_btn", "true")
        self.b_folder.clicked.connect(self._open_folder)

        act_grid.addWidget(self.b_3d, 0, 0)
        act_grid.addWidget(self.b_copy, 0, 1)
        act_grid.addWidget(self.b_docx, 1, 0)
        act_grid.addWidget(self.b_molden, 1, 1)
        act_grid.addWidget(self.b_folder, 2, 0, 1, 2)

        self.detail_lay.addLayout(act_grid)
        self.detail_lay.addStretch(1)

        right_scroll.setWidget(self.detail_widget)
        splitter.addWidget(right_scroll)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([380, 720])
        root.addWidget(splitter)

        self._set_buttons_enabled(False)

    def minimumSizeHint(self):
        return QSize(200, 200)

    def _apply_card_style(self, frame: QFrame):
        frame.setStyleSheet(f"""
            QFrame#{frame.objectName()} {{
                background-color: {hex_color('surface')};
                border: 1px solid {hex_color('border')};
                border-radius: 14px;
            }}
        """)

    def _apply_list_style(self):
        p_surf = hex_color("surface")
        p_bord = hex_color("border")
        p_hover = hex_color("hover")
        p_text = hex_color("text")

        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                background-color: {p_surf};
                border: 1px solid {p_bord};
                border-radius: 12px;
                padding: 6px;
                color: {p_text};
                outline: none;
            }}
            QListWidget::item {{
                padding: 10px 12px;
                border-radius: 8px;
                margin-bottom: 4px;
            }}
            QListWidget::item:hover {{
                background-color: {p_hover};
            }}
            QListWidget::item:selected {{
                background-color: {hex_color('accentSoft')};
                color: {hex_color('text')};
            }}
        """)

    def _on_theme_changed(self):
        self._apply_list_style()
        self._apply_card_style(self.card_energy)
        self._apply_card_style(self.card_geom)
        self._apply_card_style(self.card_params)
        if self.current_path:
            self._render_current_data()

    def _set_buttons_enabled(self, enabled: bool):
        self.b_3d.setEnabled(enabled)
        self.b_copy.setEnabled(enabled and self.current_data is not None and self.current_data.get("energy") is not None)
        self.b_docx.setEnabled(enabled)
        stem = os.path.splitext(self.current_path or "")[0]
        self.b_molden.setEnabled(enabled and os.path.isfile(stem + ".molden"))
        self.b_folder.setEnabled(enabled)

    # -------------------------------------------------------------------------
    # Public interface
    # -------------------------------------------------------------------------
    def item_count(self) -> int:
        return len(self.out_files)

    def add_out_file(self, path: str):
        norm_p = os.path.abspath(path)
        if norm_p not in self.out_files and os.path.isfile(norm_p):
            self.out_files.append(norm_p)
            self._add_list_item(norm_p)
            if self.list_widget.count() == 1:
                self.list_widget.setCurrentRow(0)

    def select_item(self, index: int):
        if 0 <= index < self.list_widget.count():
            self.list_widget.setCurrentRow(index)

    def get_selected_info(self) -> Optional[Dict]:
        return self.current_data

    def set_out(self, path: str):
        self.add_out_file(path)
        for r in range(self.list_widget.count()):
            if self.out_files[r] == os.path.abspath(path):
                self.list_widget.setCurrentRow(r)
                break

    def refresh_sources(self):
        """Scan parent/window for opened tabs and batch items with .out files."""
        parent = self.parent()
        while parent and not hasattr(parent, "tabs"):
            parent = parent.parent()
        if not parent:
            return

        # 1. From open editor tabs
        if hasattr(parent, "tabs"):
            for i in range(parent.tabs.count()):
                tab = parent.tabs.widget(i)
                if hasattr(tab, "path") and tab.path:
                    stem = os.path.splitext(tab.path)[0]
                    out_candidate = stem + ".out"
                    if os.path.isfile(out_candidate):
                        self.add_out_file(out_candidate)

        # 2. From batch view
        if hasattr(parent, "batch_view") and hasattr(parent.batch_view, "items"):
            for it in parent.batch_view.items:
                if it.get("out_path") and os.path.isfile(it["out_path"]):
                    self.add_out_file(it["out_path"])

    # -------------------------------------------------------------------------
    # List & details rendering
    # -------------------------------------------------------------------------
    def _add_list_item(self, path: str):
        name = os.path.basename(path)
        try:
            d = parse_out(path)
            method = d.get("method") or "—"
            basis = d.get("basis") or "—"
            normal = d.get("normal", False)
            e_val = f"{d['energy']:.6f} Eh" if d.get("energy") is not None else "—"
            stat_icon = "✔" if normal else "✖"
            text = f"{stat_icon} {name}\n   {method} / {basis}  ·  {e_val}"
        except Exception:
            text = f"• {name}"

        item = QListWidgetItem(text)
        item.setToolTip(path)
        self.list_widget.addItem(item)

    def _on_item_selected(self, row: int):
        if 0 <= row < len(self.out_files):
            self.current_path = self.out_files[row]
            try:
                self.current_data = parse_out(self.current_path)
            except Exception:
                self.current_data = None
            self._render_current_data()
            self._set_buttons_enabled(True)
        else:
            self.current_path = None
            self.current_data = None
            self._render_empty()
            self._set_buttons_enabled(False)

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

    def _render_empty(self):
        self.lbl_file_title.setText(tr("Выберите расчёт из списка"))
        self.lbl_energy_val.setText("—")
        self._clear_layout(self.chips_lay)
        self._clear_layout(self.grid_geom)
        self._clear_layout(self.grid_params)

    def _render_current_data(self):
        if not self.current_data or not self.current_path:
            self._render_empty()
            return

        d = self.current_data
        name = os.path.basename(self.current_path)
        self.lbl_file_title.setText(name)

        if d.get("energy") is not None:
            self.lbl_energy_val.setText(f"{d['energy']:.10f}")
            self.lbl_energy_val.setStyleSheet(f"color: {hex_color('text')};")
        else:
            self.lbl_energy_val.setText(d.get("error") or tr("Расчёт не завершён"))
            self.lbl_energy_val.setStyleSheet(f"color: {hex_color('err')}; font-size: 16px;")

        # Render status chips
        self._clear_layout(self.chips_lay)

        def add_chip(text, bg_name, fg_name):
            lbl = QLabel(text)
            lbl.setStyleSheet(f"""
                QLabel {{
                    background-color: {hex_color(bg_name)};
                    color: {hex_color(fg_name)};
                    border-radius: 6px;
                    padding: 3px 10px;
                    font-size: 11px;
                    font-weight: 600;
                }}
            """)
            self.chips_lay.addWidget(lbl)

        if d.get("normal"):
            add_chip(tr("✔ Нормальное завершение"), "okSoft", "ok")
            add_chip(tr("SCF сошёлся"), "okSoft", "ok")
        elif d.get("exit_code") is not None:
            code = d["exit_code"]
            add_chip(tr("✖ Ошибка {code}: {msg}").format(code=code, msg=EXIT_CODES.get(code, "")), "errSoft", "err")
        else:
            add_chip(tr("… В процессе или прерван"), "chip", "muted")

        if d.get("runtyp"):
            add_chip(d["runtyp"], "accentSoft", "accent")

        if d.get("wall_time") is not None:
            add_chip(tr("Время: {t:.1f} с").format(t=d["wall_time"]), "chip", "muted")

        self.chips_lay.addStretch(1)

        # Render geometry grid
        self._clear_layout(self.grid_geom)
        row = 0

        # Bonds
        bonds = d.get("bonds") or {}
        for (a, b), dist in list(bonds.items())[:6]:
            lbl_k = QLabel(f"r({a}–{b})")
            lbl_k.setStyleSheet(f"color: {hex_color('muted')}; font-size: 13px;")
            lbl_v = QLabel(f"{dist:.4f} Å")
            lbl_v.setStyleSheet(f"color: {hex_color('text')}; font-size: 13px; font-weight: 500;")
            self.grid_geom.addWidget(lbl_k, row, 0)
            self.grid_geom.addWidget(lbl_v, row, 1)
            row += 1

        # Angles
        angles = d.get("angles") or {}
        for (a, b, c), ang in list(angles.items())[:4]:
            lbl_k = QLabel(f"∠({a}–{b}–{c})")
            lbl_k.setStyleSheet(f"color: {hex_color('muted')}; font-size: 13px;")
            lbl_v = QLabel(f"{ang:.2f}°")
            lbl_v.setStyleSheet(f"color: {hex_color('text')}; font-size: 13px; font-weight: 500;")
            self.grid_geom.addWidget(lbl_k, row, 0)
            self.grid_geom.addWidget(lbl_v, row, 1)
            row += 1

        # Dipole
        if d.get("dipole") is not None:
            lbl_k = QLabel(tr("Дипольный момент"))
            lbl_k.setStyleSheet(f"color: {hex_color('muted')}; font-size: 13px;")
            lbl_v = QLabel(f"{d['dipole']:.4f} D")
            lbl_v.setStyleSheet(f"color: {hex_color('text')}; font-size: 13px; font-weight: 600;")
            self.grid_geom.addWidget(lbl_k, row, 0)
            self.grid_geom.addWidget(lbl_v, row, 1)
            row += 1

        if row == 0:
            lbl_none = QLabel(tr("Данные геометрии отсутствуют или единичный атом"))
            lbl_none.setStyleSheet(f"color: {hex_color('muted')}; font-style: italic;")
            self.grid_geom.addWidget(lbl_none, 0, 0, 1, 2)

        # Render parameters grid
        self._clear_layout(self.grid_params)
        p_row = 0
        params = [
            (tr("Заголовок"), d.get("title")),
            (tr("Метод"), d.get("method")),
            (tr("Базис"), d.get("basis")),
            ("RUNTYP", d.get("runtyp")),
        ]
        if d.get("scf") is not None:
            params.append(("E(SCF)", f"{d['scf']:.8f} Eh"))
        if d.get("mp2") is not None:
            params.append(("E(MP2)", f"{d['mp2']:.8f} Eh"))

        for k, v in params:
            if v:
                lbl_k = QLabel(k)
                lbl_k.setStyleSheet(f"color: {hex_color('muted')}; font-size: 13px;")
                lbl_v = QLabel(str(v))
                lbl_v.setStyleSheet(f"color: {hex_color('text')}; font-size: 13px; font-weight: 500;")
                self.grid_params.addWidget(lbl_k, p_row, 0)
                self.grid_params.addWidget(lbl_v, p_row, 1)
                p_row += 1

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------
    def _on_runner_finished(self, path: str, code: int):
        norm_p = os.path.abspath(path)
        out_p = os.path.splitext(norm_p)[0] + ".out"
        if os.path.isfile(out_p):
            self.add_out_file(out_p)

    def _on_browse_out(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, tr("Открыть выходной файл .out"), "", "Firefly/ffpy output (*.out *.log);;All files (*)"
        )
        for p in paths:
            self.add_out_file(p)

    def _on_open_in_3d(self):
        if self.current_path:
            self.open_in_3d.emit(self.current_path)

    def _copy_energy(self):
        if self.current_data and self.current_data.get("energy") is not None:
            QApplication.clipboard().setText(f"{self.current_data['energy']:.10f}")

    def _export_docx(self):
        if not self.current_path:
            return
        dest, _ = QFileDialog.getSaveFileName(
            self, tr("Сохранить отчёт .docx"), os.path.splitext(self.current_path)[0] + ".docx", "Word (*.docx)"
        )
        if dest:
            try:
                from ffpy.writers.docx_report import generate_report
                generate_report(self.current_path, dest)
                QMessageBox.information(self, tr("Экспорт отчёта"), tr("Отчёт успешно сохранён:\n{p}").format(p=dest))
            except Exception as e:
                QMessageBox.warning(self, tr("Ошибка экспорта"), tr("Не удалось создать отчёт: {e}").format(e=e))

    def _open_molden(self):
        if self.current_path:
            m_path = os.path.splitext(self.current_path)[0] + ".molden"
            if os.path.isfile(m_path):
                _open_external(m_path)

    def _open_folder(self):
        if self.current_path:
            _open_external(os.path.dirname(self.current_path))
