"""JSON API (ffpy --json) and the MCP server's safety rules."""

import json
import os
import time

import pytest

from ffpy import api
from ffpy.cli import main

WATER = os.path.join(os.path.dirname(__file__), "inputs", "water_mp2.inp")


def test_validate_and_keywords():
    ok = api.validate(open(WATER).read())
    assert ok["ok"] and "MP2" in ok["message"]
    bad = api.validate(" $CONTRL FOO=1 $END\n")
    assert not bad["ok"]
    kw = api.keywords("contrl")
    assert list(kw["groups"]) == ["CONTRL"]
    assert "RUNTYP" in kw["groups"]["CONTRL"]["keys"]
    json.dumps(kw)


def test_safe_path(tmp_path):
    assert api.safe_path(str(tmp_path), "a/b.inp").startswith(os.path.realpath(str(tmp_path)))
    for name in ("../x", "/etc/passwd", "a/../../x", ""):
        with pytest.raises(ValueError):
            api.safe_path(str(tmp_path), name)


def test_cli_json_check_and_keywords(capsys):
    assert main(["--check", "--json", WATER]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert main(["--keywords", "--json"]) == 0
    assert "CONTRL" in json.loads(capsys.readouterr().out)["groups"]


def test_job_manager_run_and_limits(tmp_path):
    inp = os.path.join(os.path.dirname(__file__), "inputs", "h2_rhf_opt.inp")
    (tmp_path / "h2.inp").write_text(open(inp).read())
    jm = api.JobManager(str(tmp_path), max_jobs=1)
    jid = jm.start("h2.inp")
    (tmp_path / "h2b.inp").write_text(open(inp).read())
    jid2 = jm.start("h2b.inp")             # over the limit: queued, started when the first one ends
    assert jm.status(jid2)["state"] == "queued"
    st = jm.wait(jid, 120)
    assert st["state"] == "finished" and st["exit_code"] == 0
    assert jm.wait(jid2, 120)["state"] == "finished"
    assert st["result"]["energy"] == pytest.approx(-1.1313335906, abs=1e-6)
    with pytest.raises(FileNotFoundError):
        jm.start("missing.inp")


def test_mcp_server_tools(tmp_path):
    pytest.importorskip("mcp")
    from ffpy.mcp_server import build_server
    srv, _ = build_server(str(tmp_path), allow_run=False)
    import asyncio
    names = {t.name for t in asyncio.run(srv.list_tools())}
    assert {"validate_input", "list_keywords", "write_input", "parse_output"} <= names
    assert "run_calculation" not in names
    srv2, jm = build_server(str(tmp_path), allow_run=True)
    names2 = {t.name for t in asyncio.run(srv2.list_tools())}
    assert {"run_calculation", "job_status", "wait_for_job", "cancel_job"} <= names2
    assert {"build_input", "geometry_from_output", "compare_outputs"} <= names


def test_build_input_validates_and_parses_thermo(tmp_path):
    from ffpy import inputgen
    txt = inputgen.build_input("O 0 0 0.117\nH 0 0.757 -0.467\nH 0 -0.757 -0.467", runtyp="HESSIAN",
                               basis="STO-3G")
    assert api.validate(txt)["ok"]
    out = ("  THERMOCHEMISTRY AT 298.15 K, 101325.0 PA\n"
           "  zero-point energy  :     0.0258704007 EH         67.9227 KJ/MOL         16.2339 KCAL/MOL\n"
           "  E + ZPE                         -74.9368362082 EH\n"
           "  H = E + kT                      -74.9330589656 EH\n"
           "  G = H - TS                      -74.9544621710 EH\n"
           "  S total                             188.4760 J/MOL-K\n")
    th = api.parse_out(out)["thermo"][0]
    assert th["g_eh"] == pytest.approx(-74.954462171) and th["temperature_K"] == 298.15
    with pytest.raises(ValueError):
        inputgen.build_input("Xx 0 0 0", basis="6-31G*")
    with pytest.raises(ValueError):
        inputgen.build_input("H 0 0 0", basis="nope")
