"""Tests for Z-matrix input parsing, NeRF coordinate conversion, and QC energies."""

import json
from pathlib import Path
import numpy as np
import pytest

from ffpy.constants import ANG_BOHR
from ffpy.errors import InputError, UnsupportedError
from ffpy.job import build_job
from ffpy.methods import compute, Context
from ffpy.parser import parse_input
from ffpy.zmatrix import (
    calc_angle,
    calc_dihedral,
    calc_distance,
    parse_zmatrix,
    verify_zmatrix,
)

REF_PATH = Path(__file__).parent / "reference.json"


def test_h2o_variables_and_reconstruction():
    """Water (C2v, H2O) with symbolic variables rOH and aHOH."""
    lines = [
        "O",
        "H 1 rOH",
        "H 1 rOH 2 aHOH",
        "",
        "rOH=0.9572",
        "aHOH=104.52",
    ]
    atoms, entries = parse_zmatrix(lines, units="ANGS", coord_style="ZMT")

    assert len(atoms) == 3
    assert atoms[0][0] == "O" and atoms[0][1] == 8
    assert atoms[1][0] == "H" and atoms[1][1] == 1
    assert atoms[2][0] == "H" and atoms[2][1] == 1

    coords = np.array([a[2] for a in atoms])
    verify_zmatrix(coords, entries, tol_dist=1e-10, tol_angle=1e-8)

    # Check bond lengths in Angstroms
    r_bohr = entries[1]["r"]
    r_ang = r_bohr / ANG_BOHR
    assert abs(r_ang - 0.9572) < 1e-12

    # Check angle
    ang = entries[2]["angle"]
    assert abs(ang - 104.52) < 1e-10


def test_ch4_named_atoms():
    """Methane (Td, CH4) with named atoms C1, H1, H2, H3, H4."""
    lines = [
        "C1",
        "H1 C1 rCH",
        "H2 C1 rCH H1 aHCH",
        "H3 C1 rCH H1 aHCH H2  120.0",
        "H4 C1 rCH H1 aHCH H2 -120.0",
        "",
        "rCH 1.0890",
        "aHCH 109.47122063",
    ]
    atoms, entries = parse_zmatrix(lines, units="ANGS", coord_style="ZMT")

    assert len(atoms) == 5
    coords = np.array([a[2] for a in atoms])
    verify_zmatrix(coords, entries, tol_dist=1e-10, tol_angle=1e-8)

    # Check tetrahedral symmetry: all C-H distances identical, all H-C-H angles identical
    r_c = coords[0]
    ch_dists = [calc_distance(coords[i], r_c) / ANG_BOHR for i in range(1, 5)]
    for d in ch_dists:
        assert abs(d - 1.0890) < 1e-10

    # Pairwise H-C-H angles
    for i in range(1, 5):
        for j in range(i + 1, 5):
            ang = calc_angle(coords[i], r_c, coords[j])
            assert abs(ang - 109.47122063) < 1e-5


def test_ethylene_planar_dihedrals():
    """Ethylene (D2h, C2H4) with 0 and 180 degree dihedrals."""
    lines = [
        "C1",
        "C2 C1 rCC",
        "H1 C1 rCH C2 aCCH",
        "H2 C1 rCH C2 aCCH H1 180.0",
        "H3 C2 rCH C1 aCCH H1 0.0",
        "H4 C2 rCH C1 aCCH H1 180.0",
        "",
        "rCC=1.339",
        "rCH=1.085",
        "aCCH=121.3",
    ]
    atoms, entries = parse_zmatrix(lines, units="ANGS", coord_style="ZMT")

    assert len(atoms) == 6
    coords = np.array([a[2] for a in atoms])
    verify_zmatrix(coords, entries, tol_dist=1e-10, tol_angle=1e-8)

    # All atoms should be strictly coplanar (distance to plane < 1e-10)
    pC1, pC2, pH1 = coords[0], coords[1], coords[2]
    normal = np.cross(pC2 - pC1, pH1 - pC1)
    normal /= np.linalg.norm(normal)
    for a in coords:
        dist_to_plane = abs(np.dot(a - pC1, normal))
        assert dist_to_plane < 1e-10


def test_ethane_torsion_sign():
    """Ethane staggered conformation with nonzero dihedral angle (torsion sign)."""
    lines = [
        "C1",
        "C2 C1 1.530",
        "H1 C1 1.090 C2 110.0",
        "H2 C1 1.090 C2 110.0 H1  120.0",
        "H3 C1 1.090 C2 110.0 H1 -120.0",
        "H4 C2 1.090 C1 110.0 H1   60.0",
        "H5 C2 1.090 C1 110.0 H1  180.0",
        "H6 C2 1.090 C1 110.0 H1  -60.0",
    ]
    atoms, entries = parse_zmatrix(lines, units="ANGS", coord_style="ZMT")

    assert len(atoms) == 8
    coords = np.array([a[2] for a in atoms])
    verify_zmatrix(coords, entries, tol_dist=1e-10, tol_angle=1e-8)

    # Check IUPAC dihedral directly for H4-C2-C1-H1: should be +60.0
    dih_measured = calc_dihedral(coords[2], coords[0], coords[1], coords[5])
    diff = (dih_measured - 60.0 + 180.0) % 360.0 - 180.0
    assert abs(diff) < 1e-8


def test_linear_molecules_with_dummy_atom():
    """Linear CO2 and HCN using dummy ghost atom X."""
    lines_co2 = [
        "X",
        "C 1 1.0",
        "O1 2 1.160 1 90.0",
        "O2 2 1.160 1 90.0 3 180.0",
    ]
    atoms_co2, entries_co2 = parse_zmatrix(lines_co2, units="ANGS", coord_style="ZMT")

    # Dummy atom X should be removed from the final molecule
    assert len(atoms_co2) == 3
    assert [a[0] for a in atoms_co2] == ["C", "O1", "O2"]
    assert [a[1] for a in atoms_co2] == [6, 8, 8]

    # Verify that O1-C-O2 is perfectly linear (180 degrees)
    coords_co2 = np.array([a[2] for a in atoms_co2])
    ang = calc_angle(coords_co2[1], coords_co2[0], coords_co2[2])
    assert abs(ang - 180.0) < 1e-8

    # HCN with dummy atom X
    lines_hcn = [
        "X",
        "C 1 1.0",
        "N 2 1.155 1 90.0",
        "H 2 1.065 1 90.0 3 180.0",
    ]
    atoms_hcn, entries_hcn = parse_zmatrix(lines_hcn, units="ANGS", coord_style="ZMT")
    assert len(atoms_hcn) == 3
    assert [a[0] for a in atoms_hcn] == ["C", "N", "H"]
    coords_hcn = np.array([a[2] for a in atoms_hcn])
    ang_hcn = calc_angle(coords_hcn[1], coords_hcn[0], coords_hcn[2])
    assert abs(ang_hcn - 180.0) < 1e-8


def test_two_bond_angles_format():
    """Alternative format with two bond angles (i4 = +/- 1)."""
    lines = [
        "Si",
        "H1 1 rSiH",
        "H2 1 rSiH 2 aHSiH",
        "H3 1 rSiH 2 aHSiH 3 aHSiH -1",
        "",
        "rSiH=1.15",
        "aHSiH=110.0",
    ]
    atoms, entries = parse_zmatrix(lines, units="ANGS", coord_style="ZMT")

    assert len(atoms) == 4
    coords = np.array([a[2] for a in atoms])
    verify_zmatrix(coords, entries, tol_dist=1e-10, tol_angle=1e-8)

    # Check all three H-Si-H angles are equal to 110.0
    r_si = coords[0]
    ang12 = calc_angle(coords[1], r_si, coords[2])
    ang13 = calc_angle(coords[1], r_si, coords[3])
    ang23 = calc_angle(coords[2], r_si, coords[3])
    assert abs(ang12 - 110.0) < 1e-8
    assert abs(ang13 - 110.0) < 1e-8
    assert abs(ang23 - 110.0) < 1e-8


def test_mopac_style_zmtmpc():
    """MOPAC-style ZMTMPC card sequence M parsing."""
    lines = [
        "C",
        "O 1.20 0",
        "O 1.34 0 120.0 0 1 2",
        "H 1.08 0 110.0 0 180.0 0 1 2 3",
        "H 0.98 0 105.0 0   0.0 0 3 1 2",
    ]
    atoms, entries = parse_zmatrix(lines, units="ANGS", coord_style="ZMTMPC")
    assert len(atoms) == 5
    coords = np.array([a[2] for a in atoms])
    verify_zmatrix(coords, entries, tol_dist=1e-10, tol_angle=1e-8)


def test_bohr_units():
    """UNITS=BOHR specifies bond lengths directly in atomic units."""
    lines = [
        "H",
        "H 1 1.40",
    ]
    atoms, entries = parse_zmatrix(lines, units="BOHR", coord_style="ZMT")
    coords = np.array([a[2] for a in atoms])
    d_bohr = calc_distance(coords[0], coords[1])
    assert abs(d_bohr - 1.40) < 1e-12


def test_energy_h2o_rhf_sto3g_vs_reference():
    """H2O RHF/STO-3G Z-matrix energy matches independent PySCF Cartesian reference."""
    inp = """ $CONTRL SCFTYP=RHF RUNTYP=ENERGY COORD=ZMT $END
 $BASIS GBASIS=STO NGAUSS=3 $END
 $DATA
Water RHF STO-3G ZMT
C1
O
H 1 rOH
H 1 rOH 2 aHOH

rOH=0.9572
aHOH=104.52
 $END
"""
    job = build_job(parse_input(inp))
    ctx = Context(job, log=lambda *args, **kwargs: None)
    res = compute(job, ctx)

    with open(REF_PATH, encoding="utf-8") as f:
        ref_data = json.load(f)

    ref_energy = ref_data["cases"]["h2o_zmt"]["energy"]
    tol = ref_data["tolerances"]["energy_hf_mp2"]

    assert abs(res.e_tot - ref_energy) < tol


def test_energy_ch4_rhf_631gd_vs_reference():
    """CH4 RHF/6-31G* Cartesian-d Z-matrix energy matches independent PySCF Cartesian reference."""
    inp = """ $CONTRL SCFTYP=RHF RUNTYP=ENERGY COORD=ZMT ISPHER=-1 $END
 $BASIS GBASIS=N31 NGAUSS=6 NDFUNC=1 $END
 $DATA
Methane RHF 6-31G* ZMT
C1
C1
H1 C1 rCH
H2 C1 rCH H1 aHCH
H3 C1 rCH H1 aHCH H2  120.0
H4 C1 rCH H1 aHCH H2 -120.0

rCH=1.0890
aHCH=109.47122063
 $END
"""
    job = build_job(parse_input(inp))
    ctx = Context(job, log=lambda *args, **kwargs: None)
    res = compute(job, ctx)

    with open(REF_PATH, encoding="utf-8") as f:
        ref_data = json.load(f)

    ref_energy = ref_data["cases"]["ch4_zmt"]["energy"]
    tol = ref_data["tolerances"]["energy_hf_mp2"]

    assert abs(res.e_tot - ref_energy) < tol


def test_optimize_nzvar_zero_cartesian():
    """NZVAR=0 with COORD=ZMT selects coordsys='cart'."""
    inp = """ $CONTRL SCFTYP=RHF RUNTYP=OPTIMIZE COORD=ZMT NZVAR=0 $END
 $BASIS GBASIS=STO NGAUSS=3 $END
 $STATPT NSTEP=1 OPTTOL=1E-4 $END
 $DATA
H2
C1
H
H 1 0.74
 $END
"""
    job = build_job(parse_input(inp))
    assert job.coord == "ZMT"
    assert job.nzvar == 0


def test_optimize_nzvar_greater_than_zero():
    """NZVAR>0 selects internal coordsys in geomeTRIC."""
    inp = """ $CONTRL SCFTYP=RHF RUNTYP=OPTIMIZE COORD=ZMT NZVAR=1 $END
 $ZMAT DLC=.T. AUTO=.T. $END
 $BASIS GBASIS=STO NGAUSS=3 $END
 $STATPT NSTEP=1 OPTTOL=1E-4 $END
 $DATA
H2
C1
H
H 1 0.74
 $END
"""
    job = build_job(parse_input(inp))
    assert job.coord == "ZMT"
    assert job.nzvar == 1
    assert job.dlc is True
    assert job.auto is True
