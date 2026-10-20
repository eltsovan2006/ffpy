"""name.dat: final geometry as $DATA and orbitals as $VEC, ready to paste into
a new input with  $GUESS GUESS=MOREAD NORB=n $END.

$VEC uses PySCF AO order (not GAMESS order): it is meant for ffpy itself.
"""

import numpy as np

from ffpy.constants import BOHR_ANG


def _vec_lines(C, start=0):
    lines = []
    for j in range(C.shape[1]):
        col = C[:, j]
        label = (start + j + 1) % 100
        for k in range(0, len(col), 5):
            chunk = col[k:k + 5]
            lines.append("%2d%3d%s" % (label, (k // 5 + 1) % 1000,
                                         "".join("%15.8E" % v for v in chunk)))
    return lines


def write(path, job, res, energy, method):
    mol = res.mol
    out = ["! ffpy restart data. Paste $DATA and $VEC into a new input and add",
           "!   $GUESS GUESS=MOREAD NORB=%d $END" % mol.nao,
           "! method %s, final energy %.10f" % (job.describe(), energy),
           " $DATA", job.title or "ffpy", "C1"]
    for lab, z, c in zip(job.labels, job.charges, mol.atom_coords() * BOHR_ANG):
        out.append("%-8s %5.1f %16.10f %16.10f %16.10f" % (lab, z, c[0], c[1], c[2]))
    out.append(" $END")
    if method == "CASSCF":
        C = res.post.mo_coeff
        out.append("! CASSCF natural orbitals")
    else:
        C = res.mf.mo_coeff
    C = np.asarray(C)
    out.append("! %d AO x %d MO, PySCF AO order, %s basis functions"
               % (mol.nao, C.shape[-1], "Cartesian" if mol.cart else "spherical"))
    out.append(" $VEC")
    if C.ndim == 3:
        out += _vec_lines(C[0]) + _vec_lines(C[1])
    else:
        out += _vec_lines(C)
    out.append(" $END")
    with open(path, "w", encoding="ascii", newline="\n") as f:
        f.write("\n".join(out) + "\n")
