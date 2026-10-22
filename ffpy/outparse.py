"""Read numbers back from an ffpy .out log (tests and the GUI results panel)."""

import re


def _last_float(pattern, text):
    m = re.findall(pattern, text)
    return float(m[-1]) if m else None


def parse_text(text):
    lines = text.splitlines()
    last = lines[-1].strip() if lines else ""
    res = {
        "warnings": [l.strip()[len("WARNING:"):].strip() for l in lines
                     if l.strip().startswith("WARNING:")],
        "normal": last.endswith("TERMINATED NORMALLY"),
        "finished": "TERMINATED" in last,
        "last_line": last,
        "error": None,
        "exit_code": 0 if last.endswith("TERMINATED NORMALLY") else None,
    }
    m = re.search(r"TERMINATED ABNORMALLY: ERROR CODE (\d+) \((.*)\)\s*$", last)
    if m:
        res["exit_code"], res["error"] = int(m.group(1)), m.group(2)
    for key, pat in (("title", r"^\s+title\s+:\s+(.*)$"), ("method", r"^\s+method\s+:\s+(.*)$"),
                     ("runtyp", r"^\s+RUNTYP\s+:\s+(.*)$"), ("basis", r"^\s+basis\s+:\s+(.*)$")):
        m = re.search(pat, text, re.M)
        res[key] = m.group(1).strip() if m else None
    res["energy"] = _last_float(r"FINAL ENERGY \(HARTREE\)\s+(-?\d+\.\d+)", text)
    res["mp2"] = _last_float(r"TOTAL MP2 ENERGY\s+(-?\d+\.\d+)", text)
    res["scf"] = _last_float(r"TOTAL R?U?O?(?:HF|KS) ENERGY\s+(-?\d+\.\d+)", text)
    res["dipole"] = None
    for i, l in enumerate(lines[:-1]):
        if "|D|  (DEBYE)" in l:
            try:
                res["dipole"] = float(lines[i + 1].split()[-1])
            except (ValueError, IndexError):
                pass
    m = re.search(r"wall time ([\d.]+) s", text)
    res["wall_time"] = float(m.group(1)) if m else None

    bonds, angles, bond_orders = {}, {}, {}
    mode = None
    for l in lines:
        if "bond lengths (ANGS):" in l:
            mode = "bonds"
            continue
        elif "bond angles (DEG):" in l:
            mode = "angles"
            continue
        elif "BOND PAIRS WITH ORDER GREATER THAN" in l:
            mode = "orders"
            continue
        elif l.strip().startswith("-") or (l.strip() and not l.startswith("   ")):
            mode = None

        if mode == "bonds":
            m = re.match(r"^\s{4}(\S+)\s+-\s+(\S+)\s+(\d+\.\d+)$", l)
            if m:
                bonds[(m.group(1), m.group(2))] = float(m.group(3))
        elif mode == "angles":
            m = re.match(r"^\s{4}(\S+)\s+-\s+(\S+)\s+-\s+(\S+)\s+(\d+\.\d+)$", l)
            if m:
                angles[(m.group(1), m.group(2), m.group(3))] = float(m.group(4))
        elif mode == "orders":
            for pm in re.finditer(r"(\d+)\(\s*(\S+)\s*\)\s*-\s*(\d+)\(\s*(\S+)\s*\)\s+(\d+\.\d+)", l):
                bond_orders[(int(pm.group(1)), int(pm.group(3)))] = float(pm.group(5))

    res["bonds"], res["angles"], res["bond_orders"] = bonds, angles, bond_orders

    freqs, ir = [], []
    in_vib = False
    for l in lines:
        if "MODE    FREQ (CM-1)" in l:
            in_vib, freqs, ir = True, [], []
            continue
        if in_vib:
            m = re.match(r"^\s+\d+\s+(-?\d+\.\d+)(i?)\s+\S+\s+\S+\s+\S+\s+(\S+)", l)
            if m:
                v = float(m.group(1))
                freqs.append(-v if m.group(2) else v)
                ir.append(float(m.group(3)))
            elif l.strip():
                in_vib = False
    res["freqs"], res["ir_km"] = freqs, ir

    states = []
    in_ex = False
    for l in lines:
        if l.strip().endswith("EXCITED STATES"):
            in_ex, states = True, []
            continue
        if in_ex and "dominant excitations" in l:
            in_ex = False
        if not in_ex:
            continue
        m = re.match(r"^\s+(\d+)\s+(\d+\.\d+)\s+(\d+\.\d+)\s+(\d+\.\d+)\s+(-?\d+\.\d+|nan)\s+(-?\d+\.\d+)$", l)
        if m:
            states.append({"state": int(m.group(1)), "ev": float(m.group(3)),
                           "nm": float(m.group(4)), "f": float(m.group(5))})
    res["excited"] = states

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

    m = re.search(r"\n(\s*-+\s*\n\s+OUTPUT FILES\s*\n\s*-+\s*\n)([\s\S]*?)\n\s*\n", text)
    res["files"] = [l.split()[0] for l in m.group(2).splitlines() if l.strip()] if m else []
    return res


def parse_out(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return parse_text(f.read())
