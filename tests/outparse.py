"""Read numbers back from an ffpy .out file (used by the tests)."""

import re


def parse_out(path):
    text = open(path, encoding="utf-8").read()
    lines = text.splitlines()
    res = {"warnings": [l for l in lines if l.strip().startswith("WARNING")],
           "normal": lines[-1].strip().endswith("TERMINATED NORMALLY"),
           "last_line": lines[-1].strip()}
    m = re.findall(r"FINAL ENERGY \(HARTREE\)\s+(-?\d+\.\d+)", text)
    res["energy"] = float(m[-1]) if m else None
    for key, pat in (("mp2", r"TOTAL MP2 ENERGY\s+(-?\d+\.\d+)"),
                     ("scf", r"TOTAL R?U?O?(?:HF|KS) ENERGY\s+(-?\d+\.\d+)")):
        m = re.findall(pat, text)
        res[key] = float(m[-1]) if m else None

    bonds, angles = {}, {}
    for l in lines:
        m = re.match(r"^\s{4}(\S+)\s+-\s+(\S+)\s+(\d+\.\d+)$", l)
        if m:
            bonds[(m.group(1), m.group(2))] = float(m.group(3))
        m = re.match(r"^\s{4}(\S+)\s+-\s+(\S+)\s+-\s+(\S+)\s+(\d+\.\d+)$", l)
        if m:
            angles[(m.group(1), m.group(2), m.group(3))] = float(m.group(4))
    res["bonds"], res["angles"] = bonds, angles   # last block wins (final geometry)

    freqs = []
    in_vib = False
    for l in lines:
        if "MODE    FREQ (CM-1)" in l:
            in_vib, freqs = True, []
            continue
        if in_vib:
            m = re.match(r"^\s+\d+\s+(-?\d+\.\d+)(i?)\s+", l)
            if m:
                v = float(m.group(1))
                freqs.append(-v if m.group(2) else v)
            elif l.strip():
                in_vib = False
    res["freqs"] = freqs

    mull = {}
    for i, l in enumerate(lines):
        if l.strip().startswith("ATOM") and "MULLIKEN" in l:
            mull = {}
            for row in lines[i + 1:]:
                parts = row.split()
                if not parts or parts[0] == "TOTAL":
                    break
                mull[parts[0]] = float(parts[1])
    res["mulliken"] = mull
    return res
