import os
import pytest

from ffpy.cli import main
from ffpy.parser import parse_input
from ffpy.job import build_job
from ffpy.outparse import parse_out

INPUTS_DIR = os.path.join(os.path.dirname(__file__), "inputs")

CASES = [
    "water_pbe",
    "water_rhf_6311gdp",
    "bf3_rhf",
    "c2h4_casscf",
    "c2h4_tddft",
    "water_pcm",
]


@pytest.mark.parametrize("name", CASES)
def test_input_file_structure(name):
    path = os.path.join(INPUTS_DIR, name + ".inp")
    assert os.path.isfile(path), f"Input file missing: {path}"

    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    # Must contain comment indicating Firefly reference is expected from user
    assert text.strip().startswith("!"), f"{name}.inp must start with a '!' header comment"
    assert "Firefly" in text, f"{name}.inp header comment must mention Firefly reference"

    # Explicit ISPHER=-1
    assert "ISPHER=-1" in text, f"{name}.inp must explicitly specify ISPHER=-1"

    deck = parse_input(text)
    job = build_job(deck)
    assert job.cart is True, f"{name} must use Cartesian d/f functions (ISPHER=-1)"


def test_specific_job_options():
    # 1. water_pbe
    pbe_deck = parse_input(open(os.path.join(INPUTS_DIR, "water_pbe.inp")).read())
    pbe_job = build_job(pbe_deck)
    assert pbe_job.method == "DFT"
    assert pbe_job.dfttyp == "PBE"
    assert pbe_job.symbols == ["O", "H", "H"]

    # 2. water_rhf_6311gdp
    gdp_deck = parse_input(open(os.path.join(INPUTS_DIR, "water_rhf_6311gdp.inp")).read())
    gdp_job = build_job(gdp_deck)
    assert gdp_job.method == "HF"
    assert gdp_job.basis == "6-311g(d,p)"
    assert gdp_job.symbols == ["O", "H", "H"]

    # 3. bf3_rhf
    bf3_deck = parse_input(open(os.path.join(INPUTS_DIR, "bf3_rhf.inp")).read())
    bf3_job = build_job(bf3_deck)
    assert bf3_job.method == "HF"
    assert bf3_job.point_group == "DNH 3"
    assert bf3_job.symbols.count("B") == 1
    assert bf3_job.symbols.count("F") == 3

    # 4. c2h4_casscf
    cas_deck = parse_input(open(os.path.join(INPUTS_DIR, "c2h4_casscf.inp")).read())
    cas_job = build_job(cas_deck)
    assert cas_job.method == "CASSCF"
    assert cas_job.cas["ncore"] == 7
    assert cas_job.cas["nact"] == 2
    assert cas_job.cas["nels"] == 2
    assert cas_job.symbols.count("C") == 2
    assert cas_job.symbols.count("H") == 4

    # 5. c2h4_tddft
    td_deck = parse_input(open(os.path.join(INPUTS_DIR, "c2h4_tddft.inp")).read())
    td_job = build_job(td_deck)
    assert td_job.method == "TDDFT"
    assert td_job.dfttyp == "B3LYP"
    assert td_job.basis == "6-31+g(d)"
    assert td_job.excited["nstate"] == 5
    assert td_job.symbols.count("C") == 2
    assert td_job.symbols.count("H") == 4

    # 6. water_pcm
    pcm_deck = parse_input(open(os.path.join(INPUTS_DIR, "water_pcm.inp")).read())
    pcm_job = build_job(pcm_deck)
    assert pcm_job.method == "HF"
    assert pcm_job.pcm is not None
    assert pcm_job.pcm["solvent"] == "WATER"


@pytest.mark.parametrize("name", CASES)
def test_execution(name, tmp_path):
    path = os.path.join(INPUTS_DIR, name + ".inp")
    code = main([path, "-o", str(tmp_path), "-q"])
    assert code == 0, f"Execution of {name} failed with code {code}"
    out_file = os.path.join(str(tmp_path), name + ".out")
    assert os.path.isfile(out_file)
    parsed = parse_out(out_file)
    assert parsed["normal"] is True
    assert isinstance(parsed["energy"], float)
