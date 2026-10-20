"""Results panel: summary of an ffpy .out (energy, geometry, frequencies,
excited states, warnings) and links to the output files."""

import html
import os

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QPushButton, QTextBrowser,
                               QVBoxLayout, QWidget)

from ffpy.errors import EXIT_CODES
from ffpy.gui.theme import hex_color
from ffpy.outparse import parse_out


def open_external(path):
    """Open with the program Windows associates with the file (Avogadro, Chemcraft...)."""
    return QDesktopServices.openUrl(QUrl.fromLocalFile(path))


class ResultsPanel(QWidget):
    open_file = Signal(str)          # ask the main window to open a file in a tab

    def __init__(self):
        super().__init__()
        self.out_path = None
        self.data = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        self.view = QTextBrowser()
        self.view.setOpenLinks(False)
        self.view.anchorClicked.connect(self._link)
        lay.addWidget(self.view, 1)
        row = QHBoxLayout()
        self.b_copy = QPushButton("Копировать энергию")
        self.b_copy.clicked.connect(self.copy_energy)
        self.b_molden = QPushButton("Открыть .molden")
        self.b_molden.setToolTip("Открыть орбитали и частоты в программе, связанной с .molden "
                                 "(Chemcraft, Avogadro…)")
        self.b_molden.clicked.connect(self.open_molden)
        self.b_folder = QPushButton("Папка")
        self.b_folder.clicked.connect(self.open_folder)
        for b in (self.b_copy, self.b_molden, self.b_folder):
            row.addWidget(b)
        lay.addLayout(row)
        self.clear()

    def clear(self):
        self.out_path, self.data = None, None
        self.view.setHtml("<p style='color:%s'>Здесь появится сводка результатов после расчёта "
                          "или при открытии файла .out.</p>" % hex_color("muted"))
        for b in (self.b_copy, self.b_molden, self.b_folder):
            b.setEnabled(False)

    def set_out(self, path):
        if not path or not os.path.exists(path):
            self.clear()
            return
        self.out_path = path
        try:
            self.data = parse_out(path)
        except OSError:
            self.clear()
            return
        self.view.setHtml(self._html(self.data))
        stem = os.path.splitext(path)[0]
        self.b_copy.setEnabled(self.data["energy"] is not None)
        self.b_molden.setEnabled(os.path.exists(stem + ".molden"))
        self.b_folder.setEnabled(True)

    def _html(self, d):
        ok, warn, err, muted = (hex_color(k) for k in ("ok", "warning", "error", "muted"))
        e = html.escape
        h = ["<div style='font-size:10pt'>"]
        name = os.path.basename(self.out_path)
        if d["normal"]:
            badge = "<span style='color:%s'><b>✔ завершён нормально</b></span>" % ok
        elif d["exit_code"] is not None:
            badge = "<span style='color:%s'><b>✖ ошибка, код %d</b></span> — %s" % (
                err, d["exit_code"], e(EXIT_CODES.get(d["exit_code"], "")))
        else:
            badge = "<span style='color:%s'><b>… расчёт не завершён</b></span>" % warn
        h.append("<p><b>%s</b><br>%s</p>" % (e(name), badge))
        if d["error"]:
            h.append("<p style='color:%s'>%s</p>" % (err, e(d["error"])))
        rows = [("Заголовок", d["title"]), ("Метод", d["method"]), ("RUNTYP", d["runtyp"]),
                ("Базис", d["basis"])]
        h.append("<table cellspacing=0 cellpadding=2>")
        for k, v in rows:
            if v:
                h.append("<tr><td style='color:%s'>%s&nbsp;</td><td>%s</td></tr>" % (muted, k, e(v)))
        h.append("</table>")
        if d["energy"] is not None:
            h.append("<p>Итоговая энергия<br><span style='font-size:14pt'><b>%.10f</b></span> Eh</p>"
                     % d["energy"])
        extra = []
        if d["scf"] is not None and d["mp2"] is not None:
            extra.append("E(SCF) = %.10f, E(MP2) = %.10f" % (d["scf"], d["mp2"]))
        if d["dipole"] is not None:
            extra.append("|μ| = %.4f D" % d["dipole"])
        if d["wall_time"] is not None:
            extra.append("время %.1f с" % d["wall_time"])
        if extra:
            h.append("<p>%s</p>" % "<br>".join(e(x) for x in extra))

        if d["bonds"]:
            h.append("<p><b>Геометрия</b> (последняя)</p><table cellspacing=0 cellpadding=1>")
            for (a, b), v in d["bonds"].items():
                h.append("<tr><td>%s–%s</td><td align=right>&nbsp;%.4f Å</td></tr>" % (e(a), e(b), v))
            for (a, b, c), v in d["angles"].items():
                h.append("<tr><td>%s–%s–%s</td><td align=right>&nbsp;%.2f°</td></tr>"
                         % (e(a), e(b), e(c), v))
            h.append("</table>")
        if d["freqs"]:
            h.append("<p><b>Частоты</b>, см⁻¹ (ИК, км/моль)</p><table cellspacing=0 cellpadding=1>")
            for i, (f, ir) in enumerate(zip(d["freqs"], d["ir_km"] or [None] * len(d["freqs"]))):
                fs = ("<span style='color:%s'>%.1fi</span>" % (err, -f)) if f < 0 else "%.1f" % f
                h.append("<tr><td>%d&nbsp;</td><td align=right>%s</td><td align=right>&nbsp;%s</td></tr>"
                         % (i + 1, fs, "" if ir is None else "%.1f" % ir))
            h.append("</table>")
        if d["excited"]:
            h.append("<p><b>Возбуждённые состояния</b></p><table cellspacing=0 cellpadding=1>"
                     "<tr><td></td><td align=right>эВ</td><td align=right>&nbsp;нм</td>"
                     "<td align=right>&nbsp;f</td></tr>")
            for s in d["excited"]:
                h.append("<tr><td>%d</td><td align=right>%.3f</td><td align=right>&nbsp;%.1f</td>"
                         "<td align=right>&nbsp;%.4f</td></tr>" % (s["state"], s["ev"], s["nm"], s["f"]))
            h.append("</table>")
        if d["warnings"]:
            h.append("<p><b>Предупреждения</b> (%d)</p><ul style='margin-left:-20px'>" % len(d["warnings"]))
            shown = [w for w in d["warnings"] if not w.startswith("default applied")]
            n_def = len(d["warnings"]) - len(shown)
            for w in shown[:20]:
                h.append("<li style='color:%s'>%s</li>" % (warn, e(w)))
            if n_def:
                h.append("<li style='color:%s'>применено умолчаний: %d</li>" % (muted, n_def))
            h.append("</ul>")
        stem = os.path.splitext(self.out_path)[0]
        files = [stem + ext for ext in (".out", ".molden", ".dat", ".xyz") if os.path.exists(stem + ext)]
        if files:
            h.append("<p><b>Файлы</b><br>")
            h.append("<br>".join("<a href='%s'>%s</a>" % (QUrl.fromLocalFile(f).toString(),
                                                         e(os.path.basename(f))) for f in files))
            h.append("</p>")
        h.append("</div>")
        return "".join(h)

    def _link(self, url):
        path = url.toLocalFile()
        if path.lower().endswith(".molden"):
            open_external(path)
        else:
            self.open_file.emit(path)

    def copy_energy(self):
        if self.data and self.data["energy"] is not None:
            QApplication.clipboard().setText("%.10f" % self.data["energy"])

    def open_molden(self):
        if self.out_path:
            open_external(os.path.splitext(self.out_path)[0] + ".molden")

    def open_folder(self):
        if self.out_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(self.out_path)))
