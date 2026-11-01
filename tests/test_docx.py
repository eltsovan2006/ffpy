"""Tests for .docx report generation (CLI, GUI, outparse, and docx_report)."""

import os
import pytest

from ffpy.cli import main
from ffpy.outparse import parse_text
import ffpy.writers.docx_report as docx_report

pytest.importorskip("docx")
import docx  # noqa: E402


MOCK_OUT_HF_OPT = """  ========================================================================
  ffpy 0.2.1  -  Firefly/GAMESS-style input, computed with PySCF
  input : /path/to/water_opt.inp
  ========================================================================
  ------------------------------------------------------------------------
  job
  ------------------------------------------------------------------------
  title            : water optimization
  method           : RHF
  RUNTYP           : OPTIMIZE
  charge / mult    : 0 / 1
  basis            : 6-31G(D), Cartesian d/f functions, 19 basis functions, 9 shells

  ------------------------------------------------------------------------
  input geometry
  ------------------------------------------------------------------------
  ATOM          Z        X (ANGS)        Y (ANGS)        Z (ANGS)          X (BOHR)        Y (BOHR)        Z (BOHR)
  O           8.0    0.0000000000    0.0000000000    0.1172153578       0.0000000000    0.0000000000    0.2215041042
  H           1.0    0.0000000000    0.7569999718   -0.4688614310       0.0000000000    1.4305227788   -0.8860164166
  H           1.0    0.0000000000   -0.7569999718   -0.4688614310       0.0000000000   -1.4305227788   -0.8860164166

  ------------------------------------------------------------------------
  optimized geometry
  ------------------------------------------------------------------------
  ATOM          Z        X (ANGS)        Y (ANGS)        Z (ANGS)          X (BOHR)        Y (BOHR)        Z (BOHR)
  O           8.0    0.0000000000    0.0000000000    0.1172000000       0.0000000000    0.0000000000    0.2214750849
  H           1.0    0.0000000000    0.7570000000   -0.4688000000       0.0000000000    1.4305228322   -0.8859003396
  H           1.0    0.0000000000   -0.7570000000   -0.4688000000       0.0000000000   -1.4305228322   -0.8859003396

  bond lengths (ANGS):
    O1     - H2         0.949600
    O1     - H3         0.949600
  bond angles (DEG):
    H2     - O1     - H3        104.8500

  ------------------------------------------------------------------------
  population analysis
  ------------------------------------------------------------------------
  ATOM             MULLIKEN         LOWDIN
  O1              -0.650000      -0.420000
  H2               0.325000       0.210000
  H3               0.325000       0.210000
  TOTAL            0.000000       0.000000

  ------------------------------------------------------------------------
  dipole moment
  ------------------------------------------------------------------------
              DX             DY             DZ   |D|  (DEBYE)
        0.000000       0.000000       2.150000       2.150000

  ------------------------------------------------------------------------
  final result
  ------------------------------------------------------------------------
  FINAL ENERGY (HARTREE)             -76.0107465000

  wall time 1.25 s, cpu time 1.20 s, 0 warning(s)
  ffpy TERMINATED NORMALLY
"""

MOCK_OUT_FREQ_TD = """  ========================================================================
  ffpy 0.2.1
  ========================================================================
  title            : ethylene vibration and td
  method           : B3LYP
  RUNTYP           : HESSIAN
  basis            : 6-31G

  ------------------------------------------------------------------------
  molecular geometry
  ------------------------------------------------------------------------
  ATOM          Z        X (ANGS)        Y (ANGS)        Z (ANGS)          X (BOHR)        Y (BOHR)        Z (BOHR)
  C           6.0    0.0000000000    0.0000000000    0.6650000000       0.0000000000    0.0000000000    1.2566679541
  C           6.0    0.0000000000    0.0000000000   -0.6650000000       0.0000000000    0.0000000000   -1.2566679541

  ------------------------------------------------------------------------
  population analysis
  ------------------------------------------------------------------------
  ATOM             MULLIKEN         LOWDIN
  C1              -0.150000      -0.120000
  C2              -0.150000      -0.120000
  TOTAL           -0.300000      -0.240000

  ------------------------------------------------------------------------
  vibrational analysis
  ------------------------------------------------------------------------
     MODE    FREQ (CM-1)  RED.MASS(AMU)  FORCE(MDYN/A)   IR (D2/AMU-A2)      IR (KM/MOL)
        1       820.5000       1.150000       2.100000         0.500000          25.4000
        2      1015.2000       1.200000       2.500000         0.300000          12.3000
        3      1650.0000       2.100000       5.000000         0.000000           0.0000

  ------------------------------------------------------------------------
  TDDFT EXCITED STATES
  ------------------------------------------------------------------------
    STATE         EXC (EH)     EXC (EV)   WAVEL (NM)     F(LEN)         TOTAL E (EH)
        1       0.15000000     4.081700      303.771   0.005000       -78.5000000000
        2       0.28000000     7.619200      162.734   0.320000       -78.3700000000

  FINAL ENERGY (HARTREE)             -78.6500000000
  TOTAL RKS ENERGY                   -78.6500000000
  ffpy TERMINATED NORMALLY
"""


def test_parse_out_geometry_and_lowdin():
    res = parse_text(MOCK_OUT_HF_OPT)
    assert res["normal"]
    assert res["energy"] == pytest.approx(-76.0107465)
    assert res["dipole"] == pytest.approx(2.15)
    assert res["mulliken"]["O1"] == pytest.approx(-0.65)
    assert res["lowdin"]["O1"] == pytest.approx(-0.42)
    assert res["lowdin"]["H2"] == pytest.approx(0.21)

    geom = res["geometry"]
    assert len(geom) == 3
    assert geom[0]["atom"] == "O"
    assert geom[0]["Z"] == 8.0
    assert geom[0]["x"] == 0.0
    assert geom[0]["y"] == 0.0
    assert geom[0]["z"] == pytest.approx(0.1172)
    assert ("O1", "H2") in res["bonds"]
    assert ("H2", "O1", "H3") in res["angles"]


def test_generate_docx_from_data_hf(tmp_path):
    data = parse_text(MOCK_OUT_HF_OPT)
    docx_file = str(tmp_path / "water_opt.docx")
    out_path = docx_report.generate_report(data, docx_file)
    assert out_path == docx_file
    assert os.path.isfile(docx_file)
    assert os.path.getsize(docx_file) > 1000

    # Inspect document contents
    doc = docx.Document(docx_file)
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "Отчёт о квантово-химическом расчёте" in text
    assert "water optimization" in [cell.text for t in doc.tables for r in t.rows for cell in r.cells]

    # Check tables
    # 1. Info table
    # 2. Energetics table
    # 3. Geometry table
    # 4. Bonds table
    # 5. Angles table
    # 6. Charges table
    table_texts = [[c.text for c in row.cells] for t in doc.tables for row in t.rows]
    flat_texts = " ".join(" ".join(row) for row in table_texts)
    assert "-76.0107465000" in flat_texts
    assert "2.1500" in flat_texts
    assert "Заряд Малликена" in flat_texts
    assert "Заряд Лёвдина" in flat_texts
    assert "-0.6500" in flat_texts
    assert "-0.4200" in flat_texts
    assert "0.9496" in flat_texts
    assert "104.85" in flat_texts


def test_generate_docx_freq_and_td(tmp_path):
    data = parse_text(MOCK_OUT_FREQ_TD)
    docx_file = str(tmp_path / "ethylene.docx")
    docx_report.generate_report(data, docx_file)
    assert os.path.isfile(docx_file)

    doc = docx.Document(docx_file)
    table_texts = [[c.text for c in row.cells] for t in doc.tables for row in t.rows]
    flat = " ".join(" ".join(row) for row in table_texts)
    # Check frequency section
    assert "820.50" in flat
    assert "25.40" in flat
    # Check excited states section
    assert "303.8" in flat or "303.771" in flat or "4.082" in flat
    assert "0.0050" in flat
    assert "0.3200" in flat


def test_generate_docx_from_out_file(tmp_path):
    out_path = str(tmp_path / "sample.out")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(MOCK_OUT_HF_OPT)
    docx_file = docx_report.generate_report(out_path)
    assert docx_file == str(tmp_path / "sample.docx")
    assert os.path.isfile(docx_file)


def test_cli_docx_flag_from_inp(tmp_path):
    inp_content = """ $CONTRL SCFTYP=RHF RUNTYP=ENERGY $END
 $BASIS GBASIS=STO NGAUSS=3 $END
 $DATA
H2
C1
H 1.0 0 0 0
H 1.0 0 0 0.74
 $END
"""
    inp_file = str(tmp_path / "h2.inp")
    with open(inp_file, "w", encoding="utf-8") as f:
        f.write(inp_content)

    code = main([inp_file, "-o", str(tmp_path), "--docx", "-q"])
    assert code == 0
    assert os.path.isfile(tmp_path / "h2.out")
    docx_path = tmp_path / "h2.docx"
    assert os.path.isfile(docx_path)
    assert os.path.getsize(docx_path) > 1000


def test_cli_docx_from_existing_out(tmp_path):
    out_file = str(tmp_path / "calc.out")
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(MOCK_OUT_HF_OPT)

    code = main([out_file, "-o", str(tmp_path), "-q"])
    assert code == 0
    docx_path = tmp_path / "calc.docx"
    assert os.path.isfile(docx_path)
    assert os.path.getsize(docx_path) > 1000


def test_missing_docx_error(monkeypatch):
    monkeypatch.setattr(docx_report, "docx", None)
    with pytest.raises(ImportError) as exc_info:
        docx_report.generate_report({})
    assert "python-docx" in str(exc_info.value)


def test_gui_results_panel_docx(tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QMessageBox
    from ffpy.gui.results import ResultsPanel

    app = QApplication.instance() or QApplication([])

    out_file = str(tmp_path / "gui_calc.out")
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(MOCK_OUT_HF_OPT)

    panel = ResultsPanel()
    assert not panel.b_docx.isEnabled()

    panel.set_out(out_file)
    assert panel.b_docx.isEnabled()

    # Stub QMessageBox so test doesn't block
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *args: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *args: None))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *args: None))

    target_docx = str(tmp_path / "gui_report.docx")
    panel.export_docx(target_path=target_docx)
    assert os.path.isfile(target_docx)
    assert os.path.getsize(target_docx) > 1000
