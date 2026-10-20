"""'New calculation' dialog: a form that writes a valid .inp."""

import os
import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QPlainTextEdit, QPushButton, QSpinBox, QSplitter, QVBoxLayout,
                               QWidget)

from ffpy.gui.editor import CodeEditor, editor_font
from ffpy.gui.highlight import InpHighlighter
from ffpy.gui.theme import hex_color
from ffpy.gui.validate import check_text
from ffpy.job import ELEMENTS

BASES = [
    ("STO-3G", "GBASIS=STO NGAUSS=3", False),
    ("3-21G", "GBASIS=N21 NGAUSS=3", False),
    ("6-31G", "GBASIS=N31 NGAUSS=6", False),
    ("6-31G*", "GBASIS=N31 NGAUSS=6 NDFUNC=1", False),
    ("6-31G**", "GBASIS=N31 NGAUSS=6 NDFUNC=1 NPFUNC=1", False),
    ("6-31+G*", "GBASIS=N31 NGAUSS=6 NDFUNC=1 DIFFSP=.TRUE.", False),
    ("6-31++G**", "GBASIS=N31 NGAUSS=6 NDFUNC=1 NPFUNC=1 DIFFSP=.TRUE. DIFFS=.TRUE.", False),
    ("6-311G**", "GBASIS=N311 NGAUSS=6 NDFUNC=1 NPFUNC=1", False),
    ("cc-pVDZ", "GBASIS=CCD", True),
    ("cc-pVTZ", "GBASIS=CCT", True),
    ("aug-cc-pVDZ", "GBASIS=ACCD", True),
]
RUNTYPS = [("Энергия в точке", "ENERGY"), ("Градиент", "GRADIENT"),
           ("Оптимизация геометрии", "OPTIMIZE"), ("Частоты (гессиан)", "HESSIAN")]
METHODS = ["HF", "DFT", "MP2", "CASSCF"]
EXCITED = [("нет", None), ("TDDFT / TDHF", "TDDFT"), ("TDA", "TDA"), ("CIS", "CIS")]
FUNCTIONALS = ["B3LYP", "PBE0", "PBE", "BLYP", "B3LYP1", "M062X", "CAMB3LYP", "TPSS", "SVWN"]
SOLVENT_NAMES = ["WATER", "DMSO", "CH3CN", "CH3OH", "C2H5OH", "ACETONE", "CH2CL2", "CHCL3",
                 "THF", "BENZENE", "TOLUENE", "CCL4", "CYCHEX"]

WATER_XYZ = "O   0.000000   0.000000   0.117000\nH   0.000000   0.757000  -0.467000\nH   0.000000  -0.757000  -0.467000\n"
_SYM = {s.upper(): z for z, s in enumerate(ELEMENTS) if z}


def parse_xyz(text):
    """'Sym x y z' lines (an .xyz header of two lines is skipped) -> [(sym, Z, x, y, z)]."""
    lines = [l for l in text.splitlines() if l.strip()]
    if len(lines) >= 2 and re.fullmatch(r"\s*\d+\s*", lines[0]):
        lines = lines[2:]
    atoms = []
    for i, l in enumerate(lines, 1):
        t = l.split()
        if len(t) < 4:
            raise ValueError("строка %d: нужно 'Символ x y z'" % i)
        sym = re.sub(r"[^A-Za-z]", "", t[0])
        sym = sym[:1].upper() + sym[1:2].lower() if sym else sym
        if sym.upper() not in _SYM:
            if t[0].isdigit() and 0 < int(t[0]) < len(ELEMENTS):
                sym = ELEMENTS[int(t[0])]
            else:
                raise ValueError("строка %d: неизвестный элемент '%s'" % (i, t[0]))
        try:
            x, y, z = (float(v) for v in t[1:4])
        except ValueError:
            raise ValueError("строка %d: координаты должны быть числами" % i)
        atoms.append((sym, _SYM[sym.upper()], x, y, z))
    if not atoms:
        raise ValueError("нет атомов")
    return atoms


class NewJobDialog(QDialog):
    def __init__(self, parent=None, folder=None):
        super().__init__(parent)
        self.setWindowTitle("Новый расчёт")
        self.resize(1050, 680)
        self.folder = folder
        self.result_text = None

        split = QSplitter(Qt.Horizontal)
        form_w = QWidget()
        form = QVBoxLayout(form_w)

        g1 = QGroupBox("Расчёт")
        f1 = QFormLayout(g1)
        self.title = QLineEdit("Water")
        self.method = QComboBox()
        self.method.addItems(METHODS)
        self.ref = QComboBox()
        self.ref.addItems(["RHF", "UHF", "ROHF"])
        self.functional = QComboBox()
        self.functional.addItems(FUNCTIONALS)
        self.functional.setEditable(True)
        self.runtyp = QComboBox()
        for label, val in RUNTYPS:
            self.runtyp.addItem(label, val)
        self.basis = QComboBox()
        for label, _, _ in BASES:
            self.basis.addItem(label)
        self.basis.setCurrentText("6-31G*")
        self.charge = QSpinBox()
        self.charge.setRange(-10, 10)
        self.mult = QSpinBox()
        self.mult.setRange(1, 10)
        f1.addRow("Заголовок", self.title)
        f1.addRow("Метод", self.method)
        f1.addRow("Референс (SCFTYP)", self.ref)
        f1.addRow("Функционал", self.functional)
        f1.addRow("Тип задачи", self.runtyp)
        f1.addRow("Базис", self.basis)
        f1.addRow("Заряд", self.charge)
        f1.addRow("Мультиплетность", self.mult)
        form.addWidget(g1)

        g2 = QGroupBox("Дополнительно")
        f2 = QFormLayout(g2)
        self.excited = QComboBox()
        for label, val in EXCITED:
            self.excited.addItem(label, val)
        self.nstate = QSpinBox()
        self.nstate.setRange(1, 50)
        self.nstate.setValue(5)
        ex_row = QHBoxLayout()
        ex_row.addWidget(self.excited, 1)
        ex_row.addWidget(QLabel("состояний"))
        ex_row.addWidget(self.nstate)
        self.solvent = QComboBox()
        self.solvent.addItem("газовая фаза")
        self.solvent.addItems(SOLVENT_NAMES)
        self.hssend = QCheckBox("частоты после оптимизации (HSSEND)")
        self.nstep = QSpinBox()
        self.nstep.setRange(1, 500)
        self.nstep.setValue(50)
        self.ncore, self.nact, self.nels = QSpinBox(), QSpinBox(), QSpinBox()
        for s in (self.ncore, self.nact, self.nels):
            s.setRange(0, 200)
        self.nact.setValue(2)
        self.nels.setValue(2)
        cas_row = QHBoxLayout()
        for lab, w in (("NCORE", self.ncore), ("NACT", self.nact), ("NELS", self.nels)):
            cas_row.addWidget(QLabel(lab))
            cas_row.addWidget(w)
        self.cas_box = QWidget()
        self.cas_box.setLayout(cas_row)
        cas_row.setContentsMargins(0, 0, 0, 0)
        f2.addRow("Возбуждённые", ex_row)
        f2.addRow("Растворитель (PCM)", self.solvent)
        f2.addRow("Шагов оптимизации", self.nstep)
        f2.addRow("", self.hssend)
        f2.addRow("Активное пространство", self.cas_box)
        form.addWidget(g2)

        g3 = QGroupBox("Геометрия, Å (Символ x y z или содержимое .xyz)")
        v3 = QVBoxLayout(g3)
        self.geom = QPlainTextEdit(WATER_XYZ)
        self.geom.setFont(editor_font(10))
        load = QPushButton("Загрузить .xyz…")
        load.clicked.connect(self.load_xyz)
        v3.addWidget(self.geom, 1)
        v3.addWidget(load, 0, Qt.AlignLeft)
        form.addWidget(g3, 1)
        split.addWidget(form_w)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.addWidget(QLabel("Входной файл (можно будет отредактировать после создания):"))
        self.preview = CodeEditor(read_only=True)
        InpHighlighter(self.preview.document())
        rv.addWidget(self.preview, 1)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        rv.addWidget(self.status)
        split.addWidget(right)
        split.setSizes([480, 570])

        buttons = QDialogButtonBox()
        self.b_create = buttons.addButton("Создать", QDialogButtonBox.AcceptRole)
        buttons.addButton("Отмена", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self.accept_job)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(split, 1)
        lay.addWidget(buttons)

        self.title.textChanged.connect(self.update)
        self.functional.editTextChanged.connect(self.update)
        for w in (self.method, self.ref, self.runtyp, self.basis, self.excited, self.solvent):
            w.currentIndexChanged.connect(self.update)
        for w in (self.charge, self.mult, self.nstate, self.nstep, self.ncore, self.nact, self.nels):
            w.valueChanged.connect(self.update)
        self.hssend.toggled.connect(self.update)
        self.geom.textChanged.connect(self.update)
        self.method.currentIndexChanged.connect(self._suggest_cas)
        self.charge.valueChanged.connect(self._suggest_cas)
        self.geom.textChanged.connect(self._suggest_cas)
        self.update()

    def load_xyz(self):
        path, _ = QFileDialog.getOpenFileName(self, "Геометрия", self.folder or "",
                                              "XYZ (*.xyz);;Все файлы (*)")
        if path:
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
            self.geom.setPlainText(text)
            if self.title.text() in ("", "Water"):
                self.title.setText(os.path.splitext(os.path.basename(path))[0])

    def _suggest_cas(self):
        if self.method.currentText() != "CASSCF":
            return
        try:
            nel = sum(a[1] for a in parse_xyz(self.geom.toPlainText())) - self.charge.value()
        except ValueError:
            return
        ncore = max(0, (nel - self.nels.value()) // 2)
        self.ncore.blockSignals(True)
        self.ncore.setValue(ncore)
        self.ncore.blockSignals(False)
        self.update()

    def _enable(self):
        m = self.method.currentText()
        rt = self.runtyp.currentData()
        self.functional.setEnabled(m == "DFT")
        self.ref.setEnabled(m != "CASSCF")
        self.cas_box.setEnabled(m == "CASSCF")
        self.excited.setEnabled(m in ("HF", "DFT"))
        self.nstate.setEnabled(m in ("HF", "DFT") and self.excited.currentData() is not None)
        self.nstep.setEnabled(rt == "OPTIMIZE")
        self.hssend.setEnabled(rt == "OPTIMIZE" and m in ("HF", "DFT"))

    def build_text(self):
        self._enable()
        m = self.method.currentText()
        title = self.title.text().strip() or "ffpy job"
        rt = self.runtyp.currentData()
        label, basis_line, spherical = BASES[self.basis.currentIndex()]
        contrl = []
        if m == "CASSCF":
            contrl.append("SCFTYP=MCSCF")
        else:
            contrl.append("SCFTYP=%s" % self.ref.currentText())
        if m == "DFT":
            contrl.append("DFTTYP=%s" % self.functional.currentText().strip().upper())
        if m == "MP2":
            contrl.append("MPLEVL=2")
        ex = self.excited.currentData() if self.excited.isEnabled() else None
        if ex == "CIS":
            contrl.append("CITYP=CIS")
        contrl.append("RUNTYP=%s" % rt)
        contrl.append("ICHARG=%d MULT=%d" % (self.charge.value(), self.mult.value()))
        if spherical:
            contrl.append("ISPHER=1")
        out = ["! %s, %s/%s, created by ffpy-gui" % (title, m if m != "DFT" else
                                                       self.functional.currentText().upper(), label),
               " $CONTRL %s $END" % " ".join(contrl),
               " $BASIS  %s $END" % basis_line]
        if rt == "OPTIMIZE":
            st = "NSTEP=%d" % self.nstep.value()
            if self.hssend.isEnabled() and self.hssend.isChecked():
                st += " HSSEND=.TRUE."
            out.append(" $STATPT %s $END" % st)
        if ex in ("TDDFT", "TDA"):
            out.append(" $TDDFT  NSTATE=%d%s $END" % (self.nstate.value(),
                                                      " TDA=.TRUE." if ex == "TDA" else ""))
        elif ex == "CIS":
            out.append(" $CIS    NSTATE=%d $END" % self.nstate.value())
        if m == "CASSCF":
            out.append(" $DET    NCORE=%d NACT=%d NELS=%d $END"
                       % (self.ncore.value(), self.nact.value(), self.nels.value()))
        if self.solvent.currentIndex() > 0:
            out.append(" $PCM    SOLVNT=%s $END" % self.solvent.currentText())
        out += [" $DATA", title, "C1"]
        atoms = parse_xyz(self.geom.toPlainText())
        for sym, z, x, y, zz in atoms:
            out.append("%-4s %5.1f %14.6f %14.6f %14.6f" % (sym, z, x, y, zz))
        out.append(" $END")
        return "\n".join(out) + "\n"

    def update(self, *_):
        try:
            text = self.build_text()
        except ValueError as e:
            self.preview.setPlainText("")
            self._status(False, "Геометрия: %s" % e)
            return
        self.preview.setPlainText(text)
        chk = check_text(text)
        self._status(chk.ok, ("✔ " if chk.ok else "✖ ") + chk.message)

    def _status(self, ok, msg):
        self.status.setText(msg)
        self.status.setStyleSheet("color:%s" % hex_color("ok" if ok else "error"))
        self.b_create.setEnabled(ok)

    def accept_job(self):
        try:
            self.result_text = self.build_text()
        except ValueError:
            return
        self.accept()

    def suggested_name(self):
        base = re.sub(r"[^\w\-]+", "_", self.title.text().strip()).strip("_") or "job"
        return base.lower() + ".inp"
