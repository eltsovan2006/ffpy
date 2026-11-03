"""Excitation-limited / full CI in an active orbital window (Firefly $CIDRT, CITYP=GUGA).

The determinant space is the one PySCF's FCI solver uses; a mask removes the
determinants excluded by IEXCIT (maximum number of electrons excited out of
the reference configuration), the wrong spatial symmetry, and a penalty on
(S^2 - S(S+1)) selects the requested spin. Meant for the small windows of
course-level inputs, not for SOCI of large molecules.
"""

import numpy as np
from pyscf import ao2mo, lib, scf, symm
from pyscf.fci import cistring, direct_spin1, spin_op

from ffpy.errors import InputError, UnsupportedError

_ABELIAN = {"C1", "CS", "CI", "C2", "C2V", "C2H", "D2", "D2H"}
_PENALTY = 100.0


class CIResult:
    def __init__(self, e_states, vecs, e_ref, norb, nelec, h_mo, e_core, sym, spins):
        self.e_states = e_states
        self.vecs = vecs
        self.e_ref = e_ref
        self.norb, self.nelec = norb, nelec
        self.h_mo, self.e_core = h_mo, e_core
        self.sym = sym
        self.spins = spins
        self.e_tot = e_states[0]


def _orbital_irreps(job, mol, mo):
    """(irrep code of every MO, PySCF irrep names, Firefly irrep names) or None for C1."""
    if job.ci["group"] == "C1":
        return None
    from ffpy.methods import _irrep_table
    name, ff_names = _irrep_table(job)
    if job.ci["group"].replace("_", "").upper() not in (name.upper(), job.point_group.split()[0].upper()):
        raise UnsupportedError("$CIDRT GROUP=%s differs from the molecular point group %s"
                               % (job.ci["group"], job.point_group))
    sym_mol = mol.copy()
    sym_mol.symmetry = name
    sym_mol.build(False, False)
    pnames = list(sym_mol.irrep_name)
    labels = symm.label_orb_symm(sym_mol, sym_mol.irrep_name, sym_mol.symm_orb, mo)
    # PySCF's irrep order of these Abelian groups multiplies like XOR of the index
    return [pnames.index(l) for l in labels], pnames, ff_names


def run_ci(job, mf, mol):
    ci = job.ci
    nfzc, ndoc, nalp, nval = ci["nfzc"], ci["ndoc"], ci["nalp"], ci["nval"]
    norb = ndoc + nalp + nval
    nelec = (ndoc + nalp, ndoc)
    mo = mf.mo_coeff
    if mo.shape[1] < nfzc + norb:
        raise InputError("$CIDRT: %d orbitals requested but only %d are available" % (nfzc + norb, mo.shape[1]))
    cc, ca = mo[:, :nfzc], mo[:, nfzc:nfzc + norb]
    h = mf.get_hcore()
    dmc = 2 * cc @ cc.T
    vj, vk = scf.hf.get_jk(mol, dmc)
    veff = vj - 0.5 * vk
    e_core = float(np.einsum("ij,ji", h + 0.5 * veff, dmc) + mol.energy_nuc())
    h1 = ca.T @ (h + veff) @ ca
    h2 = ao2mo.restore(1, ao2mo.kernel(mol, ca), norb)

    na, nb = nelec
    sa = cistring.make_strings(range(norb), na)
    sb = cistring.make_strings(range(norb), nb)
    ref_a, ref_b = (1 << na) - 1, (1 << nb) - 1

    def level(strings, ref):
        return np.array([bin(int(s) & ~ref).count("1") for s in strings])

    mask = np.ones((len(sa), len(sb)), bool)
    if ci["iexcit"] is not None:
        mask &= (level(sa, ref_a)[:, None] + level(sb, ref_b)[None, :]) <= ci["iexcit"]

    sym = None
    irr = _orbital_irreps(job, mol, ca)
    if irr is not None:
        codes, pnames, ff_names = irr

        def string_irrep(strings):
            out = np.zeros(len(strings), int)
            for k, s in enumerate(strings):
                r = 0
                for p in range(norb):
                    if (int(s) >> p) & 1:
                        r ^= codes[p]
                out[k] = r
            return out
        det_irrep = string_irrep(sa)[:, None] ^ string_irrep(sb)[None, :]
        sym = ff_names[ci["istsym"] - 1]
        mask &= det_irrep == pnames.index(sym)

    s0 = (nalp) / 2.0
    ss_target = s0 * (s0 + 1)
    h2e = direct_spin1.absorb_h1e(h1, h2, norb, nelec, 0.5)
    nst = ci["nstate"]
    mask_f = mask.astype(float)

    def hop(c):
        v = (c.reshape(mask.shape) * mask_f)
        w = np.asarray(direct_spin1.contract_2e(h2e, v, norb, nelec)).reshape(v.shape)
        s2v = spin_op.contract_ss(v, norb, nelec).reshape(v.shape)
        d = s2v - ss_target * v
        pen = _PENALTY * (spin_op.contract_ss(d, norb, nelec).reshape(v.shape) - ss_target * d)
        return ((w + pen) * mask_f).ravel()

    hdiag = direct_spin1.make_hdiag(h1, h2, norb, nelec)
    hdiag = np.where(mask, np.asarray(hdiag).reshape(mask.shape), 1e6)
    order = np.argsort(hdiag.ravel())
    nguess = min(max(4 * nst, 8), int(mask.sum()))
    x0 = []
    for k in order[:nguess]:
        v = np.zeros(mask.size)
        v[k] = 1.0
        x0.append(v)

    def precond(r, e0, x0_):
        d = hdiag.ravel() - e0
        d[np.abs(d) < 1e-4] = 1e-4
        return r / d

    if int(mask.sum()) <= 2500:
        n = mask.size
        idx = np.flatnonzero(mask.ravel())
        Hd = np.zeros((len(idx), len(idx)))
        for j, k in enumerate(idx):
            v = np.zeros(n)
            v[k] = 1.0
            Hd[:, j] = hop(v)[idx]
        w, u = np.linalg.eigh(0.5 * (Hd + Hd.T))
        vals, vecs = list(w[:nst]), []
        for r in range(nst):
            full = np.zeros(n)
            full[idx] = u[:, r]
            vecs.append(full.reshape(mask.shape))
    else:
        conv, vals, vecs = lib.davidson1(lambda xs: [hop(x) for x in xs], x0, precond,
                                         nroots=nst, max_cycle=200, tol=1e-9)
        vals = list(vals)
        vecs = [v.reshape(mask.shape) for v in vecs]
        if not all(conv):
            raise InputError("CI did not converge")

    spins = []
    for v in vecs:
        ss = float(np.dot(v.ravel(), np.asarray(spin_op.contract_ss(v, norb, nelec)).ravel()))
        spins.append(ss)
    # energies without the spin penalty
    e_states = [e_core + float(np.dot(v.ravel(), _plain_hop(h2e, v, norb, nelec, mask_f).ravel()))
                for v in vecs]
    return CIResult(e_states, vecs, mf.e_tot, norb, nelec, (h1, h2), e_core, sym, spins)


def _plain_hop(h2e, v, norb, nelec, mask_f):
    return np.asarray(direct_spin1.contract_2e(h2e, v * mask_f, norb, nelec)).reshape(v.shape) * mask_f


def transition_dipoles(job, res, mol, mo):
    """Dipole transition moments (a.u.) between the CI states, active window only."""
    ci = job.ci
    nfzc = ci["nfzc"]
    ca = mo[:, nfzc:nfzc + res.norb]
    with mol.with_common_orig((0, 0, 0)):
        ints = mol.intor("int1e_r", comp=3)
    mu = np.array([ca.T @ m @ ca for m in ints])
    n = len(res.vecs)
    out = {}
    for i in range(n):
        for j in range(i + 1, n):
            dm = direct_spin1.trans_rdm1(res.vecs[i], res.vecs[j], res.norb, res.nelec)
            dm = 0.5 * (dm + dm.T)
            out[(i + 1, j + 1)] = np.array([float(np.sum(dm * mu[k])) for k in range(3)])
    return out
