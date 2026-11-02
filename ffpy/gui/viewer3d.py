"""Interactive 3D molecule viewer (pure Qt QPainter, no OpenGL).

Implements Chemcraft-like interactive 3D molecular visualization,
measurements of interatomic distances, valence angles, and dihedral angles,
trajectory player for geometry optimizations, and high-resolution PNG export.
"""

import math
import os
import re
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QIcon,
    QImage,
    QKeySequence,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QRadialGradient,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ffpy.constants import BOHR_ANG
from ffpy.errors import InputError
from ffpy.job import _parse_data
from ffpy.parser import parse_input
from ffpy.zmatrix import calc_angle, calc_dihedral, calc_distance

# =============================================================================
# Reference data for chemical elements Z = 1..86
# Sources:
# 1. Covalent radii: Cordero, B. et al. "Covalent radii revisited."
#    Dalton Trans., 2008, 2832-2838. doi:10.1039/B801115J
# 2. van der Waals radii: Bondi, A. "van der Waals Volumes and Radii."
#    J. Phys. Chem. 1964, 68, 441-451; Alvarez, S. "A cartography of the
#    van der Waals territories." Dalton Trans. 2013, 42, 8617-8636.
# 3. Colors: Standard CPK (Corey-Pauling-Koltun) conventions with modern Jmol adaptations.
# =============================================================================

ELEMENT_DATA: Dict[int, dict] = {
    1: {"symbol": "H", "name": "Hydrogen", "color": "#FFFFFF", "rcov": 0.31, "rvdw": 1.20},
    2: {"symbol": "He", "name": "Helium", "color": "#D9FFFF", "rcov": 0.28, "rvdw": 1.40},
    3: {"symbol": "Li", "name": "Lithium", "color": "#CC80FF", "rcov": 1.28, "rvdw": 1.82},
    4: {"symbol": "Be", "name": "Beryllium", "color": "#C2FF00", "rcov": 0.96, "rvdw": 1.53},
    5: {"symbol": "B", "name": "Boron", "color": "#FFB5B5", "rcov": 0.84, "rvdw": 1.92},
    6: {"symbol": "C", "name": "Carbon", "color": "#505050", "rcov": 0.76, "rvdw": 1.70},
    7: {"symbol": "N", "name": "Nitrogen", "color": "#3050F8", "rcov": 0.71, "rvdw": 1.55},
    8: {"symbol": "O", "name": "Oxygen", "color": "#E5384F", "rcov": 0.66, "rvdw": 1.52},
    9: {"symbol": "F", "name": "Fluorine", "color": "#90E050", "rcov": 0.57, "rvdw": 1.47},
    10: {"symbol": "Ne", "name": "Neon", "color": "#B3E3F5", "rcov": 0.58, "rvdw": 1.54},
    11: {"symbol": "Na", "name": "Sodium", "color": "#AB5CF2", "rcov": 1.66, "rvdw": 2.27},
    12: {"symbol": "Mg", "name": "Magnesium", "color": "#8AFF00", "rcov": 1.41, "rvdw": 1.73},
    13: {"symbol": "Al", "name": "Aluminum", "color": "#BFA6A6", "rcov": 1.21, "rvdw": 1.84},
    14: {"symbol": "Si", "name": "Silicon", "color": "#F0C8A0", "rcov": 1.11, "rvdw": 2.10},
    15: {"symbol": "P", "name": "Phosphorus", "color": "#FF8000", "rcov": 1.07, "rvdw": 1.80},
    16: {"symbol": "S", "name": "Sulfur", "color": "#FFFF30", "rcov": 1.05, "rvdw": 1.80},
    17: {"symbol": "Cl", "name": "Chlorine", "color": "#1FF01F", "rcov": 1.02, "rvdw": 1.75},
    18: {"symbol": "Ar", "name": "Argon", "color": "#80D1E3", "rcov": 1.06, "rvdw": 1.88},
    19: {"symbol": "K", "name": "Potassium", "color": "#8F40D4", "rcov": 2.03, "rvdw": 2.75},
    20: {"symbol": "Ca", "name": "Calcium", "color": "#3DFF00", "rcov": 1.76, "rvdw": 2.31},
    21: {"symbol": "Sc", "name": "Scandium", "color": "#E6E6E6", "rcov": 1.70, "rvdw": 2.11},
    22: {"symbol": "Ti", "name": "Titanium", "color": "#BFC2C7", "rcov": 1.60, "rvdw": 2.00},
    23: {"symbol": "V", "name": "Vanadium", "color": "#A6A6AB", "rcov": 1.53, "rvdw": 2.00},
    24: {"symbol": "Cr", "name": "Chromium", "color": "#8A99C7", "rcov": 1.39, "rvdw": 2.00},
    25: {"symbol": "Mn", "name": "Manganese", "color": "#9C7AC7", "rcov": 1.39, "rvdw": 2.00},
    26: {"symbol": "Fe", "name": "Iron", "color": "#E06633", "rcov": 1.32, "rvdw": 2.00},
    27: {"symbol": "Co", "name": "Cobalt", "color": "#F090A0", "rcov": 1.26, "rvdw": 2.00},
    28: {"symbol": "Ni", "name": "Nickel", "color": "#50D050", "rcov": 1.24, "rvdw": 1.63},
    29: {"symbol": "Cu", "name": "Copper", "color": "#C88033", "rcov": 1.32, "rvdw": 1.40},
    30: {"symbol": "Zn", "name": "Zinc", "color": "#7D80B0", "rcov": 1.22, "rvdw": 1.39},
    31: {"symbol": "Ga", "name": "Gallium", "color": "#C28F8F", "rcov": 1.22, "rvdw": 1.87},
    32: {"symbol": "Ge", "name": "Germanium", "color": "#668F8F", "rcov": 1.20, "rvdw": 2.11},
    33: {"symbol": "As", "name": "Arsenic", "color": "#BD80E3", "rcov": 1.19, "rvdw": 1.85},
    34: {"symbol": "Se", "name": "Selenium", "color": "#FFA100", "rcov": 1.20, "rvdw": 1.90},
    35: {"symbol": "Br", "name": "Bromine", "color": "#A62929", "rcov": 1.20, "rvdw": 1.85},
    36: {"symbol": "Kr", "name": "Krypton", "color": "#5CB8D1", "rcov": 1.16, "rvdw": 2.02},
    37: {"symbol": "Rb", "name": "Rubidium", "color": "#702EB8", "rcov": 2.20, "rvdw": 3.03},
    38: {"symbol": "Sr", "name": "Strontium", "color": "#00FF00", "rcov": 1.95, "rvdw": 2.49},
    39: {"symbol": "Y", "name": "Yttrium", "color": "#94FFFF", "rcov": 1.90, "rvdw": 2.40},
    40: {"symbol": "Zr", "name": "Zirconium", "color": "#94E0E0", "rcov": 1.75, "rvdw": 2.30},
    41: {"symbol": "Nb", "name": "Niobium", "color": "#73C2C9", "rcov": 1.64, "rvdw": 2.15},
    42: {"symbol": "Mo", "name": "Molybdenum", "color": "#54B5B5", "rcov": 1.54, "rvdw": 2.10},
    43: {"symbol": "Tc", "name": "Technetium", "color": "#3B9E9E", "rcov": 1.47, "rvdw": 2.05},
    44: {"symbol": "Ru", "name": "Ruthenium", "color": "#248F8F", "rcov": 1.46, "rvdw": 2.05},
    45: {"symbol": "Rh", "name": "Rhodium", "color": "#0A7D8C", "rcov": 1.42, "rvdw": 2.00},
    46: {"symbol": "Pd", "name": "Palladium", "color": "#006985", "rcov": 1.39, "rvdw": 1.63},
    47: {"symbol": "Ag", "name": "Silver", "color": "#C0C0C0", "rcov": 1.45, "rvdw": 1.72},
    48: {"symbol": "Cd", "name": "Cadmium", "color": "#FFD98F", "rcov": 1.44, "rvdw": 1.58},
    49: {"symbol": "In", "name": "Indium", "color": "#A67573", "rcov": 1.42, "rvdw": 1.93},
    50: {"symbol": "Sn", "name": "Tin", "color": "#668080", "rcov": 1.39, "rvdw": 2.17},
    51: {"symbol": "Sb", "name": "Antimony", "color": "#9E63B5", "rcov": 1.39, "rvdw": 2.06},
    52: {"symbol": "Te", "name": "Tellurium", "color": "#D47A00", "rcov": 1.38, "rvdw": 2.06},
    53: {"symbol": "I", "name": "Iodine", "color": "#940094", "rcov": 1.39, "rvdw": 1.98},
    54: {"symbol": "Xe", "name": "Xenon", "color": "#429EB0", "rcov": 1.40, "rvdw": 2.16},
    55: {"symbol": "Cs", "name": "Cesium", "color": "#57178F", "rcov": 2.44, "rvdw": 3.43},
    56: {"symbol": "Ba", "name": "Barium", "color": "#00C900", "rcov": 2.15, "rvdw": 2.68},
    57: {"symbol": "La", "name": "Lanthanum", "color": "#70D4FF", "rcov": 2.07, "rvdw": 2.50},
    58: {"symbol": "Ce", "name": "Cerium", "color": "#FFFFC7", "rcov": 2.04, "rvdw": 2.48},
    59: {"symbol": "Pr", "name": "Praseodymium", "color": "#D9FFC7", "rcov": 2.03, "rvdw": 2.47},
    60: {"symbol": "Nd", "name": "Neodymium", "color": "#C7FFC7", "rcov": 2.01, "rvdw": 2.45},
    61: {"symbol": "Pm", "name": "Promethium", "color": "#A3FFC7", "rcov": 1.99, "rvdw": 2.43},
    62: {"symbol": "Sm", "name": "Samarium", "color": "#8FFFC7", "rcov": 1.98, "rvdw": 2.42},
    63: {"symbol": "Eu", "name": "Europium", "color": "#61FFC7", "rcov": 1.98, "rvdw": 2.40},
    64: {"symbol": "Gd", "name": "Gadolinium", "color": "#45FFC7", "rcov": 1.96, "rvdw": 2.38},
    65: {"symbol": "Tb", "name": "Terbium", "color": "#30FFC7", "rcov": 1.94, "rvdw": 2.37},
    66: {"symbol": "Dy", "name": "Dysprosium", "color": "#1FFFC7", "rcov": 1.92, "rvdw": 2.35},
    67: {"symbol": "Ho", "name": "Holmium", "color": "#00FF9C", "rcov": 1.92, "rvdw": 2.33},
    68: {"symbol": "Er", "name": "Erbium", "color": "#00E675", "rcov": 1.89, "rvdw": 2.32},
    69: {"symbol": "Tm", "name": "Thulium", "color": "#00D452", "rcov": 1.90, "rvdw": 2.30},
    70: {"symbol": "Yb", "name": "Ytterbium", "color": "#00BF38", "rcov": 1.87, "rvdw": 2.28},
    71: {"symbol": "Lu", "name": "Lutetium", "color": "#00AB24", "rcov": 1.87, "rvdw": 2.27},
    72: {"symbol": "Hf", "name": "Hafnium", "color": "#4DC2FF", "rcov": 1.75, "rvdw": 2.25},
    73: {"symbol": "Ta", "name": "Tantalum", "color": "#4DA6FF", "rcov": 1.70, "rvdw": 2.20},
    74: {"symbol": "W", "name": "Tungsten", "color": "#2194D6", "rcov": 1.62, "rvdw": 2.10},
    75: {"symbol": "Re", "name": "Rhenium", "color": "#267DAB", "rcov": 1.51, "rvdw": 2.05},
    76: {"symbol": "Os", "name": "Osmium", "color": "#266696", "rcov": 1.44, "rvdw": 2.00},
    77: {"symbol": "Ir", "name": "Iridium", "color": "#175487", "rcov": 1.41, "rvdw": 2.00},
    78: {"symbol": "Pt", "name": "Platinum", "color": "#D0D0E0", "rcov": 1.36, "rvdw": 1.75},
    79: {"symbol": "Au", "name": "Gold", "color": "#FFD123", "rcov": 1.36, "rvdw": 1.66},
    80: {"symbol": "Hg", "name": "Mercury", "color": "#B8B8D0", "rcov": 1.32, "rvdw": 1.55},
    81: {"symbol": "Tl", "name": "Thallium", "color": "#A6544D", "rcov": 1.45, "rvdw": 1.96},
    82: {"symbol": "Pb", "name": "Lead", "color": "#575961", "rcov": 1.46, "rvdw": 2.02},
    83: {"symbol": "Bi", "name": "Bismuth", "color": "#9E4FB5", "rcov": 1.48, "rvdw": 2.07},
    84: {"symbol": "Po", "name": "Polonium", "color": "#AB5C00", "rcov": 1.40, "rvdw": 1.97},
    85: {"symbol": "At", "name": "Astatine", "color": "#754245", "rcov": 1.50, "rvdw": 2.02},
    86: {"symbol": "Rn", "name": "Radon", "color": "#428296", "rcov": 1.50, "rvdw": 2.20},
}

SYMBOL_TO_Z: Dict[str, int] = {
    data["symbol"].upper(): z for z, data in ELEMENT_DATA.items()
}


def get_element_z(symbol_or_charge: Union[str, int, float]) -> int:
    """Resolve element symbol or charge to integer Z in 1..86."""
    if isinstance(symbol_or_charge, (int, float)):
        z = int(round(symbol_or_charge))
        return z if 1 <= z <= 86 else 6
    s = str(symbol_or_charge).strip().upper()
    # Strip any trailing numbers like C1 -> C
    clean = re.sub(r"[^A-Z]", "", s)
    if clean in SYMBOL_TO_Z:
        return SYMBOL_TO_Z[clean]
    if len(clean) >= 2 and clean[:2] in SYMBOL_TO_Z:
        return SYMBOL_TO_Z[clean[:2]]
    if len(clean) >= 1 and clean[:1] in SYMBOL_TO_Z:
        return SYMBOL_TO_Z[clean[:1]]
    return 6


def measure_distance(r1: np.ndarray, r2: np.ndarray) -> float:
    """Calculate distance in Angstroms between two points."""
    return float(calc_distance(np.asarray(r1), np.asarray(r2)))


def measure_angle(r1: np.ndarray, r2: np.ndarray, r3: np.ndarray) -> float:
    """Calculate valence angle in degrees around center point r2."""
    return float(calc_angle(np.asarray(r1), np.asarray(r2), np.asarray(r3)))


def measure_dihedral(r1: np.ndarray, r2: np.ndarray, r3: np.ndarray, r4: np.ndarray) -> float:
    """Calculate torsion / dihedral angle in degrees around bond r2-r3."""
    return float(calc_dihedral(np.asarray(r1), np.asarray(r2), np.asarray(r3), np.asarray(r4)))


# =============================================================================
# Molecule data model
# =============================================================================

class Molecule:
    """Represents a molecular structure with optional multi-frame trajectory."""

    def __init__(
        self,
        symbols: List[str],
        coords: np.ndarray,
        charges: Optional[List[int]] = None,
        frames: Optional[List[dict]] = None,
        energy: Optional[float] = None,
        title: str = "",
    ):
        self.symbols = [s.strip().capitalize() for s in symbols]
        self.charges = charges or [get_element_z(s) for s in self.symbols]
        self.coords = np.asarray(coords, dtype=float)
        self.title = title
        self.energy = energy
        self.frame_index = 0

        if frames and len(frames) > 0:
            self.frames = frames
            self.coords = np.asarray(frames[0]["coords"], dtype=float)
            self.energy = frames[0].get("energy", energy)
        else:
            self.frames = [{"coords": self.coords.copy(), "energy": self.energy, "title": title}]

        self.bonds = self.detect_bonds()

    @property
    def natoms(self) -> int:
        return len(self.symbols)

    def detect_bonds(self) -> List[Tuple[int, int]]:
        """Detect covalent bonds based on Cordero/Alvarez covalent radii."""
        bonds = []
        n = self.natoms
        coords = self.coords
        charges = self.charges
        for i in range(n):
            z1 = charges[i]
            r1 = ELEMENT_DATA.get(z1, {}).get("rcov", 0.76)
            for j in range(i + 1, n):
                z2 = charges[j]
                r2 = ELEMENT_DATA.get(z2, {}).get("rcov", 0.76)
                # Criterion threshold: (rcov1 + rcov2) * 1.2 + 0.1
                thresh = (r1 + r2) * 1.2 + 0.1
                d = float(np.linalg.norm(coords[i] - coords[j]))
                if 0.4 < d <= thresh:
                    bonds.append((i, j))
        return bonds

    def set_frame(self, index: int):
        """Set current trajectory frame and update coordinates, energy, and bonds."""
        if not self.frames:
            return
        idx = max(0, min(index, len(self.frames) - 1))
        self.frame_index = idx
        fr = self.frames[idx]
        self.coords = np.asarray(fr["coords"], dtype=float)
        self.energy = fr.get("energy", None)
        self.bonds = self.detect_bonds()

    @classmethod
    def from_xyz(cls, text_or_path: str) -> "Molecule":
        """Load single-frame or multi-frame geometry from XYZ format."""
        if os.path.isfile(text_or_path):
            with open(text_or_path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        else:
            text = text_or_path

        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if not lines:
            raise InputError("Empty XYZ file")

        frames = []
        symbols = []
        charges = []
        idx = 0
        while idx < len(lines):
            try:
                natoms = int(lines[idx])
            except ValueError:
                break
            idx += 1
            comment = lines[idx] if idx < len(lines) else ""
            idx += 1

            energy = None
            m = re.search(r"[Ee]\s*=\s*([+-]?\d+\.\d+)", comment)
            if m:
                energy = float(m.group(1))

            cur_symbols = []
            cur_charges = []
            cur_coords = []
            for _ in range(natoms):
                if idx >= len(lines):
                    break
                parts = lines[idx].split()
                idx += 1
                sym = parts[0]
                x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                cur_symbols.append(sym)
                cur_charges.append(get_element_z(sym))
                cur_coords.append([x, y, z])

            if len(cur_coords) == natoms:
                frames.append({
                    "coords": np.array(cur_coords, dtype=float),
                    "energy": energy,
                    "title": comment,
                })
                if not symbols:
                    symbols = cur_symbols
                    charges = cur_charges

        if not frames:
            raise InputError("Failed to parse XYZ geometries")

        first_coords = frames[0]["coords"]
        first_energy = frames[0]["energy"]
        return cls(symbols, first_coords, charges=charges, frames=frames, energy=first_energy)

    @classmethod
    def from_molden(cls, text_or_path: str) -> "Molecule":
        """Load geometry and trajectory from Molden format."""
        if os.path.isfile(text_or_path):
            with open(text_or_path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        else:
            text = text_or_path

        lines = text.splitlines()
        symbols = []
        charges = []
        coords = []
        is_au = False

        in_atoms = False
        for l in lines:
            sl = l.strip()
            if sl.upper().startswith("[ATOMS]"):
                in_atoms = True
                is_au = "(AU)" in sl.upper()
                continue
            if in_atoms:
                if sl.startswith("["):
                    in_atoms = False
                    continue
                parts = sl.split()
                if len(parts) >= 6:
                    sym = parts[0]
                    z = int(round(float(parts[2])))
                    x, y, z_c = float(parts[3]), float(parts[4]), float(parts[5])
                    scale = BOHR_ANG if is_au else 1.0
                    symbols.append(sym)
                    charges.append(z)
                    coords.append([x * scale, y * scale, z_c * scale])

        # Check for [GEOCONV] and [GEOMETRIES] (XYZ)
        energies = []
        in_geoconv = False
        for l in lines:
            sl = l.strip()
            if sl.upper().startswith("[GEOCONV]"):
                in_geoconv = True
                continue
            if in_geoconv:
                if sl.startswith("["):
                    in_geoconv = False
                    continue
                if sl.lower() == "energy":
                    continue
                try:
                    energies.append(float(sl))
                except ValueError:
                    pass

        frames = []
        in_geom = False
        geom_lines = []
        for l in lines:
            sl = l.strip()
            if "[GEOMETRIES]" in sl.upper():
                in_geom = True
                continue
            if in_geom:
                if sl.startswith("[") and not sl.upper().startswith("[GEOMETRIES]"):
                    break
                geom_lines.append(sl)

        if in_geom and geom_lines:
            # Parse XYZ-like frames from GEOMETRIES
            idx = 0
            fr_i = 0
            while idx < len(geom_lines):
                if not geom_lines[idx]:
                    idx += 1
                    continue
                try:
                    nat = int(geom_lines[idx])
                except ValueError:
                    idx += 1
                    continue
                idx += 1
                comm = geom_lines[idx] if idx < len(geom_lines) else ""
                idx += 1
                fcoords = []
                fsyms = []
                for _ in range(nat):
                    if idx >= len(geom_lines):
                        break
                    p = geom_lines[idx].split()
                    idx += 1
                    if len(p) >= 4:
                        fsyms.append(p[0])
                        fcoords.append([float(p[1]), float(p[2]), float(p[3])])
                if len(fcoords) == nat:
                    e = energies[fr_i] if fr_i < len(energies) else None
                    frames.append({
                        "coords": np.array(fcoords, dtype=float),
                        "energy": e,
                        "title": comm,
                    })
                    fr_i += 1
                    if not symbols:
                        symbols = fsyms
                        charges = [get_element_z(s) for s in symbols]

        if not coords and not frames:
            raise InputError("No atoms found in Molden input")

        base_coords = np.array(coords, dtype=float) if coords else frames[0]["coords"]
        return cls(symbols, base_coords, charges=charges, frames=frames if frames else None)

    @classmethod
    def from_out(cls, text_or_path: str) -> "Molecule":
        """Load optimized geometry and energy from ffpy .out log."""
        from ffpy.outparse import parse_text
        if os.path.isfile(text_or_path):
            with open(text_or_path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        else:
            text = text_or_path

        res = parse_text(text)
        geom = res.get("geometry", [])
        if not geom:
            raise InputError("No geometry found in .out file")

        symbols = [g["atom"] for g in geom]
        charges = [int(round(g["Z"])) for g in geom]
        coords = np.array([[g["x"], g["y"], g["z"]] for g in geom], dtype=float)
        energy = res.get("energy", None)
        return cls(symbols, coords, charges=charges, energy=energy, title=res.get("title", ""))

    @classmethod
    def from_inp(cls, text_or_path: str) -> "Molecule":
        """Load geometry from Firefly/GAMESS .inp (resolving Z-matrix and point group symmetry)."""
        if os.path.isfile(text_or_path):
            with open(text_or_path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        else:
            text = text_or_path

        deck = parse_input(text)
        if "DATA" not in deck.groups:
            raise InputError("$DATA group is required in .inp")

        coord = deck.get("CONTRL", "COORD", "UNIQUE")
        units = deck.get("CONTRL", "UNITS", "ANGS")
        title, grp, atoms, nops = _parse_data(deck.groups["DATA"].lines, units="BOHR", coord=coord)

        symbols = [a[0] for a in atoms]
        charges = [int(a[1]) for a in atoms]
        coords = np.array([a[2] for a in atoms], dtype=float)
        if units.upper() == "BOHR":
            coords *= BOHR_ANG

        return cls(symbols, coords, charges=charges, title=title)

    @classmethod
    def from_file(cls, path: str) -> "Molecule":
        """Load molecule from file by automatically detecting format."""
        ext = os.path.splitext(path)[1].lower()
        if ext == ".xyz":
            return cls.from_xyz(path)
        elif ext == ".molden":
            return cls.from_molden(path)
        elif ext in (".out", ".log"):
            return cls.from_out(path)
        elif ext == ".inp":
            return cls.from_inp(path)
        else:
            # Fallback sniffer
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                head = f.read(2048)
            if "$DATA" in head:
                return cls.from_inp(path)
            elif "[MOLDEN" in head.upper() or "[ATOMS]" in head.upper():
                return cls.from_molden(path)
            elif "TERMINATED" in head or "COORDINATES OF ALL ATOMS" in head:
                return cls.from_out(path)
            else:
                return cls.from_xyz(path)


# =============================================================================
# MoleculeViewer3D Widget (pure Qt QPainter)
# =============================================================================

class MoleculeViewer3D(QWidget):
    """Interactive 3D molecule viewer widget rendered entirely with QPainter."""

    frameChanged = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)

        self.molecule: Optional[Molecule] = None
        self.style = "ball_and_stick"  # "ball_and_stick", "sticks", "vdw"
        self.label_mode = "none"  # "none", "symbol", "symbol_number"
        self.measurement_mode = False
        self.selected_atoms: List[int] = []
        self.measurement_text = ""

        # Camera state
        self.rot_matrix = np.eye(3, dtype=float)
        self.pan_offset = QPointF(0.0, 0.0)
        self.scale = 1.0
        self.last_mouse_pos = QPointF()
        self.is_rotating = False
        self.is_panning = False
        self.hovered_atom: Optional[int] = None

        # Playback animation timer
        self.play_timer = QTimer(self)
        self.play_timer.setInterval(120)  # ~8 FPS
        self.play_timer.timeout.connect(self._on_play_step)

        self._build_ui_overlays()

    @property
    def current_frame(self) -> int:
        return self.molecule.frame_index if self.molecule else 0

    def _build_ui_overlays(self):
        """Create floating overlay controls matching the .dc mock layout."""
        # Main overlay layout
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(16, 16, 16, 16)
        self.root_layout.setSpacing(0)

        # Top row: Left vertical pill + Right horizontal segmented control
        top_row = QHBoxLayout()
        top_row.setSpacing(0)

        # Left vertical pill
        self.pill_left = QWidget(self)
        self.pill_left.setObjectName("pill_left")
        self.pill_left.setStyleSheet(
            "#pill_left { background: rgba(255, 255, 255, 0.12); "
            "border: 1px solid rgba(255, 255, 255, 0.22); border-radius: 12px; padding: 4px; }"
            "QToolButton { background: transparent; color: #dfe6fb; border: 0; "
            "border-radius: 8px; font-size: 15px; font-weight: 600; min-width: 32px; min-height: 32px; }"
            "QToolButton:checked, QToolButton:hover { background: rgba(255, 255, 255, 0.25); color: #ffffff; }"
        )
        pill_left_v = QVBoxLayout(self.pill_left)
        pill_left_v.setContentsMargins(4, 4, 4, 4)
        pill_left_v.setSpacing(4)

        self.btn_orbit = QToolButton(self.pill_left)
        self.btn_orbit.setText("⟳")
        self.btn_orbit.setToolTip("Сброс вращения и вида")
        self.btn_orbit.clicked.connect(self.reset_view)

        self.btn_measure = QToolButton(self.pill_left)
        self.btn_measure.setText("⟷")
        self.btn_measure.setCheckable(True)
        self.btn_measure.setToolTip("Режим измерений (2 атома: расстояние, 3: угол, 4: диэдр)")
        self.btn_measure.toggled.connect(self.set_measurement_mode)

        self.btn_labels = QToolButton(self.pill_left)
        self.btn_labels.setText("Aa")
        self.btn_labels.setToolTip("Подписи атомов (нет / элемент / элемент+номер)")
        self.btn_labels.clicked.connect(self._cycle_labels)

        self.btn_fit = QToolButton(self.pill_left)
        self.btn_fit.setText("◍")
        self.btn_fit.setToolTip("Вписать молекулу в окно")
        self.btn_fit.clicked.connect(self.reset_view)

        pill_left_v.addWidget(self.btn_orbit)
        pill_left_v.addWidget(self.btn_measure)
        pill_left_v.addWidget(self.btn_labels)
        pill_left_v.addWidget(self.btn_fit)

        top_row.addWidget(self.pill_left, 0, Qt.AlignTop | Qt.AlignLeft)
        top_row.addStretch(1)

        # Right horizontal segmented control for styles
        self.pill_right = QWidget(self)
        self.pill_right.setObjectName("pill_right")
        self.pill_right.setStyleSheet(
            "#pill_right { background: rgba(255, 255, 255, 0.12); "
            "border: 1px solid rgba(255, 255, 255, 0.22); border-radius: 10px; padding: 3px; }"
            "QPushButton { background: transparent; color: #dfe6fb; border: 0; "
            "border-radius: 7px; padding: 5px 10px; font-size: 12px; }"
            "QPushButton:checked { background: rgba(255, 255, 255, 0.25); color: #ffffff; font-weight: 600; }"
        )
        pill_right_h = QHBoxLayout(self.pill_right)
        pill_right_h.setContentsMargins(3, 3, 3, 3)
        pill_right_h.setSpacing(4)

        self.btn_style_bs = QPushButton("Шары и палочки", self.pill_right)
        self.btn_style_bs.setCheckable(True)
        self.btn_style_bs.setChecked(True)
        self.btn_style_bs.clicked.connect(lambda: self.set_style("ball_and_stick"))

        self.btn_style_sticks = QPushButton("Палочки", self.pill_right)
        self.btn_style_sticks.setCheckable(True)
        self.btn_style_sticks.clicked.connect(lambda: self.set_style("sticks"))

        self.btn_style_vdw = QPushButton("Объёмная", self.pill_right)
        self.btn_style_vdw.setCheckable(True)
        self.btn_style_vdw.clicked.connect(lambda: self.set_style("vdw"))

        pill_right_h.addWidget(self.btn_style_bs)
        pill_right_h.addWidget(self.btn_style_sticks)
        pill_right_h.addWidget(self.btn_style_vdw)

        top_row.addWidget(self.pill_right, 0, Qt.AlignTop | Qt.AlignRight)
        self.root_layout.addLayout(top_row)
        self.root_layout.addStretch(1)

        # Bottom player pill
        self.pill_player = QWidget(self)
        self.pill_player.setObjectName("pill_player")
        self.pill_player.setStyleSheet(
            "#pill_player { background: rgba(255, 255, 255, 0.12); "
            "border: 1px solid rgba(255, 255, 255, 0.22); border-radius: 12px; padding: 6px 14px; color: #ffffff; }"
            "QSlider::groove:horizontal { height: 4px; background: rgba(255, 255, 255, 0.25); border-radius: 2px; }"
            "QSlider::sub-page:horizontal { background: #8fb0ff; border-radius: 2px; }"
            "QSlider::handle:horizontal { background: #ffffff; border: 1px solid #13214d; width: 12px; margin: -4px 0; border-radius: 6px; }"
            "QLabel { color: #ffffff; font-size: 12px; }"
        )
        player_h = QHBoxLayout(self.pill_player)
        player_h.setContentsMargins(8, 4, 8, 4)
        player_h.setSpacing(12)

        self.btn_play = QToolButton(self.pill_player)
        self.btn_play.setText("▶")
        self.btn_play.setFixedSize(30, 30)
        self.btn_play.setStyleSheet("background: #ffffff; color: #13214d; border-radius: 15px; font-size: 11px; font-weight: bold;")
        self.btn_play.clicked.connect(self.toggle_play)

        self.step_label = QLabel("Шаг 1 из 1", self.pill_player)
        self.step_label.setMinimumWidth(80)

        self.slider = QSlider(Qt.Horizontal, self.pill_player)
        self.slider.setRange(0, 0)
        self.slider.valueChanged.connect(self.set_frame)

        self.energy_label = QLabel("E = —", self.pill_player)
        self.energy_label.setStyleSheet("font-family: monospace; font-size: 12px;")

        player_h.addWidget(self.btn_play)
        player_h.addWidget(self.step_label)
        player_h.addWidget(self.slider, 1)
        player_h.addWidget(self.energy_label)

        self.root_layout.addWidget(self.pill_player)

    def load_molecule(self, molecule: Molecule):
        """Load a molecule instance and update camera, slider, and views."""
        self.molecule = molecule
        self.selected_atoms.clear()
        self.measurement_text = ""

        n_frames = len(molecule.frames)
        self.slider.blockSignals(True)
        self.slider.setRange(0, max(0, n_frames - 1))
        self.slider.setValue(molecule.frame_index)
        self.slider.blockSignals(False)

        # Show player bar if multiple frames or molecule has frames
        self.pill_player.setVisible(n_frames > 1)
        self._update_player_labels()
        self.reset_view()

    def load_file(self, path: str):
        """Load molecule directly from file path."""
        mol = Molecule.from_file(path)
        self.load_molecule(mol)

    def set_style(self, style: str):
        """Set visualization style: 'ball_and_stick', 'sticks', or 'vdw'."""
        self.style = style
        self.btn_style_bs.setChecked(style == "ball_and_stick")
        self.btn_style_sticks.setChecked(style == "sticks")
        self.btn_style_vdw.setChecked(style == "vdw")
        self.update()

    def set_label_mode(self, mode: str):
        """Set atom label mode: 'none', 'symbol', or 'symbol_number'."""
        self.label_mode = mode
        self.update()

    def _cycle_labels(self):
        modes = ["none", "symbol", "symbol_number"]
        idx = (modes.index(self.label_mode) + 1) % len(modes)
        self.set_label_mode(modes[idx])

    def set_measurement_mode(self, enabled: bool):
        """Toggle measurement mode."""
        self.measurement_mode = enabled
        self.btn_measure.setChecked(enabled)
        if not enabled:
            self.clear_measurement()
        self.update()

    def select_atom(self, atom_idx: int):
        """Select or deselect atom for measurement."""
        if atom_idx in self.selected_atoms:
            self.selected_atoms.remove(atom_idx)
        else:
            if len(self.selected_atoms) >= 4:
                self.selected_atoms = [atom_idx]
            else:
                self.selected_atoms.append(atom_idx)

        self._update_measurement_text()
        self.update()

    def clear_measurement(self):
        """Clear measurement atom selection."""
        self.selected_atoms.clear()
        self.measurement_text = ""
        self.update()

    def _update_measurement_text(self):
        if not self.molecule or not self.selected_atoms:
            self.measurement_text = ""
            return

        coords = self.molecule.coords
        symbols = self.molecule.symbols
        sel = self.selected_atoms

        if len(sel) == 1:
            i = sel[0]
            self.measurement_text = f"{symbols[i]}{i+1} ({coords[i][0]:.3f}, {coords[i][1]:.3f}, {coords[i][2]:.3f})"
        elif len(sel) == 2:
            i, j = sel
            d = measure_distance(coords[i], coords[j])
            self.measurement_text = f"r({symbols[i]}{i+1}–{symbols[j]}{j+1}) = {d:.3f} Å"
        elif len(sel) == 3:
            i, j, k = sel
            ang = measure_angle(coords[i], coords[j], coords[k])
            self.measurement_text = f"∠({symbols[i]}{i+1}–{symbols[j]}{j+1}–{symbols[k]}{k+1}) = {ang:.1f}°"
        elif len(sel) == 4:
            i, j, k, l = sel
            dih = measure_dihedral(coords[i], coords[j], coords[k], coords[l])
            self.measurement_text = f"τ({symbols[i]}{i+1}–{symbols[j]}{j+1}–{symbols[k]}{k+1}–{symbols[l]}{l+1}) = {dih:.1f}°"

    def set_frame(self, frame_index: int):
        """Switch current trajectory frame."""
        if not self.molecule:
            return
        self.molecule.set_frame(frame_index)
        self.slider.blockSignals(True)
        self.slider.setValue(self.molecule.frame_index)
        self.slider.blockSignals(False)
        self._update_player_labels()
        self._update_measurement_text()
        self.frameChanged.emit(self.molecule.frame_index)
        self.update()

    def _update_player_labels(self):
        if not self.molecule:
            self.step_label.setText("Шаг 0 из 0")
            self.energy_label.setText("E = —")
            return
        total = len(self.molecule.frames)
        cur = self.molecule.frame_index + 1
        self.step_label.setText(f"Шаг {cur} из {total}")
        if self.molecule.energy is not None:
            self.energy_label.setText(f"E = {self.molecule.energy:.6f} Eh")
        else:
            self.energy_label.setText("E = —")

    def toggle_play(self):
        if self.is_playing():
            self.pause()
        else:
            self.play()

    def play(self):
        self.play_timer.start()
        self.btn_play.setText("❚❚")

    def pause(self):
        self.play_timer.stop()
        self.btn_play.setText("▶")

    def is_playing(self) -> bool:
        return self.play_timer.isActive()

    def _on_play_step(self):
        if not self.molecule or len(self.molecule.frames) <= 1:
            self.pause()
            return
        next_frame = (self.molecule.frame_index + 1) % len(self.molecule.frames)
        self.set_frame(next_frame)

    # -------------------------------------------------------------------------
    # Camera and 3D Transformations
    # -------------------------------------------------------------------------

    def reset_view(self):
        """Reset camera orientation, pan offset, and zoom to fit molecule."""
        self.rot_matrix = np.eye(3, dtype=float)
        self.pan_offset = QPointF(0.0, 0.0)
        self.scale = 1.0
        self.update()

    def rotate_by(self, dx_deg: float, dy_deg: float):
        """Rotate model by degrees around screen Y and X axes."""
        rx = math.radians(dy_deg)
        ry = math.radians(dx_deg)
        cx, sx = math.cos(rx), math.sin(rx)
        cy, sy = math.cos(ry), math.sin(ry)

        # Rotation matrices in screen space
        rot_x = np.array([[1.0, 0.0, 0.0], [0.0, cx, -sx], [0.0, sx, cx]])
        rot_y = np.array([[cy, 0.0, sy], [0.0, 1.0, 0.0], [-sy, 0.0, cy]])
        self.rot_matrix = rot_x @ rot_y @ self.rot_matrix
        self.update()

    def pan_by(self, dx: float, dy: float):
        """Pan view in screen coordinates."""
        self.pan_offset += QPointF(dx, dy)
        self.update()

    def zoom_by(self, factor: float):
        """Zoom view by multiplication factor."""
        self.scale = max(0.1, min(self.scale * factor, 20.0))
        self.update()

    # -------------------------------------------------------------------------
    # Interaction Events
    # -------------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent):
        self.last_mouse_pos = event.position()
        if event.button() == Qt.LeftButton:
            if event.modifiers() & Qt.ShiftModifier:
                self.is_panning = True
            else:
                self.is_rotating = True
        elif event.button() == Qt.RightButton:
            self.is_panning = True
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        cur_pos = event.position()
        diff = cur_pos - self.last_mouse_pos
        self.last_mouse_pos = cur_pos

        if self.is_rotating:
            self.rotate_by(diff.x() * 0.5, diff.y() * 0.5)
        elif self.is_panning:
            self.pan_by(diff.x(), diff.y())
        else:
            # Check atom hover
            hovered = self._hit_test_atom(cur_pos.x(), cur_pos.y())
            if hovered != self.hovered_atom:
                self.hovered_atom = hovered
                self.setCursor(Qt.PointingHandCursor if hovered is not None else Qt.ArrowCursor)
                self.update()

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            if self.is_rotating and (event.position() - self.last_mouse_pos).manhattanLength() < 4:
                # Click without drag: pick atom
                hit = self._hit_test_atom(event.position().x(), event.position().y())
                if hit is not None:
                    self.select_atom(hit)
            self.is_rotating = False
        elif event.button() == Qt.RightButton:
            self.is_panning = False
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.reset_view()
        super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        if delta != 0:
            factor = 1.12 if delta > 0 else 0.89
            self.zoom_by(factor)
        super().wheelEvent(event)

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_Escape:
            self.clear_measurement()
        elif key == Qt.Key_Space:
            self.toggle_play()
        elif key == Qt.Key_Left:
            self.rotate_by(-5.0, 0.0)
        elif key == Qt.Key_Right:
            self.rotate_by(5.0, 0.0)
        elif key == Qt.Key_Up:
            self.rotate_by(0.0, -5.0)
        elif key == Qt.Key_Down:
            self.rotate_by(0.0, 5.0)
        else:
            super().keyPressEvent(event)

    # -------------------------------------------------------------------------
    # Hit testing and 3D Projection
    # -------------------------------------------------------------------------

    def _get_projected_scene(self, width: int, height: int):
        """Compute 3D perspective projection and depth-sorted primitives."""
        if not self.molecule or self.molecule.natoms == 0:
            return [], []

        coords = self.molecule.coords
        n = len(coords)

        # Centroid
        centroid = np.mean(coords, axis=0)
        centered = coords - centroid

        # Compute bounding radius
        dists = np.linalg.norm(centered, axis=1)
        max_dist = max(float(np.max(dists)), 1.5)

        # Camera distance and focal length
        cam_dist = max_dist * 3.2
        focal = min(width, height) * 0.85 * self.scale

        # Rotated coordinates
        rotated = centered @ self.rot_matrix.T

        # Screen positions and projected radii
        screen_pts = np.zeros((n, 2), dtype=float)
        screen_radii = np.zeros(n, dtype=float)
        cx = width * 0.5 + self.pan_offset.x()
        cy = height * 0.5 + self.pan_offset.y()

        for i in range(n):
            rx, ry, rz = rotated[i]
            z_view = max(0.5, cam_dist - rz)
            proj_scale = focal / z_view

            screen_pts[i, 0] = cx + rx * proj_scale
            screen_pts[i, 1] = cy - ry * proj_scale

            z_elem = self.molecule.charges[i]
            rvdw = ELEMENT_DATA.get(z_elem, {}).get("rvdw", 1.5)
            rcov = ELEMENT_DATA.get(z_elem, {}).get("rcov", 0.76)

            if self.style == "vdw":
                r_ang = rvdw * 0.75
            elif self.style == "sticks":
                r_ang = 0.22
            else:  # ball_and_stick
                r_ang = 0.38 + 0.3 * (rcov - 0.3)

            screen_radii[i] = max(4.0, r_ang * proj_scale)

        # Primitives list for painter's algorithm
        primitives = []

        # Add bonds
        bond_width_ang = 0.18 if self.style == "ball_and_stick" else (0.24 if self.style == "sticks" else 0.12)
        for i, j in self.molecule.bonds:
            z_mid = (rotated[i, 2] + rotated[j, 2]) * 0.5
            primitives.append({
                "type": "bond",
                "z": z_mid,
                "i": i,
                "j": j,
                "p1": screen_pts[i],
                "p2": screen_pts[j],
                "r1": screen_radii[i],
                "r2": screen_radii[j],
                "width": max(3.0, bond_width_ang * focal / max(0.5, cam_dist - z_mid)),
            })

        # Add atoms
        for i in range(n):
            primitives.append({
                "type": "atom",
                "z": rotated[i, 2],
                "index": i,
                "pos": screen_pts[i],
                "radius": screen_radii[i],
            })

        # Sort back-to-front (Z ascending)
        primitives.sort(key=lambda p: p["z"])
        return primitives, screen_pts

    def _hit_test_atom(self, x: float, y: float) -> Optional[int]:
        """Hit test atom under screen coordinates (x, y)."""
        primitives, _ = self._get_projected_scene(self.width(), self.height())
        closest = None
        highest_z = -1e9
        for p in primitives:
            if p["type"] == "atom":
                ax, ay = p["pos"]
                r = p["radius"] + 6.0
                dist_sq = (x - ax) ** 2 + (y - ay) ** 2
                if dist_sq <= r * r:
                    if p["z"] > highest_z:
                        highest_z = p["z"]
                        closest = p["index"]
        return closest

    # -------------------------------------------------------------------------
    # QPainter Rendering
    # -------------------------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self._render_scene(painter, self.width(), self.height(), transparent=False)
        painter.end()

    def _render_scene(self, painter: QPainter, width: int, height: int, transparent: bool = False):
        rect = QRectF(0, 0, width, height)

        # 1. Background
        if not transparent:
            bg_grad = QRadialGradient(width * 0.5, height * 0.4, max(width, height) * 0.75)
            bg_grad.setColorAt(0.0, QColor("#25407f"))
            bg_grad.setColorAt(0.55, QColor("#13214d"))
            bg_grad.setColorAt(1.0, QColor("#0b1330"))
            painter.fillRect(rect, bg_grad)

            # Soft ground shadow ellipse
            shadow_grad = QRadialGradient(width * 0.5, height * 0.88, width * 0.35)
            shadow_grad.setColorAt(0.0, QColor(0, 0, 0, 75))
            shadow_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(shadow_grad)
            painter.drawEllipse(QPointF(width * 0.5, height * 0.88), width * 0.32, height * 0.045)

        if not self.molecule or self.molecule.natoms == 0:
            # Watermark when no molecule is loaded
            painter.setPen(QColor(255, 255, 255, 120))
            font = painter.font()
            font.setPixelSize(14)
            painter.setFont(font)
            painter.drawText(rect, Qt.AlignCenter, "Перетащите или откройте .xyz, .molden, .out, .inp файл")
            return

        # 2. Project primitives
        primitives, screen_pts = self._get_projected_scene(width, height)

        # 3. Draw depth-sorted primitives (Painter's algorithm)
        for p in primitives:
            if p["type"] == "bond":
                self._draw_bond(painter, p)
            elif p["type"] == "atom":
                self._draw_atom(painter, p)

        # 4. Measurement lines & badges
        self._draw_measurements(painter, screen_pts)

        # 5. Active measurement banner
        if self.measurement_text:
            self._draw_measurement_badge(painter, width, height)

    def _draw_bond(self, painter: QPainter, bond_prim: dict):
        p1 = bond_prim["p1"]
        p2 = bond_prim["p2"]
        i = bond_prim["i"]
        j = bond_prim["j"]
        w = bond_prim["width"]

        z1 = self.molecule.charges[i]
        z2 = self.molecule.charges[j]
        c1 = QColor(ELEMENT_DATA.get(z1, {}).get("color", "#CCCCCC"))
        c2 = QColor(ELEMENT_DATA.get(z2, {}).get("color", "#CCCCCC"))

        v = p2 - p1
        length = float(np.linalg.norm(v))
        if length < 1e-4:
            return

        mid = (p1 + p2) * 0.5
        u = v / length
        normal = np.array([-u[1], u[0]])

        # Draw two halves of the cylindrical bond
        for start, end, col in ((p1, mid, c1), (mid, p2, c2)):
            half_poly = QPolygonF([
                QPointF(start[0] + normal[0] * w * 0.5, start[1] + normal[1] * w * 0.5),
                QPointF(end[0] + normal[0] * w * 0.5, end[1] + normal[1] * w * 0.5),
                QPointF(end[0] - normal[0] * w * 0.5, end[1] - normal[1] * w * 0.5),
                QPointF(start[0] - normal[0] * w * 0.5, start[1] - normal[1] * w * 0.5),
            ])

            # Cylindrical gradient across the bond width
            p_left = QPointF(start[0] + normal[0] * w * 0.5, start[1] + normal[1] * w * 0.5)
            p_right = QPointF(start[0] - normal[0] * w * 0.5, start[1] - normal[1] * w * 0.5)
            grad = QLinearGradient(p_left, p_right)
            grad.setColorAt(0.0, col.darker(160))
            grad.setColorAt(0.35, col.lighter(140))
            grad.setColorAt(0.7, col)
            grad.setColorAt(1.0, col.darker(170))

            painter.setPen(Qt.NoPen)
            painter.setBrush(grad)
            painter.drawPolygon(half_poly)

    def _draw_atom(self, painter: QPainter, atom_prim: dict):
        idx = atom_prim["index"]
        pos = atom_prim["pos"]
        r = atom_prim["radius"]

        z_elem = self.molecule.charges[idx]
        col_hex = ELEMENT_DATA.get(z_elem, {}).get("color", "#CCCCCC")
        base_col = QColor(col_hex)

        # 3D Spherical Radial Gradient with light source at top-left-front
        light_x = pos[0] - r * 0.35
        light_y = pos[1] - r * 0.35
        grad = QRadialGradient(light_x, light_y, r * 1.35, light_x, light_y)
        grad.setColorAt(0.0, QColor(255, 255, 255, 240))
        grad.setColorAt(0.18, base_col.lighter(135))
        grad.setColorAt(0.55, base_col)
        grad.setColorAt(0.85, base_col.darker(150))
        grad.setColorAt(1.0, base_col.darker(230))

        painter.setPen(Qt.NoPen)
        painter.setBrush(grad)
        painter.drawEllipse(QPointF(pos[0], pos[1]), r, r)

        # Highlight ring if selected or hovered
        is_sel = idx in self.selected_atoms
        is_hov = (idx == self.hovered_atom)
        if is_sel or is_hov:
            ring_pen = QPen(QColor("#ffdd44" if is_sel else "#8fb0ff"), 2.6 if is_sel else 1.8)
            painter.setPen(ring_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPointF(pos[0], pos[1]), r + 3.0, r + 3.0)

        # Atom text label
        if self.label_mode != "none":
            sym = self.molecule.symbols[idx]
            txt = f"{sym}{idx+1}" if self.label_mode == "symbol_number" else sym
            painter.setPen(QColor("#ffffff"))
            font = painter.font()
            font.setPixelSize(max(9, int(r * 0.75)))
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(
                QRectF(pos[0] - r, pos[1] - r, 2 * r, 2 * r),
                Qt.AlignCenter,
                txt
            )

    def _draw_measurements(self, painter: QPainter, screen_pts: np.ndarray):
        sel = self.selected_atoms
        if len(sel) < 2:
            return

        pen = QPen(QColor("#ffdd44"), 2.0, Qt.DashLine)
        painter.setPen(pen)

        for i in range(len(sel) - 1):
            p1 = screen_pts[sel[i]]
            p2 = screen_pts[sel[i + 1]]
            painter.drawLine(QPointF(p1[0], p1[1]), QPointF(p2[0], p2[1]))

    def _draw_measurement_badge(self, painter: QPainter, width: int, height: int):
        font = painter.font()
        font.setPixelSize(13)
        font.setBold(True)
        painter.setFont(font)

        # Draw badge at top center
        txt = self.measurement_text
        badge_w = max(180, len(txt) * 9 + 28)
        badge_h = 32
        x = (width - badge_w) * 0.5
        y = 16

        bg_rect = QRectF(x, y, badge_w, badge_h)
        painter.setPen(QPen(QColor(255, 255, 255, 60), 1.0))
        painter.setBrush(QColor(15, 27, 61, 210))
        painter.drawRoundedRect(bg_rect, 10, 10)

        painter.setPen(QColor("#ffdd44"))
        painter.drawText(bg_rect, Qt.AlignCenter, txt)

    # -------------------------------------------------------------------------
    # Offscreen PNG Export
    # -------------------------------------------------------------------------

    def export_png(self, path: str, width: int = 1920, height: int = 1080, transparent: bool = False) -> bool:
        """Render high-resolution PNG image offscreen and save to path."""
        img = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
        img.fill(Qt.transparent if transparent else QColor("#0b1330"))

        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        self._render_scene(p, width, height, transparent=transparent)
        p.end()

        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        return img.save(path, "PNG")
