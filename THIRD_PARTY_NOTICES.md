# Third-party software

The Windows build of ffpy (ffpy.exe and the `_internal` folder) bundles the
following libraries. Their license files are included in `_internal` next
to each package (`*.dist-info` folders) where the package ships them.

| Component | License | Project |
|---|---|---|
| PySCF | Apache-2.0 | https://github.com/pyscf/pyscf |
| libcint | BSD-2-Clause | https://github.com/sunqm/libcint |
| Libxc | MPL-2.0 | https://libxc.gitlab.io |
| XCFun | MPL-2.0 | https://github.com/dftlibs/xcfun |
| geomeTRIC | BSD-3-Clause | https://github.com/leeping/geomeTRIC |
| NumPy | BSD-3-Clause | https://numpy.org |
| SciPy | BSD-3-Clause | https://scipy.org |
| h5py / HDF5 | BSD-3-Clause | https://www.h5py.org |
| NetworkX | BSD-3-Clause | https://networkx.org |
| OpenBLAS | BSD-3-Clause | https://www.openblas.net |
| Python | PSF-2.0 | https://www.python.org |

ffpy does not contain any code or files from Firefly. Behaviour was
written from public documentation, the input format and observed results.
