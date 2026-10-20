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
    for ext in (".out", ".molden", ".dat", ".xyz"):
        assert os.path.getsize(os.path.join(str(tmp_path), "water_rhf_opt" + ext)) > 0
    molden = open(os.path.join(str(tmp_path), "water_rhf_opt.molden")).read()
    assert "[MO]" in molden and "[GTO]" in molden and "[GEOMETRIES] (XYZ)" in molden


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
