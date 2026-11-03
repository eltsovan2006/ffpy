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
    th = []
    for blk in re.split(r"thermochemistry at ", text, flags=re.I)[1:]:
        t = re.match(r"([\d.]+) K, ([\d.]+) Pa", blk, re.I)
        row = {"temperature_K": float(t.group(1)), "pressure_Pa": float(t.group(2))} if t else {}
        for key, pat in (("zpe_eh", r"zero-point energy\s+:\s+(-?\d+\.\d+)"),
                         ("e_plus_zpe_eh", r"E \+ ZPE\s+(-?\d+\.\d+)"),
                         ("h_eh", r"H = E \+ kT\s+(-?\d+\.\d+)"), ("g_eh", r"G = H - TS\s+(-?\d+\.\d+)"),
                         ("s_j_mol_k", r"S total\s+(-?\d+\.\d+)")):
            m = re.search(pat, blk)
            if m:
                row[key] = float(m.group(1))
        th.append(row)
    res["thermo"] = th
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

    mull, lowdin = {}, {}
    for i, l in enumerate(lines):
        if l.strip().startswith("ATOM") and "MULLIKEN" in l:
            mull, lowdin = {}, {}
            for row in lines[i + 1:]:
                parts = row.split()
                if not parts or parts[0] == "TOTAL":
                    break
                mull[parts[0]] = float(parts[1])
                if len(parts) >= 3:
                    try:
                        lowdin[parts[0]] = float(parts[2])
                    except ValueError:
                        pass
    res["mulliken"] = mull
    res["lowdin"] = lowdin

    geometry = []
    in_geom = False
    for l in lines:
        if "X (ANGS)" in l and "Y (ANGS)" in l and "ATOM" in l:
            in_geom = True
            geometry = []
            continue
        if in_geom:
            parts = l.split()
            if len(parts) >= 5:
                try:
                    geometry.append({
                        "atom": parts[0],
                        "Z": float(parts[1]),
                        "x": float(parts[2]),
                        "y": float(parts[3]),
                        "z": float(parts[4]),
                    })
                except ValueError:
                    in_geom = False
            else:
                in_geom = False
    res["geometry"] = geometry

    opt_steps = []
    in_opt = False
    for l in lines:
        if "STEP" in l and "ENERGY" in l and "MAX GRAD" in l:
            in_opt = True
            opt_steps = []
            continue
        if in_opt:
            m = re.match(r"^\s*(\d+)\s+(-?\d+\.\d+)\s+([+-]?\d+(?:\.\d+)?(?:[Ee][+-]?\d+)?)\s+(\d+(?:\.\d+)?(?:[Ee][+-]?\d+)?)\s+(\d+(?:\.\d+)?(?:[Ee][+-]?\d+)?)", l)
            if m:
                opt_steps.append({
                    "step": int(m.group(1)),
                    "energy": float(m.group(2)),
                    "delta_e": float(m.group(3)),
                    "max_grad": float(m.group(4)),
                    "rms_grad": float(m.group(5)),
                })
            elif l.strip() and not l.startswith("   "):
                in_opt = False
    res["opt_steps"] = opt_steps

    normal_modes = []
    in_modes = False
    cur_cols = []
    cur_modes_dict = {}
    i = 0
    while i < len(lines):
        l = lines[i]
        if "normal modes (cartesian displacements" in l:
            in_modes = True
            cur_modes_dict = {}
            i += 1
            continue
        if in_modes:
            if l.strip().startswith("section:") or "thermochemistry" in l.lower() or "OUTPUT FILES" in l or l.strip().startswith("FINAL ENERGY"):
                in_modes = False
                i += 1
                continue
            sl = l.strip()
            if sl.startswith("MODE"):
                parts = sl.split()[1:]
                cur_cols = [int(p) - 1 for p in parts if p.isdigit()]
                for c in cur_cols:
                    if c not in cur_modes_dict:
                        cur_modes_dict[c] = {}
                i += 1
                continue
            if sl.startswith("FREQ"):
                i += 1
                continue
            m = re.match(r"^\s*([A-Za-z0-9_]+)\s+([XYZxyz])\s+(.*)$", l)
            if m and cur_cols:
                atom_lbl = m.group(1)
                axis = m.group(2).upper()
                axis_idx = {"X": 0, "Y": 1, "Z": 2}[axis]
                vals = [float(v) for v in m.group(3).split()]
                for col_idx, val in zip(cur_cols, vals):
                    if atom_lbl not in cur_modes_dict[col_idx]:
                        cur_modes_dict[col_idx][atom_lbl] = [0.0, 0.0, 0.0]
                    cur_modes_dict[col_idx][atom_lbl][axis_idx] = val
        i += 1

    if cur_modes_dict:
        sorted_keys = sorted(cur_modes_dict.keys())
        for k in sorted_keys:
            atom_dict = cur_modes_dict[k]
            normal_modes.append([atom_dict[a] for a in atom_dict])
    res["normal_modes"] = normal_modes

    m = re.search(r"\n(\s*-+\s*\n\s+OUTPUT FILES\s*\n\s*-+\s*\n)([\s\S]*?)\n\s*\n", text)
    res["files"] = [l.split()[0] for l in m.group(2).splitlines() if l.strip()] if m else []
    return res


def parse_out(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return parse_text(f.read())
