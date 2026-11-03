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
    """Perfect-pairing wavefunction in the active space [o1 .. ok  a1 b1 a2 b2 ...]: k singly
    occupied high-spin open orbitals times NPAIR geminals."""

    def __init__(self, mol, npair, nopen=0, theta0=None):
        super().__init__(mol)
        self.npair = npair
        self.nopen = nopen
        self.theta = np.full(npair, 0.15) if theta0 is None else np.array(theta0, float)
        self.converged = True
        self.nroots = 1

    def _structure(self, norb):
        na = self.npair + self.nopen
        sa = cistring.make_strings(range(norb), na)
        sb = cistring.make_strings(range(norb), self.npair)
        open_mask = (1 << self.nopen) - 1
        rows, cols, choice = [], [], []
        for ia, s in enumerate(sa):
            if int(s) & open_mask != open_mask:
                continue
            ch = []
            for p in range(self.npair):
                a = (int(s) >> (self.nopen + 2 * p)) & 1
                b = (int(s) >> (self.nopen + 2 * p + 1)) & 1
                if a + b != 1:
                    break
                ch.append(b)
            else:
                # the beta string with the same choice per pair
                bits = sum(1 << (self.nopen + 2 * p + c) for p, c in enumerate(ch))
                ib = int(np.flatnonzero(sb == bits)[0])
                rows.append(ia)
                cols.append(ib)
                choice.append(ch)
        return np.array(rows), np.array(cols), np.array(choice).reshape(len(rows), self.npair)

    def vector(self, theta, norb):
        rows, cols, choice = self._structure(norb)
        psi = np.zeros((cistring.num_strings(norb, self.npair + self.nopen),
                        cistring.num_strings(norb, self.npair)))
        psi[rows, cols] = np.prod(np.where(choice == 0, np.cos(theta), -np.sin(theta)), axis=1)
        return psi

    def kernel(self, h1, h2, norb, nelec, ci0=None, ecore=0, **kwargs):
        nel = (self.npair + self.nopen, self.npair)
        h2e = direct_spin1.absorb_h1e(h1, h2, norb, nel, 0.5)

        def energy(theta):
            psi = self.vector(theta, norb)
            hpsi = direct_spin1.contract_2e(h2e, psi, norb, nel)
            return float(np.sum(psi * hpsi))

        res = minimize(energy, self.theta, method="BFGS", options={"gtol": 1e-10})
        self.theta = res.x
        psi = self.vector(res.x, norb)
        self.eci = res.fun + ecore
        return self.eci, psi

    approx_kernel = kernel

    def spin_square(self, fcivec, norb, nelec):
        s = 0.5 * self.nopen
        return s * (s + 1), 2 * s + 1


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


class CoupledSolver(direct_spin1.FCISolver):
    """Energy functional of a general open-shell SCF with Roothaan coupling coefficients.

    Orbitals are ordered by shells; shell[i] is the shell index of active orbital i (0 = the closed
    shell), f[s] the fractional occupation (electrons per orbital = 2 f), alpha/beta the symmetric
    shell-pair matrices:

        E = sum_i 2 f_i h_ii + sum_ij ( alpha_ij J_ij + beta_ij K_ij )     (i, j over all ordered pairs)

    The density matrices are fixed by these numbers, so PySCF's CASSCF supplies only the orbital
    optimization (with internal rotations between shells)."""

    def __init__(self, mol, shell, f, alpha, beta):
        super().__init__(mol)
        self.shell = np.asarray(shell, int)
        self.f = np.asarray(f, float)
        self.alpha = np.asarray(alpha, float)
        self.beta = np.asarray(beta, float)
        self.nroots = 1
        self.converged = True
        n = len(self.shell)
        self._dm1 = np.diag(2.0 * self.f[self.shell])
        a = self.alpha[np.ix_(self.shell, self.shell)]
        b = self.beta[np.ix_(self.shell, self.shell)]
        dm2 = np.zeros((n,) * 4)
        for i in range(n):
            for j in range(n):
                dm2[i, i, j, j] += 2 * a[i, j]
                dm2[i, j, j, i] += 2 * b[i, j]
        self._dm2 = dm2

    def kernel(self, h1, h2, norb, nelec, ci0=None, ecore=0, **kwargs):
        from pyscf import ao2mo
        eri = ao2mo.restore(1, h2, norb)
        e = float(np.einsum("pq,pq", h1, self._dm1) + 0.5 * np.einsum("pqrs,pqrs", eri, self._dm2))
        self.eci = e + ecore
        return self.eci, np.zeros(1)

    approx_kernel = kernel

    def make_rdm1(self, fcivec, norb, nelec, link_index=None, **kwargs):
        return self._dm1

    def make_rdm12(self, fcivec, norb, nelec, link_index=None, reorder=True):
        return self._dm1, self._dm2

    def make_rdm1s(self, fcivec, norb, nelec, link_index=None, **kwargs):
        return self._dm1 / 2, self._dm1 / 2

    def spin_square(self, fcivec, norb, nelec):
        return 0.0, 1.0


def default_couplings(nseto, no, mult):
    """F, ALPHA, BETA of the open-shell cases the GVB module knows without COUPLE=.T."""
    if nseto == 1 and list(no) == [1] and mult == 2:
        f = [1.0, 0.5]
        a = [[2, 1], [1, 0]]
        b = [[-1, -0.5], [-0.5, 0]]
    elif nseto == 2 and list(no) == [1, 1] and mult in (1, 3):
        f = [1.0, 0.5, 0.5]
        k = 0.5 if mult == 1 else -0.5
        a = [[2, 1, 1], [1, 0, 0.5], [1, 0.5, 0]]
        b = [[-1, -0.5, -0.5], [-0.5, 0, k], [-0.5, k, 0]]
    else:
        raise UnsupportedError("SCFTYP=GVB with NSETO=%d NO=%s MULT=%d needs COUPLE=.TRUE. with "
                               "F, ALPHA and BETA" % (nseto, list(no), mult))
    return f, np.array(a, float), np.array(b, float)
