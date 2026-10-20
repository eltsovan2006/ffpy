# PyInstaller spec for ffpy.exe (one-folder build). Run via packaging/build.ps1.
import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

datas, binaries, hiddenimports = [], [], []
for pkg in ("pyscf", "geometric"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h
hiddenimports += collect_submodules("ffpy")

# On Windows pyscf.lib.load_library() looks for libcint/xc/xcfun next to its
# own DLLs or in sys.prefix\Library\bin; put them next to pyscf\lib\*.dll.
env_bin = os.path.join(sys.prefix, "Library", "bin")
for dll in ("libcint.dll", "xc.dll", "xcfun.dll"):
    binaries.append((os.path.join(env_bin, dll), os.path.join("pyscf", "lib")))

a = Analysis(
    [os.path.join(SPECPATH, "ffpy_entry.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "IPython", "jupyter", "notebook", "PyQt5",
              "PySide2", "PySide6", "pytest", "sphinx"],
    noarchive=False,
)

# ffpy runs MKL in sequential mode (see ffpy/__init__.py), so its threading
# layers, cluster and vector-math libraries and the TBB -> hwloc -> libxml2 ->
# ICU chain they pull in are not needed.
_DROP = ("mkl_intel_thread", "mkl_tbb_thread", "mkl_pgi_thread", "mkl_scalapack",
         "mkl_blacs", "mkl_cdft", "mkl_vml", "tbb", "libhwloc", "libxml2", "icu",
         "libiomp5")
# Found by pyscf\lib\*.dll from their own folder; the top-level copies that
# PyInstaller's dependency scan adds are duplicates.
_MOVED = {"libcint.dll", "xc.dll", "xcfun.dll"}


def _keep(entry):
    dest = entry[0].replace("\\", "/")
    name = os.path.basename(dest).lower()
    if "/" not in dest and name in _MOVED:
        return False
    return not any(name.startswith(p) for p in _DROP)


a.binaries = [b for b in a.binaries if _keep(b)]
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ffpy",
    console=True,
    icon=None,
    version=os.path.join(SPECPATH, "version_info.txt"),
)
coll = COLLECT(exe, a.binaries, a.datas, name="ffpy", upx=False)
