"""ffpy: Firefly/GAMESS-style input front end for PySCF."""

import os

# PySCF parallelizes with its own OpenMP threads and calls BLAS inside them.
# The Windows conda-forge PySCF links MKL; threaded MKL nested in those
# threads made DFT response/TDDFT up to 20x slower. Must be set before
# NumPy/MKL is loaded.
os.environ.setdefault("MKL_THREADING_LAYER", "SEQUENTIAL")

__version__ = "0.2.0"
PROGRAM = "ffpy"
