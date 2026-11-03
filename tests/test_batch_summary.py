"""Tests for Batch mode (BatchView) and Summary mode (SummaryView)."""

import csv
import os
import shutil
import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.name == "nt":
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

from PySide6.QtCore import QSettings
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

H2_INP = """ $CONTRL SCFTYP=RHF RUNTYP=ENERGY $END
 $BASIS GBASIS=STO NGAUSS=3 $END
 $DATA
H2 molecule
C1
H 1.0 0.0 0.0 0.0
H 1.0 0.0 0.0 0.74
 $END
"""

WATER_RHF_INP = """ $CONTRL SCFTYP=RHF RUNTYP=ENERGY $END
 $BASIS GBASIS=N31 NGAUSS=6 NDFUNC=1 $END
 $DATA
Water RHF
C1
O 8.0 0.000 0.000 0.117
H 1.0 0.000 0.757 -0.467
H 1.0 0.000 -0.757 -0.467
 $END
"""

WATER_DFT_INP = """ $CONTRL SCFTYP=RHF DFTTYP=B3LYP RUNTYP=ENERGY $END
 $BASIS GBASIS=N31 NGAUSS=6 NDFUNC=1 $END
 $DATA
Water B3LYP
C1
O 8.0 0.000 0.000 0.117
H 1.0 0.000 0.757 -0.467
H 1.0 0.000 -0.757 -0.467
 $END
"""

WATER_OUT_SYNTHETIC = """  ========================================================================
  ffpy 0.2.1
  ========================================================================
  title            : Water RHF
  method           : RHF
  RUNTYP           : ENERGY
  basis            : 6-31G(d)

  ------------------------------------------------------------------------
  molecular geometry
  ------------------------------------------------------------------------
  ATOM          Z        X (ANGS)        Y (ANGS)        Z (ANGS)
  O           8.0    0.0000000000    0.0000000000    0.1170000000
  H           1.0    0.0000000000    0.7570000000   -0.4670000000
  H           1.0    0.0000000000   -0.7570000000   -0.4670000000

  ------------------------------------------------------------------------
  dipole moment
  ------------------------------------------------------------------------
              DX             DY             DZ   |D|  (DEBYE)
        0.000000       0.000000       2.204500       2.204500

  ------------------------------------------------------------------------
  final result
  ------------------------------------------------------------------------
  FINAL ENERGY (HARTREE)             -76.0107465085

  wall time 4.2 s, cpu time 4.1 s, 0 warning(s)
  ffpy TERMINATED NORMALLY
"""

WATER_DFT_OUT_SYNTHETIC = """  ========================================================================
  ffpy 0.2.1
  ========================================================================
  title            : Water B3LYP
  method           : B3LYP
  RUNTYP           : ENERGY
  basis            : 6-31G(d)

  ------------------------------------------------------------------------
  molecular geometry
  ------------------------------------------------------------------------
  ATOM          Z        X (ANGS)        Y (ANGS)        Z (ANGS)
  O           8.0    0.0000000000    0.0000000000    0.1170000000
  H           1.0    0.0000000000    0.7570000000   -0.4670000000
  H           1.0    0.0000000000   -0.7570000000   -0.4670000000

  ------------------------------------------------------------------------
  dipole moment
  ------------------------------------------------------------------------
              DX             DY             DZ   |D|  (DEBYE)
        0.000000       0.000000       2.150000       2.150000

  ------------------------------------------------------------------------
  final result
  ------------------------------------------------------------------------
  FINAL ENERGY (HARTREE)             -76.4087210000

  wall time 6.8 s, cpu time 6.5 s, 0 warning(s)
  ffpy TERMINATED NORMALLY
"""


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path_factory.mktemp("settings")))
    a = QApplication.instance() or QApplication([])
    from ffpy.gui import i18n
    i18n._LANG = "ru"
    yield a


def test_batch_view_add_files_and_folder(app, tmp_path):
    from ffpy.gui.batch import BatchView
    from ffpy.gui.runner import RunManager

    runner = RunManager()
    bv = BatchView(runner=runner)

    # Prepare files
    f1 = tmp_path / "water_rhf.inp"
    f1.write_text(WATER_RHF_INP, encoding="utf-8")
    f2 = tmp_path / "water_dft.inp"
    f2.write_text(WATER_DFT_INP, encoding="utf-8")

    sub_dir = tmp_path / "sub"
    sub_dir.mkdir()
    f3 = sub_dir / "h2.inp"
    f3.write_text(H2_INP, encoding="utf-8")

    # Add individual files
    bv.add_files([str(f1), str(f2)])
    assert bv.item_count() == 2

    # Add folder
    bv.add_folder(str(sub_dir))
    assert bv.item_count() == 3

    # Adding duplicate should not increase count
    bv.add_files([str(f1)])
    assert bv.item_count() == 3

    # Check extracted parameters
    item0 = bv.get_item(0)
    assert item0["name"] == "water_rhf.inp"
    assert item0["method"] == "RHF"
    assert "6-31G" in item0["basis"].upper()

    item1 = bv.get_item(1)
    assert item1["name"] == "water_dft.inp"
    assert item1["method"] == "B3LYP"


def test_batch_view_counters_and_status(app, tmp_path):
    from ffpy.gui.batch import BatchView
    from ffpy.gui.runner import RunManager

    runner = RunManager()
    bv = BatchView(runner=runner)

    f1 = tmp_path / "job1.inp"
    f1.write_text(WATER_RHF_INP, encoding="utf-8")
    f2 = tmp_path / "job2.inp"
    f2.write_text(WATER_DFT_INP, encoding="utf-8")

    bv.add_files([str(f1), str(f2)])
    # Initial counters: total=2, done=0, running=0, error=0
    counters = bv.get_counters()
    assert counters == {"total": 2, "done": 0, "running": 0, "error": 0}

    # Simulate job1 starting
    runner.started.emit(str(f1))
    counters = bv.get_counters()
    assert counters["running"] == 1
    assert counters["done"] == 0

    # Write output for job1 and simulate finish
    out1 = tmp_path / "job1.out"
    out1.write_text(WATER_OUT_SYNTHETIC, encoding="utf-8")
    runner.finished.emit(str(f1), 0)

    counters = bv.get_counters()
    assert counters["running"] == 0
    assert counters["done"] == 1

    item1 = bv.get_item(0)
    assert item1["status"] == "done"
    assert abs(item1["energy"] - (-76.0107465085)) < 1e-6
    assert item1["wall_time"] == 4.2

    # Simulate job2 failing with error code 3
    runner.started.emit(str(f2))
    assert bv.get_counters()["running"] == 1
    runner.finished.emit(str(f2), 3)

    counters = bv.get_counters()
    assert counters["running"] == 0
    assert counters["done"] == 1
    assert counters["error"] == 1

    item2 = bv.get_item(1)
    assert item2["status"] == "error"
    assert "3" in item2["status_text"]


def test_batch_view_csv_export(app, tmp_path):
    from ffpy.gui.batch import BatchView
    from ffpy.gui.runner import RunManager

    runner = RunManager()
    bv = BatchView(runner=runner)

    f1 = tmp_path / "water_rhf.inp"
    f1.write_text(WATER_RHF_INP, encoding="utf-8")
    out1 = tmp_path / "water_rhf.out"
    out1.write_text(WATER_OUT_SYNTHETIC, encoding="utf-8")

    bv.add_files([str(f1)])
    csv_file = tmp_path / "batch_report.csv"
    bv.export_csv(str(csv_file))

    assert csv_file.exists()
    with open(csv_file, "r", encoding="utf-8-sig") as f:
        reader = list(csv.reader(f))
        assert len(reader) >= 2
        header = reader[0]
        assert "ЗАДАНИЕ" in header[0]
        assert "МЕТОД" in header[1]
        assert "БАЗИС" in header[2]
        row1 = reader[1]
        assert row1[0] == "water_rhf.inp"
        assert row1[1] == "RHF"
        assert "-76.01074" in row1[3]


def test_delta_energy_comparison(app, tmp_path):
    from ffpy.gui.batch import BatchView
    from ffpy.gui.runner import RunManager

    runner = RunManager()
    bv = BatchView(runner=runner)

    f1 = tmp_path / "water_rhf.inp"
    f1.write_text(WATER_RHF_INP, encoding="utf-8")
    out1 = tmp_path / "water_rhf.out"
    out1.write_text(WATER_OUT_SYNTHETIC, encoding="utf-8")

    f2 = tmp_path / "water_dft.inp"
    f2.write_text(WATER_DFT_INP, encoding="utf-8")
    out2 = tmp_path / "water_dft.out"
    out2.write_text(WATER_DFT_OUT_SYNTHETIC, encoding="utf-8")

    bv.add_files([str(f1), str(f2)])

    # Calculate delta E
    res = bv.compute_comparison([0, 1])
    assert res is not None
    # E(DFT) - E(RHF) = -76.408721 - (-76.0107465085) = -0.39797449 Eh
    delta_eh = res["diffs"][0]["delta_eh"]
    delta_kcal = res["diffs"][0]["delta_kcal"]
    assert abs(delta_eh - (-0.39797449)) < 1e-5
    # 1 Eh = 627.5095 kcal/mol
    expected_kcal = delta_eh * 627.5095
    assert abs(delta_kcal - expected_kcal) < 1e-2


def test_summary_view(app, tmp_path):
    from ffpy.gui.summary import SummaryView

    sv = SummaryView()
    out1 = tmp_path / "water_rhf.out"
    out1.write_text(WATER_OUT_SYNTHETIC, encoding="utf-8")

    sv.add_out_file(str(out1))
    assert sv.item_count() == 1

    sv.select_item(0)
    info = sv.get_selected_info()
    assert info is not None
    assert abs(info["energy"] - (-76.0107465085)) < 1e-6
    assert info["method"] == "RHF"
    assert info["dipole"] == 2.2045


def test_main_window_integration_and_screenshots(app, tmp_path):
    from ffpy.gui.app import MainWindow
    from ffpy.gui.batch import BatchView
    from ffpy.gui.summary import SummaryView
    from ffpy.gui.theme import set_theme_mode

    win = MainWindow()
    win.resize(1340, 820)
    win.show()

    # Verify stubs replaced
    assert isinstance(win.summary_view, SummaryView)
    assert isinstance(win.batch_view, BatchView)
    assert win.stack.widget(1) is win.summary_view
    assert win.stack.widget(3) is win.batch_view

    # Add sample files to batch view
    f1 = tmp_path / "water_rhf_opt.inp"
    f1.write_text(WATER_RHF_INP, encoding="utf-8")
    out1 = tmp_path / "water_rhf_opt.out"
    out1.write_text(WATER_OUT_SYNTHETIC, encoding="utf-8")

    f2 = tmp_path / "water_b3lyp.inp"
    f2.write_text(WATER_DFT_INP, encoding="utf-8")
    out2 = tmp_path / "water_b3lyp.out"
    out2.write_text(WATER_DFT_OUT_SYNTHETIC, encoding="utf-8")

    win.batch_view.add_files([str(f1), str(f2)])

    # Switch to Batch mode
    win.set_mode(3)
    app.processEvents()

    shots_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".ai", "shots")
    os.makedirs(shots_dir, exist_ok=True)

    # 1. Light theme shot for Batch mode
    set_theme_mode("light")
    app.processEvents()
    pix_light = QPixmap(win.size())
    win.render(pix_light)
    light_path = os.path.join(shots_dir, "017_light.png")
    pix_light.save(light_path, "PNG")
    assert os.path.exists(light_path)
    assert os.path.getsize(light_path) > 10000

    # 2. Dark theme shot for Summary mode
    win.summary_view.add_out_file(str(out1))
    win.summary_view.add_out_file(str(out2))
    win.set_mode(1)
    set_theme_mode("dark")
    app.processEvents()
    pix_dark = QPixmap(win.size())
    win.render(pix_dark)
    dark_path = os.path.join(shots_dir, "017_dark.png")
    pix_dark.save(dark_path, "PNG")
    assert os.path.exists(dark_path)
    assert os.path.getsize(dark_path) > 10000

    win.close()
