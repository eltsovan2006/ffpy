"""Semiempirical NDDO methods (MNDO, AM1, PM3, RM1) against numbers printed by Firefly."""

import os

import numpy as np
import pytest

from ffpy.cli import main
from ffpy.dispatcher import select
from ffpy.errors import UnsupportedError
from ffpy.job import build_job
from ffpy.nddo import A0, NDDO
from ffpy.outparse import parse_out
from ffpy.parser import parse_input


def _sih3(r=1.15, a=110.0):
    th = np.radians(a)
    cb = np.sqrt((1 + 2 * np.cos(th)) / 3)
    sb = np.sqrt(1 - cb ** 2)
    xyz = [[0, 0, 0]] + [[r * sb * np.cos(2 * np.pi * k / 3), r * sb * np.sin(2 * np.pi * k / 3), -r * cb]
                         for k in range(3)]
    return np.array(xyz) / A0


@pytest.mark.parametrize("method,hof", [("MNDO", 105.14088), ("AM1", 93.45997), ("PM3", 46.89387)])
def test_silyl_anion_heat_of_formation(method, hof):
    mol = NDDO(method, [14, 1, 1, 1], _sih3(), charge=-1)
    mol.scf()
    assert mol.heat_kcal == pytest.approx(hof, abs=1e-3)


def test_ammonia_am1_energy():
    xyz = np.array([[0, 0, 0], [-0.4882960784, 0.8457536168, 0], [-0.4882960784, -0.8457536168, 0],
                    [0.9765921567, 0, 0]])
    mol = NDDO("AM1", [7, 1, 1, 1], xyz / A0 * 0.52917721067 / 0.52917721067)
    mol.scf()
    assert mol.etot_ev / 27.21165 == pytest.approx(-9.1286961082, abs=2e-6)


def test_semi_input_is_dispatched():
    job = build_job(parse_input(" $CONTRL RUNTYP=OPTIMIZE $END\n $BASIS GBASIS=PM3 $END\n $DATA\nt\nC1\nO 8.0 0 0 0\n"
                                "H 1.0 0 0 0.96\nH 1.0 0.9 0 -0.3\n $END\n"))
    assert job.method == "SEMI" and job.semi == "PM3"
    assert select(job).__name__ == "semi"


def test_semi_rohf_is_refused(tmp_path):
    inp = tmp_path / "t.inp"
    inp.write_text(" $CONTRL SCFTYP=ROHF MULT=2 $END\n $BASIS GBASIS=AM1 $END\n $DATA\nt\nC1\nC 6.0 0 0 0\nH 1.0 0 0 1.1\n"
                   "H 1.0 0 1.0 -0.4\nH 1.0 0.9 -0.5 -0.4\n $END\n")
    assert main([str(inp), "-o", str(tmp_path), "-q"]) != 0


def test_exam23_pm3_optimization(tmp_path):
    inp = tmp_path / "sih3.inp"
    inp.write_text(""" $CONTRL SCFTYP=RHF RUNTYP=OPTIMIZE COORD=ZMT ICHARG=-1 $END
 $BASIS GBASIS=PM3 $END
 $DATA
Silyl anion
Cnv 3

Si
H  1  rSiH
H  1  rSiH  2 aHSiH
H  1  rSiH  2 aHSiH  3   aHSiH  -1

rSiH=1.15
aHSiH=110.0
 $END
""")
    assert main([str(inp), "-o", str(tmp_path), "-q"]) == 0
    out = parse_out(str(tmp_path / "sih3.out"))
    assert out["energy"] == pytest.approx(-4.3587033972, abs=1e-6)


def test_drc_conserves_energy_and_matches_firefly_exam27(tmp_path):
    inp = tmp_path / "nh3.inp"
    inp.write_text(""" $CONTRL SCFTYP=RHF RUNTYP=DRC $END
 $BASIS  GBASIS=AM1 $END
 $DRC NSTEP=10 DELTAT=0.1 EKIN=1.0
   VEL(1)=0.0 0.0 -0.1128,
          0.0 0.0 0.5213,
          0.0 0.0 0.5213,
          0.0 0.0 0.5213
 $END
 $DATA
ammonia...DRC starting from the planar transition state
C1
NITROGEN    7.0   0.0000000000   0.0000000000   0.0000000000
HYDROGEN    1.0  -0.4882960784   0.8457536168   0.0000000000
HYDROGEN    1.0  -0.4882960784  -0.8457536168   0.0000000000
HYDROGEN    1.0   0.9765921567   0.0000000000   0.0000000000
 $END
""")
    assert main([str(inp), "-o", str(tmp_path), "-q"]) == 0
    text = (tmp_path / "nh3.out").read_text()
    totals = [float(l.split("TOTAL")[1]) for l in text.splitlines() if l.strip().startswith("TIME")]
    assert len(totals) == 11 and max(totals) - min(totals) < 1e-6
    out = parse_out(str(tmp_path / "nh3.out"))
    assert out["energy"] == pytest.approx(-9.1287351998, abs=1e-6)


def test_zapt2_methylnitrene_energy(tmp_path):
    """ZAPT2/6-31G* single point of triplet CH3N at the exam34 starting geometry (Firefly: E(ZAPT) -0.2336161903)."""
    inp = tmp_path / "ch3n.inp"
    inp.write_text(""" $CONTRL SCFTYP=ROHF MULT=3 RUNTYP=ENERGY MPLEVL=2 COORD=ZMT $END
 $BASIS  GBASIS=N31 NGAUSS=6 NDFUNC=1 NPFUNC=0 $END
 $GUESS  GUESS=HUCKEL $END
 $MP2 OSPT=ZAPT $END
 $DATA
Methylnitrene
Cnv 3

N
C  1  rCN
H  2  rCH  1  aHCN
H  2  rCH  1  aHCN  3  120.0
H  2  rCH  1  aHCN  3 -120.0

rCN=1.4329216
rCH=1.0876477
aHCN=110.21928
 $END
""")
    assert main([str(inp), "-o", str(tmp_path), "-q"]) == 0
    out = parse_out(str(tmp_path / "ch3n.out"))
    assert out["energy"] == pytest.approx(-93.9955428414 - 0.2336161903, abs=3e-7)
