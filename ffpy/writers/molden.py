"""name.molden: geometry, basis, orbitals; frequencies and optimization path
when available. Read by Chemcraft, Avogadro, Jmol, Molden."""

from pyscf.tools import molden as pmolden

from ffpy.constants import BOHR_ANG


def _write_orbitals(path, res, method):
    if method == "CASSCF":
        pmolden.from_mcscf(res.post, path)
    else:
        pmolden.from_scf(res.mf, path)


def write(path, res, method, freq=None, trajectory=None, symbols=None):
    _write_orbitals(path, res, method)
    stem = path[:-7] if path.lower().endswith(".molden") else path
    written = [path]
    if freq is not None:
        freq_path = stem + "_freq.molden"
        _write_orbitals(freq_path, res, method)
        with open(freq_path, "a", encoding="ascii", newline="\n") as f:
            _freq(f, res.mol, freq)
        written.append(freq_path)
    if trajectory and len(trajectory) > 1:
        opt_path = stem + "_opt.molden"
        _write_orbitals(opt_path, res, method)
        with open(opt_path, "a", encoding="ascii", newline="\n") as f:
            _geoconv(f, trajectory, symbols)
        written.append(opt_path)
    return written


def _freq(f, mol, freq):
    wn = freq["wavenumbers"]
    f.write("[FREQ]\n")
    for w in wn:
        f.write("%14.6f\n" % w)
    f.write("[FR-COORD]\n")
    for i in range(mol.natm):
        x, y, z = mol.atom_coord(i)
        f.write("%-3s %16.10f %16.10f %16.10f\n" % (mol.atom_pure_symbol(i), x, y, z))
    f.write("[FR-NORM-COORD]\n")
    for k, mode in enumerate(freq["modes"]):
        f.write(" vibration %6d\n" % (k + 1))
        for row in mode:
            f.write("%16.10f %16.10f %16.10f\n" % tuple(row))
    f.write("[INT]\n")
    for v in freq["ir_km"]:
        f.write("%14.6f\n" % v)


def _geoconv(f, trajectory, symbols):
    f.write("[GEOCONV]\nenergy\n")
    for e, _ in trajectory:
        f.write("%20.10f\n" % e)
    f.write("[GEOMETRIES] (XYZ)\n")
    for k, (e, coords) in enumerate(trajectory):
        f.write("%d\nstep %d E=%.10f\n" % (len(symbols), k, e))
        for s, c in zip(symbols, coords * BOHR_ANG):
            f.write("%-3s %16.10f %16.10f %16.10f\n" % (s, c[0], c[1], c[2]))
