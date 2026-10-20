"""Regenerate tests/reference.json from the current ffpy build.

    python tests/make_reference.py

Values produced this way are marked "source": "ffpy-regression". When
Firefly numbers for a case are available, put them in by hand and change
the source to "firefly"; this script keeps such entries untouched.
"""

import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from ffpy.cli import main  # noqa: E402
from outparse import parse_out  # noqa: E402

TOLERANCES = {"energy_hf_mp2": 1e-6, "energy_dft": 1e-4, "bond": 1e-3, "angle": 0.1,
              "freq": 5.0, "mulliken": 0.01}
DFT = {"water_b3lyp"}


def main_():
    path = os.path.join(HERE, "reference.json")
    old = json.load(open(path)) if os.path.exists(path) else {"cases": {}}
    cases = {}
    tmp = tempfile.mkdtemp()
    for fn in sorted(os.listdir(os.path.join(HERE, "inputs"))):
        name = fn[:-4]
        prev = old["cases"].get(name)
        if prev and prev.get("source") != "ffpy-regression":
            cases[name] = prev
            continue
        code = main([os.path.join(HERE, "inputs", fn), "-o", tmp, "-q", "-n", "4"])
        if code:
            raise SystemExit("%s failed with code %d" % (name, code))
        out = parse_out(os.path.join(tmp, name + ".out"))
        c = {"source": "ffpy-regression", "energy": out["energy"],
             "mulliken": {k: round(v, 4) for k, v in out["mulliken"].items()}}
        if name in DFT:
            c["dft"] = True
        if "opt" in name:
            c["bonds"] = {"%s-%s" % k: v for k, v in out["bonds"].items()}
            c["angles"] = {"%s-%s-%s" % k: v for k, v in out["angles"].items()}
        if out["freqs"]:
            c["freqs"] = [round(f, 2) for f in out["freqs"]]
        cases[name] = c
        print("%-22s %.10f" % (name, out["energy"]))
    json.dump({"tolerances": TOLERANCES, "cases": cases}, open(path, "w"), indent=2)


if __name__ == "__main__":
    main_()
