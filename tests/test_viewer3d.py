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
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QApplication

from ffpy.gui.viewer3d import (
    ELEMENT_DATA,
    SYMBOL_TO_Z,
    Molecule,
    MoleculeViewer3D,
    compute_principal_axes,
    lorentzian_spectrum,
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


def test_principal_axes_orientation():
    """Verify principal axes orientation maps planar water and benzene flat to screen (Z ~ 0)."""
    # 1. Water in YZ plane (x=0)
    water_coords = np.array([
        [0.000, 0.000, 0.117],
        [0.000, 0.757, -0.467],
        [0.000, -0.757, -0.467],
    ])
    masses = np.array([16.0, 1.0, 1.0])
    R_water = compute_principal_axes(water_coords, masses)

    com = np.average(water_coords, axis=0, weights=masses)
    centered = water_coords - com
    rotated = (R_water @ centered.T).T

    # All Z coordinates must be zero within tolerance
    assert np.all(np.abs(rotated[:, 2]) < 1e-5)
    # Extent along X (H-H vector, ~1.514 A) must be greater than extent along Y
    x_span = np.max(rotated[:, 0]) - np.min(rotated[:, 0])
    y_span = np.max(rotated[:, 1]) - np.min(rotated[:, 1])
    assert x_span > y_span
    assert np.isclose(np.linalg.det(R_water), 1.0)

    # 2. Benzene in XY plane
    r_cc = 1.397
    r_ch = 1.084
    c_coords = [[r_cc * math.cos(i * math.pi / 3), r_cc * math.sin(i * math.pi / 3), 0.0] for i in range(6)]
    h_coords = [[(r_cc + r_ch) * math.cos(i * math.pi / 3), (r_cc + r_ch) * math.sin(i * math.pi / 3), 0.0] for i in range(6)]
    benzene_coords = np.array(c_coords + h_coords)
    b_masses = np.array([12.0] * 6 + [1.0] * 6)
    R_benz = compute_principal_axes(benzene_coords, b_masses)
    b_com = np.average(benzene_coords, axis=0, weights=b_masses)
    b_rot = (R_benz @ (benzene_coords - b_com).T).T
    assert np.all(np.abs(b_rot[:, 2]) < 1e-5)
    assert np.isclose(np.linalg.det(R_benz), 1.0)


def test_atom_label_font_size(app):
    """Verify atom label font size dynamic calculation and strict upper bound of 14 px."""
    viewer = MoleculeViewer3D()
    for r in [6.0, 10.0, 18.0, 25.0, 40.0, 80.0, 120.0]:
        sz = viewer._calc_atom_font_size(r)
        assert sz <= 14
        assert sz >= 8
    viewer.close()


def test_lorentzian_broadening_integral():
    """Verify Lorentzian broadening function and conservation of total integrated band intensity."""
    freqs = [1826.55, 4070.47, 4188.71]
    intensities = [99.0, 14.0, 66.0]
    grid = np.linspace(500, 5000, 45000)
    fwhm = 20.0

    spec = lorentzian_spectrum(freqs, intensities, grid, fwhm=fwhm)
    assert spec.shape == grid.shape
    assert np.all(spec >= 0)

    trapz_func = getattr(np, "trapezoid", getattr(np, "trapz", None))
    integral = trapz_func(spec, grid)
    total_expected = sum(intensities)
    rel_error = abs(integral - total_expected) / total_expected
    # Error should be well under 1%
    assert rel_error < 0.01


def test_outparse_opt_steps_and_normal_modes():
    """Verify outparse extraction of optimization steps and vibrational normal mode displacements."""
    from ffpy.outparse import parse_text

    sample_out = """
------------------------------------------------------------------------
  geometry optimization (geomeTRIC)
------------------------------------------------------------------------
  STEP               ENERGY        DELTA E       MAX GRAD       RMS GRAD
     0       -76.0100000000   0.000000E+00   2.345678E-02   1.234567E-02
     1       -76.0107465085  -7.465085E-04   9.700000E-06   4.200000E-06

------------------------------------------------------------------------
  vibrational analysis
------------------------------------------------------------------------
   MODE    FREQ (CM-1)  RED.MASS(AMU)  FORCE(MDYN/A)   IR (D2/AMU-A2)      IR (KM/MOL)
      1      1826.5500       1.082000       2.134000         0.245000          99.1200
      2      4070.4700       1.045000       9.876000         0.035000          14.2300
      3      4188.7100       1.081000      10.456000         0.162000          66.4500

  normal modes (cartesian displacements, mass-weighted modes normalized):

  MODE                  1             2             3
  FREQ            1826.55       4070.47       4188.71
  O1       X       0.00000000    0.00000000    0.00000000
  O1       Y       0.00000000    0.00000000    0.06890000
  O1       Z      -0.06640000    0.05210000    0.00000000
  H2       X       0.00000000    0.00000000    0.00000000
  H2       Y      -0.42830000   -0.55620000   -0.54710000
  H2       Z       0.52690000   -0.41320000   -0.42150000
  H3       X       0.00000000    0.00000000    0.00000000
  H3       Y       0.42830000    0.55620000   -0.54710000
  H3       Z       0.52690000   -0.41320000    0.42150000

  wall time 4.2 s
ffpy TERMINATED NORMALLY
"""
    res = parse_text(sample_out)

    # Opt steps
    assert "opt_steps" in res
    assert len(res["opt_steps"]) == 2
    s0 = res["opt_steps"][0]
    assert s0["step"] == 0
    assert s0["energy"] == pytest.approx(-76.01)
    s1 = res["opt_steps"][1]
    assert s1["step"] == 1
    assert s1["energy"] == pytest.approx(-76.0107465085)
    assert s1["max_grad"] == pytest.approx(9.7e-6)

    # Normal modes
    assert "normal_modes" in res
    assert len(res["normal_modes"]) == 3
    m1 = res["normal_modes"][0]  # Mode 1, 3 atoms
    assert len(m1) == 3
    assert m1[0] == pytest.approx([0.0, 0.0, -0.0664])
    assert m1[1] == pytest.approx([0.0, -0.4283, 0.5269])
    assert m1[2] == pytest.approx([0.0, 0.4283, 0.5269])


def test_vibrational_harmonic_animation(app):
    """Verify harmonic animation of vibrational displacements in MoleculeViewer3D."""
    mol = Molecule(
        symbols=["O", "H", "H"],
        charges=[8, 1, 1],
        coords=np.array([
            [0.000, 0.000, 0.117],
            [0.000, 0.757, -0.467],
            [0.000, -0.757, -0.467],
        ]),
    )
    mol.freqs = [1826.55, 4070.47, 4188.71]
    mol.ir_km = [99.12, 14.23, 66.45]
    mol.normal_modes = [
        np.array([[0.0, 0.0, -0.0664], [0.0, -0.4283, 0.5269], [0.0, 0.4283, 0.5269]]),
        np.array([[0.0, 0.0, 0.0521], [0.0, -0.5562, -0.4132], [0.0, 0.5562, -0.4132]]),
        np.array([[0.0, 0.0689, 0.0], [0.0, -0.5471, -0.4215], [0.0, -0.5471, 0.4215]]),
    ]

    viewer = MoleculeViewer3D()
    viewer.resize(800, 600)
    viewer.load_molecule(mol)

    base_coords = mol.coords.copy()

    # Start vibration for mode 0
    viewer.start_vibration(0)
    assert viewer.is_vibrating()
    assert viewer.current_vibration_mode == 0

    # Advance one step in vibration timer
    viewer._on_vibration_step()
    # Coordinates should have displaced
    assert not np.allclose(mol.coords, base_coords)

    # Stop vibration
    viewer.stop_vibration()
    assert not viewer.is_vibrating()
    # Coordinates must return to equilibrium
    assert np.allclose(mol.coords, base_coords)

    viewer.close()


def test_spectrum_and_properties_panels_toggle_and_settings(app, tmp_path):
    """Verify toggling Spectrum and Properties panels and persistence in QSettings."""
    from ffpy.gui.app import MainWindow
    from PySide6.QtCore import QSettings

    win = MainWindow()
    win.resize(1000, 700)
    win.show()

    # Switch to 3D mode
    win.set_mode(2)
    assert win.btn_toggle_spectrum.isVisible()
    assert win.btn_toggle_props.isVisible()

    viewer = win.viewer3d
    # Defaults are open
    assert viewer.is_spectrum_visible()
    assert viewer.is_properties_visible()

    # Toggle off spectrum
    win.btn_toggle_spectrum.setChecked(False)
    assert not viewer.is_spectrum_visible()
    assert win.settings.value("viewer3d/spectrum_open", True, type=bool) is False

    # Toggle off props
    win.btn_toggle_props.setChecked(False)
    assert not viewer.is_properties_visible()
    assert win.settings.value("viewer3d/props_open", True, type=bool) is False

    # Toggle back on
    win.btn_toggle_spectrum.setChecked(True)
    win.btn_toggle_props.setChecked(True)
    assert viewer.is_spectrum_visible()
    assert viewer.is_properties_visible()

    win.close()


def test_generate_016_screenshots(app, tmp_path):
    """Generate reference screenshots .ai/shots/016_light.png and 016_dark.png offscreen."""
    from ffpy.gui.app import MainWindow
    from ffpy.gui.theme import set_theme_mode

    win = MainWindow()
    win.resize(1338, 800)
    win.show()

    # Create water molecule with optimization steps, frequencies, normal modes, and properties
    coords_0 = np.array([
        [0.000, 0.000, 0.125],
        [0.000, 0.770, -0.475],
        [0.000, -0.770, -0.475],
    ])
    coords_1 = np.array([
        [0.000, 0.000, 0.117],
        [0.000, 0.757, -0.467],
        [0.000, -0.757, -0.467],
    ])
    frames = [
        {"coords": coords_0, "energy": -76.0100000000, "title": "step 0"},
        {"coords": coords_1, "energy": -76.0107465085, "title": "step 1"},
    ]
    mol = Molecule(
        symbols=["O", "H", "H"],
        coords=coords_1,
        charges=[8, 1, 1],
        frames=frames,
        energy=-76.0107465085,
        title="water_opt.out · RHF/6-31G(d) · OPTIMIZE",
    )
    mol.freqs = [1826.55, 4070.47, 4188.71]
    mol.ir_km = [99.12, 14.23, 66.45]
    mol.normal_modes = [
        np.array([[0.0, 0.0, -0.0664], [0.0, -0.4283, 0.5269], [0.0, 0.4283, 0.5269]]),
        np.array([[0.0, 0.0, 0.0521], [0.0, -0.5562, -0.4132], [0.0, 0.5562, -0.4132]]),
        np.array([[0.0, 0.0689, 0.0], [0.0, -0.5471, -0.4215], [0.0, -0.5471, 0.4215]]),
    ]
    mol.opt_steps = [
        {"step": 0, "energy": -76.0100000000, "delta_e": 0.0, "max_grad": 2.345678e-2, "rms_grad": 1.234567e-2},
        {"step": 1, "energy": -76.0107465085, "delta_e": -7.465085e-4, "max_grad": 9.7e-6, "rms_grad": 4.2e-6},
    ]
    mol.mulliken = {"O1": -0.79, "H2": 0.40, "H3": 0.40}
    mol.lowdin = {"O1": -0.48, "H2": 0.24, "H3": 0.24}
    mol.dipole = 2.20
    mol.wall_time = 4.2
    mol.bonds_dict = {("O1", "H2"): 0.9473, ("O1", "H3"): 0.9473}
    mol.angles_dict = {("H2", "O1", "H3"): 105.5}

    win.viewer3d.load_molecule(mol)
    win.set_mode(2)
    win.btn_toggle_spectrum.setChecked(True)
    win.btn_toggle_props.setChecked(True)

    shots_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".ai", "shots")
    os.makedirs(shots_dir, exist_ok=True)

    # 1. Light theme shot
    set_theme_mode("light")
    app.processEvents()
    pix_light = QPixmap(win.size())
    win.render(pix_light)
    light_path = os.path.join(shots_dir, "016_light.png")
    pix_light.save(light_path, "PNG")
    assert os.path.exists(light_path)
    assert os.path.getsize(light_path) > 10000

    # 2. Dark theme shot
    set_theme_mode("dark")
    app.processEvents()
    pix_dark = QPixmap(win.size())
    win.render(pix_dark)
    dark_path = os.path.join(shots_dir, "016_dark.png")
    pix_dark.save(dark_path, "PNG")
    assert os.path.exists(dark_path)
    assert os.path.getsize(dark_path) > 10000

    win.close()


