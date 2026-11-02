"""ffpy-gui without a screen: validation, input builder, editor, a real run."""

import os
import shutil
import sys
import time

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.name == "nt":
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

HERE = os.path.dirname(__file__)
EXAMPLES = os.path.join(os.path.dirname(HERE), "examples")
H2 = """ $CONTRL SCFTYP=RHF RUNTYP=ENERGY $END
 $BASIS GBASIS=STO NGAUSS=3 $END
 $DATA
H2
C1
H 1.0 0 0 0
H 1.0 0 0 0.74
 $END
"""


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path_factory.mktemp("settings")))
    a = QApplication.instance() or QApplication([])
    yield a


@pytest.fixture
def no_modal(monkeypatch):
    asked = []

    def answer(*args, **kwargs):
        asked.append(args[2] if len(args) > 2 else "")
        return QMessageBox.Yes

    for name in ("question", "warning", "information"):
        monkeypatch.setattr(QMessageBox, name, staticmethod(answer))
    return asked


def pump(app, cond, timeout=120):
    t0 = time.time()
    while not cond() and time.time() - t0 < timeout:
        app.processEvents()
        time.sleep(0.02)
    for _ in range(10):
        app.processEvents()


def test_check_text():
    from ffpy.gui.validate import check_text
    assert check_text(H2).ok
    bad = check_text(H2.replace("RUNTYP=ENERGY", "RUNTYP=ENERGY FOO=1"))
    assert not bad.ok and "FOO" in bad.message
    missing = check_text(" $CONTRL SCFTYP=RHF\n" + H2)
    assert not missing.ok and missing.line == 2


def test_builder_makes_valid_inputs(app):
    from ffpy.gui.builder import NewJobDialog
    from ffpy.gui.validate import check_text
    d = NewJobDialog()
    for method in ("HF", "DFT", "MP2"):
        for rt in range(4):
            d.method.setCurrentText(method)
            d.runtyp.setCurrentIndex(rt)
            text = d.build_text()
            chk = check_text(text)
            if method == "MP2" and rt == 3:
                assert not chk.ok          # MP2 hessian is not supported
            else:
                assert chk.ok, (method, rt, chk.message, text)
    d.method.setCurrentText("CASSCF")
    d.runtyp.setCurrentIndex(0)
    d._suggest_cas()
    assert check_text(d.build_text()).ok


def test_parse_xyz():
    from ffpy.gui.builder import parse_xyz
    atoms = parse_xyz("3\nwater\nO 0 0 0.117\nH 0 0.757 -0.467\nh1 0 -0.757 -0.467\n")
    assert [a[1] for a in atoms] == [8, 1, 1]
    with pytest.raises(ValueError):
        parse_xyz("Xx 0 0 0")


def test_editor_comment_toggle(app):
    from ffpy.gui.editor import FileTab
    t = FileTab(None)
    t.editor.setPlainText("a\nb\n")
    t.editor.selectAll()
    t.editor.toggle_comment()
    assert t.editor.toPlainText().startswith("! a\n! b")
    t.editor.selectAll()
    t.editor.toggle_comment()
    assert t.editor.toPlainText().startswith("a\nb")


def test_open_run_and_results(app, no_modal, tmp_path):
    from ffpy.gui.app import MainWindow
    inp = tmp_path / "h2.inp"
    inp.write_text(H2)
    w = MainWindow()
    w.set_folder(str(tmp_path))
    tab = w.open_path(str(inp))
    w._validate_current()
    assert w.check_label.text().startswith("✔")
    w.runner.threads = 2
    w.run_current()
    pump(app, lambda: not w.runner.is_running() and not w.runner.queue)
    out = tmp_path / "h2.out"
    assert out.exists()
    assert w.results.data["normal"]
    assert w.results.data["energy"] == pytest.approx(-1.1167, abs=1e-3)
    assert w.find_tab(str(out)) >= 0
    assert "TERMINATED NORMALLY" in w.log_view.toPlainText()
    out_tab = w.tab(w.find_tab(str(out)))
    assert out_tab.read_only and out_tab.outline.count() > 3
    out_tab.copy_all()
    assert "TERMINATED NORMALLY" in QApplication.clipboard().text()
    tab.editor.document().setModified(False)
    w.close()


def test_results_panel_on_examples(app, tmp_path):
    """Parse a TDDFT and a hessian log: no cross-talk between tables."""
    from ffpy.cli import main
    from ffpy.outparse import parse_out
    for name in ("ethylene_tddft", "water_hessian"):
        shutil.copy(os.path.join(EXAMPLES, name + ".inp"), tmp_path)
        assert main([str(tmp_path / (name + ".inp")), "-q", "-n", "4"]) == 0
    td = parse_out(str(tmp_path / "ethylene_tddft.out"))
    hs = parse_out(str(tmp_path / "water_hessian.out"))
    assert len(td["excited"]) == 5 and not td["freqs"]
    assert len(hs["freqs"]) == 3 and not hs["excited"]


def test_gui_folder_navigation(app, no_modal, tmp_path, monkeypatch):
    from ffpy.gui.app import MainWindow
    from PySide6.QtWidgets import QFileDialog
    sub = tmp_path / "acetate"
    sub.mkdir()
    inp = sub / "job.inp"
    inp.write_text(H2)

    w = MainWindow()
    w.set_folder(str(tmp_path))
    assert not w.folder_edit.isReadOnly()

    # Manual input + Enter
    w.folder_edit.setText(str(sub))
    w.folder_edit.returnPressed.emit()
    assert os.path.abspath(w.folder) == os.path.abspath(str(sub))

    # Button click simulation passing boolean argument
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: str(sub))
    w.choose_folder(False)
    assert os.path.abspath(w.folder) == os.path.abspath(str(sub))

    # Open file from outside current folder switches tree folder
    w.set_folder(str(tmp_path))
    w.open_path(str(inp))
    assert os.path.abspath(w.folder) == os.path.abspath(str(sub))
    w.close()


def test_ffpy_command(monkeypatch):
    from ffpy.gui.runner import ffpy_command

    # 1. Non-frozen (development environment)
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert ffpy_command() == [sys.executable, "-m", "ffpy"]

    # 2. Frozen on Windows
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", os.path.normpath("C:/ffpy/ffpy-gui.exe"))
    monkeypatch.setattr(sys, "platform", "win32")
    assert ffpy_command() == [os.path.normpath("C:/ffpy/ffpy.exe")]

    # 3. Frozen on macOS / Linux (POSIX)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "/opt/ffpy/ffpy-gui")
    monkeypatch.setattr(sys, "platform", "darwin")
    assert ffpy_command() == [os.path.join(os.path.dirname("/opt/ffpy/ffpy-gui"), "ffpy")]

    # 4. Frozen inside macOS .app bundle
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "/Applications/ffpy.app/Contents/MacOS/ffpy-gui")
    monkeypatch.setattr(sys, "platform", "darwin")
    assert ffpy_command() == [os.path.join(os.path.dirname("/Applications/ffpy.app/Contents/MacOS/ffpy-gui"), "ffpy")]


def test_compact_path_label():
    from ffpy.gui.app import compact_path_label
    assert compact_path_label("/home/user/calc/water.inp") == "water.inp   —   calc"
    assert compact_path_label("/calc/water.inp") == "water.inp   —   calc"
    cur_parent = os.path.basename(os.path.abspath("."))
    assert compact_path_label("water.inp") == f"water.inp   —   {cur_parent}"


def test_window_fit_to_screen(app):
    from PySide6.QtCore import QRect
    from ffpy.gui.app import MainWindow
    w = MainWindow()
    screen_rect = QRect(0, 0, 1024, 768)
    # Exceeding size
    w.setGeometry(QRect(0, 0, 1600, 1200))
    w.ensure_within_screen(screen_rect)
    geo = w.geometry()
    assert geo.width() <= screen_rect.width()
    assert geo.height() <= screen_rect.height()
    assert geo.right() <= screen_rect.right()
    assert geo.bottom() <= screen_rect.bottom()
    assert geo.left() >= screen_rect.left()
    assert geo.top() >= screen_rect.top()

    # Position outside screen
    w.setGeometry(QRect(1200, 900, 800, 600))
    w.ensure_within_screen(screen_rect)
    geo2 = w.geometry()
    assert screen_rect.contains(geo2)
    w.close()


def test_results_panel_narrow_dock(app):
    from ffpy.gui.results import ResultsPanel
    p = ResultsPanel()
    p.show()
    app.processEvents()
    assert p.minimumSizeHint().width() <= 260
    for width in (260, 280, 320):
        p.resize(width, 400)
        app.processEvents()
        for btn in (p.b_copy, p.b_folder, p.b_molden, p.b_docx):
            assert btn.isVisible()
            assert btn.width() > 0
            assert btn.height() > 0
            assert btn.geometry().right() <= p.width()
    p.close()


def test_recent_files_formatting(app, tmp_path):
    from ffpy.gui.app import MainWindow
    f1 = tmp_path / "water.inp"
    f1.write_text("test")
    w = MainWindow()
    w._add_recent(str(f1))
    w._fill_recent()
    assert w.recent_list.count() >= 1
    item = w.recent_list.item(0)
    assert item.text().startswith("water.inp   —   ")
    assert item.toolTip() == str(f1)

    w._fill_recent_menu()
    actions = w.recent_menu.actions()
    assert len(actions) >= 1
    assert actions[0].text().startswith("water.inp   —   ")
    assert actions[0].toolTip() == str(f1)
    w.close()

