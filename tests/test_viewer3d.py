"""Tests for Viewer3D: Molecule parsing, bonding, measurements, and rendering."""

import math
import os
import tempfile
import numpy as np
import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.name == "nt":
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from ffpy.gui.viewer3d import (
    ELEMENT_DATA,
    SYMBOL_TO_Z,
    Molecule,
    MoleculeViewer3D,
    measure_distance,
    measure_angle,
    measure_dihedral,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_element_database():
    """Verify all 86 elements are defined with valid properties."""
    assert len(ELEMENT_DATA) >= 86
    for z in range(1, 87):
        data = ELEMENT_DATA[z]
        assert "symbol" in data
        assert "name" in data
        assert "color" in data
        assert "rcov" in data and data["rcov"] > 0
        assert "rvdw" in data and data["rvdw"] > 0
        assert SYMBOL_TO_Z[data["symbol"].upper()] == z


def test_molecule_bonds_reference():
    """Verify strictly reference bond counts for water (2), methane (4), benzene (12)."""
    # 1. Water
    mol_water = Molecule(
        symbols=["O", "H", "H"],
        charges=[8, 1, 1],
        coords=np.array([
            [0.000, 0.000, 0.117],
            [0.000, 0.757, -0.467],
            [0.000, -0.757, -0.467]
        ])
    )
    bonds_water = mol_water.detect_bonds()
    assert len(bonds_water) == 2
    # Verify O-H bonds: (0, 1) and (0, 2)
    assert (0, 1) in bonds_water
    assert (0, 2) in bonds_water

    # 2. Methane
    mol_methane = Molecule(
        symbols=["C", "H", "H", "H", "H"],
        charges=[6, 1, 1, 1, 1],
        coords=np.array([
            [0.000000, 0.000000, 0.000000],
            [0.627600, 0.627600, 0.627600],
            [-0.627600, -0.627600, 0.627600],
            [-0.627600, 0.627600, -0.627600],
            [0.627600, -0.627600, -0.627600]
        ])
    )
    bonds_methane = mol_methane.detect_bonds()
    assert len(bonds_methane) == 4
    for h in range(1, 5):
        assert (0, h) in bonds_methane

    # 3. Benzene
    r_cc = 1.397
    r_ch = 1.084
    c_coords = [[r_cc * math.cos(i * math.pi / 3), r_cc * math.sin(i * math.pi / 3), 0.0] for i in range(6)]
    h_coords = [[(r_cc + r_ch) * math.cos(i * math.pi / 3), (r_cc + r_ch) * math.sin(i * math.pi / 3), 0.0] for i in range(6)]
    mol_benzene = Molecule(
        symbols=["C"] * 6 + ["H"] * 6,
        charges=[6] * 6 + [1] * 6,
        coords=np.array(c_coords + h_coords)
    )
    bonds_benzene = mol_benzene.detect_bonds()
    assert len(bonds_benzene) == 12


def test_measurements():
    """Verify distance, angle, and dihedral measurements on reference geometries."""
    # Water geometry: standard r(O-H) ~ 0.957 A, angle ~ 104.5 deg
    rO = np.array([0.000, 0.000, 0.117])
    rH1 = np.array([0.000, 0.757, -0.467])
    rH2 = np.array([0.000, -0.757, -0.467])

    d1 = measure_distance(rO, rH1)
    assert abs(d1 - 0.957) <= 0.005

    ang = measure_angle(rH1, rO, rH2)
    assert abs(ang - 104.5) <= 0.3

    # Staggered ethane dihedral: exactly 60.0 deg
    c1 = np.array([0.0, 0.0, -0.765])
    c2 = np.array([0.0, 0.0, 0.765])
    h1 = np.array([1.02, 0.0, -1.16])
    phi = math.radians(60.0)
    h4 = np.array([1.02 * math.cos(phi), 1.02 * math.sin(phi), 1.16])
    dih = measure_dihedral(h1, c1, c2, h4)
    assert abs(abs(dih) - 60.0) <= 0.2


def test_molecule_loaders(tmp_path):
    """Verify loading from .xyz, .molden, .out, and .inp formats."""
    # 1. Multi-frame .xyz
    xyz_content = """3
step 0  E = -76.0100000000
O   0.0000000000   0.0000000000   0.1170000000
H   0.0000000000   0.7570000000  -0.4670000000
H   0.0000000000  -0.7570000000  -0.4670000000
3
step 1  E = -76.0107465000
O   0.0000000000   0.0000000000   0.1150000000
H   0.0000000000   0.7550000000  -0.4650000000
H   0.0000000000  -0.7550000000  -0.4650000000
"""
    xyz_file = tmp_path / "water_opt.xyz"
    xyz_file.write_text(xyz_content)

    mol_xyz = Molecule.from_xyz(str(xyz_file))
    assert mol_xyz.natoms == 3
    assert len(mol_xyz.frames) == 2
    assert mol_xyz.symbols == ["O", "H", "H"]
    assert mol_xyz.energy == pytest.approx(-76.010000)

    # Change frame
    mol_xyz.set_frame(1)
    assert mol_xyz.energy == pytest.approx(-76.0107465)

    # 2. .molden format
    molden_content = """[Molden Format]
[Atoms] (Angs)
O   1   8   0.000000   0.000000   0.117000
H   2   1   0.000000   0.757000  -0.467000
H   3   1   0.000000  -0.757000  -0.467000
[GEOCONV]
energy
-76.0100000000
-76.0107460000
[GEOMETRIES] (XYZ)
3
step 0 E=-76.0100000000
O   0.0000000000   0.0000000000   0.1170000000
H   0.0000000000   0.7570000000  -0.4670000000
H   0.0000000000  -0.7570000000  -0.4670000000
3
step 1 E=-76.0107460000
O   0.0000000000   0.0000000000   0.1150000000
H   0.0000000000   0.7550000000  -0.4650000000
H   0.0000000000  -0.7550000000  -0.4650000000
"""
    molden_file = tmp_path / "water.molden"
    molden_file.write_text(molden_content)

    mol_molden = Molecule.from_molden(str(molden_file))
    assert mol_molden.natoms == 3
    assert len(mol_molden.frames) == 2

    # 3. .out format
    out_content = """
------------------------------------------------------------------------
  EQUILIBRIUM GEOMETRY
------------------------------------------------------------------------
  ATOM          Z        X (ANGS)        Y (ANGS)        Z (ANGS)          X (BOHR)        Y (BOHR)        Z (BOHR)
  O           8.0    0.0000000000    0.0000000000    0.1170000000      0.0000000000    0.0000000000    0.2211000000
  H           1.0    0.0000000000    0.7570000000   -0.4670000000      0.0000000000    1.4305000000   -0.8825000000
  H           1.0    0.0000000000   -0.7570000000   -0.4670000000      0.0000000000   -1.4305000000   -0.8825000000

 FINAL ENERGY (HARTREE)     -76.0107465085
 ffpy TERMINATED NORMALLY
"""
    out_file = tmp_path / "water.out"
    out_file.write_text(out_content)

    mol_out = Molecule.from_out(str(out_file))
    assert mol_out.natoms == 3
    assert mol_out.energy == pytest.approx(-76.0107465085)

    # 4. .inp format with symmetry expansion (Benzene D6h)
    benzene_inp = """ $CONTRL SCFTYP=RHF RUNTYP=ENERGY $END
 $BASIS  GBASIS=STO NGAUSS=3 $END
 $DATA
Benzene
DNH 6

C  6.0   1.3950000   0.0000000   0.0000000
H  1.0   2.4810000   0.0000000   0.0000000
 $END
"""
    inp_file = tmp_path / "benzene.inp"
    inp_file.write_text(benzene_inp)

    mol_inp = Molecule.from_inp(str(inp_file))
    assert mol_inp.natoms == 12
    assert mol_inp.symbols.count("C") == 6
    assert mol_inp.symbols.count("H") == 6

    # 5. .inp with Z-matrix
    zmt_inp = """ $CONTRL SCFTYP=RHF COORD=ZMT $END
 $BASIS  GBASIS=STO $END
 $DATA
Water ZMT
C1
O
H 1 0.957
H 1 0.957 2 104.5
 $END
"""
    zmt_file = tmp_path / "water_zmt.inp"
    zmt_file.write_text(zmt_inp)

    mol_zmt = Molecule.from_inp(str(zmt_file))
    assert mol_zmt.natoms == 3
    assert mol_zmt.symbols == ["O", "H", "H"]


def test_viewer_widget_lifecycle(app, tmp_path):
    """Test MoleculeViewer3D widget rendering, styles, camera, and trajectory."""
    viewer = MoleculeViewer3D()
    viewer.resize(800, 600)
    viewer.show()

    # Load multi-frame trajectory
    xyz_content = """3
step 0  E = -76.0100000000
O   0.0000000000   0.0000000000   0.1170000000
H   0.0000000000   0.7570000000  -0.4670000000
H   0.0000000000  -0.7570000000  -0.4670000000
3
step 1  E = -76.0107465000
O   0.0000000000   0.0000000000   0.1150000000
H   0.0000000000   0.7550000000  -0.4650000000
H   0.0000000000  -0.7550000000  -0.4650000000
"""
    xyz_file = tmp_path / "water_opt.xyz"
    xyz_file.write_text(xyz_content)

    viewer.load_file(str(xyz_file))
    assert viewer.molecule is not None
    assert viewer.molecule.natoms == 3

    # Display styles
    viewer.set_style("ball_and_stick")
    assert viewer.style == "ball_and_stick"
    viewer.set_style("sticks")
    assert viewer.style == "sticks"
    viewer.set_style("vdw")
    assert viewer.style == "vdw"

    # Atom labels
    viewer.set_label_mode("none")
    assert viewer.label_mode == "none"
    viewer.set_label_mode("symbol")
    assert viewer.label_mode == "symbol"
    viewer.set_label_mode("symbol_number")
    assert viewer.label_mode == "symbol_number"

    # Trajectory controls
    viewer.set_frame(1)
    assert viewer.current_frame == 1
    assert viewer.step_label.text() == "Шаг 2 из 2"

    # Play/Pause
    viewer.play()
    assert viewer.is_playing()
    viewer.pause()
    assert not viewer.is_playing()

    # Camera controls
    viewer.rotate_by(10.0, 5.0)
    viewer.zoom_by(1.2)
    viewer.pan_by(15, -10)
    viewer.reset_view()

    # Measurement selection
    viewer.set_measurement_mode(True)
    viewer.select_atom(0)
    assert viewer.selected_atoms == [0]
    viewer.select_atom(1)
    assert viewer.selected_atoms == [0, 1]
    assert viewer.measurement_text.startswith("r =") or "Å" in viewer.measurement_text

    viewer.select_atom(2)
    assert viewer.selected_atoms == [0, 1, 2]
    assert "°" in viewer.measurement_text

    # Esc key clears selection
    viewer.clear_measurement()
    assert len(viewer.selected_atoms) == 0

    # PNG Export offscreen
    png_path = tmp_path / "export_test.png"
    ok = viewer.export_png(str(png_path), width=800, height=600)
    assert ok
    assert png_path.exists()
    assert png_path.stat().st_size > 1000

    # Verify exported image is valid
    img = QImage(str(png_path))
    assert not img.isNull()
    assert img.width() == 800
    assert img.height() == 600

    viewer.close()


def test_viewer_projection_and_depth_sorting():
    """Verify 3D perspective projection and ascending depth sorting (painter's algorithm)."""
    mol = Molecule(
        symbols=["O", "H", "H"],
        charges=[8, 1, 1],
        coords=np.array([
            [0.0, 0.0, 1.5],
            [0.0, 0.8, -0.5],
            [0.0, -0.8, -1.0],
        ])
    )
    viewer = MoleculeViewer3D()
    viewer.load_molecule(mol)
    primitives, screen_pts = viewer._get_projected_scene(800, 600)
    assert len(primitives) >= 3

    # Painter's algorithm requirement: primitives must be strictly sorted by ascending z
    z_values = [p["z"] for p in primitives]
    assert z_values == sorted(z_values)
    viewer.close()


def test_mainwindow_3d_integration(app, tmp_path):
    """Verify integration of MoleculeViewer3D in MainWindow and auto-load on optimization finish."""
    from ffpy.gui.app import MainWindow

    win = MainWindow()
    win.resize(1000, 700)
    win.show()

    # 1. 3D mode on rail
    win.set_mode(2)
    assert win.stack.currentIndex() == 2
    assert win.viewer3d is not None
    assert win.stub_3d is win.viewer3d

    # 2. Open file in 3D
    xyz_content = """3
step 0  E = -76.0100000000
O   0.0000000000   0.0000000000   0.1170000000
H   0.0000000000   0.7570000000  -0.4670000000
H   0.0000000000  -0.7570000000  -0.4670000000
"""
    xyz_path = tmp_path / "test_run.xyz"
    xyz_path.write_text(xyz_content)

    inp_path = tmp_path / "test_run.inp"
    inp_path.write_text("! mock inp")

    win.open_in_3d(str(xyz_path))
    assert win.viewer3d.molecule is not None
    assert win.viewer3d.molecule.natoms == 3

    # 3. Trajectory auto-load on run finished
    win.viewer3d.molecule = None
    win._on_run_finished(str(inp_path), code=0)
    assert win.viewer3d.molecule is not None
    assert win.viewer3d.molecule.natoms == 3

    win.close()

