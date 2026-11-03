"""GVB with perfect pairing (SCFTYP=GVB, NPAIR geminals) on top of PySCF's CASSCF orbital optimizer.

The wavefunction is a core of doubly occupied orbitals times a product of NPAIR two-electron
geminals  (cos t_p |a_p a_p> - sin t_p |b_p b_p>).  It is written as a vector in the determinant
space of the 2*NPAIR active orbitals, so PySCF's CASSCF machinery supplies the density matrices and
the orbital rotations; the geminal angles t_p are optimized here for fixed orbitals.
"""

import numpy as np
from pyscf import lib
from pyscf.fci import cistring, direct_spin1
from scipy.optimize import minimize

from ffpy.errors import UnsupportedError


class PPSolver(direct_spin1.FCISolver):
    """Perfect-pairing wavefunction in the active space [a1 b1 a2 b2 ...]."""

    def __init__(self, mol, npair, theta0=None):
        super().__init__(mol)
        self.npair = npair
        self.theta = np.full(npair, 0.15) if theta0 is None else np.array(theta0, float)
        self.converged = True
        self.nroots = 1

    def _structure(self, norb):
        strings = cistring.make_strings(range(norb), self.npair)
        idx, sign_a = [], []
        for k, s in enumerate(strings):
            bits = [(int(s) >> q) & 1 for q in range(norb)]
            ok = all(bits[2 * p] + bits[2 * p + 1] == 1 for p in range(self.npair))
            if ok:
                idx.append(k)
                sign_a.append([bits[2 * p + 1] for p in range(self.npair)])
        return np.array(idx), np.array(sign_a)

    def vector(self, theta, norb):
        idx, choice = self._structure(norb)
        n = cistring.num_strings(norb, self.npair)
        psi = np.zeros((n, n))
        coef = np.prod(np.where(choice == 0, np.cos(theta), -np.sin(theta)), axis=1)
        psi[idx, idx] = coef
        return psi

    def kernel(self, h1, h2, norb, nelec, ci0=None, ecore=0, **kwargs):
        h2e = direct_spin1.absorb_h1e(h1, h2, norb, (self.npair, self.npair), 0.5)

        def energy(theta):
            psi = self.vector(theta, norb)
            hpsi = direct_spin1.contract_2e(h2e, psi, norb, (self.npair, self.npair))
            return float(np.sum(psi * hpsi))

        res = minimize(energy, self.theta, method="BFGS", options={"gtol": 1e-10})
        self.theta = res.x
        psi = self.vector(res.x, norb)
        self.eci = res.fun + ecore
        return self.eci, psi

    approx_kernel = kernel

    def spin_square(self, fcivec, norb, nelec):
        return 0.0, 1.0


def _plane_parity(mol, C):
    """Parity (+1 even / -1 odd) of every column of C under the reflection through the molecular
    plane, for a planar molecule lying in a Cartesian plane (s, p, d functions); otherwise None."""
    xyz = mol.atom_coords()
    if len(xyz) < 3:
        return None
    axis = None
    for k in range(3):
        if np.ptp(xyz[:, k]) < 1e-6:
            axis = k
            break
    if axis is None:
        return None
    letter = "xyz"[axis]
    sign = []
    for _, _, _, comp in mol.ao_labels(fmt=False):
        comp = comp.strip()
        if comp in ("", "z^2", "x2-y2", "x2-y2"):
            n = {"z^2": 0, "x2-y2": 0}.get(comp, 0)
        elif len(comp.replace("^2", "")) > 2 and comp not in ("xx", "yy", "zz", "xy", "xz", "yz"):
            return None
        else:
            n = comp.count(letter)
        sign.append(-1.0 if n % 2 else 1.0)
    sign = np.array(sign)
    S = mol.intor("int1e_ovlp")
    return np.einsum("pi,pq,qi->i", C, S, sign[:, None] * C)


def pair_orbitals(mol, mf, nco, npair):
    """Orbital order [core, a1, b1, a2, b2, ..., rest] for the pair wavefunction.

    The orbitals of a geminal pair are taken as the highest occupied and lowest virtual orbitals;
    for a planar molecule with exactly NPAIR occupied pi (plane-antisymmetric) orbitals those are
    used, paired by energy order (HOMO with LUMO, ...)."""
    C, e = mf.mo_coeff, mf.mo_energy
    nocc = mol.nelectron // 2
    occ, virt = list(range(nocc)), list(range(nocc, C.shape[1]))
    par = None
    try:
        par = _plane_parity(mol, C)
    except Exception:
        par = None
    if par is not None:
        odd_occ = [i for i in occ if par[i] < -0.5]
        odd_virt = [i for i in virt if par[i] < -0.5]
        if len(odd_occ) >= npair and len(odd_virt) >= npair:
            pocc = sorted(odd_occ, key=lambda i: -e[i])[:npair]
            pvirt = sorted(odd_virt, key=lambda i: e[i])[:npair]
        else:
            pocc, pvirt = None, None
    else:
        pocc = pvirt = None
    if pocc is None:
        pocc = sorted(occ, key=lambda i: -e[i])[:npair]
        pvirt = sorted(virt, key=lambda i: e[i])[:npair]
    core = [i for i in occ if i not in pocc]
    if len(core) != nco:
        raise UnsupportedError("GVB: NCO=%d but the pair orbitals leave %d doubly occupied orbitals"
                               % (nco, len(core)))
    order = list(core)
    for a, b in zip(pocc, pvirt):
        order += [a, b]
    rest = [i for i in range(C.shape[1]) if i not in order]
    mo = C[:, order + rest]
    orbsym = getattr(C, "orbsym", None)
    if orbsym is not None:
        mo = lib.tag_array(mo, orbsym=np.asarray(orbsym)[order + rest])
    return mo
