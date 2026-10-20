"""Point groups in $DATA: generate all atoms from the symmetry-unique ones.

Orientation follows the GAMESS "master frame": the principal axis is z,
the C2' axis of Dn/Dnh/Dnd groups is x, the sigma_v plane of Cnv is xz,
the plane of Cs is xy, and in T/Td/Th/O/Oh the C2 (or C4/S4) axes are
x, y, z. The calculation itself always runs without symmetry (C1).
"""

import numpy as np

from ffpy.errors import InputError, UnsupportedError

_TOL = 1e-6


def _rot(axis, angle):
    axis = np.asarray(axis, float)
    axis = axis / np.linalg.norm(axis)
    x, y, z = axis
    c, s = np.cos(angle), np.sin(angle)
    C = 1 - c
    return np.array([
        [c + x * x * C, x * y * C - z * s, x * z * C + y * s],
        [y * x * C + z * s, c + y * y * C, y * z * C - x * s],
        [z * x * C - y * s, z * y * C + x * s, c + z * z * C]])


def _mirror(normal):
    n = np.asarray(normal, float)
    n = n / np.linalg.norm(n)
    return np.eye(3) - 2 * np.outer(n, n)


Z = (0, 0, 1)
X = (1, 0, 0)
INV = -np.eye(3)


def _cn(n, axis=Z):
    return _rot(axis, 2 * np.pi / n)


def _sn(n, axis=Z):
    return _mirror(axis) @ _rot(axis, 2 * np.pi / n)


def generators(group, order):
    g = group.upper()
    n = order
    needs_n = g in ("CN", "CNV", "CNH", "DN", "DNH", "DND", "S2N")
    if needs_n and (n is None or n < 1):
        raise InputError("$DATA: point group %s needs an axis order, e.g. '%s 2'" % (g, g))
    if g == "C1":
        return []
    if g == "CS":
        return [_mirror(Z)]
    if g == "CI":
        return [INV]
    if g == "CN":
        return [_cn(n)]
    if g == "CNV":
        return [_cn(n), _mirror((0, 1, 0))]
    if g == "CNH":
        return [_cn(n), _mirror(Z)]
    if g == "DN":
        return [_cn(n), _cn(2, X)]
    if g == "DNH":
        return [_cn(n), _cn(2, X), _mirror(Z)]
    if g == "DND":
        return [_sn(2 * n), _cn(2, X)]
    if g == "S2N":
        return [_sn(2 * n)]
    c3 = _cn(3, (1, 1, 1))
    if g == "T":
        return [_cn(2), _cn(2, X), c3]
    if g == "TH":
        return [_cn(2), _cn(2, X), c3, INV]
    if g == "TD":
        return [_sn(4), c3]
    if g == "O":
        return [_cn(4), c3]
    if g == "OH":
        return [_cn(4), c3, INV]
    raise UnsupportedError("$DATA: point group %s is not supported" % g)


def group_elements(gens):
    elems = [np.eye(3)]
    frontier = [np.eye(3)]
    while frontier:
        new = []
        for a in frontier:
            for gm in gens:
                b = gm @ a
                if not any(np.allclose(b, e, atol=1e-8) for e in elems):
                    elems.append(b)
                    new.append(b)
        frontier = new
        if len(elems) > 120:
            raise InputError("$DATA: symmetry group did not close (bad order?)")
    return elems


def expand(unique_atoms, group, order):
    """unique_atoms: list of (label, Z, xyz) -> full list in the same units."""
    ops = group_elements(generators(group, order))
    atoms = []
    for label, z, xyz in unique_atoms:
        r = np.asarray(xyz, float)
        images = []
        for op in ops:
            p = op @ r
            if not any(np.linalg.norm(p - q) < 1e-4 for q in images):
                images.append(p)
        for p in images:
            for other in atoms:
                if np.linalg.norm(other[2] - p) < 1e-4:
                    raise InputError("$DATA: atoms %s and %s coincide after applying %s symmetry"
                                     % (other[0], label, group))
            atoms.append((label, z, np.where(np.abs(p) < _TOL, 0.0, p)))
    return atoms, len(ops)
