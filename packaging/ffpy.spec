# PyInstaller spec: ffpy.exe (console) and ffpy-gui.exe (windowed) in one
# folder sharing _internal. Run via packaging/build.ps1.
import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
ICON = os.path.join(SPECPATH, "ffpy.ico")
VERSION = os.path.join(SPECPATH, "version_info.txt")

datas, binaries, hiddenimports = [], [], []
for pkg in ("pyscf", "geometric"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h
hiddenimports += collect_submodules("ffpy", filter=lambda name: not name.startswith("ffpy.gui"))

# On Windows pyscf.lib.load_library() looks for libcint/xc/xcfun next to its
# own DLLs or in sys.prefix\Library\bin; put them next to pyscf\lib\*.dll.
env_bin = os.path.join(sys.prefix, "Library", "bin")
for dll in ("libcint.dll", "xc.dll", "xcfun.dll"):
    binaries.append((os.path.join(env_bin, dll), os.path.join("pyscf", "lib")))

cli = Analysis(
    [os.path.join(SPECPATH, "ffpy_entry.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "IPython", "jupyter", "notebook", "PyQt5",
              "PySide2", "PySide6", "shiboken6", "pytest", "sphinx"],
    noarchive=False,
)
gui = Analysis(
    [os.path.join(SPECPATH, "ffpy_gui_entry.py")],
    pathex=[ROOT],
    hiddenimports=collect_submodules("ffpy.gui"),
    excludes=["tkinter", "matplotlib", "IPython", "jupyter", "notebook", "PyQt5", "PySide2",
              "pytest", "sphinx", "pyscf", "geometric", "scipy", "h5py",
              "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
              "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtCharts",
              "PySide6.QtDataVisualization", "PySide6.QtPdf"],
    noarchive=False,
)

# ffpy runs MKL in sequential mode (see ffpy/__init__.py), so its threading
# layers, cluster and vector-math libraries and the TBB -> hwloc -> libxml2
# chain they pull in are not needed. (ICU stays: Qt6Core links icuuc/icuin.)
_DROP = ("mkl_intel_thread", "mkl_tbb_thread", "mkl_pgi_thread", "mkl_scalapack",
         "mkl_blacs", "mkl_cdft", "mkl_vml", "tbb", "libhwloc", "libxml2",
         "libiomp5", "qt6webengine", "qt6quick", "qt6qml", "qt6pdf", "qt6multimedia",
         "qt63d", "qt6charts", "qt6datavisualization", "opengl32sw")
# Found by pyscf\lib\*.dll from their own folder; the top-level copies that
# PyInstaller's dependency scan adds are duplicates.
_MOVED = {"libcint.dll", "xc.dll", "xcfun.dll"}


def _keep(entry):
    dest = entry[0].replace("\\", "/")
    name = os.path.basename(dest).lower()
    if "/" not in dest and name in _MOVED:
        return False
    return not any(name.startswith(p) for p in _DROP)


for a in (cli, gui):
    a.binaries = [b for b in a.binaries if _keep(b)]

cli_exe = EXE(PYZ(cli.pure), cli.scripts, [], exclude_binaries=True, name="ffpy",
              console=True, icon=ICON, version=VERSION)
gui_exe = EXE(PYZ(gui.pure), gui.scripts, [], exclude_binaries=True, name="ffpy-gui",
              console=False, icon=ICON, version=VERSION)
coll = COLLECT(cli_exe, cli.binaries, cli.datas,
               gui_exe, gui.binaries, gui.datas,
               name="ffpy", upx=False)
