"""End-to-end runs of tests/inputs/*.inp compared with tests/reference.json.

Tolerances are those of the specification. Entries whose "source" is
"ffpy-regression" were produced by ffpy itself and must be replaced with
numbers from a real Firefly run (black-box comparison).
"""

import json
import os

import pytest

from ffpy.cli import main
from ffpy.outparse import parse_out

HERE = os.path.dirname(__file__)
REF = json.load(open(os.path.join(HERE, "reference.json"), encoding="utf-8"))
TOL = REF["tolerances"]


def run(name, tmp_path):
    inp = os.path.join(HERE, "inputs", name + ".inp")
    code = main([inp, "-o", str(tmp_path), "-q", "-n", "4"])
    out = parse_out(os.path.join(str(tmp_path), name + ".out"))
    return code, out


@pytest.mark.parametrize("name", sorted(REF["cases"]))
def test_case(name, tmp_path):
    ref = REF["cases"][name]
    code, out = run(name, tmp_path)
    assert code == 0, out["last_line"]
    assert out["normal"]
    tol_e = TOL["energy_dft"] if ref.get("dft") else TOL["energy_hf_mp2"]
    assert out["energy"] == pytest.approx(ref["energy"], abs=tol_e)
    for key, val in ref.get("bonds", {}).items():
        a, b = key.split("-")
        assert out["bonds"][(a, b)] == pytest.approx(val, abs=TOL["bond"])
    for key, val in ref.get("angles", {}).items():
        a, b, c = key.split("-")
        assert out["angles"][(a, b, c)] == pytest.approx(val, abs=TOL["angle"])
    if "freqs" in ref:
        assert len(out["freqs"]) == len(ref["freqs"])
        for f, r in zip(out["freqs"], ref["freqs"]):
            assert f == pytest.approx(r, abs=TOL["freq"])
    for atom, q in ref.get("mulliken", {}).items():
        assert out["mulliken"][atom] == pytest.approx(q, abs=TOL["mulliken"])


def test_output_files(tmp_path):
    code, out = run("water_rhf_opt", tmp_path)
    assert code == 0
    for ext in (".out", ".molden", "_opt.molden", ".dat", ".xyz"):
        assert os.path.getsize(os.path.join(str(tmp_path), "water_rhf_opt" + ext)) > 0
    molden = open(os.path.join(str(tmp_path), "water_rhf_opt.molden")).read()
    assert "[MO]" in molden and "[GTO]" in molden
    assert "[GEOMETRIES]" not in molden
    opt_molden = open(os.path.join(str(tmp_path), "water_rhf_opt_opt.molden")).read()
    assert "[GEOMETRIES] (XYZ)" in opt_molden


def test_moread_restart(tmp_path):
    """The .dat of one run is a valid MOREAD restart for the next one."""
    code, out1 = run("water_rhf_opt", tmp_path)
    assert code == 0
    dat = open(os.path.join(str(tmp_path), "water_rhf_opt.dat")).read()
    norb = int(dat.split("NORB=")[1].split()[0])
    inp = tmp_path / "restart.inp"
    inp.write_text(" $CONTRL SCFTYP=RHF RUNTYP=ENERGY $END\n"
                   " $BASIS GBASIS=N31 NGAUSS=6 NDFUNC=1 $END\n"
                   " $GUESS GUESS=MOREAD NORB=%d $END\n" % norb + dat)
    assert main([str(inp), "-o", str(tmp_path), "-q", "-n", "4"]) == 0
    text = open(os.path.join(str(tmp_path), "restart.out")).read()
    out2 = parse_out(os.path.join(str(tmp_path), "restart.out"))
    assert out2["energy"] == pytest.approx(out1["energy"], abs=1e-8)
    assert "SCF converged in 1 iterations" in text or "SCF converged in 2 iterations" in text


def test_lowdin_and_bond_orders_rhf(tmp_path):
    inp = tmp_path / "water_rhf.inp"
    inp.write_text(""" $CONTRL SCFTYP=RHF RUNTYP=ENERGY ISPHER=-1 $END
 $BASIS GBASIS=N31 NGAUSS=6 NDFUNC=1 $END
 $DATA
Water
C1
O 8.0 0 0 0.117
H 1.0 0 0.757 -0.467
H 1.0 0 -0.757 -0.467
 $END
""")
    assert main([str(inp), "-o", str(tmp_path), "-q"]) == 0
    out_file = str(tmp_path / "water_rhf.out")
    parsed = parse_out(out_file)
    text = open(out_file).read()
    assert parsed["bond_orders"][(1, 2)] == pytest.approx(0.786, abs=0.005)
    assert parsed["bond_orders"][(1, 3)] == pytest.approx(0.786, abs=0.005)
    assert "LOWDIN" in text
    assert "BOND ORDER AND VALENCE ANALYSIS" in text
    assert "TOTAL VALENCE" in text and "BONDED VALENCE" in text and "FREE VALENCE" in text


def test_lowdin_and_bond_orders_uhf(tmp_path):
    inp = tmp_path / "water_cat.inp"
    inp.write_text(""" $CONTRL SCFTYP=UHF ICHARG=1 MULT=2 RUNTYP=ENERGY ISPHER=-1 $END
 $BASIS GBASIS=N31 NGAUSS=6 NDFUNC=1 $END
 $DATA
Water cation
C1
O 8.0 0 0 0.117
H 1.0 0 0.757 -0.467
H 1.0 0 -0.757 -0.467
 $END
""")
    assert main([str(inp), "-o", str(tmp_path), "-q"]) == 0
    out_file = str(tmp_path / "water_cat.out")
    parsed = parse_out(out_file)
    text = open(out_file).read()
    assert parsed["bond_orders"][(1, 2)] == pytest.approx(0.639, abs=0.005)
    assert "SPIN(LOWD)" in text
    assert "SPIN(MULL)" in text


def test_force_projct(tmp_path):
    inp_unproj = tmp_path / "water_unproj.inp"
    inp_unproj.write_text(""" $CONTRL SCFTYP=RHF RUNTYP=HESSIAN $END
 $FORCE PROJCT=.FALSE. $END
 $BASIS GBASIS=STO NGAUSS=3 $END
 $DATA
Water
C1
O 8.0 0 0 0.117
H 1.0 0 0.757 -0.467
H 1.0 0 -0.757 -0.467
 $END
""")
    assert main([str(inp_unproj), "-o", str(tmp_path), "-q"]) == 0
    out_unproj = parse_out(str(tmp_path / "water_unproj.out"))
    assert len(out_unproj["freqs"]) == 9

    inp_proj = tmp_path / "water_proj.inp"
    inp_proj.write_text(""" $CONTRL SCFTYP=RHF RUNTYP=HESSIAN $END
 $FORCE PROJCT=.TRUE. $END
 $BASIS GBASIS=STO NGAUSS=3 $END
 $DATA
Water
C1
O 8.0 0 0 0.117
H 1.0 0 0.757 -0.467
H 1.0 0 -0.757 -0.467
 $END
""")
    assert main([str(inp_proj), "-o", str(tmp_path), "-q"]) == 0
    out_proj = parse_out(str(tmp_path / "water_proj.out"))
    assert len(out_proj["freqs"]) == 3
    assert os.path.exists(str(tmp_path / "water_proj_freq.molden"))
    assert "[FREQ]" in open(str(tmp_path / "water_proj_freq.molden")).read()
    assert "[FREQ]" not in open(str(tmp_path / "water_proj.molden")).read()
