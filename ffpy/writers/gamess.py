"""Optional GAMESS-like blocks (--gamess), for viewers that only parse
GAMESS logs. The layout was written from general knowledge of GAMESS
output and must be checked against example outputs from the Firefly
distribution; the program header is ffpy's own and does not imitate
Firefly.
"""

import numpy as np

from ffpy.constants import BOHR_ANG


def coordinates_bohr(log, symbols, charges, coords):
    log("")
    log(" ATOM      ATOMIC                      COORDINATES (BOHR)")
    log("           CHARGE         X                   Y                   Z")
    for s, z, c in zip(symbols, charges, coords):
        log(" %-10s%5.1f  %18.10f  %18.10f  %18.10f" % (s.upper(), z, c[0], c[1], c[2]))


def coordinates_angs(log, symbols, charges, coords, title="COORDINATES OF ALL ATOMS ARE (ANGS)"):
    log("")
    log(" " + title)
    log("   ATOM   CHARGE       X              Y              Z")
    log(" ------------------------------------------------------------")
    for s, z, c in zip(symbols, charges, coords * BOHR_ANG):
        log(" %-8s%6.1f  %14.10f %14.10f %14.10f" % (s.upper(), z, c[0], c[1], c[2]))


def final_energy(log, kind, energy, niter):
    log("")
    log("          FINAL %s ENERGY IS %20.10f AFTER %3d ITERATIONS" % (kind, energy, niter))


def eigenvectors(log, mol, mo_energy, mo_coeff, title="EIGENVECTORS"):
    labels = mol.ao_labels(fmt=False)
    log("")
    log("          ------------")
    log("          " + title)
    log("          ------------")
    nmo = mo_coeff.shape[1]
    for c0 in range(0, nmo, 5):
        cols = range(c0, min(c0 + 5, nmo))
        log("")
        log("                 " + "".join("%11d" % (j + 1) for j in cols))
        log("                 " + "".join("%11.4f" % mo_energy[j] for j in cols))
        log("                 " + "".join("%11s" % "A" for _ in cols))
        for i, (ia, sym, nl, mlab) in enumerate(labels):
            ao = (nl[-1:] if nl else "") + mlab
            ao = ao.upper()[:4]
            log("%5d  %-2s%3d  %-4s" % (i + 1, sym.upper(), ia + 1, ao)
                + "".join("%11.6f" % mo_coeff[i, j] for j in cols))


def nserch(log, step, energy, grad):
    g = np.asarray(grad)
    log("")
    log(" NSERCH:%4d  E=%20.10f  GRAD. MAX=%11.7f  R.M.S.=%11.7f"
        % (step, energy, np.abs(g).max(), np.sqrt(np.mean(g ** 2))))


def equilibrium(log, symbols, charges, coords):
    log("")
    log("      ***** EQUILIBRIUM GEOMETRY LOCATED *****")
    coordinates_angs(log, symbols, charges, coords)


def frequencies(log, symbols, freq):
    wn = freq["wavenumbers"]
    modes = freq["modes"]
    log("")
    log("     FREQUENCIES IN CM**-1, IR INTENSITIES IN DEBYE**2/AMU-ANGSTROM**2")
    for c0 in range(0, len(wn), 5):
        cols = range(c0, min(c0 + 5, len(wn)))
        log("")
        log("                       " + "".join("%12d" % (k + 1) for k in cols))
        log("       FREQUENCY:      " + "".join(
            ("%11.2f I" % -wn[k]) if wn[k] < 0 else "%12.2f" % wn[k] for k in cols))
        log("        SYMMETRY:      " + "".join("%12s" % "A" for _ in cols))
        log("    REDUCED MASS:      " + "".join("%12.5f" % freq["reduced_mass"][k] for k in cols))
        log("    IR INTENSITY:      " + "".join("%12.5f" % freq["ir_d2"][k] for k in cols))
        log("")
        for a, s in enumerate(symbols):
            for x, ax in enumerate("XYZ"):
                head = ("%4d   %-8s" % (a + 1, s.upper())) if x == 0 else " " * 15
                log("  %s%2s      " % (head, ax) + "".join("%12.8f" % modes[k][a][x] for k in cols))
