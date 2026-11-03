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
    with pytest.raises(RuntimeError):
        jm.start("h2.inp")
    for _ in range(120):
        st = jm.status(jid)
        if st["state"] != "running":
            break
        time.sleep(1)
    assert st["state"] == "finished" and st["exit_code"] == 0
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
    assert {"run_calculation", "job_status", "cancel_job"} <= names2
