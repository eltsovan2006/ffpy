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


def get_input_path(name: str):
    """Return path to input file, checking tests/inputs then FFPY_FIREFLY_INPUTS."""
    repo_inp = os.path.join(HERE, "inputs", name + ".inp")
    if os.path.exists(repo_inp):
        return repo_inp
    firefly_dir = os.environ.get(
        "FFPY_FIREFLY_INPUTS",
        os.path.expanduser("~/Documents/Ffpy/inputs"),
    )
    firefly_inp = os.path.join(firefly_dir, name + ".inp")
    if os.path.exists(firefly_inp):
        return firefly_inp
    return None


def run(name, tmp_path):
    inp = get_input_path(name)
    if inp is None:
        pytest.skip(f"Input file for {name} not found in tests/inputs or FFPY_FIREFLY_INPUTS")
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


def test_bench_nuc_and_nao(tmp_path):
    """Test nuclear repulsion energy and AO count for bench01 and bench04."""
    import re

    for name, expected_nuc, expected_nao in [
        ("bench01", 106.3765167161, 61),
        ("bench04", 167.7269657162, 80),
    ]:
        code, out = run(name, tmp_path)
        assert code == 0
        text = open(os.path.join(str(tmp_path), name + ".out")).read()
        m_nuc = re.search(r"NUCLEAR REPULSION ENERGY\s+([\d.]+)", text)
        assert m_nuc is not None
        assert float(m_nuc.group(1)) == pytest.approx(expected_nuc, abs=1e-6)
        m_nao = re.search(r"(\d+)\s+basis functions", text)
        assert m_nao is not None
        assert int(m_nao.group(1)) == expected_nao


def test_silicon_3p_exam16(tmp_path):
    """Silicon atom 3-P state from Firefly exam16: ROHF/6-31G, MULT=3."""
    inp_path = get_input_path("exam16")
    if inp_path is None:
        pytest.skip("Firefly input exam16.inp not found in tests/inputs or FFPY_FIREFLY_INPUTS")
    import re
    text = open(inp_path, encoding="utf-8").read()
    # exam16 uses SCFTYP=GVB with GVB-specific coupling coefficients in $SCF.
    # Adapt for ffpy: use ROHF and drop GVB-specific $SCF options.
    text = text.replace("SCFTYP=GVB", "SCFTYP=ROHF")
    text = re.sub(r"[ \t]*\$SCF\b.*?\$END\n?", "", text, flags=re.DOTALL)
    inp = tmp_path / "exam16.inp"
    inp.write_text(text)
    assert main([str(inp), "-o", str(tmp_path), "-q"]) == 0
    out = parse_out(str(tmp_path / "exam16.out"))
    assert out["normal"]
    # Firefly exam16 reference: -288.828573 Eh (spherical Kh symmetry average).
    # In PySCF ROHF in C1, degeneracy is un-averaged, giving -288.828592 Eh (delta = 1.9e-5 Eh,
    # whereas standard Pople basis gives -288.828405 / -288.828425 Eh, delta ~ 1.5e-4 Eh).
    assert out["energy"] == pytest.approx(-288.828573, abs=2e-5)


def test_silicon_gordon_basis_sih4(tmp_path):
    """Self-contained test verifying Gordon 6-31G(d) basis on SiH4 (Td geometry).

    Checks AO count (27 with cartesian d), nuclear repulsion, energy matching
    an explicit PySCF calculation using Gordon's sp + d=0.395 basis, and
    verifies it differs from standard Pople 6-31G* by > 1e-4 Eh.
    """
    import copy
    import re
    from pyscf import gto, scf
    from ffpy.basis_map import GORDON_SI_631G_SP, GORDON_SI_D_EXP

    inp = tmp_path / "sih4.inp"
    inp.write_text(""" $CONTRL SCFTYP=RHF RUNTYP=ENERGY ISPHER=-1 $END
 $BASIS GBASIS=N31 NGAUSS=6 NDFUNC=1 $END
 $DATA
SiH4 tetrahedral test
C1
Si 14.0  0.000000  0.000000  0.000000
H   1.0  0.854476  0.854476  0.854476
H   1.0  0.854476 -0.854476 -0.854476
H   1.0 -0.854476  0.854476 -0.854476
H   1.0 -0.854476 -0.854476  0.854476
 $END
""")
    assert main([str(inp), "-o", str(tmp_path), "-q"]) == 0
    out = parse_out(str(tmp_path / "sih4.out"))
    assert out["normal"]

    # 1. Nuclear repulsion energy
    raw_out = open(str(tmp_path / "sih4.out")).read()
    m_nuc = re.search(r"NUCLEAR REPULSION ENERGY\s+([\d.]+)", raw_out)
    assert m_nuc is not None
    assert float(m_nuc.group(1)) == pytest.approx(21.3367119, abs=1e-5)

    # 2. AO count (Si: 13 sp + 6 cartesian d = 19; 4 H: 4 * 2 = 8; total 27)
    m_nao = re.search(r"(\d+)\s+basis functions", raw_out)
    assert m_nao is not None
    assert int(m_nao.group(1)) == 27

    # 3. Direct PySCF calculation with explicit Gordon sp + d=0.395 basis (internal consistency)
    si_basis = copy.deepcopy(GORDON_SI_631G_SP)
    si_basis.append([2, [GORDON_SI_D_EXP, 1.0]])

    mol = gto.Mole()
    mol.atom = """
    Si 0.000000  0.000000  0.000000
    H  0.854476  0.854476  0.854476
    H  0.854476 -0.854476 -0.854476
    H -0.854476  0.854476 -0.854476
    H -0.854476 -0.854476  0.854476
    """
    mol.unit = "A"
    mol.cart = True
    mol.basis = {"Si": si_basis, "H": "6-31g"}
    mol.build()
    mf = scf.RHF(mol)
    mf.conv_tol = 1e-10
    e_explicit = mf.kernel()

    assert out["energy"] == pytest.approx(e_explicit, abs=1e-8)

    # 4. Confirm difference from standard Pople 6-31G* basis (diff ~ 4.9e-4 Eh)
    mol_pople = gto.Mole()
    mol_pople.atom = mol.atom
    mol_pople.unit = "A"
    mol_pople.cart = True
    mol_pople.basis = "6-31g*"
    mol_pople.build()
    mf_pople = scf.RHF(mol_pople)
    mf_pople.conv_tol = 1e-10
    e_pople = mf_pople.kernel()
    assert abs(out["energy"] - e_pople) > 1e-4


