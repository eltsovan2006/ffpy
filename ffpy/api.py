"""JSON-friendly functions shared by ``ffpy --json`` and the MCP server.

Everything here returns plain dicts/lists/strings/numbers, so any client
(MCP, a script, another AI tool) can use it. Nothing here imports PySCF
except through a child process started by ``JobManager``.
"""

import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid

from ffpy import __version__
from ffpy.errors import EXIT_CODES


def validate(text):
    """Parse and check an input deck the way a run would, without running it."""
    from ffpy.gui.validate import check_text
    c = check_text(text)
    return {"ok": c.ok, "message": c.message, "line": c.line, "warnings": c.warnings}


def keywords(group=None):
    """Supported groups and keys with types, defaults, allowed values and help."""
    from ffpy.parser import fmt_value
    from ffpy.schema import IGNORED, SCHEMA
    groups = {}
    for g, keys in SCHEMA.items():
        if group and g != group.upper().lstrip("$"):
            continue
        groups[g] = {
            "keys": {k: {"type": s.type,
                         "default": None if s.default is None else fmt_value(s.default),
                         "choices": [fmt_value(c) for c in s.choices] if s.choices else None,
                         "help": s.help} for k, s in keys.items()},
            "accepted_without_effect": sorted(IGNORED.get(g, ())),
        }
    return {"version": __version__, "groups": groups,
            "exit_codes": {str(c): m for c, m in EXIT_CODES.items()}}


def _jsonable(o):
    if isinstance(o, dict):
        return {("-".join(map(str, k)) if isinstance(k, tuple) else str(k)): _jsonable(v)
                for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    return o


def parse_out(text):
    """Numbers from an ffpy .out log: energies, geometry, charges, frequencies..."""
    from ffpy.outparse import parse_text
    return _jsonable(parse_text(text))


def run_summary(out_path):
    """parse_out of a finished run plus the files it produced."""
    with open(out_path, encoding="utf-8", errors="replace") as f:
        res = parse_out(f.read())
    stem = os.path.splitext(out_path)[0]
    res["files"] = [os.path.basename(stem + e) for e in (".out", ".molden", ".dat", ".xyz")
                    if os.path.isfile(stem + e)]
    return res


HARTREE_KCAL = 627.5094740631


def geometry_xyz(out_path):
    """Last geometry of a finished .out as .xyz text (angstrom)."""
    with open(out_path, encoding="utf-8", errors="replace") as f:
        res = parse_out(f.read())
    geo = res.get("geometry") or []
    if not geo:
        raise ValueError("no geometry in %s" % os.path.basename(out_path))
    from ffpy.job import ELEMENTS
    rows = ["%-2s %14.8f %14.8f %14.8f" % (ELEMENTS[int(round(a["Z"]))], a["x"], a["y"], a["z"]) for a in geo]
    return "%d\n%s\n%s\n" % (len(rows), res.get("title") or "", "\n".join(rows))


def compare_energies(paths):
    """Energies of several .out files relative to the first one (hartree, kcal/mol)."""
    rows = []
    for p in paths:
        with open(p, encoding="utf-8", errors="replace") as f:
            r = parse_out(f.read())
        rows.append({"file": os.path.basename(p), "method": r.get("method"), "energy_eh": r.get("energy"),
                     "normal": r.get("normal")})
    ref = rows[0]["energy_eh"] if rows else None
    for r in rows:
        e = r["energy_eh"]
        r["relative_kcal_mol"] = None if e is None or ref is None else round((e - ref) * HARTREE_KCAL, 4)
    return rows


def safe_path(workdir, name):
    """Resolve ``name`` inside ``workdir``; refuse anything that escapes it."""
    if not name or os.path.isabs(name) or ".." in re.split(r"[\\/]", name):
        raise ValueError("file name must be relative to the work directory: %r" % name)
    full = os.path.realpath(os.path.join(workdir, name))
    root = os.path.realpath(workdir)
    if full != root and not full.startswith(root + os.sep):
        raise ValueError("path escapes the work directory: %r" % name)
    return full


class JobManager:
    """Runs ffpy calculations in child processes inside one work directory."""

    def __init__(self, workdir, max_jobs=1, default_timeout=3600):
        self.workdir = os.path.abspath(workdir)
        os.makedirs(self.workdir, exist_ok=True)
        self.max_jobs = max_jobs
        self.default_timeout = default_timeout
        self.jobs = {}
        self.lock = threading.Lock()

    def _cmd(self, inp, nproc):
        cmd = [sys.executable, "-m", "ffpy", inp, "-q", "--pipe"]
        if getattr(sys, "frozen", False):
            cmd = [os.path.join(os.path.dirname(sys.executable), "ffpy.exe"), inp, "-q", "--pipe"]
        if nproc:
            cmd += ["-n", str(nproc)]
        return cmd

    def start(self, name, nproc=0, timeout=None):
        """Queue a calculation; it starts as soon as fewer than max_jobs are running."""
        inp = safe_path(self.workdir, name)
        if not os.path.isfile(inp):
            raise FileNotFoundError("input file not found in the work directory: %s" % name)
        with self.lock:
            job_id = uuid.uuid4().hex[:8]
            self.jobs[job_id] = {"proc": None, "input": name, "t0": time.time(), "nproc": nproc,
                                 "timeout": timeout or self.default_timeout, "inp": inp,
                                 "out": os.path.splitext(inp)[0] + ".out", "cancelled": False}
        self._dispatch()
        return job_id

    def _running(self):
        return [j for j in self.jobs.values() if j["proc"] is not None and j["proc"].poll() is None]

    def _dispatch(self):
        with self.lock:
            for job_id, j in self.jobs.items():
                if j["proc"] is not None or j["cancelled"]:
                    continue
                if len(self._running()) >= self.max_jobs:
                    break
                env = dict(os.environ)
                pkg_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                env["PYTHONPATH"] = os.pathsep.join(filter(None, [pkg_parent, env.get("PYTHONPATH")]))
                j["t0"] = time.time()
                j["proc"] = subprocess.Popen(self._cmd(j["inp"], j["nproc"]), cwd=self.workdir, env=env,
                                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                threading.Thread(target=self._watch, args=(job_id,), daemon=True).start()

    def _watch(self, job_id):
        j = self.jobs[job_id]
        try:
            j["proc"].wait(timeout=j["timeout"])
        except subprocess.TimeoutExpired:
            j["timed_out"] = True
            j["proc"].kill()
            j["proc"].wait()
        self._dispatch()

    def status(self, job_id):
        j = self.jobs.get(job_id)
        if j is None:
            raise KeyError("unknown job id: %s" % job_id)
        if j["proc"] is None:
            if j["cancelled"]:
                return {"job_id": job_id, "input": j["input"], "state": "cancelled"}
            return {"job_id": job_id, "input": j["input"], "state": "queued",
                    "queue_position": 1 + sum(1 for k in self.jobs.values()
                                              if k["proc"] is None and not k["cancelled"]
                                              and k["t0"] < j["t0"])}
        code = j["proc"].poll()
        state = "running" if code is None else (
            "cancelled" if j["cancelled"] else
            "timeout" if j.get("timed_out") else "finished")
        res = {"job_id": job_id, "input": j["input"], "state": state,
               "elapsed_s": round(time.time() - j["t0"], 1)}
        if code is not None:
            res["exit_code"] = code
            res["exit_meaning"] = EXIT_CODES.get(code, "")
            if os.path.isfile(j["out"]):
                res["result"] = run_summary(j["out"])
        elif os.path.isfile(j["out"]):
            res["log_tail"] = tail(j["out"], 8)
        return res

    def wait(self, job_id, timeout_s=50):
        """Block until the job leaves queued/running or timeout_s passes; returns status()."""
        end = time.time() + min(max(timeout_s, 0), 300)
        while time.time() < end:
            st = self.status(job_id)
            if st["state"] not in ("queued", "running"):
                return st
            time.sleep(0.5)
        return self.status(job_id)

    def cancel(self, job_id):
        j = self.jobs.get(job_id)
        if j is None:
            raise KeyError("unknown job id: %s" % job_id)
        if j["proc"] is None:
            j["cancelled"] = True
        elif j["proc"].poll() is None:
            j["cancelled"] = True
            j["proc"].kill()
        return self.status(job_id)

    def shutdown(self):
        for j in self.jobs.values():
            j["cancelled"] = True
            if j["proc"] is not None and j["proc"].poll() is None:
                j["proc"].kill()


def tail(path, n):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read().splitlines()[-n:]


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2)
