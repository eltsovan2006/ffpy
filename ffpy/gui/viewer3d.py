"""Interactive 3D molecule viewer (pure Qt QPainter, no OpenGL).

Implements Chemcraft-like interactive 3D molecular visualization,
principal axes automatic orientation, vibrational normal mode harmonic animation,
Lorentzian broadened IR spectrum plot, optimization convergence plot,
measurements of interatomic distances, valence angles, and dihedral angles,
trajectory player for geometry optimizations, and high-resolution PNG export.
"""

import math
import os
import re
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
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
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ffpy.constants import BOHR_ANG
from ffpy.errors import InputError
from ffpy.gui.theme import get_palette, get_theme_bus, hex_color, is_dark
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
    1: {"symbol": "H", "name": "Hydrogen", "color": "#FFFFFF", "rcov": 0.31, "rvdw": 1.20, "mass": 1.008},
    2: {"symbol": "He", "name": "Helium", "color": "#D9FFFF", "rcov": 0.28, "rvdw": 1.40, "mass": 4.0026},
    3: {"symbol": "Li", "name": "Lithium", "color": "#CC80FF", "rcov": 1.28, "rvdw": 1.82, "mass": 6.94},
    4: {"symbol": "Be", "name": "Beryllium", "color": "#C2FF00", "rcov": 0.96, "rvdw": 1.53, "mass": 9.0122},
    5: {"symbol": "B", "name": "Boron", "color": "#FFB5B5", "rcov": 0.84, "rvdw": 1.92, "mass": 10.81},
    6: {"symbol": "C", "name": "Carbon", "color": "#505050", "rcov": 0.76, "rvdw": 1.70, "mass": 12.011},
    7: {"symbol": "N", "name": "Nitrogen", "color": "#3050F8", "rcov": 0.71, "rvdw": 1.55, "mass": 14.007},
    8: {"symbol": "O", "name": "Oxygen", "color": "#E5384F", "rcov": 0.66, "rvdw": 1.52, "mass": 15.999},
    9: {"symbol": "F", "name": "Fluorine", "color": "#90E050", "rcov": 0.57, "rvdw": 1.47, "mass": 18.998},
    10: {"symbol": "Ne", "name": "Neon", "color": "#B3E3F5", "rcov": 0.58, "rvdw": 1.54, "mass": 20.180},
    11: {"symbol": "Na", "name": "Sodium", "color": "#AB5CF2", "rcov": 1.66, "rvdw": 2.27, "mass": 22.990},
    12: {"symbol": "Mg", "name": "Magnesium", "color": "#8AFF00", "rcov": 1.41, "rvdw": 1.73, "mass": 24.305},
    13: {"symbol": "Al", "name": "Aluminum", "color": "#BFA6A6", "rcov": 1.21, "rvdw": 1.84, "mass": 26.982},
    14: {"symbol": "Si", "name": "Silicon", "color": "#F0C8A0", "rcov": 1.11, "rvdw": 2.10, "mass": 28.085},
    15: {"symbol": "P", "name": "Phosphorus", "color": "#FF8000", "rcov": 1.07, "rvdw": 1.80, "mass": 30.974},
    16: {"symbol": "S", "name": "Sulfur", "color": "#FFFF30", "rcov": 1.05, "rvdw": 1.80, "mass": 32.06},
    17: {"symbol": "Cl", "name": "Chlorine", "color": "#1FF01F", "rcov": 1.02, "rvdw": 1.75, "mass": 35.45},
    18: {"symbol": "Ar", "name": "Argon", "color": "#80D1E3", "rcov": 1.06, "rvdw": 1.88, "mass": 39.948},
    19: {"symbol": "K", "name": "Potassium", "color": "#8F40D4", "rcov": 2.03, "rvdw": 2.75, "mass": 39.098},
    20: {"symbol": "Ca", "name": "Calcium", "color": "#3DFF00", "rcov": 1.76, "rvdw": 2.31, "mass": 40.078},
    21: {"symbol": "Sc", "name": "Scandium", "color": "#E6E6E6", "rcov": 1.70, "rvdw": 2.11, "mass": 44.956},
    22: {"symbol": "Ti", "name": "Titanium", "color": "#BFC2C7", "rcov": 1.60, "rvdw": 2.00, "mass": 47.867},
    23: {"symbol": "V", "name": "Vanadium", "color": "#A6A6AB", "rcov": 1.53, "rvdw": 2.00, "mass": 50.942},
    24: {"symbol": "Cr", "name": "Chromium", "color": "#8A99C7", "rcov": 1.39, "rvdw": 2.00, "mass": 51.996},
    25: {"symbol": "Mn", "name": "Manganese", "color": "#9C7AC7", "rcov": 1.39, "rvdw": 2.00, "mass": 54.938},
    26: {"Fe": 26, "symbol": "Fe", "name": "Iron", "color": "#E06633", "rcov": 1.32, "rvdw": 2.00, "mass": 55.845},
    27: {"symbol": "Co", "name": "Cobalt", "color": "#F090A0", "rcov": 1.26, "rvdw": 2.00, "mass": 58.933},
    28: {"symbol": "Ni", "name": "Nickel", "color": "#50D050", "rcov": 1.24, "rvdw": 1.63, "mass": 58.693},
    29: {"symbol": "Cu", "name": "Copper", "color": "#C88033", "rcov": 1.32, "rvdw": 1.40, "mass": 63.546},
    30: {"symbol": "Zn", "name": "Zinc", "color": "#7D80B0", "rcov": 1.22, "rvdw": 1.39, "mass": 65.38},
    31: {"symbol": "Ga", "name": "Gallium", "color": "#C28F8F", "rcov": 1.22, "rvdw": 1.87, "mass": 69.723},
    32: {"symbol": "Ge", "name": "Germanium", "color": "#668F8F", "rcov": 1.20, "rvdw": 2.11, "mass": 72.630},
    33: {"symbol": "As", "name": "Arsenic", "color": "#BD80E3", "rcov": 1.19, "rvdw": 1.85, "mass": 74.922},
    34: {"symbol": "Se", "name": "Selenium", "color": "#FFA100", "rcov": 1.20, "rvdw": 1.90, "mass": 78.971},
    35: {"symbol": "Br", "name": "Bromine", "color": "#A62929", "rcov": 1.20, "rvdw": 1.85, "mass": 79.904},
    36: {"symbol": "Kr", "name": "Krypton", "color": "#5CB8D1", "rcov": 1.16, "rvdw": 2.02, "mass": 83.798},
    37: {"symbol": "Rb", "name": "Rubidium", "color": "#702EB8", "rcov": 2.20, "rvdw": 3.03, "mass": 85.468},
    38: {"symbol": "Sr", "name": "Strontium", "color": "#00FF00", "rcov": 1.95, "rvdw": 2.49, "mass": 87.62},
    39: {"symbol": "Y", "name": "Yttrium", "color": "#94FFFF", "rcov": 1.90, "rvdw": 2.40, "mass": 88.906},
    40: {"symbol": "Zr", "name": "Zirconium", "color": "#94E0E0", "rcov": 1.75, "rvdw": 2.30, "mass": 91.224},
    41: {"symbol": "Nb", "name": "Niobium", "color": "#73C2C9", "rcov": 1.64, "rvdw": 2.15, "mass": 92.906},
    42: {"symbol": "Mo", "name": "Molybdenum", "color": "#54B5B5", "rcov": 1.54, "rvdw": 2.10, "mass": 95.95},
    43: {"symbol": "Tc", "name": "Technetium", "color": "#3B9E9E", "rcov": 1.47, "rvdw": 2.05, "mass": 98.0},
    44: {"symbol": "Ru", "name": "Ruthenium", "color": "#248F8F", "rcov": 1.46, "rvdw": 2.05, "mass": 101.07},
    45: {"symbol": "Rh", "name": "Rhodium", "color": "#0A7D8C", "rcov": 1.42, "rvdw": 2.00, "mass": 102.91},
    46: {"symbol": "Pd", "name": "Palladium", "color": "#006985", "rcov": 1.39, "rvdw": 1.63, "mass": 106.42},
    47: {"symbol": "Ag", "name": "Silver", "color": "#C0C0C0", "rcov": 1.45, "rvdw": 1.72, "mass": 107.87},
    48: {"symbol": "Cd", "name": "Cadmium", "color": "#FFD98F", "rcov": 1.44, "rvdw": 1.58, "mass": 112.41},
    49: {"symbol": "In", "name": "Indium", "color": "#A67573", "rcov": 1.42, "rvdw": 1.93, "mass": 114.82},
    50: {"symbol": "Sn", "name": "Tin", "color": "#668080", "rcov": 1.39, "rvdw": 2.17, "mass": 118.71},
    51: {"symbol": "Sb", "name": "Antimony", "color": "#9E63B5", "rcov": 1.39, "rvdw": 2.06, "mass": 121.76},
    52: {"symbol": "Te", "name": "Tellurium", "color": "#D47A00", "rcov": 1.38, "rvdw": 2.06, "mass": 127.60},
    53: {"symbol": "I", "name": "Iodine", "color": "#940094", "rcov": 1.39, "rvdw": 1.98, "mass": 126.90},
    54: {"symbol": "Xe", "name": "Xenon", "color": "#429EB0", "rcov": 1.40, "rvdw": 2.16, "mass": 131.29},
    55: {"symbol": "Cs", "name": "Cesium", "color": "#57178F", "rcov": 2.44, "rvdw": 3.43, "mass": 132.91},
    56: {"symbol": "Ba", "name": "Barium", "color": "#00C900", "rcov": 2.15, "rvdw": 2.68, "mass": 137.33},
    57: {"symbol": "La", "name": "Lanthanum", "color": "#70D4FF", "rcov": 2.07, "rvdw": 2.50, "mass": 138.91},
    58: {"symbol": "Ce", "name": "Cerium", "color": "#FFFFC7", "rcov": 2.04, "rvdw": 2.48, "mass": 140.12},
    59: {"symbol": "Pr", "name": "Praseodymium", "color": "#D9FFC7", "rcov": 2.03, "rvdw": 2.47, "mass": 140.91},
    60: {"symbol": "Nd", "name": "Neodymium", "color": "#C7FFC7", "rcov": 2.01, "rvdw": 2.45, "mass": 144.24},
    61: {"symbol": "Pm", "name": "Promethium", "color": "#A3FFC7", "rcov": 1.99, "rvdw": 2.43, "mass": 145.0},
    62: {"symbol": "Sm", "name": "Samarium", "color": "#8FFFC7", "rcov": 1.98, "rvdw": 2.42, "mass": 150.36},
    63: {"symbol": "Eu", "name": "Europium", "color": "#61FFC7", "rcov": 1.98, "rvdw": 2.40, "mass": 151.96},
    64: {"symbol": "Gd", "name": "Gadolinium", "color": "#45FFC7", "rcov": 1.96, "rvdw": 2.38, "mass": 157.25},
    65: {"symbol": "Tb", "name": "Terbium", "color": "#30FFC7", "rcov": 1.94, "rvdw": 2.37, "mass": 158.93},
    66: {"symbol": "Dy", "name": "Dysprosium", "color": "#1FFFC7", "rcov": 1.92, "rvdw": 2.35, "mass": 162.50},
    67: {"symbol": "Ho", "name": "Holmium", "color": "#00FF9C", "rcov": 1.92, "rvdw": 2.33, "mass": 164.93},
    68: {"symbol": "Er", "name": "Erbium", "color": "#00E675", "rcov": 1.89, "rvdw": 2.32, "mass": 167.26},
    69: {"symbol": "Tm", "name": "Thulium", "color": "#00D452", "rcov": 1.90, "rvdw": 2.30, "mass": 168.93},
    70: {"symbol": "Yb", "name": "Ytterbium", "color": "#00BF38", "rcov": 1.87, "rvdw": 2.28, "mass": 173.05},
    71: {"symbol": "Lu", "name": "Lutetium", "color": "#00AB24", "rcov": 1.87, "rvdw": 2.27, "mass": 174.97},
    72: {"symbol": "Hf", "name": "Hafnium", "color": "#4DC2FF", "rcov": 1.75, "rvdw": 2.25, "mass": 178.49},
    73: {"symbol": "Ta", "name": "Tantalum", "color": "#4DA6FF", "rcov": 1.70, "rvdw": 2.20, "mass": 180.95},
    74: {"symbol": "W", "name": "Tungsten", "color": "#2194D6", "rcov": 1.62, "rvdw": 2.10, "mass": 183.84},
    75: {"symbol": "Re", "name": "Rhenium", "color": "#267DAB", "rcov": 1.51, "rvdw": 2.05, "mass": 186.21},
    76: {"symbol": "Os", "name": "Osmium", "color": "#266696", "rcov": 1.44, "rvdw": 2.00, "mass": 190.23},
    77: {"symbol": "Ir", "name": "Iridium", "color": "#175487", "rcov": 1.41, "rvdw": 2.00, "mass": 192.22},
    78: {"symbol": "Pt", "name": "Platinum", "color": "#D0D0E0", "rcov": 1.36, "rvdw": 1.75, "mass": 195.08},
    79: {"symbol": "Au", "name": "Gold", "color": "#FFD123", "rcov": 1.36, "rvdw": 1.66, "mass": 196.97},
    80: {"symbol": "Hg", "name": "Mercury", "color": "#B8B8D0", "rcov": 1.32, "rvdw": 1.55, "mass": 200.59},
    81: {"symbol": "Tl", "name": "Thallium", "color": "#A6544D", "rcov": 1.45, "rvdw": 1.96, "mass": 204.38},
    82: {"symbol": "Pb", "name": "Lead", "color": "#575961", "rcov": 1.46, "rvdw": 2.02, "mass": 207.2},
    83: {"symbol": "Bi", "name": "Bismuth", "color": "#9E4FB5", "rcov": 1.48, "rvdw": 2.07, "mass": 208.98},
    84: {"symbol": "Po", "name": "Polonium", "color": "#AB5C00", "rcov": 1.40, "rvdw": 1.97, "mass": 209.0},
    85: {"symbol": "At", "name": "Astatine", "color": "#754245", "rcov": 1.50, "rvdw": 2.02, "mass": 210.0},
    86: {"symbol": "Rn", "name": "Radon", "color": "#428296", "rcov": 1.50, "rvdw": 2.20, "mass": 222.0},
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


def _calc_atom_font_size(r: float) -> int:
    """Dynamically calculate atom label font size bounded strictly to <= 14 px."""
    return min(14, max(8, int(r * 0.5)))


# =============================================================================
# Principal axes auto-orientation & Lorentzian spectrum
# =============================================================================

def compute_principal_axes(coords: np.ndarray, masses: Optional[np.ndarray] = None) -> np.ndarray:
    """Compute 3x3 rotation matrix aligning principal axes with screen coordinates.

    X axis (screen horizontal) <- axis of maximum spatial extent
    Y axis (screen vertical)   <- axis of intermediate spatial extent
    Z axis (screen normal)     <- axis of minimum spatial extent (face-on for planar molecules)
    """
    coords = np.asarray(coords, dtype=float)
    if len(coords) < 2:
        return np.eye(3, dtype=float)

    if masses is None:
        w = np.ones(len(coords), dtype=float) / len(coords)
    else:
        m = np.asarray(masses, dtype=float)
        w = m / m.sum() if m.sum() > 0 else np.ones(len(coords), dtype=float) / len(coords)

    com = np.average(coords, axis=0, weights=w)
    centered = coords - com
    C = (centered * w[:, None]).T @ centered
    vals, vecs = np.linalg.eigh(C)

    vx = vecs[:, 2]
    vy = vecs[:, 1]

    if vals[1] < 1e-7 * max(vals[2], 1.0):
        cand = np.array([0.0, 1.0, 0.0]) if abs(vx[1]) < 0.9 else np.array([1.0, 0.0, 0.0])
        vz = np.cross(vx, cand)
        vz = vz / np.linalg.norm(vz)
        vy = np.cross(vz, vx)
        vy = vy / np.linalg.norm(vy)
    else:
        vz = np.cross(vx, vy)
        vz = vz / np.linalg.norm(vz)
        vy = np.cross(vz, vx)
        vy = vy / np.linalg.norm(vy)

    R = np.vstack([vx, vy, vz])
    if np.linalg.det(R) < 0:
        R[1, :] = -R[1, :]
    return R


def lorentzian_spectrum(
    freqs: Union[List[float], np.ndarray],
    intensities: Union[List[float], np.ndarray],
    grid: Union[List[float], np.ndarray],
    fwhm: float = 20.0,
) -> np.ndarray:
    """Calculate Lorentzian-broadened IR spectrum over frequency grid."""
    freqs = np.asarray(freqs, dtype=float)
    intensities = np.asarray(intensities, dtype=float)
    grid = np.asarray(grid, dtype=float)

    if len(freqs) == 0 or len(grid) == 0:
        return np.zeros_like(grid)

    gamma_half = float(fwhm) / 2.0
    factor = gamma_half / np.pi
    diff = grid[:, None] - freqs[None, :]
    lorentz = factor / (diff ** 2 + gamma_half ** 2)
    return np.dot(lorentz, intensities)


# =============================================================================
# Molecule data model
# =============================================================================

class Molecule:
    """Represents a molecular structure with optional multi-frame trajectory and quantum properties."""

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

        # Quantum chemistry properties
        self.freqs: List[float] = []
        self.ir_km: List[float] = []
        self.normal_modes: List[np.ndarray] = []
        self.opt_steps: List[dict] = []
        self.mulliken: Dict[str, float] = {}
        self.lowdin: Dict[str, float] = {}
        self.dipole: Optional[float] = None
        self.wall_time: Optional[float] = None
        self.bonds_dict: Dict[Tuple[str, str], float] = {}
        self.angles_dict: Dict[Tuple[str, str, str], float] = {}

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

    def get_masses(self) -> np.ndarray:
        return np.array([ELEMENT_DATA.get(z, {}).get("mass", 12.0) for z in self.charges], dtype=float)

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
        mol = cls(symbols, first_coords, charges=charges, frames=frames, energy=first_energy)

        # Construct opt steps from trajectory if energies exist
        if len(frames) > 1 and all(f.get("energy") is not None for f in frames):
            opt_steps = []
            for k, f in enumerate(frames):
                e = f["energy"]
                de = 0.0 if k == 0 else e - frames[k - 1]["energy"]
                opt_steps.append({
                    "step": k,
                    "energy": e,
                    "delta_e": de,
                    "max_grad": 0.0,
                    "rms_grad": 0.0,
                })
            mol.opt_steps = opt_steps

        return mol

    @classmethod
    def from_molden(cls, text_or_path: str) -> "Molecule":
        """Load geometry, trajectory, and vibrational frequencies from Molden format."""
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

        # Parse [FREQ], [INT], [FR-NORM-COORD]
        freqs, ir_km, normal_modes = [], [], []
        in_freq = False
        in_int = False
        in_norm = False
        cur_mode = []

        for l in lines:
            sl = l.strip()
            if sl.upper().startswith("[FREQ]"):
                in_freq, in_int, in_norm = True, False, False
                continue
            elif sl.upper().startswith("[INT]"):
                in_int, in_freq, in_norm = True, False, False
                continue
            elif sl.upper().startswith("[FR-NORM-COORD]"):
                in_norm, in_freq, in_int = True, False, False
                continue
            elif sl.startswith("["):
                in_freq = in_int = in_norm = False
                continue

            if in_freq and sl:
                try:
                    freqs.append(float(sl))
                except ValueError:
                    pass
            elif in_int and sl:
                try:
                    ir_km.append(float(sl))
                except ValueError:
                    pass
            elif in_norm:
                if sl.lower().startswith("vibration"):
                    if cur_mode:
                        normal_modes.append(np.array(cur_mode, dtype=float))
                        cur_mode = []
                elif sl:
                    parts = sl.split()
                    if len(parts) >= 3:
                        cur_mode.append([float(parts[0]), float(parts[1]), float(parts[2])])

        if cur_mode:
            normal_modes.append(np.array(cur_mode, dtype=float))

        if not coords and not frames:
            raise InputError("No atoms found in Molden input")

        base_coords = np.array(coords, dtype=float) if coords else frames[0]["coords"]
        mol = cls(symbols, base_coords, charges=charges, frames=frames if frames else None)
        mol.freqs = freqs
        mol.ir_km = ir_km
        mol.normal_modes = normal_modes

        if len(frames) > 1 and all(f.get("energy") is not None for f in frames):
            opt_steps = []
            for k, f in enumerate(frames):
                e = f["energy"]
                de = 0.0 if k == 0 else e - frames[k - 1]["energy"]
                opt_steps.append({
                    "step": k,
                    "energy": e,
                    "delta_e": de,
                    "max_grad": 0.0,
                    "rms_grad": 0.0,
                })
            mol.opt_steps = opt_steps

        return mol

    @classmethod
    def from_out(cls, text_or_path: str) -> "Molecule":
        """Load optimized geometry and quantum properties from ffpy .out log."""
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
        mol = cls(symbols, coords, charges=charges, energy=energy, title=res.get("title", ""))

        mol.freqs = res.get("freqs", [])
        mol.ir_km = res.get("ir_km", [])
        mol.normal_modes = [np.array(m, dtype=float) for m in res.get("normal_modes", [])]
        mol.opt_steps = res.get("opt_steps", [])
        mol.mulliken = res.get("mulliken", {})
        mol.lowdin = res.get("lowdin", {})
        mol.dipole = res.get("dipole", None)
        mol.wall_time = res.get("wall_time", None)
        mol.bonds_dict = res.get("bonds", {})
        mol.angles_dict = res.get("angles", {})
        return mol

    @classmethod
    def from_inp(cls, text_or_path: str) -> "Molecule":
        """Load geometry from Firefly/GAMESS .inp."""
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
        """Load molecule from file and enrich with sibling .out properties if available."""
        ext = os.path.splitext(path)[1].lower()
        if ext == ".xyz":
            mol = cls.from_xyz(path)
        elif ext == ".molden":
            mol = cls.from_molden(path)
        elif ext in (".out", ".log"):
            return cls.from_out(path)
        elif ext == ".inp":
            mol = cls.from_inp(path)
        else:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                head = f.read(2048)
            if "$DATA" in head:
                mol = cls.from_inp(path)
            elif "[MOLDEN" in head.upper() or "[ATOMS]" in head.upper():
                mol = cls.from_molden(path)
            elif "TERMINATED" in head or "COORDINATES OF ALL ATOMS" in head:
                return cls.from_out(path)
            else:
                mol = cls.from_xyz(path)

        # Check for sibling .out
        base_out = os.path.splitext(path)[0] + ".out"
        if os.path.isfile(base_out):
            try:
                from ffpy.outparse import parse_out
                res = parse_out(base_out)
                if not mol.freqs and res.get("freqs"):
                    mol.freqs = res.get("freqs")
                    mol.ir_km = res.get("ir_km", [])
                if not mol.normal_modes and res.get("normal_modes"):
                    mol.normal_modes = [np.array(m, dtype=float) for m in res.get("normal_modes")]
                if not mol.opt_steps and res.get("opt_steps"):
                    mol.opt_steps = res.get("opt_steps")
                if not mol.mulliken and res.get("mulliken"):
                    mol.mulliken = res.get("mulliken")
                if not mol.lowdin and res.get("lowdin"):
                    mol.lowdin = res.get("lowdin")
                if mol.dipole is None:
                    mol.dipole = res.get("dipole")
                if mol.wall_time is None:
                    mol.wall_time = res.get("wall_time")
                if not mol.bonds_dict and res.get("bonds"):
                    mol.bonds_dict = res.get("bonds")
                if not mol.angles_dict and res.get("angles"):
                    mol.angles_dict = res.get("angles")
            except Exception:
                pass

        return mol


# =============================================================================
# 3D Viewport Widget
# =============================================================================

class _Viewer3DViewport(QWidget):
    """3D canvas viewport rendering atoms, bonds, labels, and floating pills."""

    frameChanged = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)

        self.molecule: Optional[Molecule] = None
        self.base_coords: Optional[np.ndarray] = None
        self.style = "ball_and_stick"
        self.label_mode = "none"
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

        # Trajectory player timer
        self.play_timer = QTimer(self)
        self.play_timer.setInterval(120)
        self.play_timer.timeout.connect(self._on_play_step)

        # Vibration animation timer
        self.vib_timer = QTimer(self)
        self.vib_timer.setInterval(33)  # ~30 FPS
        self.vib_timer.timeout.connect(self._on_vibration_step)
        self.vib_mode: Optional[int] = None
        self.vib_phase = 0.0

        self._build_ui_overlays()

    @property
    def current_frame(self) -> int:
        return self.molecule.frame_index if self.molecule else 0

    def minimumSizeHint(self) -> QSize:
        return QSize(200, 150)

    def _build_ui_overlays(self):
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(16, 16, 16, 16)
        self.root_layout.setSpacing(0)

        # Top row: Left vertical pill + Right horizontal segmented control
        top_row = QHBoxLayout()
        top_row.setSpacing(0)

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
        self.btn_orbit.setToolTip("Сброс вращения и ориентации (R / Home / двойной клик)")
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
        self.pill_player.setVisible(False)

    def load_molecule(self, molecule: Optional[Molecule]):
        self.molecule = molecule
        if molecule is None:
            self.base_coords = None
            self.stop_vibration()
            self.selected_atoms.clear()
            self.measurement_text = ""
            self.pill_player.setVisible(False)
            self._update_player_labels()
            self.update()
            return

        self.base_coords = molecule.coords.copy()
        self.stop_vibration()
        self.selected_atoms.clear()
        self.measurement_text = ""

        n_frames = len(molecule.frames) if molecule.frames else 1
        self.slider.blockSignals(True)
        self.slider.setRange(0, max(0, n_frames - 1))
        self.slider.setValue(molecule.frame_index)
        self.slider.blockSignals(False)

        # Player visible only when frames > 1
        self.pill_player.setVisible(n_frames > 1)
        self._update_player_labels()
        self.reset_view()

    def set_style(self, style: str):
        self.style = style
        self.btn_style_bs.setChecked(style == "ball_and_stick")
        self.btn_style_sticks.setChecked(style == "sticks")
        self.btn_style_vdw.setChecked(style == "vdw")
        self.update()

    def set_label_mode(self, mode: str):
        self.label_mode = mode
        self.update()

    def _cycle_labels(self):
        modes = ["none", "symbol", "symbol_number"]
        idx = (modes.index(self.label_mode) + 1) % len(modes)
        self.set_label_mode(modes[idx])

    def set_measurement_mode(self, enabled: bool):
        self.measurement_mode = enabled
        self.btn_measure.setChecked(enabled)
        if not enabled:
            self.clear_measurement()
        self.update()

    def select_atom(self, atom_idx: int):
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
        if not self.molecule:
            return
        self.stop_vibration()
        self.molecule.set_frame(frame_index)
        self.base_coords = self.molecule.coords.copy()
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
        self.stop_vibration()
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
    # Vibrational Mode Animation
    # -------------------------------------------------------------------------

    def start_vibration(self, mode_idx: int):
        """Start sinusoidal vibrational mode animation."""
        if not self.molecule or not self.molecule.normal_modes:
            return
        if mode_idx < 0 or mode_idx >= len(self.molecule.normal_modes):
            return
        self.pause()
        self.vib_mode = mode_idx
        self.vib_phase = 0.0
        if self.base_coords is None and self.molecule:
            self.base_coords = self.molecule.coords.copy()
        self.vib_timer.start()
        self.update()

    def stop_vibration(self):
        """Stop vibrational animation and restore equilibrium coordinates."""
        if self.vib_timer.isActive():
            self.vib_timer.stop()
        self.vib_mode = None
        if self.molecule and self.base_coords is not None:
            self.molecule.coords = self.base_coords.copy()
        self.update()

    def is_vibrating(self) -> bool:
        return self.vib_timer.isActive()

    @property
    def current_vibration_mode(self) -> Optional[int]:
        return self.vib_mode

    def _on_vibration_step(self):
        if not self.molecule or self.vib_mode is None or not self.molecule.normal_modes:
            self.stop_vibration()
            return
        if self.base_coords is None:
            self.base_coords = self.molecule.coords.copy()

        mode_vec = np.asarray(self.molecule.normal_modes[self.vib_mode], dtype=float)
        # Advance phase
        self.vib_phase = (self.vib_phase + (2.0 * math.pi / 25.0)) % (2.0 * math.pi)

        # Scale displacements so maximum atomic displacement is ~0.35 A
        atom_norms = np.linalg.norm(mode_vec, axis=1)
        max_norm = float(np.max(atom_norms)) if len(atom_norms) > 0 else 1.0
        norm_factor = 0.35 / max(max_norm, 1e-4)

        disp = mode_vec * (norm_factor * math.sin(self.vib_phase))
        self.molecule.coords = self.base_coords + disp
        self.update()

    # -------------------------------------------------------------------------
    # Camera and Principal Axes Orientation
    # -------------------------------------------------------------------------

    def reset_view(self):
        """Reset camera orientation by auto-aligning with principal axes."""
        if self.molecule and self.molecule.natoms > 0:
            coords = self.base_coords if self.base_coords is not None else self.molecule.coords
            masses = self.molecule.get_masses()
            self.rot_matrix = compute_principal_axes(coords, masses)
        else:
            self.rot_matrix = np.eye(3, dtype=float)

        self.pan_offset = QPointF(0.0, 0.0)
        self.scale = 1.0
        self.update()

    def rotate_by(self, dx_deg: float, dy_deg: float):
        rx = math.radians(dy_deg)
        ry = math.radians(dx_deg)
        cx, sx = math.cos(rx), math.sin(rx)
        cy, sy = math.cos(ry), math.sin(ry)

        rot_x = np.array([[1.0, 0.0, 0.0], [0.0, cx, -sx], [0.0, sx, cx]])
        rot_y = np.array([[cy, 0.0, sy], [0.0, 1.0, 0.0], [-sy, 0.0, cy]])
        self.rot_matrix = rot_x @ rot_y @ self.rot_matrix
        self.update()

    def pan_by(self, dx: float, dy: float):
        self.pan_offset += QPointF(dx, dy)
        self.update()

    def zoom_by(self, factor: float):
        self.scale = max(0.1, min(self.scale * factor, 20.0))
        self.update()

    # -------------------------------------------------------------------------
    # Events
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
            hovered = self._hit_test_atom(cur_pos.x(), cur_pos.y())
            if hovered != self.hovered_atom:
                self.hovered_atom = hovered
                self.setCursor(Qt.PointingHandCursor if hovered is not None else Qt.ArrowCursor)
                self.update()

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            if self.is_rotating and (event.position() - self.last_mouse_pos).manhattanLength() < 4:
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
        if key in (Qt.Key_R, Qt.Key_Home):
            self.reset_view()
        elif key == Qt.Key_Escape:
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
    # Projection & Rendering
    # -------------------------------------------------------------------------

    def _get_projected_scene(self, width: int, height: int):
        if not self.molecule or self.molecule.natoms == 0:
            return [], []

        coords = self.molecule.coords
        n = len(coords)

        centroid = np.mean(coords, axis=0)
        centered = coords - centroid

        dists = np.linalg.norm(centered, axis=1)
        max_dist = max(float(np.max(dists)), 1.5)

        cam_dist = max_dist * 3.2
        focal = min(width, height) * 0.85 * self.scale
        rotated = centered @ self.rot_matrix.T

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

        primitives = []
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

        for i in range(n):
            primitives.append({
                "type": "atom",
                "z": rotated[i, 2],
                "index": i,
                "pos": screen_pts[i],
                "radius": screen_radii[i],
            })

        primitives.sort(key=lambda p: p["z"])
        return primitives, screen_pts

    def _hit_test_atom(self, x: float, y: float) -> Optional[int]:
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

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self._render_scene(painter, self.width(), self.height(), transparent=False)
        painter.end()

    def _render_scene(self, painter: QPainter, width: int, height: int, transparent: bool = False):
        rect = QRectF(0, 0, width, height)

        if not transparent:
            bg_grad = QRadialGradient(width * 0.5, height * 0.4, max(width, height) * 0.75)
            bg_grad.setColorAt(0.0, QColor("#25407f"))
            bg_grad.setColorAt(0.55, QColor("#13214d"))
            bg_grad.setColorAt(1.0, QColor("#0b1330"))
            painter.fillRect(rect, bg_grad)

            shadow_grad = QRadialGradient(width * 0.5, height * 0.88, width * 0.35)
            shadow_grad.setColorAt(0.0, QColor(0, 0, 0, 75))
            shadow_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(shadow_grad)
            painter.drawEllipse(QPointF(width * 0.5, height * 0.88), width * 0.32, height * 0.045)

        if not self.molecule or self.molecule.natoms == 0:
            painter.setPen(QColor(255, 255, 255, 120))
            font = painter.font()
            font.setPixelSize(14)
            painter.setFont(font)
            painter.drawText(rect, Qt.AlignCenter, "Перетащите или откройте .xyz, .molden, .out, .inp файл")
            return

        primitives, screen_pts = self._get_projected_scene(width, height)

        for p in primitives:
            if p["type"] == "bond":
                self._draw_bond(painter, p)
            elif p["type"] == "atom":
                self._draw_atom(painter, p)

        self._draw_measurements(painter, screen_pts)

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

        for start, end, col in ((p1, mid, c1), (mid, p2, c2)):
            half_poly = QPolygonF([
                QPointF(start[0] + normal[0] * w * 0.5, start[1] + normal[1] * w * 0.5),
                QPointF(end[0] + normal[0] * w * 0.5, end[1] + normal[1] * w * 0.5),
                QPointF(end[0] - normal[0] * w * 0.5, end[1] - normal[1] * w * 0.5),
                QPointF(start[0] - normal[0] * w * 0.5, start[1] - normal[1] * w * 0.5),
            ])

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

        is_sel = idx in self.selected_atoms
        is_hov = (idx == self.hovered_atom)
        if is_sel or is_hov:
            ring_pen = QPen(QColor("#ffdd44" if is_sel else "#8fb0ff"), 2.6 if is_sel else 1.8)
            painter.setPen(ring_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPointF(pos[0], pos[1]), r + 3.0, r + 3.0)

        if self.label_mode != "none":
            sym = self.molecule.symbols[idx]
            txt = f"{sym}{idx+1}" if self.label_mode == "symbol_number" else sym
            painter.setPen(QColor("#ffffff"))
            font = painter.font()
            # Dynamic calculation with upper bound <= 14 px
            font.setPixelSize(_calc_atom_font_size(r))
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

    def export_png(self, path: str, width: int = 1920, height: int = 1080, transparent: bool = False) -> bool:
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


# =============================================================================
# IR Spectrum & Convergence QPainter Plots
# =============================================================================

class IRSpectrumPlot(QWidget):
    """QPainter graph of Lorentzian-broadened vibrational IR spectrum."""

    modeClicked = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.freqs: List[float] = []
        self.intensities: List[float] = []
        self.grid: np.ndarray = np.array([])
        self.spectrum: np.ndarray = np.array([])
        self.selected_mode: Optional[int] = None

    def set_data(self, freqs: List[float], intensities: List[float]):
        self.freqs = list(freqs)
        self.intensities = list(intensities) if intensities else [1.0] * len(freqs)
        if self.freqs:
            min_f = max(200.0, min(self.freqs) - 300.0)
            max_f = max(self.freqs) + 400.0
            self.grid = np.linspace(min_f, max_f, 1200)
            self.spectrum = lorentzian_spectrum(self.freqs, self.intensities, self.grid, fwhm=24.0)
        else:
            self.grid = np.array([])
            self.spectrum = np.array([])
        self.update()

    def set_selected_mode(self, mode_idx: Optional[int]):
        self.selected_mode = mode_idx
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        pal = get_palette()
        w, h = self.width(), self.height()

        bg_col = QColor(pal.get("surface", "#ffffff"))
        border_col = QColor(pal.get("border", "#dde2ef"))
        text_col = QColor(pal.get("text", "#1b2440"))
        muted_col = QColor(pal.get("muted", "#7a84a3"))
        accent_col = QColor(pal.get("accent", "#2f5bd8"))

        painter.fillRect(self.rect(), bg_col)

        pad_l, pad_r = 30, 20
        pad_t, pad_b = 20, 28
        plot_w = max(10, w - pad_l - pad_r)
        plot_h = max(10, h - pad_t - pad_b)
        base_y = h - pad_b

        # Baseline
        painter.setPen(QPen(border_col, 1.2))
        painter.drawLine(QPointF(pad_l, base_y), QPointF(w - pad_r, base_y))

        if len(self.grid) == 0 or len(self.spectrum) == 0:
            painter.setPen(muted_col)
            font = painter.font()
            font.setPixelSize(12)
            painter.setFont(font)
            painter.drawText(self.rect(), Qt.AlignCenter, "Нет данных колебательных частот")
            painter.end()
            return

        min_f = self.grid[0]
        max_f = self.grid[-1]
        f_span = max(1.0, max_f - min_f)
        max_s = max(float(np.max(self.spectrum)), 1e-4)

        # Plot curve
        curve_poly = QPolygonF()
        for f_val, s_val in zip(self.grid, self.spectrum):
            x = pad_l + (f_val - min_f) / f_span * plot_w
            y = base_y - (s_val / max_s) * (plot_h - 10)
            curve_poly.append(QPointF(x, y))

        fill_poly = QPolygonF()
        fill_poly.append(QPointF(pad_l, base_y))
        for i in range(curve_poly.count()):
            fill_poly.append(curve_poly.at(i))
        fill_poly.append(QPointF(w - pad_r, base_y))

        # Fill under curve
        fill_grad = QLinearGradient(pad_l, pad_t, pad_l, base_y)
        c_fill = QColor(accent_col)
        c_fill.setAlphaF(0.25)
        fill_grad.setColorAt(0.0, c_fill)
        c_fill.setAlphaF(0.02)
        fill_grad.setColorAt(1.0, c_fill)

        painter.setPen(Qt.NoPen)
        painter.setBrush(fill_grad)
        painter.drawPolygon(fill_poly)

        # Draw stroke
        painter.setPen(QPen(accent_col, 2.2))
        painter.setBrush(Qt.NoBrush)
        painter.drawPolyline(curve_poly)

        # Frequency tick labels at multiples of 1000 cm-1
        font = painter.font()
        font.setPixelSize(10)
        painter.setFont(font)
        painter.setPen(muted_col)

        start_tick = int(math.ceil(min_f / 1000.0) * 1000)
        for tick in range(start_tick, int(max_f) + 1, 1000):
            tx = pad_l + (tick - min_f) / f_span * plot_w
            painter.drawLine(QPointF(tx, base_y), QPointF(tx, base_y + 4))
            painter.drawText(QRectF(tx - 30, base_y + 6, 60, 16), Qt.AlignCenter, str(tick))

        # Peak annotations
        font.setPixelSize(11)
        font.setBold(True)
        painter.setFont(font)
        for k, f_val in enumerate(self.freqs):
            px = pad_l + (f_val - min_f) / f_span * plot_w
            is_active = (k == self.selected_mode)
            painter.setPen(accent_col if is_active else muted_col)
            lbl = f"{int(round(f_val))}"
            painter.drawText(QRectF(px - 25, base_y - plot_h - 2, 50, 16), Qt.AlignCenter, lbl)

            # Indicator line if active
            if is_active:
                pen = QPen(accent_col, 1.5, Qt.DashLine)
                painter.setPen(pen)
                painter.drawLine(QPointF(px, pad_t), QPointF(px, base_y))
                painter.setPen(Qt.NoPen)
                painter.setBrush(accent_col)
                painter.drawEllipse(QPointF(px, base_y), 4.0, 4.0)

        painter.end()

    def mousePressEvent(self, event: QMouseEvent):
        if not self.freqs or len(self.grid) == 0:
            return
        w = self.width()
        pad_l, pad_r = 30, 20
        plot_w = max(10, w - pad_l - pad_r)
        min_f, max_f = self.grid[0], self.grid[-1]
        f_span = max(1.0, max_f - min_f)

        click_x = event.position().x()
        closest_mode = None
        min_dist = 24.0
        for k, f_val in enumerate(self.freqs):
            px = pad_l + (f_val - min_f) / f_span * plot_w
            dist = abs(click_x - px)
            if dist < min_dist:
                min_dist = dist
                closest_mode = k

        if closest_mode is not None:
            self.modeClicked.emit(closest_mode)
        super().mousePressEvent(event)


class ConvergencePlot(QWidget):
    """QPainter graph of optimization convergence (energy / gradient vs step)."""

    stepClicked = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.opt_steps: List[dict] = []
        self.current_step = 0

    def set_data(self, opt_steps: List[dict]):
        self.opt_steps = list(opt_steps)
        self.current_step = len(self.opt_steps) - 1 if self.opt_steps else 0
        self.update()

    def set_current_step(self, step: int):
        self.current_step = step
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        pal = get_palette()
        w, h = self.width(), self.height()

        bg_col = QColor(pal.get("surface", "#ffffff"))
        border_col = QColor(pal.get("border", "#dde2ef"))
        text_col = QColor(pal.get("text", "#1b2440"))
        muted_col = QColor(pal.get("muted", "#7a84a3"))
        accent_col = QColor(pal.get("accent", "#2f5bd8"))

        painter.fillRect(self.rect(), bg_col)

        pad_l, pad_r = 40, 24
        pad_t, pad_b = 20, 28
        plot_w = max(10, w - pad_l - pad_r)
        plot_h = max(10, h - pad_t - pad_b)
        base_y = h - pad_b

        painter.setPen(QPen(border_col, 1.2))
        painter.drawLine(QPointF(pad_l, base_y), QPointF(w - pad_r, base_y))

        if not self.opt_steps:
            painter.setPen(muted_col)
            font = painter.font()
            font.setPixelSize(12)
            painter.setFont(font)
            painter.drawText(self.rect(), Qt.AlignCenter, "Нет данных оптимизации")
            painter.end()
            return

        energies = [s["energy"] for s in self.opt_steps]
        n_steps = len(energies)
        e_min, e_max = min(energies), max(energies)
        e_span = max(1e-6, e_max - e_min)

        pts = []
        for i, s in enumerate(self.opt_steps):
            x = pad_l if n_steps == 1 else pad_l + (i / (n_steps - 1)) * plot_w
            y = pad_t + 10 if e_span < 1e-6 else pad_t + 10 + ((e_max - s["energy"]) / e_span) * (plot_h - 20)
            pts.append(QPointF(x, y))

        # Polyline connecting steps
        painter.setPen(QPen(accent_col, 2.4))
        painter.setBrush(Qt.NoBrush)
        if len(pts) > 1:
            painter.drawPolyline(pts)

        # Points
        font = painter.font()
        font.setPixelSize(10)
        painter.setFont(font)

        for i, pt in enumerate(pts):
            is_cur = (i == self.current_step)
            painter.setPen(Qt.NoPen)
            painter.setBrush(accent_col)
            painter.drawEllipse(pt, 5.0, 5.0)

            if is_cur:
                painter.setPen(QPen(QColor("#ffffff"), 1.8))
                painter.drawEllipse(pt, 2.5, 2.5)

            # Step label on X axis
            painter.setPen(muted_col)
            painter.drawText(QRectF(pt.x() - 15, base_y + 6, 30, 16), Qt.AlignCenter, str(i))

        painter.end()

    def mousePressEvent(self, event: QMouseEvent):
        if not self.opt_steps:
            return
        w = self.width()
        pad_l, pad_r = 40, 24
        plot_w = max(10, w - pad_l - pad_r)
        n_steps = len(self.opt_steps)
        click_x = event.position().x()

        closest = 0
        min_d = 1e9
        for i in range(n_steps):
            x = pad_l if n_steps == 1 else pad_l + (i / (n_steps - 1)) * plot_w
            d = abs(click_x - x)
            if d < min_d:
                min_d = d
                closest = i

        self.set_current_step(closest)
        self.stepClicked.emit(closest)
        super().mousePressEvent(event)


# =============================================================================
# Collapsible Spectrum & Properties Panels
# =============================================================================

class SpectrumPanel(QWidget):
    """Bottom spectrum panel matching .dc mock layout (IR Spectrum + Convergence tabs)."""

    hideRequested = Signal()
    modeSelected = Signal(int)
    stepSelected = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedHeight(230)
        self.active_tab = "ir"  # "ir" or "conv"
        self._build_ui()
        self._apply_theme()
        get_theme_bus().theme_changed.connect(self._apply_theme)

    def minimumSizeHint(self) -> QSize:
        return QSize(200, 100)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(1, 1, 1, 1)
        root.setSpacing(0)

        # Container card
        self.card = QWidget(self)
        self.card.setObjectName("spectrum_card")
        card_v = QVBoxLayout(self.card)
        card_v.setContentsMargins(12, 8, 12, 10)
        card_v.setSpacing(8)

        # Header with tabs and hide button
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)

        self.btn_tab_ir = QPushButton("ИК-спектр", self.card)
        self.btn_tab_ir.setCheckable(True)
        self.btn_tab_ir.setChecked(True)
        self.btn_tab_ir.clicked.connect(lambda: self.set_tab("ir"))

        self.btn_tab_conv = QPushButton("Сходимость", self.card)
        self.btn_tab_conv.setCheckable(True)
        self.btn_tab_conv.setChecked(False)
        self.btn_tab_conv.clicked.connect(lambda: self.set_tab("conv"))

        self.btn_hide = QPushButton("Скрыть", self.card)
        self.btn_hide.setObjectName("btn_hide")
        self.btn_hide.clicked.connect(self.hideRequested.emit)

        header.addWidget(self.btn_tab_ir)
        header.addWidget(self.btn_tab_conv)
        header.addStretch(1)
        header.addWidget(self.btn_hide)
        card_v.addLayout(header)

        # Tab content container
        content_h = QHBoxLayout()
        content_h.setContentsMargins(0, 0, 0, 0)
        content_h.setSpacing(16)

        # 1. IR Tab Content
        self.ir_widget = QWidget(self.card)
        ir_h = QHBoxLayout(self.ir_widget)
        ir_h.setContentsMargins(0, 0, 0, 0)
        ir_h.setSpacing(14)

        self.ir_plot = IRSpectrumPlot(self.ir_widget)
        self.ir_plot.modeClicked.connect(self._on_mode_clicked)

        # Modes list right panel
        self.modes_list = QWidget(self.ir_widget)
        self.modes_list.setFixedWidth(280)
        self.modes_v = QVBoxLayout(self.modes_list)
        self.modes_v.setContentsMargins(4, 4, 4, 4)
        self.modes_v.setSpacing(4)
        self.modes_v.setAlignment(Qt.AlignTop)

        ir_h.addWidget(self.ir_plot, 1)
        ir_h.addWidget(self.modes_list, 0)

        # 2. Convergence Tab Content
        self.conv_widget = QWidget(self.card)
        conv_h = QHBoxLayout(self.conv_widget)
        conv_h.setContentsMargins(0, 0, 0, 0)
        conv_h.setSpacing(16)

        self.conv_plot = ConvergencePlot(self.conv_widget)
        self.conv_plot.stepClicked.connect(self.stepSelected.emit)

        self.conv_stats = QWidget(self.conv_widget)
        self.conv_stats.setFixedWidth(220)
        stats_v = QVBoxLayout(self.conv_stats)
        stats_v.setContentsMargins(8, 8, 8, 8)
        stats_v.setSpacing(10)
        stats_v.setAlignment(Qt.AlignVCenter)

        # Gmax
        self.lbl_gmax_title = QLabel("Максимальный градиент", self.conv_stats)
        self.lbl_gmax = QLabel("—", self.conv_stats)
        self.lbl_gmax.setStyleSheet("font-family: monospace; font-size: 15px; font-weight: bold;")
        # Steps
        self.lbl_steps_title = QLabel("Шагов до сходимости", self.conv_stats)
        self.lbl_steps = QLabel("—", self.conv_stats)
        self.lbl_steps.setStyleSheet("font-family: monospace; font-size: 15px; font-weight: bold;")
        # Time
        self.lbl_time_title = QLabel("Время", self.conv_stats)
        self.lbl_time = QLabel("—", self.conv_stats)
        self.lbl_time.setStyleSheet("font-family: monospace; font-size: 15px; font-weight: bold;")

        stats_v.addWidget(self.lbl_gmax_title)
        stats_v.addWidget(self.lbl_gmax)
        stats_v.addWidget(self.lbl_steps_title)
        stats_v.addWidget(self.lbl_steps)
        stats_v.addWidget(self.lbl_time_title)
        stats_v.addWidget(self.lbl_time)

        conv_h.addWidget(self.conv_plot, 1)
        conv_h.addWidget(self.conv_stats, 0)

        card_v.addWidget(self.ir_widget, 1)
        card_v.addWidget(self.conv_widget, 1)
        self.conv_widget.setVisible(False)

        root.addWidget(self.card)

    def _apply_theme(self):
        pal = get_palette()
        surface = pal.get("surface", "#ffffff")
        border = pal.get("border", "#dde2ef")
        text = pal.get("text", "#1b2440")
        muted = pal.get("muted", "#7a84a3")
        accent = pal.get("accent", "#2f5bd8")
        hover = pal.get("hover", "#f1f5ff")

        self.setStyleSheet(f"""
            #spectrum_card {{
                background: {surface};
                border: 1px solid {border};
                border-radius: 12px;
            }}
            QPushButton {{
                border: 1px solid transparent;
                border-radius: 6px;
                padding: 4px 12px;
                font-size: 13px;
                font-weight: 500;
                color: {muted};
                background: transparent;
            }}
            QPushButton:hover {{
                color: {text};
                background: {hover};
            }}
            QPushButton:checked {{
                color: {text};
                background: {hover};
                border-color: {border};
                font-weight: 600;
            }}
            #btn_hide {{
                color: {muted};
                font-size: 12px;
                padding: 3px 8px;
            }}
            QLabel {{
                color: {text};
            }}
        """)
        self.lbl_gmax_title.setStyleSheet(f"color: {muted}; font-size: 11px;")
        self.lbl_steps_title.setStyleSheet(f"color: {muted}; font-size: 11px;")
        self.lbl_time_title.setStyleSheet(f"color: {muted}; font-size: 11px;")

    def set_tab(self, tab: str):
        self.active_tab = tab
        self.btn_tab_ir.setChecked(tab == "ir")
        self.btn_tab_conv.setChecked(tab == "conv")
        self.ir_widget.setVisible(tab == "ir")
        self.conv_widget.setVisible(tab == "conv")

    def set_molecule(self, mol: Optional[Molecule]):
        if not mol:
            self.ir_plot.set_data([], [])
            self.conv_plot.set_data([])
            self._rebuild_modes_list([], [])
            self.lbl_gmax.setText("—")
            self.lbl_steps.setText("—")
            self.lbl_time.setText("—")
            return

        self.ir_plot.set_data(mol.freqs, mol.ir_km)
        self._rebuild_modes_list(mol.freqs, mol.ir_km)
        self.conv_plot.set_data(mol.opt_steps)

        if mol.opt_steps:
            last = mol.opt_steps[-1]
            gmax = last.get("max_grad", 0.0)
            self.lbl_gmax.setText(f"{gmax:.2e}" if gmax > 0 else "—")
            self.lbl_steps.setText(str(len(mol.opt_steps)))
        else:
            self.lbl_gmax.setText("—")
            self.lbl_steps.setText(str(len(mol.frames)))

        if mol.wall_time is not None:
            self.lbl_time.setText(f"{mol.wall_time:.1f} с")
        else:
            self.lbl_time.setText("—")

    def _rebuild_modes_list(self, freqs: List[float], ir_km: List[float]):
        # Clear existing mode rows
        while self.modes_v.count():
            item = self.modes_v.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if not freqs:
            lbl = QLabel("Нет мод", self.modes_list)
            lbl.setStyleSheet("color: %s; font-size: 12px;" % hex_color("muted"))
            self.modes_v.addWidget(lbl)
            return

        for k, (f, intens) in enumerate(zip(freqs, ir_km if ir_km else [0.0] * len(freqs))):
            row_btn = QPushButton(self.modes_list)
            row_btn.setCheckable(True)
            row_btn.setFixedHeight(30)
            row_h = QHBoxLayout(row_btn)
            row_h.setContentsMargins(8, 2, 8, 2)

            num_lbl = QLabel(f"{k+1}", row_btn)
            num_lbl.setFixedWidth(24)
            num_lbl.setStyleSheet("color: %s; font-size: 12px;" % hex_color("muted"))

            freq_lbl = QLabel(f"{int(round(f))} см⁻¹", row_btn)
            freq_lbl.setStyleSheet("font-family: monospace; font-size: 13px;")

            int_lbl = QLabel(f"I {int(round(intens))}", row_btn)
            int_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            int_lbl.setStyleSheet("color: %s; font-size: 12px;" % hex_color("muted"))

            row_h.addWidget(num_lbl)
            row_h.addWidget(freq_lbl, 1)
            row_h.addWidget(int_lbl)

            row_btn.clicked.connect(lambda _, idx=k: self._on_mode_clicked(idx))
            self.modes_v.addWidget(row_btn)

    def _on_mode_clicked(self, mode_idx: int):
        self.ir_plot.set_selected_mode(mode_idx)
        # Update checked state in list
        for i in range(self.modes_v.count()):
            w = self.modes_v.itemAt(i).widget()
            if isinstance(w, QPushButton):
                w.setChecked(i == mode_idx)
        self.modeSelected.emit(mode_idx)


class PropertiesPanel(QWidget):
    """Right properties panel matching .dc mock layout (Geometry, Charges, Dipole)."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedWidth(310)
        self.molecule: Optional[Molecule] = None
        self._build_ui()
        self._apply_theme()
        get_theme_bus().theme_changed.connect(self._apply_theme)

    def minimumSizeHint(self) -> QSize:
        return QSize(200, 100)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        # Header Title
        self.lbl_title = QLabel("СВОЙСТВА", self)
        self.lbl_title.setStyleSheet("font-size: 11px; font-weight: 700; letter-spacing: 0.5px;")
        root.addWidget(self.lbl_title)

        # Card 1: Geometry
        self.card_geom = QWidget(self)
        self.card_geom.setObjectName("card_geom")
        geom_v = QVBoxLayout(self.card_geom)
        geom_v.setContentsMargins(14, 12, 14, 12)
        geom_v.setSpacing(8)

        self.lbl_geom_hdr = QLabel("Геометрия, Å и °", self.card_geom)
        self.lbl_geom_hdr.setStyleSheet("font-size: 12px; font-weight: 600;")
        geom_v.addWidget(self.lbl_geom_hdr)

        self.geom_content = QWidget(self.card_geom)
        self.geom_v = QVBoxLayout(self.geom_content)
        self.geom_v.setContentsMargins(0, 0, 0, 0)
        self.geom_v.setSpacing(6)
        geom_v.addWidget(self.geom_content)
        root.addWidget(self.card_geom)

        # Card 2: Charges
        self.card_charges = QWidget(self)
        self.card_charges.setObjectName("card_charges")
        charges_v = QVBoxLayout(self.card_charges)
        charges_v.setContentsMargins(14, 12, 14, 12)
        charges_v.setSpacing(8)

        self.lbl_charges_hdr = QLabel("Заряды", self.card_charges)
        self.lbl_charges_hdr.setStyleSheet("font-size: 12px; font-weight: 600;")
        charges_v.addWidget(self.lbl_charges_hdr)

        self.charges_content = QWidget(self.card_charges)
        self.charges_v = QVBoxLayout(self.charges_content)
        self.charges_v.setContentsMargins(0, 0, 0, 0)
        self.charges_v.setSpacing(6)
        charges_v.addWidget(self.charges_content)
        root.addWidget(self.card_charges)

        # Card 3: Dipole Moment
        self.card_dipole = QWidget(self)
        self.card_dipole.setObjectName("card_dipole")
        dipole_v = QVBoxLayout(self.card_dipole)
        dipole_v.setContentsMargins(14, 12, 14, 14)
        dipole_v.setSpacing(4)

        self.lbl_dipole_hdr = QLabel("Дипольный момент", self.card_dipole)
        self.lbl_dipole_hdr.setStyleSheet("font-size: 12px; font-weight: 600;")
        self.lbl_dipole_val = QLabel("—", self.card_dipole)
        self.lbl_dipole_val.setStyleSheet("font-family: monospace; font-size: 22px; font-weight: 700;")

        dipole_v.addWidget(self.lbl_dipole_hdr)
        dipole_v.addWidget(self.lbl_dipole_val)
        root.addWidget(self.card_dipole)

        root.addStretch(1)

    def _apply_theme(self):
        pal = get_palette()
        surface = pal.get("surface", "#ffffff")
        border = pal.get("border", "#dde2ef")
        text = pal.get("text", "#1b2440")
        muted = pal.get("muted", "#7a84a3")

        self.lbl_title.setStyleSheet(f"font-size: 11px; font-weight: 700; color: {muted}; letter-spacing: 0.5px;")
        card_style = f"""
            QWidget {{
                background: {surface};
                border: 1px solid {border};
                border-radius: 12px;
                color: {text};
            }}
            QLabel {{
                border: 0;
                background: transparent;
            }}
        """
        self.card_geom.setStyleSheet(card_style)
        self.card_charges.setStyleSheet(card_style)
        self.card_dipole.setStyleSheet(card_style)

    def set_molecule(self, mol: Optional[Molecule]):
        self.molecule = mol
        self._update_geometry()
        self._update_charges()
        self._update_dipole()

    def set_measurement(self, sel: List[int], text: str):
        if text:
            # Clear and show active measurement
            self._clear_layout(self.geom_v)
            row = QHBoxLayout()
            lbl = QLabel(text, self.geom_content)
            lbl.setStyleSheet("font-weight: 600; color: #ffdd44;")
            row.addWidget(lbl)
            self.geom_v.addLayout(row)
        else:
            self._update_geometry()

    def _update_geometry(self):
        self._clear_layout(self.geom_v)
        if not self.molecule:
            lbl = QLabel("—", self.geom_content)
            lbl.setStyleSheet("color: %s;" % hex_color("muted"))
            self.geom_v.addWidget(lbl)
            return

        # Show key bonds and angles
        bonds = self.molecule.bonds_dict
        angles = self.molecule.angles_dict

        if not bonds and not angles and self.molecule.bonds:
            coords = self.molecule.coords
            syms = self.molecule.symbols
            for i, j in self.molecule.bonds[:4]:
                d = measure_distance(coords[i], coords[j])
                self._add_key_val(self.geom_v, f"r({syms[i]}–{syms[j]})", f"{d:.4f}")

        if bonds:
            for (a1, a2), val in list(bonds.items())[:4]:
                self._add_key_val(self.geom_v, f"r({a1}–{a2})", f"{val:.4f}")

        if angles:
            for (a1, a2, a3), val in list(angles.items())[:3]:
                self._add_key_val(self.geom_v, f"∠({a1}–{a2}–{a3})", f"{val:.1f}")

    def _update_charges(self):
        self._clear_layout(self.charges_v)
        if not self.molecule or not self.molecule.mulliken:
            lbl = QLabel("—", self.charges_content)
            lbl.setStyleSheet("color: %s;" % hex_color("muted"))
            self.charges_v.addWidget(lbl)
            return

        # Header row
        hdr_row = QHBoxLayout()
        hdr_atom = QLabel("Атом", self.charges_content)
        hdr_atom.setStyleSheet("color: %s; font-size: 11px;" % hex_color("muted"))
        hdr_mull = QLabel("Малликен", self.charges_content)
        hdr_mull.setStyleSheet("color: %s; font-size: 11px;" % hex_color("muted"))
        hdr_mull.setAlignment(Qt.AlignRight)
        hdr_low = QLabel("Лёвдин", self.charges_content)
        hdr_low.setStyleSheet("color: %s; font-size: 11px;" % hex_color("muted"))
        hdr_low.setAlignment(Qt.AlignRight)

        hdr_row.addWidget(hdr_atom, 1)
        hdr_row.addWidget(hdr_mull, 1)
        hdr_row.addWidget(hdr_low, 1)
        self.charges_v.addLayout(hdr_row)

        mull = self.molecule.mulliken
        low = self.molecule.lowdin
        for atom, m_val in list(mull.items())[:8]:
            row = QHBoxLayout()
            a_lbl = QLabel(atom, self.charges_content)
            m_str = f"{m_val:+.2f}"
            m_lbl = QLabel(m_str, self.charges_content)
            m_lbl.setStyleSheet("font-family: monospace; font-size: 13px;")
            m_lbl.setAlignment(Qt.AlignRight)

            l_str = f"{low.get(atom, 0.0):+.2f}" if atom in low else "—"
            l_lbl = QLabel(l_str, self.charges_content)
            l_lbl.setStyleSheet("font-family: monospace; font-size: 13px;")
            l_lbl.setAlignment(Qt.AlignRight)

            row.addWidget(a_lbl, 1)
            row.addWidget(m_lbl, 1)
            row.addWidget(l_lbl, 1)
            self.charges_v.addLayout(row)

    def _update_dipole(self):
        if self.molecule and self.molecule.dipole is not None:
            self.lbl_dipole_val.setText(f"{self.molecule.dipole:.2f} D")
        else:
            self.lbl_dipole_val.setText("—")

    def _add_key_val(self, layout: QVBoxLayout, key: str, val: str):
        row = QHBoxLayout()
        k_lbl = QLabel(key, self.geom_content)
        k_lbl.setStyleSheet("color: %s; font-size: 13px;" % hex_color("muted"))
        v_lbl = QLabel(val, self.geom_content)
        v_lbl.setStyleSheet("font-family: monospace; font-size: 13px;")
        v_lbl.setAlignment(Qt.AlignRight)
        row.addWidget(k_lbl)
        row.addWidget(v_lbl)
        layout.addLayout(row)

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())


# =============================================================================
# Composite MoleculeViewer3D Widget (3D + Spectrum + Properties)
# =============================================================================

class MoleculeViewer3D(QWidget):
    """Complete 3D visualizer containing 3D viewport, spectrum panel, and properties panel."""

    frameChanged = Signal(int)
    spectrumVisibilityChanged = Signal(bool)
    propertiesVisibilityChanged = Signal(bool)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)

        self._build_ui()
        self._sync_connections()

    def _build_ui(self):
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(12, 12, 12, 12)
        self.main_layout.setSpacing(12)

        # Center Column (3D viewport on top, Spectrum panel below)
        self.center_layout = QVBoxLayout()
        self.center_layout.setContentsMargins(0, 0, 0, 0)
        self.center_layout.setSpacing(12)

        self.viewport = _Viewer3DViewport(self)
        self.spectrum_panel = SpectrumPanel(self)
        self.properties_panel = PropertiesPanel(self)

        self.center_layout.addWidget(self.viewport, 1)
        self.center_layout.addWidget(self.spectrum_panel, 0)

        self.main_layout.addLayout(self.center_layout, 1)
        self.main_layout.addWidget(self.properties_panel, 0)

    def minimumSizeHint(self) -> QSize:
        return QSize(361, 218)

    def _sync_connections(self):
        self.viewport.frameChanged.connect(self._on_viewport_frame_changed)
        self.spectrum_panel.hideRequested.connect(lambda: self.set_spectrum_visible(False))
        self.spectrum_panel.modeSelected.connect(self.viewport.start_vibration)
        self.spectrum_panel.stepSelected.connect(self.viewport.set_frame)

    def _on_viewport_frame_changed(self, frame_idx: int):
        self.properties_panel.set_molecule(self.viewport.molecule)
        self.frameChanged.emit(frame_idx)

    # -------------------------------------------------------------------------
    # Backward compatibility API delegates
    # -------------------------------------------------------------------------

    @property
    def molecule(self) -> Optional[Molecule]:
        return self.viewport.molecule

    @molecule.setter
    def molecule(self, mol: Optional[Molecule]):
        self.load_molecule(mol)

    @property
    def style(self) -> str:
        return self.viewport.style

    @property
    def label_mode(self) -> str:
        return self.viewport.label_mode

    @property
    def measurement_mode(self) -> bool:
        return self.viewport.measurement_mode

    @property
    def selected_atoms(self) -> List[int]:
        return self.viewport.selected_atoms

    @property
    def measurement_text(self) -> str:
        return self.viewport.measurement_text

    @property
    def current_frame(self) -> int:
        return self.viewport.current_frame

    @property
    def pill_player(self) -> QWidget:
        return self.viewport.pill_player

    @property
    def step_label(self) -> QLabel:
        return self.viewport.step_label

    @property
    def energy_label(self) -> QLabel:
        return self.viewport.energy_label

    @property
    def slider(self) -> QSlider:
        return self.viewport.slider

    @property
    def btn_play(self) -> QToolButton:
        return self.viewport.btn_play

    def _calc_atom_font_size(self, r: float) -> int:
        return _calc_atom_font_size(r)

    def _get_projected_scene(self, width: int, height: int):
        return self.viewport._get_projected_scene(width, height)

    def load_molecule(self, molecule: Optional[Molecule]):
        self.viewport.load_molecule(molecule)
        self.spectrum_panel.set_molecule(molecule)
        self.properties_panel.set_molecule(molecule)

    def load_file(self, path: str):
        mol = Molecule.from_file(path)
        self.load_molecule(mol)

    def set_style(self, style: str):
        self.viewport.set_style(style)

    def set_label_mode(self, mode: str):
        self.viewport.set_label_mode(mode)

    def set_measurement_mode(self, enabled: bool):
        self.viewport.set_measurement_mode(enabled)

    def select_atom(self, atom_idx: int):
        self.viewport.select_atom(atom_idx)
        self.properties_panel.set_measurement(self.viewport.selected_atoms, self.viewport.measurement_text)

    def clear_measurement(self):
        self.viewport.clear_measurement()
        self.properties_panel.set_measurement([], "")

    def set_frame(self, frame_index: int):
        self.viewport.set_frame(frame_index)

    def reset_view(self):
        self.viewport.reset_view()

    def rotate_by(self, dx_deg: float, dy_deg: float):
        self.viewport.rotate_by(dx_deg, dy_deg)

    def pan_by(self, dx: float, dy: float):
        self.viewport.pan_by(dx, dy)

    def zoom_by(self, factor: float):
        self.viewport.zoom_by(factor)

    def play(self):
        self.viewport.play()

    def pause(self):
        self.viewport.pause()

    def toggle_play(self):
        self.viewport.toggle_play()

    def is_playing(self) -> bool:
        return self.viewport.is_playing()

    def start_vibration(self, mode_idx: int):
        self.viewport.start_vibration(mode_idx)

    def stop_vibration(self):
        self.viewport.stop_vibration()

    def is_vibrating(self) -> bool:
        return self.viewport.is_vibrating()

    @property
    def current_vibration_mode(self) -> Optional[int]:
        return self.viewport.current_vibration_mode

    def _on_vibration_step(self):
        self.viewport._on_vibration_step()

    def export_png(self, path: str, width: int = 1920, height: int = 1080, transparent: bool = False) -> bool:
        return self.viewport.export_png(path, width=width, height=height, transparent=transparent)

    # -------------------------------------------------------------------------
    # Panel visibility toggles
    # -------------------------------------------------------------------------

    def toggle_spectrum(self):
        self.set_spectrum_visible(not self.is_spectrum_visible())

    def set_spectrum_visible(self, visible: bool):
        self.spectrum_panel.setVisible(visible)
        self.spectrumVisibilityChanged.emit(visible)

    def is_spectrum_visible(self) -> bool:
        return self.spectrum_panel.isVisible()

    def toggle_properties(self):
        self.set_properties_visible(not self.is_properties_visible())

    def set_properties_visible(self, visible: bool):
        self.properties_panel.setVisible(visible)
        self.propertiesVisibilityChanged.emit(visible)

    def is_properties_visible(self) -> bool:
        return self.properties_panel.isVisible()
