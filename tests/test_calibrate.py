"""Tests for tools/calibrate.py calibration script."""

from pathlib import Path
import pytest

_CALIBRATE_PY = Path(__file__).resolve().parent.parent / "tools" / "calibrate.py"
if not _CALIBRATE_PY.exists():
    pytest.skip("tools/calibrate.py is a local calibration tool", allow_module_level=True)

from tools.calibrate import (
    parse_inp_comment,
    parse_firefly_out,
    classify_case,
    TOLERANCES,
)


def test_parse_inp_comment():
    text = """! EXAM01.
! 1-A-1 CH2    RHF geometry optimization using Firefly.
! FINAL ENERGY IS  -37.2376451083 AFTER 7 ITERS   RMS GRADIENT = 0.0046682
! FINAL ENERGY IS  -37.2380397693 AFTER 5 ITERS   RMS GRADIENT = 0.0000026
 $CONTRL SCFTYP=RHF RUNTYP=OPTIMIZE COORD=ZMT NZVAR=0 $END
 $BASIS GBASIS=STO NGAUSS=2 $END
 $DATA
Methylene
Cnv 2
 $END
"""
    meta = parse_inp_comment(text)
    assert meta["expected_energy"] == pytest.approx(-37.2380397693, abs=1e-10)
    assert meta["scftyp"] == "RHF"
    assert meta["runtyp"] == "OPTIMIZE"
    assert meta["coord"] == "ZMT"
    assert "Z-matrix (COORD=ZMT)" in meta["unsupported_features"]


def test_parse_inp_comment_mp2():
    text = """! EXAM 38.
! E(MP2) is -75.7060362075, RMS grad=0.017449477
 $CONTRL SCFTYP=RHF MPLEVL=2 RUNTYP=GRADIENT $END
"""
    meta = parse_inp_comment(text)
    assert meta["expected_energy"] == pytest.approx(-75.7060362075, abs=1e-10)
    assert meta["mplevl"] == 2


def test_parse_firefly_out_energy_and_freqs():
    text = """
          NUCLEAR ENERGY    =        5.9560138288
          ELECTRONIC ENERGY =      -43.1940535980
          TOTAL ENERGY      =      -37.2380397693

 MODES 1 TO 6 ARE TAKEN AS ROTATIONS AND TRANSLATIONS.

     FREQUENCIES IN CM**-1, IR INTENSITIES IN DEBYE**2/AMU-ANGSTROM**2

                          1           2           3           4           5
       FREQUENCY:         3.97        0.03        0.03        0.03        2.52  
    REDUCED MASS:      1.12588     6.00295     6.00352     6.00385     1.05018

                          6           7           8           9
       FREQUENCY:         3.54     2170.05     4140.00     4391.07  
    REDUCED MASS:      1.00783     1.07849     1.04909     1.07736

 EXECUTION OF FIREFLY TERMINATED NORMALLY
"""
    data = parse_firefly_out(text)
    assert data["energy"] == pytest.approx(-37.2380397693, abs=1e-10)
    assert len(data["freqs"]) == 3
    assert data["freqs"] == pytest.approx([2170.05, 4140.00, 4391.07], abs=1e-2)


def test_classify_case_ok():
    inp_meta = {"method": "HF", "runtyp": "ENERGY", "unsupported_features": []}
    ff_ref = {"energy": -76.0107465, "bonds": {}, "angles": {}, "freqs": []}
    ffpy_res = {
        "exit_code": 0,
        "energy": -76.0107468,
        "bonds": {},
        "angles": {},
        "freqs": [],
        "wall_time": 1.5,
    }
    verdict, reason, delta = classify_case(inp_meta, ff_ref, ffpy_res)
    assert verdict == "OK"
    assert delta == pytest.approx(3e-7, abs=1e-8)


def test_classify_case_mismatch():
    inp_meta = {"method": "HF", "runtyp": "ENERGY", "unsupported_features": []}
    ff_ref = {"energy": -76.0107465, "bonds": {}, "angles": {}, "freqs": []}
    ffpy_res = {
        "exit_code": 0,
        "energy": -76.0050000,
        "bonds": {},
        "angles": {},
        "freqs": [],
        "wall_time": 1.5,
    }
    verdict, reason, delta = classify_case(inp_meta, ff_ref, ffpy_res)
    assert verdict == "MISMATCH"
    assert "energy mismatch" in reason


def test_classify_case_unsupported_code2():
    inp_meta = {"method": "CASSCF", "runtyp": "GRADIENT", "unsupported_features": []}
    ff_ref = {"energy": -100.0}
    ffpy_res = {"exit_code": 2, "error": "gradients of SA-CASSCF are not supported"}
    verdict, reason, delta = classify_case(inp_meta, ff_ref, ffpy_res)
    assert verdict == "UNSUPPORTED"


def test_classify_case_unsupported_feature():
    inp_meta = {
        "method": "HF",
        "runtyp": "OPTIMIZE",
        "unsupported_features": ["Z-matrix (COORD=ZMT)"],
    }
    ff_ref = {"energy": -37.238}
    ffpy_res = {
        "exit_code": 1,
        "error": "INPUT ERROR: $CONTRL COORD=ZMT: allowed values are UNIQUE, CART",
    }
    verdict, reason, delta = classify_case(inp_meta, ff_ref, ffpy_res)
    assert verdict == "UNSUPPORTED"
    assert "Z-matrix" in reason


def test_classify_case_error():
    inp_meta = {"method": "HF", "runtyp": "ENERGY", "unsupported_features": []}
    ff_ref = {"energy": -100.0}
    ffpy_res = {
        "exit_code": 1,
        "error": "INPUT ERROR: $SYSTEM: unknown keyword MEMORY",
    }
    verdict, reason, delta = classify_case(inp_meta, ff_ref, ffpy_res)
    assert verdict == "ERROR/TIMEOUT"
