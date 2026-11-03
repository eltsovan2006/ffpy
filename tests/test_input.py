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


def test_zmat_schema_and_options():
    # Valid ZMAT with Cartesian coords
    d = deck(" $CONTRL NZVAR=3 $END\n"
             " $ZMAT DLC=.T. AUTO=.T. $END\n"
             " $BASIS GBASIS=STO NGAUSS=3 $END\n")
    job = build_job(d)
    assert job.coord == "UNIQUE"
    assert job.nzvar == 3
    assert job.dlc is True
    assert job.auto is True

    # Valid ZMAT with COORD=ZMT
    z_inp = (" $CONTRL COORD=ZMT NZVAR=3 $END\n"
             " $ZMAT DLC=.T. AUTO=.T. $END\n"
             " $BASIS GBASIS=STO NGAUSS=3 $END\n"
             " $DATA\nH2O\nC1\nO\nH 1 0.96\nH 1 0.96 2 104.5\n $END\n")
    job_z = build_job(parse_input(z_inp))
    assert job_z.coord == "ZMT"
    assert job_z.nzvar == 3

    # COORD=ZMTMPC
    mpc_inp = (" $CONTRL COORD=ZMTMPC $END\n"
               " $BASIS GBASIS=STO NGAUSS=3 $END\n"
               " $DATA\nH2O\nC1\nO\nH 0.96 0\nH 0.96 0 104.5 0 1 2\n $END\n")
    job2 = build_job(parse_input(mpc_inp))
    assert job2.coord == "ZMTMPC"

    # Unsupported IFREEZ in ZMAT
    with pytest.raises(UnsupportedError, match="IFREEZ"):
        d_f = deck(" $ZMAT IFREEZ(1)=1,2 $END\n $BASIS GBASIS=STO NGAUSS=3 $END\n")
        build_job(d_f)

    # Unsupported SCAN in ZMAT
    with pytest.raises(UnsupportedError, match="SCAN"):
        d_s = deck(" $ZMAT SCAN=BOND $END\n $BASIS GBASIS=STO NGAUSS=3 $END\n")
        build_job(d_s)

    # Negative NZVAR
    with pytest.raises(InputError, match="NZVAR"):
        d_n = deck(" $CONTRL NZVAR=-1 $END\n $BASIS GBASIS=STO NGAUSS=3 $END\n")
        build_job(d_n)



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
    # Firefly manual: plain B3LYP defaults to B3LYP1 (VWN formula 1 RPA); $DFT B3LYP=GAMESS selects formula 5
    assert xc_for("B3LYP") == "b3lypg"
    assert xc_for("B3LYP", "NWCHEM") == "b3lypg"
    assert xc_for("B3LYP", "GAMESS") == "b3lyp5"
    assert xc_for("B3LYP1") == "b3lypg"
    assert xc_for("B3LYP5") == "b3lyp5"
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


def test_statpt_firefly_keys_accepted():
    d = deck(" $CONTRL RUNTYP=OPTIMIZE $END\n"
             " $STATPT METHOD=GDIIS OPTTOL=1D-6 NSTEP=2000 DXMAX=0.1 TRMAX=0.3 IDUMP=2 $END\n"
             " $BASIS GBASIS=STO NGAUSS=3 $END\n")
    job = build_job(d)
    assert job.nstep == 2000
    assert job.opttol == 1e-6
    notes = [msg for kind, msg in d.notes if kind == "warning"]
    assert any("DXMAX" in n for n in notes)
    assert any("TRMAX" in n for n in notes)
    assert any("IDUMP" in n for n in notes)


def test_force_projct_parsed():
    d1 = deck(" $CONTRL RUNTYP=HESSIAN $END\n"
              " $FORCE PROJCT=.FALSE. $END\n"
              " $BASIS GBASIS=STO NGAUSS=3 $END\n")
    job1 = build_job(d1)
    assert job1.projct is False

    d2 = deck(" $CONTRL RUNTYP=HESSIAN $END\n"
              " $FORCE PROJCT=.TRUE. $END\n"
              " $BASIS GBASIS=STO NGAUSS=3 $END\n")
    job2 = build_job(d2)
    assert job2.projct is True


def test_system_memory_and_mwords():
    # MEMORY only
    d1 = deck(" $SYSTEM MEMORY=200000 $END\n $BASIS GBASIS=STO NGAUSS=3 $END\n")
    job1 = build_job(d1)
    assert job1.memory_mb == pytest.approx(200000 * 8e-6)
    notes1 = [msg for kind, msg in d1.notes if kind == "warning"]
    assert any("$SYSTEM MEMORY=" in n and "converted to MWORDS=" in n for n in notes1)

    # MWORDS has precedence when both are given
    d2 = deck(" $SYSTEM MWORDS=100 MEMORY=200000 $END\n $BASIS GBASIS=STO NGAUSS=3 $END\n")
    job2 = build_job(d2)
    assert job2.memory_mb == 800.0
    notes2 = [msg for kind, msg in d2.notes if kind == "warning"]
    assert any("takes precedence" in n for n in notes2)


def test_system_and_smp_ignored_keys():
    d = deck(" $SYSTEM MEMDDI=100 KDIAG=3 NOJAC=1 PARALL=.T. MKLNP=2 NP=4 CORE=1 BALNCS=1 XDLB=1 $END\n"
             " $SMP HTTNP=2 MKLNP=2 NP=4 CALL64=1 $END\n"
             " $BASIS GBASIS=STO NGAUSS=3 $END\n")
    job = build_job(d)
    notes = [msg for kind, msg in d.notes if kind == "warning"]
    for key in ("MEMDDI", "KDIAG", "NOJAC", "PARALL", "MKLNP", "NP", "CORE", "BALNCS", "XDLB"):
        assert any(f"$SYSTEM {key}=" in n and "is accepted but has no effect in ffpy" in n for n in notes)
    for key in ("HTTNP", "MKLNP", "NP", "CALL64"):
        assert any(f"$SMP {key}=" in n and "is accepted but has no effect in ffpy" in n for n in notes)

    # Unknown key in $SMP should raise InputError
    with pytest.raises(InputError, match="unknown keyword"):
        deck(" $SMP UNKNOWN_KEY=1 $END\n $BASIS GBASIS=STO NGAUSS=3 $END\n")


def test_contrl_wide_ignored():
    d = deck(" $CONTRL WIDE=.TRUE. $END\n $BASIS GBASIS=STO NGAUSS=3 $END\n")
    job = build_job(d)
    notes = [msg for kind, msg in d.notes if kind == "warning"]
    assert any("$CONTRL WIDE=" in n and "is accepted but has no effect in ffpy" in n for n in notes)


def test_boolean_literals():
    for val in ("1", "0", ".T.", ".F.", ".TRUE.", ".FALSE.", "T", "F", "TRUE", "FALSE"):
        d = deck(f" $SCF DIRSCF={val} $END\n $BASIS GBASIS=STO NGAUSS=3 $END\n")
        job = build_job(d)
        expected = val in ("1", ".T.", ".TRUE.", "T", "TRUE")
        assert job.direct is expected

    # Non-boolean integer keys must still require an integer and not accept booleans
    with pytest.raises(InputError, match="integer"):
        deck(" $CONTRL MULT=.TRUE. $END\n $BASIS GBASIS=STO NGAUSS=3 $END\n")

    # Invalid boolean values should raise InputError
    with pytest.raises(InputError, match=r"\.TRUE\. or \.FALSE\."):
        deck(" $SCF DIRSCF=2 $END\n $BASIS GBASIS=STO NGAUSS=3 $END\n")
    with pytest.raises(InputError, match=r"\.TRUE\. or \.FALSE\."):
        deck(" $SCF DIRSCF=INVALID $END\n $BASIS GBASIS=STO NGAUSS=3 $END\n")


def test_data_incomplete_coordinates():
    inp = """ $BASIS GBASIS=STO NGAUSS=3 $END
 $DATA
Test Incomplete Coords
C1
O  8.0
H  1.0  0.757
N  7.0  0.100  0.200
C  6.0  0.100  0.200  0.300
 $END
"""
    d = parse_input(inp)
    job = build_job(d)
    assert len(job.labels) == 4
    # O (only name Z) -> [0, 0, 0]
    np.testing.assert_allclose(job.coords[0], [0.0, 0.0, 0.0])
    # H (name Z X) -> [X*scale, 0, 0]
    assert job.coords[1][0] != 0.0
    assert job.coords[1][1] == 0.0
    assert job.coords[1][2] == 0.0
    # N (name Z X Y) -> [X*scale, Y*scale, 0]
    assert job.coords[2][0] != 0.0
    assert job.coords[2][1] != 0.0
    assert job.coords[2][2] == 0.0
    # C (name Z X Y Z) -> [X*scale, Y*scale, Z*scale]
    assert job.coords[3][2] != 0.0

    # < 2 tokens -> InputError
    inp_short = """ $BASIS GBASIS=STO NGAUSS=3 $END
 $DATA
Title
C1
O
 $END
"""
    with pytest.raises(InputError, match=r"\$DATA: atom line"):
        build_job(parse_input(inp_short))

    # > 5 tokens -> UnsupportedError
    inp_long = """ $BASIS GBASIS=STO NGAUSS=3 $END
 $DATA
Title
C1
O 8.0 0.0 0.0 0.0 1.0
 $END
"""
    with pytest.raises(UnsupportedError, match=r"\$DATA: extra fields"):
        build_job(parse_input(inp_long))


def test_strict_rejection_of_unsupported_physics():
    with pytest.raises(InputError, match="CITYP"):
        deck(" $CONTRL CITYP=GUGA $END\n $BASIS GBASIS=STO NGAUSS=3 $END\n")
    with pytest.raises(InputError, match="MPLEVL"):
        deck(" $CONTRL MPLEVL=5 $END\n $BASIS GBASIS=STO NGAUSS=3 $END\n")
    with pytest.raises(InputError, match="COORD"):
        deck(" $CONTRL COORD=FOO $END\n $BASIS GBASIS=STO NGAUSS=3 $END\n")
    with pytest.raises(InputError, match="NZVAR"):
        build_job(deck(" $CONTRL NZVAR=-1 $END\n $BASIS GBASIS=STO NGAUSS=3 $END\n"))
    with pytest.raises(InputError, match="DFTTYP"):
        deck(" $CONTRL DFTTYP=D-PBEP86 $END\n $BASIS GBASIS=STO NGAUSS=3 $END\n")
    with pytest.raises(UnsupportedError, match=r"\$ECP"):
        deck(" $ECP $END\n $BASIS GBASIS=STO NGAUSS=3 $END\n")



EXPLICIT_BASIS = """ $CONTRL SCFTYP=RHF D5=.T. CITYP=TDHF $END
 $TDHF NSTATE=3 ISTSYM=1 ISTATE=-2 MULT=3 $END
 $DATA
H2O
CNV 2

O 8.0 0.0 0.0 0.0
   S 1
     1  5.0  1.0
   L 2
     1  2.0  0.5  0.6
     2  0.5  0.5  0.4

H 1.0 0.0 0.76 0.59
   S 1
     1  1.0  1.0

 $END
"""


def test_explicit_basis_in_data_and_tdhf_keywords():
    job = build_job(parse_input(EXPLICIT_BASIS))
    assert job.atom_tags == ["O1", "H2", "H2"]          # symmetry images share a basis tag
    assert job.basis["O1"] == [[0, [5.0, 1.0]], [0, [2.0, 0.5], [0.5, 0.5]], [1, [2.0, 0.6], [0.5, 0.4]]]
    assert job.cart is False                              # D5=.T.
    ex = job.excited
    assert (ex["kind"], ex["nstate"], ex["iroot"], ex["triplet"], ex["istsym"]) == ("TDHF", 3, 2, True, 1)


def test_cityp_tddft_needs_dfttyp():
    with pytest.raises(InputError):
        build_job(parse_input(EXPLICIT_BASIS.replace("CITYP=TDHF", "CITYP=TDDFT")))


def test_sto2g_hydrogen_matches_published_fit():
    from ffpy.basis_map import sto2g_shells
    (shell,) = sto2g_shells("H")
    exps = [e for e, _ in shell[1:]]
    coefs = [c for _, c in shell[1:]]
    assert exps == pytest.approx([1.309756377, 0.2331359749], rel=1e-5)
    assert coefs == pytest.approx([0.4301284983, 0.6789135305], rel=1e-6)


def test_basis_library_keyword_and_extra_shells_in_data():
    text = """ $CONTRL SCFTYP=RHF ICHARG=-1 $END
 $DATA
t
C1
Oxygen 8.0 0 0 0
   N21 3
   D 1
     1 0.8 1.0

Hydrogen 1.0 0 0 1.8
   N21 3

 $END
"""
    job = build_job(parse_input(text))
    # 3-21G oxygen (3 s + 2 p shells) plus one added d shell
    assert [sh[0] for sh in job.basis["O1"]] == [0, 0, 0, 1, 1, 2]
    assert job.atom_tags == ["O1", "H2"]


def test_mp3_mp4_job():
    base = " $BASIS GBASIS=STO NGAUSS=3 $END\n $DATA\nt\nC1\nHe 2.0 0 0 0\n $END\n"
    job = build_job(parse_input(" $CONTRL MPLEVL=3 $END\n" + base))
    assert job.method == "MP3"
    job = build_job(parse_input(" $CONTRL MPLEVL=4 $END\n $MP4 SDTQ=.T. $END\n" + base))
    assert job.method == "MP4" and job.mp4["sdtq"]
    with pytest.raises(UnsupportedError, match="RHF"):
        build_job(parse_input(" $CONTRL MPLEVL=4 SCFTYP=UHF MULT=1 $END\n" + base))


def test_gvb_one_pair_is_cas22():
    base = (" $BASIS GBASIS=STO NGAUSS=2 $END\n $DATA\nt\nCnv 2\n\nO 8.0 0 0 0.1\nH 1.0 0 0.75 -0.5\n $END\n")
    job = build_job(parse_input(" $CONTRL SCFTYP=GVB $END\n $SCF NCO=4 NPAIR=1 $END\n" + base))
    assert job.method == "CASSCF" and (job.cas["nact"], job.cas["nels"], job.cas["ncore"]) == (2, 2, 4)
    with pytest.raises(UnsupportedError, match="NPAIR"):
        build_job(parse_input(" $CONTRL SCFTYP=GVB $END\n $SCF NCO=2 NPAIR=2 $END\n" + base))
