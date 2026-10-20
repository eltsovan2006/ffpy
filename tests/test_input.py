"""Parser, defaults, basis/xc mapping, symmetry, dispatcher: no SCF needed."""

import numpy as np
import pytest

from ffpy.basis_map import basis_name
from ffpy.dispatcher import select
from ffpy.errors import InputError, UnsupportedError
from ffpy.job import build_job
from ffpy.parser import parse_input
from ffpy.symmetry import expand, generators, group_elements
from ffpy.xc_map import xc_for

WATER = """ $DATA
Water
C1
O  8.0   0.000   0.000   0.117
H  1.0   0.000   0.757  -0.467
H  1.0   0.000  -0.757  -0.467
 $END
"""


def deck(head):
    return parse_input(head + WATER)


def test_spec_example_parses():
    d = deck(" $CONTRL SCFTYP=RHF RUNTYP=OPTIMIZE ICHARG=0 MULT=1 $END\n"
             " $SYSTEM MWORDS=50 $END\n"
             " $BASIS  GBASIS=N31 NGAUSS=6 NDFUNC=1 $END\n")
    job = build_job(d)
    assert job.basis == "6-31g(d)"
    assert job.runtyp == "OPTIMIZE" and job.method == "HF"
    assert job.memory_mb == 400
    assert job.cart  # GAMESS default ISPHER=-1
    assert len(job.labels) == 3
    assert select(job).__name__ == "optimize_hf"


def test_case_comments_and_multiline():
    d = deck(" $contrl scftyp=uhf   ! comment\n"
             "   mult=2 icharg=1\n"
             " $end\n $basis gbasis=n31 ngauss=6 $end\n")
    job = build_job(d)
    assert job.scftyp == "UHF" and job.mult == 2 and job.charge == 1


def test_defaults_are_reported():
    job = build_job(deck(" $BASIS GBASIS=STO NGAUSS=3 $END\n"))
    assert "$CONTRL SCFTYP=RHF" in job.defaults
    assert "$CONTRL RUNTYP=ENERGY" in job.defaults


def test_unknown_group_and_key():
    with pytest.raises(InputError, match="unknown group"):
        deck(" $FOO A=1 $END\n $BASIS GBASIS=STO NGAUSS=3 $END\n")
    with pytest.raises(InputError, match="unknown keyword"):
        deck(" $CONTRL FOO=1 $END\n $BASIS GBASIS=STO NGAUSS=3 $END\n")


def test_bad_values():
    with pytest.raises(InputError, match="allowed values"):
        deck(" $CONTRL RUNTYP=SADPOINT $END\n")
    with pytest.raises(InputError, match="integer"):
        deck(" $CONTRL MULT=X $END\n")
    with pytest.raises(InputError, match="missing \\$END"):
        parse_input(" $CONTRL SCFTYP=RHF\n $BASIS GBASIS=STO $END\n" + WATER)


def test_unsupported_group():
    with pytest.raises(UnsupportedError, match="XMCQDPT2"):
        deck(" $XMCQDPT NSTATE=1 $END\n")


def test_ignored_key_warns():
    d = deck(" $CONTRL NPRINT=7 $END\n $BASIS GBASIS=STO NGAUSS=3 $END\n")
    assert any("NPRINT" in n for _, n in d.notes)


def test_rhf_open_shell_rejected():
    with pytest.raises(InputError, match="RHF requires MULT=1"):
        build_job(deck(" $CONTRL MULT=3 $END\n $BASIS GBASIS=STO NGAUSS=3 $END\n"))
    with pytest.raises(InputError, match="impossible"):
        build_job(deck(" $CONTRL SCFTYP=UHF MULT=2 $END\n $BASIS GBASIS=STO NGAUSS=3 $END\n"))


@pytest.mark.parametrize("args,name", [
    (("STO", 3), "sto-3g"),
    (("N21", 3), "3-21g"),
    (("N31", 6, 1), "6-31g(d)"),
    (("N31", 6, 1, 1), "6-31g(d,p)"),
    (("N31", 6, 1, 0, 0, True), "6-31+g(d)"),
    (("N31", 6, 1, 1, 0, True, True), "6-31++g(d,p)"),
    (("N311", 6, 2, 1, 1), "6-311g(2df,p)"),
    (("CCD",), "cc-pvdz"),
    (("ACCT",), "aug-cc-pvtz"),
])
def test_basis_map(args, name):
    assert basis_name(*args) == name


def test_basis_map_errors():
    with pytest.raises(InputError):
        basis_name("N31", None)
    with pytest.raises(InputError):
        basis_name("STO", 3, 1)
    with pytest.raises(UnsupportedError):
        basis_name("TZV", 6)


def test_xc_map():
    assert xc_for("B3LYP") == "b3lyp5"
    assert xc_for("PBE0") == "pbe0"
    with pytest.raises(InputError):
        xc_for("NOPE")


@pytest.mark.parametrize("group,order,n", [
    ("C1", None, 1), ("CS", None, 2), ("CI", None, 2), ("CNV", 2, 4), ("CNV", 3, 6),
    ("DNH", 2, 8), ("DNH", 6, 24), ("DND", 2, 8), ("D3D", None, None), ("TD", None, 24),
    ("OH", None, 48), ("S2N", 2, 4), ("CNH", 2, 4), ("T", None, 12), ("O", None, 24)])
def test_group_orders(group, order, n):
    if n is None:
        with pytest.raises(UnsupportedError):
            generators(group, order)
        return
    assert len(group_elements(generators(group, order))) == n


def test_expand_methane_benzene():
    atoms, _ = expand([("C", 6, [0, 0, 0]), ("H", 1, [0.63, 0.63, 0.63])], "TD", None)
    assert [a[0] for a in atoms] == ["C", "H", "H", "H", "H"]
    atoms, _ = expand([("C", 6, [1.395, 0, 0]), ("H", 1, [2.481, 0, 0])], "DNH", 6)
    assert len(atoms) == 12
    r = [np.linalg.norm(a[2]) for a in atoms if a[0] == "C"]
    assert np.allclose(r, 1.395)


def test_symmetry_in_data():
    d = parse_input(" $BASIS GBASIS=STO NGAUSS=3 $END\n $DATA\nWater\nCNV 2\n\n"
                    "O 8.0 0 0 0.117\nH 1.0 0 0.757 -0.467\n $END\n")
    job = build_job(d)
    assert job.labels == ["O", "H", "H"]
    assert job.nsym_ops == 4


def test_dispatcher_rejects():
    job = build_job(deck(" $CONTRL SCFTYP=ROHF ICHARG=1 MULT=2 RUNTYP=HESSIAN $END\n"
                         " $BASIS GBASIS=STO NGAUSS=3 $END\n"))
    with pytest.raises(UnsupportedError):
        select(job)
    job = build_job(deck(" $CONTRL MPLEVL=2 RUNTYP=HESSIAN $END\n $BASIS GBASIS=STO NGAUSS=3 $END\n"))
    with pytest.raises(UnsupportedError):
        select(job)


def test_casscf_checks():
    with pytest.raises(InputError, match="electrons"):
        build_job(deck(" $CONTRL SCFTYP=MCSCF $END\n $BASIS GBASIS=STO NGAUSS=3 $END\n"
                       " $DET NCORE=3 NACT=4 NELS=6 $END\n"))
    job = build_job(deck(" $CONTRL SCFTYP=MCSCF $END\n $BASIS GBASIS=STO NGAUSS=3 $END\n"
                         " $DET NCORE=3 NACT=4 NELS=4 $END\n"))
    assert job.method == "CASSCF"
