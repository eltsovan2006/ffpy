"""Z-matrix parsing and conversion to Cartesian coordinates using NeRF.

Supports:
- COORD=ZMT (GAUSSIAN-style card sequence G in $DATA)
- COORD=ZMTMPC (MOPAC-style card sequence M in $DATA)
- Symbolic parameter variables (rCH=1.09, aHCH=110.0) with unary minus (-aHCH)
- Integer (1-based) and string atom references (C1, H2)
- Dummy / ghost atoms (X, BQ) used as reference centers and removed before computation
- Alternative third angle format (i4 = +/-1 for second bond angle)
- Natural Extension Reference Frame (NeRF) Cartesian placement with < 1e-10 A / < 1e-8 deg error
"""

import math
import re
from typing import Dict, List, Optional, Tuple

import numpy as np

from ffpy.constants import ANG_BOHR
from ffpy.errors import InputError, UnsupportedError

# Standard chemical element symbols from nuclear charge 0 to 54
ELEMENTS = [
    "X", "H", "He", "Li", "Be", "B", "C", "N", "O", "F", "Ne", "Na", "Mg", "Al", "Si", "P",
    "S", "Cl", "Ar", "K", "Ca", "Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn",
    "Ga", "Ge", "As", "Se", "Br", "Kr", "Rb", "Sr", "Y", "Zr", "Nb", "Mo", "Tc", "Ru", "Rh",
    "Pd", "Ag", "Cd", "In", "Sn", "Sb", "Te", "I", "Xe"
]

ELEMENT_NAMES = {
    "HYDROGEN": 1, "HELIUM": 2, "LITHIUM": 3, "BERYLLIUM": 4, "BORON": 5,
    "CARBON": 6, "NITROGEN": 7, "OXYGEN": 8, "FLUORINE": 9, "NEON": 10,
    "SODIUM": 11, "MAGNESIUM": 12, "ALUMINUM": 13, "SILICON": 14,
    "PHOSPHORUS": 15, "SULFUR": 16, "CHLORINE": 17, "ARGON": 18,
    "POTASSIUM": 19, "CALCIUM": 20, "SCANDIUM": 21, "TITANIUM": 22,
    "VANADIUM": 23, "CHROMIUM": 24, "MANGANESE": 25, "IRON": 26,
    "COBALT": 27, "NICKEL": 28, "COPPER": 29, "ZINC": 30, "GALLIUM": 31,
    "GERMANIUM": 32, "ARSENIC": 33, "SELENIUM": 34, "BROMINE": 35,
    "KRYPTON": 36, "X": 0, "BQ": 0, "GHOST": 0,
}


def _perpendicular_unit_vector(u: np.ndarray) -> np.ndarray:
    """Return an arbitrary unit vector perpendicular to unit vector u."""
    if abs(u[0]) <= abs(u[1]) and abs(u[0]) <= abs(u[2]):
        v = np.array([1.0, 0.0, 0.0])
    elif abs(u[1]) <= abs(u[2]):
        v = np.array([0.0, 1.0, 0.0])
    else:
        v = np.array([0.0, 0.0, 1.0])
    p = v - np.dot(v, u) * u
    norm = np.linalg.norm(p)
    if norm < 1e-12:
        v = np.array([0.0, 1.0, 0.0]) if abs(u[0]) > 0.9 else np.array([1.0, 0.0, 0.0])
        p = v - np.dot(v, u) * u
        norm = np.linalg.norm(p)
    return p / norm


def parse_atom_identity(token: str, z_val: Optional[float] = None) -> Tuple[str, int]:
    """Parse atom label and determine chemical symbol and nuclear charge.

    Returns (label, nuclear_charge).
    """
    token_clean = token.strip()
    upper = token_clean.upper()

    # Explicit nuclear charge provided
    if z_val is not None:
        z = int(round(z_val))
        return token_clean, z

    # Full name check
    if upper in ELEMENT_NAMES:
        return token_clean, ELEMENT_NAMES[upper]

    # Dummy / ghost atoms
    if upper in ("X", "BQ", "GHOST") or upper.startswith("X") or upper.startswith("BQ"):
        # Check if X or BQ followed by digits (e.g. X1, BQ2)
        m = re.match(r"^(X|BQ|GHOST)\d*$", upper)
        if m:
            return token_clean, 0

    # Two-letter element symbol prefix (e.g. Si1 -> Si, Cl2 -> Cl)
    if len(upper) >= 2:
        two = upper[:2].capitalize()
        if two in ELEMENTS:
            # ensure remainder is digits or empty
            rem = upper[2:]
            if not rem or rem.isdigit():
                return token_clean, ELEMENTS.index(two)

    # One-letter element symbol prefix (e.g. C1 -> C, H3 -> H)
    one = upper[:1].capitalize()
    if one in ELEMENTS:
        rem = upper[1:]
        if not rem or rem.isdigit():
            return token_clean, ELEMENTS.index(one)

    # Fallback: strip all trailing digits
    alpha_part = re.sub(r"\d+$", "", upper)
    if alpha_part in ELEMENT_NAMES:
        return token_clean, ELEMENT_NAMES[alpha_part]
    if alpha_part.capitalize() in ELEMENTS:
        return token_clean, ELEMENTS.index(alpha_part.capitalize())

    raise InputError(f"$DATA: cannot determine chemical element for atom '{token_clean}'")


def parse_variables(lines: List[str]) -> Dict[str, float]:
    """Parse symbolic variable definitions after the blank line in $DATA.

    Supports formats:
      rCH = 1.09
      aHCH=110.0
      r1 1.05
      r1=1.05, r2=1.08
    """
    variables: Dict[str, float] = {}
    for line in lines:
        s = line.split("!", 1)[0].strip()
        if not s or s.upper().startswith("$END"):
            continue
        # Replace commas with whitespace
        cleaned = s.replace(",", " ")
        # Match KEY=VALUE or KEY VALUE
        # Tokenize by finding key/value pairs
        tokens = cleaned.split()
        idx = 0
        while idx < len(tokens):
            tok = tokens[idx]
            if "=" in tok:
                parts = tok.split("=", 1)
                name = parts[0].strip()
                val_str = parts[1].strip()
                if not val_str and idx + 1 < len(tokens):
                    idx += 1
                    val_str = tokens[idx].strip()
            elif idx + 1 < len(tokens) and tokens[idx + 1] == "=":
                name = tok.strip()
                idx += 2
                if idx < len(tokens):
                    val_str = tokens[idx].strip()
                else:
                    raise InputError(f"$DATA: missing value for variable '{name}'")
            elif idx + 1 < len(tokens):
                name = tok.strip()
                idx += 1
                val_str = tokens[idx].strip()
            else:
                break
            idx += 1
            if name:
                try:
                    v = float(val_str.upper().replace("D", "E"))
                except ValueError:
                    raise InputError(f"$DATA: cannot parse numeric value '{val_str}' for variable '{name}'")
                variables[name.upper()] = v
    return variables


def resolve_val(token: str, variables: Dict[str, float]) -> float:
    """Resolve a parameter token to a float, supporting variable substitution and unary minus."""
    t = token.strip()
    neg = False
    if t.startswith("-"):
        neg = True
        t = t[1:].strip()
    elif t.startswith("+"):
        t = t[1:].strip()

    try:
        val = float(t.upper().replace("D", "E"))
    except ValueError:
        u = t.upper()
        if u not in variables:
            raise InputError(f"$DATA: undefined variable '{t}' in Z-matrix")
        val = variables[u]

    return -val if neg else val


def resolve_ref(token: str, atom_labels: List[str]) -> int:
    """Resolve an atom reference (1-based integer or string label) to a 0-based atom index."""
    t = token.strip()
    if t.isdigit() or (t.startswith("-") and t[1:].isdigit()):
        idx = int(t) - 1
        if idx < 0 or idx >= len(atom_labels):
            raise InputError(f"$DATA: atom index {t} out of range (1..{len(atom_labels)})")
        return idx

    # Match by label (case-insensitive)
    u = t.upper()
    for i, lab in enumerate(atom_labels):
        if lab.upper() == u:
            return i

    raise InputError(f"$DATA: reference atom '{t}' not found among previously defined atoms")


def calc_distance(p1: np.ndarray, p2: np.ndarray) -> float:
    """Euclidean distance between two 3D points."""
    return float(np.linalg.norm(p1 - p2))


def calc_angle(p1: np.ndarray, p2: np.ndarray, p3: np.ndarray) -> float:
    """Angle p1-p2-p3 in degrees (vertex at p2)."""
    v1 = p1 - p2
    v2 = p3 - p2
    n1 = np.linalg.norm(v1)
    n2 = np.linalg.norm(v2)
    if n1 < 1e-12 or n2 < 1e-12:
        return 0.0
    cosine = np.clip(np.dot(v1, v2) / (n1 * n2), -1.0, 1.0)
    return float(np.degrees(np.arccos(cosine)))


def calc_dihedral(p1: np.ndarray, p2: np.ndarray, p3: np.ndarray, p4: np.ndarray) -> float:
    """Dihedral angle p1-p2-p3-p4 in degrees according to IUPAC convention."""
    b1 = p2 - p1
    b2 = p3 - p2
    b3 = p4 - p3
    n1 = np.cross(b1, b2)
    n1_norm = np.linalg.norm(n1)
    if n1_norm > 1e-12:
        n1 = n1 / n1_norm
    n2 = np.cross(b2, b3)
    n2_norm = np.linalg.norm(n2)
    if n2_norm > 1e-12:
        n2 = n2 / n2_norm
    b2_norm = np.linalg.norm(b2)
    b2_u = b2 / b2_norm if b2_norm > 1e-12 else np.array([0.0, 0.0, 1.0])
    m1 = np.cross(n1, b2_u)
    x = float(np.dot(n1, n2))
    y = float(np.dot(m1, n2))
    return float(np.degrees(np.arctan2(y, x)))


def verify_zmatrix(coords: np.ndarray, zmat_entries: List[dict],
                   tol_dist: float = 1e-10, tol_angle: float = 1e-8) -> bool:
    """Verify that Cartesian coords reconstruct the input Z-matrix internal coordinates."""
    for entry in zmat_entries:
        i = entry["idx"]
        p_d = coords[i]

        if "i1" in entry:
            p_a = coords[entry["i1"]]
            d = calc_distance(p_d, p_a)
            if abs(d - entry["r"]) > tol_dist:
                raise ValueError(f"Distance mismatch on atom {i+1}: expected {entry['r']}, got {d}")

        if "i2" in entry:
            p_a = coords[entry["i1"]]
            p_b = coords[entry["i2"]]
            ang = calc_angle(p_d, p_a, p_b)
            if abs(ang - entry["angle"]) > tol_angle:
                raise ValueError(f"Angle mismatch on atom {i+1}: expected {entry['angle']}, got {ang}")

        if "i3" in entry:
            p_a = coords[entry["i1"]]
            p_b = coords[entry["i2"]]
            p_c = coords[entry["i3"]]
            if entry.get("i4", 0) == 0:
                dih = calc_dihedral(p_c, p_b, p_a, p_d)
                diff = (dih - entry["dihedral"] + 180.0) % 360.0 - 180.0
                if abs(diff) > tol_angle:
                    raise ValueError(f"Dihedral mismatch on atom {i+1}: expected {entry['dihedral']}, got {dih}")
            else:
                ang2 = calc_angle(p_d, p_a, p_c)
                if abs(ang2 - entry["dihedral"]) > tol_angle:
                    raise ValueError(f"Second angle mismatch on atom {i+1}: expected {entry['dihedral']}, got {ang2}")

    return True


def parse_zmatrix(lines: List[str], units: str = "ANGS",
                  coord_style: str = "ZMT") -> Tuple[List[Tuple[str, int, List[float]]], List[dict]]:
    """Parse Z-matrix from $DATA body and build Cartesian coordinates using NeRF.

    Returns:
      atoms: List of (label, nuclear_charge, [x, y, z]) with real atoms only (dummy atoms removed)
      zmat_entries: internal representation for verification
    """
    scale = ANG_BOHR if units == "ANGS" else 1.0

    # 1. Separate atom lines from variable definitions
    atom_lines: List[str] = []
    var_lines: List[str] = []
    in_vars = False

    for line in lines:
        s = line.split("!", 1)[0].rstrip()
        if not s.strip():
            if atom_lines:
                in_vars = True
            continue
        if s.strip().upper().startswith("$END"):
            break
        if in_vars:
            var_lines.append(s)
        else:
            atom_lines.append(s)

    variables = parse_variables(var_lines)

    # 2. Parse atom entries
    defined_labels: List[str] = []
    raw_atoms: List[dict] = []

    for atom_idx, line in enumerate(atom_lines):
        tok = line.split()
        if not tok:
            continue

        if coord_style == "ZMTMPC":
            # Sequence M (MOPAC style)
            # Atom 1: ATOM
            # Atom 2: ATOM BLENGTH [j1]
            # Atom 3: ATOM BLENGTH j1 ALPHA j2 [i1 i2]
            # Atom 4+: ATOM BLENGTH j1 ALPHA j2 BETA j3 [i1 i2 i3]
            label, z = parse_atom_identity(tok[0])
            entry = {"label": label, "z": z, "idx": atom_idx}

            if atom_idx == 0:
                pass
            elif atom_idx == 1:
                r_val = float(tok[1].upper().replace("D", "E")) * scale
                entry["i1"] = 0
                entry["r"] = r_val
            elif atom_idx == 2:
                r_val = float(tok[1].upper().replace("D", "E")) * scale
                alpha_val = float(tok[3].upper().replace("D", "E"))
                i1 = int(tok[5]) - 1 if len(tok) > 5 else 1
                i2 = int(tok[6]) - 1 if len(tok) > 6 else 0
                entry["i1"] = i1
                entry["r"] = r_val
                entry["i2"] = i2
                entry["angle"] = alpha_val
            else:
                r_val = float(tok[1].upper().replace("D", "E")) * scale
                alpha_val = float(tok[3].upper().replace("D", "E"))
                beta_val = float(tok[5].upper().replace("D", "E"))
                i1 = int(tok[7]) - 1 if len(tok) > 7 else atom_idx - 1
                i2 = int(tok[8]) - 1 if len(tok) > 8 else atom_idx - 2
                i3 = int(tok[9]) - 1 if len(tok) > 9 else atom_idx - 3
                entry["i1"] = i1
                entry["r"] = r_val
                entry["i2"] = i2
                entry["angle"] = alpha_val
                entry["i3"] = i3
                entry["dihedral"] = beta_val
                entry["i4"] = 0
        else:
            # Sequence G (GAUSSIAN style)
            # Atom 1: ATOM [Z]
            # Atom 2: ATOM [Z] i1 r
            # Atom 3: ATOM [Z] i1 r i2 angle
            # Atom 4+: ATOM [Z] i1 r i2 angle i3 dihedral [i4]

            # Detect if token 1 is an explicit nuclear charge Z
            has_explicit_z = False
            z_val = None
            if len(tok) >= 2:
                # Check if tok[1] is a float and not an atom index/label
                try:
                    num = float(tok[1].upper().replace("D", "E"))
                    # If this is atom 0: tok[1] can only be Z
                    if atom_idx == 0:
                        has_explicit_z = True
                        z_val = num
                    elif atom_idx == 1 and len(tok) == 4:
                        # ATOM Z i1 r
                        has_explicit_z = True
                        z_val = num
                    elif atom_idx == 2 and len(tok) == 6:
                        # ATOM Z i1 r i2 angle
                        has_explicit_z = True
                        z_val = num
                    elif atom_idx >= 3 and len(tok) in (8, 9):
                        # Could be ATOM Z ... or ATOM i1 ... i4
                        if len(tok) == 9:
                            has_explicit_z = True
                            z_val = num
                        elif len(tok) == 8 and tok[7] not in ("0", "1", "+1", "-1"):
                            has_explicit_z = True
                            z_val = num
                except ValueError:
                    pass

            label, z = parse_atom_identity(tok[0], z_val)
            rem = tok[2:] if has_explicit_z else tok[1:]
            entry = {"label": label, "z": z, "idx": atom_idx}

            if atom_idx == 0:
                if len(rem) != 0:
                    raise InputError(f"$DATA: unexpected tokens on first atom line: {line}")
            elif atom_idx == 1:
                if len(rem) < 2:
                    raise InputError(f"$DATA: expected 'ATOM [Z] i1 r' on atom 2: {line}")
                i1 = resolve_ref(rem[0], defined_labels)
                r_val = resolve_val(rem[1], variables) * scale
                entry["i1"] = i1
                entry["r"] = r_val
            elif atom_idx == 2:
                if len(rem) < 4:
                    raise InputError(f"$DATA: expected 'ATOM [Z] i1 r i2 angle' on atom 3: {line}")
                i1 = resolve_ref(rem[0], defined_labels)
                r_val = resolve_val(rem[1], variables) * scale
                i2 = resolve_ref(rem[2], defined_labels)
                angle_val = resolve_val(rem[3], variables)
                entry["i1"] = i1
                entry["r"] = r_val
                entry["i2"] = i2
                entry["angle"] = angle_val
            else:
                if len(rem) < 6:
                    raise InputError(f"$DATA: expected 'ATOM [Z] i1 r i2 angle i3 dihedral [i4]' on atom {atom_idx+1}: {line}")
                i1 = resolve_ref(rem[0], defined_labels)
                r_val = resolve_val(rem[1], variables) * scale
                i2 = resolve_ref(rem[2], defined_labels)
                angle_val = resolve_val(rem[3], variables)
                i3 = resolve_ref(rem[4], defined_labels)
                dih_val = resolve_val(rem[5], variables)
                i4 = 0
                if len(rem) > 6:
                    i4_str = rem[6].strip()
                    if i4_str in ("+1", "1"):
                        i4 = 1
                    elif i4_str == "-1":
                        i4 = -1
                    elif i4_str == "0":
                        i4 = 0
                    else:
                        raise InputError(f"$DATA: i4 must be 0, +1, or -1 in: {line}")

                entry["i1"] = i1
                entry["r"] = r_val
                entry["i2"] = i2
                entry["angle"] = angle_val
                entry["i3"] = i3
                entry["dihedral"] = dih_val
                entry["i4"] = i4

        defined_labels.append(label)
        raw_atoms.append(entry)

    if not raw_atoms:
        raise InputError("$DATA: no atoms found in Z-matrix")

    # 3. NeRF coordinate generation
    natms = len(raw_atoms)
    coords = np.zeros((natms, 3), dtype=float)

    for i, entry in enumerate(raw_atoms):
        if i == 0:
            coords[i] = np.array([0.0, 0.0, 0.0])
        elif i == 1:
            i1 = entry["i1"]
            r = entry["r"]
            coords[i] = coords[i1] + np.array([0.0, 0.0, r])
        elif i == 2:
            i1 = entry["i1"]
            i2 = entry["i2"]
            r = entry["r"]
            theta = math.radians(entry["angle"])

            u_ba = coords[i1] - coords[i2]
            norm_ba = np.linalg.norm(u_ba)
            u_ba = u_ba / norm_ba if norm_ba > 1e-12 else np.array([0.0, 0.0, 1.0])

            u_p = _perpendicular_unit_vector(u_ba)
            coords[i] = coords[i1] - r * math.cos(theta) * u_ba + r * math.sin(theta) * u_p
        else:
            i1 = entry["i1"]
            i2 = entry["i2"]
            i3 = entry["i3"]
            r = entry["r"]
            i4 = entry.get("i4", 0)

            rA = coords[i1]
            rB = coords[i2]
            rC = coords[i3]

            if i4 == 0:
                # Dihedral angle representation
                theta = math.radians(entry["angle"])
                phi = math.radians(entry["dihedral"])

                u_ba = rA - rB
                norm_ba = np.linalg.norm(u_ba)
                u_ba = u_ba / norm_ba if norm_ba > 1e-12 else np.array([0.0, 0.0, 1.0])

                v_bc = rC - rB
                v_bc_perp = v_bc - np.dot(v_bc, u_ba) * u_ba
                norm_perp = np.linalg.norm(v_bc_perp)
                if norm_perp < 1e-10:
                    u_p = _perpendicular_unit_vector(u_ba)
                else:
                    u_p = v_bc_perp / norm_perp

                u_n = np.cross(u_p, u_ba)
                u_n /= np.linalg.norm(u_n)

                d = -r * math.cos(theta) * u_ba + r * math.sin(theta) * (math.cos(phi) * u_p + math.sin(phi) * u_n)
                coords[i] = rA + d
            else:
                # Two bond angles representation (i4 = +/- 1)
                alpha = math.radians(entry["angle"])
                beta = math.radians(entry["dihedral"])

                v_ab = rB - rA
                v_ac = rC - rA
                norm_ab = np.linalg.norm(v_ab)
                norm_ac = np.linalg.norm(v_ac)
                if norm_ab < 1e-12 or norm_ac < 1e-12:
                    raise InputError(f"$DATA: coincident reference atoms on atom {i+1}")

                u_ab = v_ab / norm_ab
                u_ac = v_ac / norm_ac

                cos_gamma = np.clip(np.dot(u_ab, u_ac), -1.0, 1.0)
                sin_gamma = math.sqrt(max(0.0, 1.0 - cos_gamma ** 2))
                if sin_gamma < 1e-10:
                    raise InputError(f"$DATA: reference atoms {i2+1} and {i3+1} are collinear for atom {i+1}")

                e1 = u_ab
                e2 = (u_ac - cos_gamma * e1) / sin_gamma
                e3 = np.cross(e1, e2)
                e3 /= np.linalg.norm(e3)

                cos_a = math.cos(alpha)
                cos_b = math.cos(beta)

                x = cos_a
                y = (cos_b - x * cos_gamma) / sin_gamma
                z_sq = 1.0 - x ** 2 - y ** 2
                if z_sq < -1e-8:
                    raise InputError(f"$DATA: geometrically impossible bond angles on atom {i+1}")

                z_val = math.sqrt(max(0.0, z_sq))
                z = (1.0 if i4 > 0 else -1.0) * z_val

                d = r * (x * e1 + y * e2 + z * e3)
                coords[i] = rA + d

    # 4. Verify reconstruction
    verify_zmatrix(coords, raw_atoms)

    # 5. Filter out dummy atoms (X, BQ, nuclear charge 0)
    final_atoms: List[Tuple[str, int, List[float]]] = []
    for i, entry in enumerate(raw_atoms):
        z = entry["z"]
        lab = entry["label"]
        upper_lab = lab.upper()
        if z == 0 or upper_lab in ("X", "BQ", "GHOST") or upper_lab.startswith("X") or upper_lab.startswith("BQ"):
            continue
        final_atoms.append((lab, z, coords[i].tolist()))

    if not final_atoms:
        raise InputError("$DATA: no real atoms remaining after removing dummy atoms")

    return final_atoms, raw_atoms
