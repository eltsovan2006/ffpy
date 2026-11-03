"""Builders that turn a Job into PySCF objects. The only module (with the
runners) that touches the PySCF API."""

import time
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
from pyscf import df, dft, fci, gto, lib, mcscf, mp, scf, tdscf
from pyscf.data.elements import chemcore

from ffpy.errors import InputError, SCFNotConverged, TimeLimitExceeded, UnsupportedError


class Context:
    """Run-wide state shared by runners and writers."""

    def __init__(self, job, log, t0=None, pyscf_fh=None, gamess=False):
        self.job = job
        self.log = log
        self.t0 = t0 or time.time()
        self.pyscf_fh = pyscf_fh
        self.gamess = gamess
        self.print_scf = True
        self.status = 0            # non-fatal failure code for the last line
        self.status_msg = ""
        self.trajectory = []       # (energy, coords_bohr)
        self.freq = None           # dict for molden/out after HESSIAN

    def elapsed(self):
        return time.time() - self.t0

    def check_time(self):
        if self.elapsed() > self.job.timlim_s:
            raise TimeLimitExceeded("time limit of %.1f min exceeded" % (self.job.timlim_s / 60))

    def soft_fail(self, code, msg):
        if not self.status:
            self.status, self.status_msg = code, msg


@dataclass
class Result:
    mol: Any
    mf: Any
    post: Optional[Any]      # MP2 / CASSCF / TD object
    e_scf: float
    e_tot: float
    e_nl: float = 0.0       # VV10 term of DFT-NL (already included in e_tot)
    e_disp: float = 0.0     # D3BJ dispersion (already included in e_tot)


# Firefly numbering of irreps (ISTSYM) for the abelian point groups: PySCF group, irrep names
_IRREPS = {
    "C1": ("C1", ["A"]),
    "CS": ("Cs", ["A'", 'A"']),
    "CI": ("Ci", ["Ag", "Au"]),
    "C2": ("C2", ["A", "B"]),
    "CNV 2": ("C2v", ["A1", "A2", "B1", "B2"]),
    "CNH 2": ("C2h", ["Ag", "Au", "Bu", "Bg"]),
    "DN 2": ("D2", ["A", "B1", "B2", "B3"]),
    "DNH 2": ("D2h", ["Ag", "B1g", "B2g", "B3g", "Au", "B1u", "B2u", "B3u"]),
}


def _irrep_table(job):
    key = job.point_group.upper()
    if key not in _IRREPS:
        raise UnsupportedError("ISTSYM is not supported for point group %s" % job.point_group)
    return _IRREPS[key]


def build_mol(job, ctx, coords=None):
    coords = job.coords if coords is None else coords
    mol = gto.Mole()
    mol.atom = [(s, tuple(float(x) for x in c)) for s, c in zip(job.atom_tags or job.symbols, coords)]
    mol.unit = "Bohr"
    mol.basis = job.basis
    if job.ecp:
        mol.ecp = job.ecp
    mol.charge = job.charge
    mol.spin = job.mult - 1
    mol.cart = job.cart
    mol.symmetry = False
    if (job.excited and job.excited.get("istsym")) or (job.cas and (job.cas.get("istsym") or job.cas.get("pp_sym"))):
        mol.symmetry = _irrep_table(job)[0]
    if job.memory_mb:
        mol.max_memory = job.memory_mb
    if ctx.pyscf_fh:
        # one debug file for all rebuilds (optimization steps, displacements)
        mol.verbose = 4
        mol.stdout = ctx.pyscf_fh
    else:
        mol.verbose = 0
    try:
        mol.build()
    except (KeyError, RuntimeError, ValueError) as e:
        raise InputError("cannot build the molecule with basis %s: %s" % (job.basis, e))
    if mol.symmetry and not np.allclose(mol.atom_coords(), np.asarray(coords, float), atol=1e-9):
        # PySCF rotates the molecule into its symmetry frame; adopt that frame for the whole run
        # (geometry optimization steps then stay in a frame where the symmetry is exact)
        job.coords = np.array(mol.atom_coords())
    return mol


def _scf_callback(ctx):
    log = ctx.log

    def cb(envs):
        ctx.check_time()
        if not ctx.print_scf:
            return
        cyc = envs.get("cycle", 0)
        e = envs.get("e_tot", 0.0)
        last = envs.get("last_hf_e", e)
        if cyc == 0:
            log("  ITER       TOTAL ENERGY          DELTA E       |ORB GRAD|    |DELTA D|")
        log(" %5d  %20.10f  %14.6E  %12.4E  %12.4E"
            % (cyc + 1, e, e - last, envs.get("norm_gorb", 0.0), envs.get("norm_ddm", 0.0)))
    return cb


def build_scf(job, mol, ctx, tight=False):
    if job.xc:
        cls = {"RHF": dft.RKS, "UHF": dft.UKS, "ROHF": dft.ROKS}[job.scftyp]
        mf = cls(mol)
        mf.xc = job.xc
        if job.grid:
            mf.grids.atom_grid = job.grid
    elif job.scftyp == "MCSCF":
        mf = scf.RHF(mol) if job.mult == 1 else scf.ROHF(mol)
    else:
        mf = {"RHF": scf.RHF, "UHF": scf.UHF, "ROHF": scf.ROHF}[job.scftyp](mol)
    mf.max_cycle = job.maxit
    conv_grad = job.nconv_density
    conv_e = min(1e-9, conv_grad ** 2)
    if tight:
        conv_grad, conv_e = min(conv_grad, 1e-7), min(conv_e, 1e-12)
    mf.conv_tol, mf.conv_tol_grad = conv_e, conv_grad
    mf.init_guess = {"HUCKEL": "huckel", "HCORE": "1e", "MOREAD": "minao"}[job.guess]
    if not job.diis:
        mf.diis = False
    if job.damp:
        mf.damp = 0.5
    if job.shift:
        mf.level_shift = 0.2
    if job.direct:
        mf.direct_scf = True
        mf._is_mem_enough = lambda: False
    if job.pcm:
        mf = mf.PCM()
        mf.with_solvent.method = "IEF-PCM"
        mf.with_solvent.eps = job.pcm["eps"]
    if job.scrf:
        from ffpy.scrf import attach, reaction_field_g
        mf = attach(mf, reaction_field_g(job.scrf["dielec"], job.scrf["radius"]))
    if job.soscf:
        mf = mf.newton()
    mf.callback = _scf_callback(ctx)
    return mf


def read_vec(job, mol):
    """The $VEC orbitals (alpha, beta) in PySCF AO order; a Firefly-order $VEC is converted and
    orthonormalized (it may come from a slightly different geometry)."""
    Ca, Cb = job.vec
    if Ca.shape[0] != mol.nao:
        raise InputError("$VEC has %d AO coefficients per orbital, the basis has %d "
                         "(the $VEC must come from an ffpy .dat with the same basis and ISPHER)"
                         % (Ca.shape[0], mol.nao))
    if job.vec_firefly:
        s1 = mol.intor("int1e_ovlp")

        def conv(C):
            if C is None:
                return None
            C = firefly_vec_to_pyscf(job, mol, C)
            w, u = np.linalg.eigh(C.T @ s1 @ C)
            return C @ (u / np.sqrt(w)) @ u.T
        Ca, Cb = conv(Ca), conv(Cb)
    return Ca, Cb


def moread_dm(job, mf, mol):
    Ca, Cb = read_vec(job, mol)
    na, nb = mol.nelec
    if job.scftyp == "UHF":
        Cb = Ca if Cb is None else Cb
        return np.array([Ca[:, :na] @ Ca[:, :na].T, Cb[:, :nb] @ Cb[:, :nb].T])
    if job.scftyp == "ROHF" or (job.scftyp == "MCSCF" and job.mult > 1):
        return np.array([Ca[:, :na] @ Ca[:, :na].T, Ca[:, :nb] @ Ca[:, :nb].T])
    return 2.0 * Ca[:, :na] @ Ca[:, :na].T


def casscf_guess(job, mf, mol):
    """Orbitals for CASSCF from MOREAD: the $VEC orbitals first (in their order), completed
    with the remaining SCF orbitals projected out of their span."""
    Ca, _ = read_vec(job, mol)
    s1 = mol.intor("int1e_ovlp")
    k = Ca.shape[1]
    rest = mf.mo_coeff
    rest = rest - Ca @ (Ca.T @ s1 @ rest)
    w, u = np.linalg.eigh(rest.T @ s1 @ rest)
    keep = w > 1e-6
    extra = rest @ u[:, keep] / np.sqrt(w[keep])
    return np.hstack([Ca, extra])[:, :mol.nao]


def _escape_saddle(mf, log):
    """A closed-shell SCF started from a poor guess can stop at a saddle point of the energy
    (observed with HUCKEL on linear molecules); in that case start over from the MINAO guess."""
    mo = mf.stability(internal=True, external=False, verbose=0)[0]
    if np.abs(mo - mf.mo_coeff).max() < 1e-7:
        return
    e_old = mf.e_tot
    mf.kernel(dm0=mf.get_init_guess(key="minao"))
    log.warning("SCF solution was unstable; restarted from the MINAO guess: %.10f -> %.10f"
                % (e_old, mf.e_tot))


def run_scf(job, mf, ctx, dm0=None, strict=True):
    log = ctx.log
    if dm0 is None and job.guess == "MOREAD":
        dm0 = moread_dm(job, mf, mf.mol)
    mf.kernel(dm0=dm0)
    if mf.converged and job.scftyp == "RHF" and job.guess != "MOREAD" and mf.mol.nao <= 400:
        _escape_saddle(mf, log)
    if not mf.converged:
        msg = "SCF did not converge in MAXIT=%d iterations" % job.maxit
        if strict:
            raise SCFNotConverged(msg)
        log.warning(msg)
        ctx.soft_fail(SCFNotConverged.code, msg)
    return mf.e_tot


class RMP2Result:
    """ROHF-MBPT2 (RMP): semicanonical UMP2 doubles plus the singles term."""

    def __init__(self, e_ref, e_doubles, e_singles):
        self.e_doubles, self.e_singles = e_doubles, e_singles
        self.e_corr = e_doubles + e_singles
        self.e_tot = e_ref + self.e_corr


def run_rmp2(job, mf, mol):
    """RMP / ROHF-MBPT2: alpha and beta Fock matrices are canonicalized separately inside their
    occupied and virtual blocks of the ROHF orbital space, doubles are UHF-like MP2 in these
    orbitals, and the occupied-virtual Fock elements give a singles contribution."""
    c, occ = mf.mo_coeff, mf.mo_occ
    na, nb, nmo = int((occ > 0).sum()), int((occ > 1).sum()), c.shape[1]
    dma, dmb = c[:, :na] @ c[:, :na].T, c[:, :nb] @ c[:, :nb].T
    vj, vk = scf.hf.get_jk(mol, [dma, dmb])
    h = mf.get_hcore()
    nfz = job.mp2_frozen if job.mp2_frozen is not None else chemcore(mol)

    def semicanonical(f, nocc):
        F = c.T @ f @ c
        eo, uo = np.linalg.eigh(F[:nocc, :nocc])
        ev, uv = np.linalg.eigh(F[nocc:, nocc:])
        U = np.zeros((nmo, nmo))
        U[:nocc, :nocc], U[nocc:, nocc:] = uo, uv
        e = np.concatenate([eo, ev])
        Fs = U.T @ F @ U
        singles = -sum(Fs[i, a] ** 2 / (e[a] - e[i]) for i in range(nfz, nocc) for a in range(nocc, nmo))
        return e, c @ U, singles

    ea, ca, sa = semicanonical(h + vj[0] + vj[1] - vk[0], na)
    eb, cb, sb = semicanonical(h + vj[0] + vj[1] - vk[1], nb)
    mfu = scf.UHF(mol)
    mfu.mo_coeff, mfu.mo_energy = (ca, cb), (ea, eb)
    mfu.mo_occ = (np.array([1.0] * na + [0.0] * (nmo - na)), np.array([1.0] * nb + [0.0] * (nmo - nb)))
    mfu.e_tot = mf.e_tot
    pt = mp.UMP2(mfu, frozen=nfz if nfz else None)
    pt.verbose = 0
    pt.kernel(mo_energy=(ea, eb), mo_coeff=(ca, cb))
    return RMP2Result(mf.e_tot, float(pt.e_corr), float(sa + sb))


def build_mp2(job, mf, mol):
    nfrz = job.mp2_frozen if job.mp2_frozen is not None else chemcore(mol)
    pt = mp.MP2(mf, frozen=nfrz if nfrz else None)
    pt.verbose = mol.verbose
    return pt, nfrz


def d3bj_energy(job, mol):
    """Grimme D3 with Becke-Johnson damping (no three-body term), parameters from $DFTD."""
    try:
        from dftd3.interface import DispersionModel, RationalDampingParam
    except ImportError:
        raise UnsupportedError("DFT-D needs the 'dftd3' package: pip install dftd3")
    p = job.disp
    model = DispersionModel(np.array(mol.atom_charges()), np.array(mol.atom_coords()))
    par = RationalDampingParam(s6=p["s6"], s8=p["s8"], a1=p["a1"], a2=p["a2"], alp=p["alp"], s9=0.0)
    return float(model.get_dispersion(par, grad=False)["energy"])


class DHResult:
    """Scaled opposite- and same-spin MP2 terms of a double hybrid (canonical, frozen core)."""

    def __init__(self, e_os, e_ss, c_os, c_ss):
        self.e_os, self.e_ss, self.c_os, self.c_ss = e_os, e_ss, c_os, c_ss
        self.e_corr = c_os * e_os + c_ss * e_ss


def _ri_mp2(job, mf, mol, nfrz):
    from pyscf.mp import dfmp2
    pt = dfmp2.DFMP2(mf, frozen=nfrz if nfrz else None)
    pt.with_df = df.DF(mol, auxbasis=job.auxbas)
    return pt


def run_dh(job, mf, mol):
    nfrz = job.mp2_frozen if job.mp2_frozen is not None else chemcore(mol)
    pt = _ri_mp2(job, mf, mol, nfrz) if job.auxbas else mp.MP2(mf, frozen=nfrz if nfrz else None)
    pt.verbose = 0
    pt.kernel(with_t2=False) if job.auxbas else pt.kernel()
    return DHResult(float(pt.e_corr_os), float(pt.e_corr_ss), job.dh["os"], job.dh["ss"])


class MPn:
    """MP3 / MP4 energies of a closed-shell reference (spin-adapted, from CC pieces)."""

    def __init__(self, e_ref, parts):
        self.e_ref = e_ref
        self.parts = parts
        self.e_corr = sum(v for k, v in parts.items())
        self.e_tot = e_ref + self.e_corr


def run_mpn(job, mf, mol):
    """MP3 and MP4(SDQ/SDTQ) by perturbation expansion of the CCSD equations.

    The residual numerator R(t1, t2) of PySCF's closed-shell CCSD is a
    polynomial in the amplitudes; its parts of given degree are separated by
    evaluating it at +-t. With canonical HF orbitals the third-order doubles
    are [L(t2_2) + Q(t2_1) + S(t1_2)] / D and E4(T) is the (T) correction
    evaluated with the first-order doubles.
    """
    from pyscf import cc
    from pyscf.cc import ccsd_t

    nfrz = job.mp2_frozen if job.mp2_frozen is not None else chemcore(mol)
    mycc = cc.RCCSD(mf, frozen=nfrz if nfrz else None)
    mycc.verbose = 0
    eris = mycc.ao2mo()
    nocc = mycc.nocc
    eia = eris.mo_energy[:nocc, None] - eris.mo_energy[None, nocc:]
    eijab = eia[:, None, :, None] + eia[None, :, None, :]
    t1z = np.zeros_like(eia)
    t2_1 = mycc.init_amps(eris)[2]

    def resid(t1, t2):
        a, b = mycc.update_amps(t1, t2, eris)
        return a * eia, b * eijab

    zero2 = np.zeros_like(t2_1)
    r2_0 = resid(t1z, zero2)[1]

    def lin(t1, t2):
        (a, b), (c, d) = resid(t1, t2), resid(-t1, -t2)
        return (a - c) / 2, (b - d) / 2

    def quad(t2):
        (_, b), (_, d) = resid(t1z, t2), resid(t1z, -t2)
        return (b + d) / 2 - r2_0

    w = 2 * t2_1 - t2_1.transpose(0, 1, 3, 2)
    contract = lambda r: float(np.einsum("ijab,ijab", w, r))
    parts = {"MP2": contract(np.asarray(eris.ovov).reshape(w.shape[0], w.shape[2], w.shape[1], w.shape[3]).transpose(0, 2, 1, 3))}
    parts["MP3"] = contract(lin(t1z, t2_1)[1])
    if job.mplevl == 4:
        tonly = job.mp4.get("tonly")
        if not tonly:
            t1_2 = lin(t1z, t2_1)[0] / eia
            t2_2 = lin(t1z, t2_1)[1] / eijab
            parts["MP4(S)"] = contract(lin(t1_2, zero2)[1])
            parts["MP4(D)"] = contract(lin(t1z, t2_2)[1])
            parts["MP4(Q)"] = contract(quad(t2_1))
        if job.mp4.get("sdtq") or tonly:
            parts["MP4(T)"] = float(ccsd_t.kernel(mycc, eris, t1z, t2_1, verbose=0))
    return MPn(mf.e_tot, parts)


class MRPTResult:
    def __init__(self, e_ref, e2):
        self.e_ref, self.e_corr = e_ref, e2
        self.e_tot = e_ref + e2


def run_mrmp2(job, mf, mc, mol):
    """One-state MCQDPT2: second-order multireference PT for a CASSCF state.

    H0 is the one-electron operator built from the generalized Fock matrix of the state-averaged
    density; orbitals are canonicalized inside the frozen/inactive, active and external blocks, so
    H0 is diagonal in determinants (sum of orbital energies). The first-order wavefunction lies in
    the determinants outside the CAS space, with denominators E0 - E_K (E0 = <Psi0|H0|Psi0>).
    """
    from pyscf import ao2mo
    from pyscf.fci import addons, cistring, direct_spin1

    ncore, nact = job.cas["ncore"], job.cas["nact"]
    na_el, nb_el = mc.nelecas
    C = mc.mo_coeff
    nmo = C.shape[1]
    nfz = min(chemcore(mol), ncore)
    nin = ncore - nfz
    ci = mc.ci
    dm_act = mc.fcisolver.make_rdm1(ci, nact, mc.nelecas)
    D = np.zeros((nmo, nmo))
    D[:ncore, :ncore] = 2.0 * np.eye(ncore)
    D[ncore:ncore + nact, ncore:ncore + nact] = dm_act
    dmao = C @ D @ C.T
    vj, vk = scf.hf.get_jk(mol, dmao)
    F = C.T @ (mf.get_hcore() + vj - 0.5 * vk) @ C
    blocks = [slice(0, nfz), slice(nfz, ncore), slice(ncore, ncore + nact), slice(ncore + nact, nmo)]
    U = np.zeros((nmo, nmo))
    for b in blocks:
        if b.stop > b.start:
            U[b, b] = np.linalg.eigh(F[b, b])[1]
    eps = np.diag(U.T @ F @ U).copy()
    C2 = C @ U
    u_act = U[ncore:ncore + nact, ncore:ncore + nact]
    ci2 = addons.transform_ci_for_orbital_rotation(ci, nact, mc.nelecas, u_act)

    ncorr = nmo - nfz
    na, nb = na_el + nin, nb_el + nin
    from math import comb
    if comb(ncorr, na) * comb(ncorr, nb) > 4_000_000:
        raise UnsupportedError("MCQDPT2: the correlated space (%d orbitals) is too large for this implementation" % ncorr)
    # frozen-core Hamiltonian over the correlated orbitals
    cfz = C2[:, :nfz]
    dmc = 2 * cfz @ cfz.T
    vjc, vkc = scf.hf.get_jk(mol, dmc)
    cc = C2[:, nfz:]
    h1 = cc.T @ (mf.get_hcore() + vjc - 0.5 * vkc) @ cc
    eri = ao2mo.restore(1, ao2mo.kernel(mol, cc), ncorr)
    h2e = direct_spin1.absorb_h1e(h1, eri, ncorr, (na, nb), 0.5)

    def strings(nel):
        return cistring.make_strings(range(ncorr), nel)

    sa, sb = strings(na), strings(nb)
    inact_bits = (1 << nin) - 1
    act_mask_bits = ((1 << nact) - 1) << nin

    def in_cas(s):
        return (int(s) & inact_bits) == inact_bits and (int(s) & ~(inact_bits | act_mask_bits)) == 0

    cas_a = np.array([in_cas(s) for s in sa])
    cas_b = np.array([in_cas(s) for s in sb])
    sa_act = cistring.make_strings(range(nact), na_el)
    sb_act = cistring.make_strings(range(nact), nb_el)
    ia = np.array([cistring.str2addr(ncorr, na, (int(s) << nin) | inact_bits) for s in sa_act])
    ib = np.array([cistring.str2addr(ncorr, nb, (int(s) << nin) | inact_bits) for s in sb_act])
    psi = np.zeros((len(sa), len(sb)))
    psi[np.ix_(ia, ib)] = ci2
    hpsi = np.asarray(direct_spin1.contract_2e(h2e, psi, ncorr, (na, nb))).reshape(psi.shape)
    cas = np.outer(cas_a, cas_b)
    hq = np.where(cas, 0.0, hpsi)
    e_corr = eps[nfz:]
    ea = np.array([sum(e_corr[p] for p in range(ncorr) if (int(s) >> p) & 1) for s in sa])
    eb = np.array([sum(e_corr[p] for p in range(ncorr) if (int(s) >> p) & 1) for s in sb])
    ek = ea[:, None] + eb[None, :]
    e0 = float(np.sum(psi ** 2 * ek))
    den = e0 - ek
    sel = ~cas
    return MRPTResult(mc.e_tot, float(np.sum(hq[sel] ** 2 / den[sel])))


def reorder_orbitals(job, C):
    """Apply $GUESS NORDER=1 IORDER(k)=... to the starting orbitals (columns of C)."""
    if not job.iorder:
        return C
    start, olds = job.iorder
    perm = list(range(C.shape[1]))
    for k, old in enumerate(olds):
        perm[start - 1 + k] = old - 1
    if sorted(perm) != list(range(C.shape[1])):
        raise InputError("$GUESS IORDER does not describe a permutation of the orbitals")
    out = C[:, perm]
    orbsym = getattr(C, "orbsym", None)
    return lib.tag_array(out, orbsym=np.asarray(orbsym)[perm]) if orbsym is not None else out


def best_open_pair(job, mf, ctx):
    """Open orbitals plus one geminal: try the SOMOs as the open shell and the pair taken from the
    highest doubly occupied and lowest virtual orbitals; the lowest converged energy is kept (the
    wavefunction has several solutions and Firefly's orbital order cannot be transferred)."""
    import itertools
    c = job.cas
    nopen, npair = c["nopen"], c["pp"]
    if npair != 1:
        raise UnsupportedError("open shells together with more than one geminal are not supported")
    nmo = mf.mo_coeff.shape[1]
    occ = np.asarray(mf.mo_occ)
    somo = [i for i in range(nmo) if occ[i] == 1]
    dbl = [i for i in range(nmo) if occ[i] == 2]
    virt = [i for i in range(nmo) if occ[i] == 0]
    if len(somo) != nopen:
        raise UnsupportedError("the ROHF reference has %d singly occupied orbitals, NSETO=%d" % (len(somo), nopen))
    best = None
    ncore = c["ncore"]
    for po, pv in itertools.product(dbl[-3:], virt[:3]):
        order = [i for i in dbl if i != po]
        if len(order) != ncore:
            order = order[:ncore] if len(order) > ncore else order
        order = order + somo + [po, pv]
        if len(set(order)) != len(order):
            continue
        rest = [i for i in range(nmo) if i not in order]
        perm = order + rest
        C = mf.mo_coeff[:, perm]
        orbsym = getattr(mf.mo_coeff, "orbsym", None)
        if orbsym is not None:
            C = lib.tag_array(C, orbsym=np.asarray(orbsym)[perm])
        mc = build_cas(job, mf)
        try:
            mc.kernel(C)
        except Exception:
            continue
        if mc.converged and (best is None or mc.e_tot < best.e_tot):
            best = mc
    if best is None:
        raise SCFNotConverged("no orbital assignment of the open shell and geminal converged")
    return best


def build_cas(job, mf):
    c = job.cas
    s = job.mult - 1
    nelecas = ((c["nels"] + s) // 2, (c["nels"] - s) // 2)
    mc = mcscf.CASSCF(mf, c["nact"], nelecas)
    if c.get("open"):
        from ffpy.gvb import CoupledSolver
        o = c["open"]
        mc.fcisolver = CoupledSolver(mf.mol, o["shell"], o["f"], o["alpha"], o["beta"])
        mc.internal_rotation = True
    if c.get("pp"):
        from ffpy.gvb import PPSolver
        mc.fcisolver = PPSolver(mf.mol, c["pp"], c.get("nopen", 0))
        mc.internal_rotation = True
        mc.max_cycle_macro = 200
    mc.max_cycle_macro = max(c["maxit"], mc.max_cycle_macro) if (c.get("pp") or c.get("open")) else c["maxit"]
    mc.conv_tol = 1e-10 if (c.get("pp") or c.get("open")) else 1e-9
    mc.conv_tol_grad = 1e-5 if (c.get("pp") or c.get("open")) else c["acurcy"]
    mc.natorb = not (c.get("pp") or c.get("open"))
    if c.get("istsym"):
        names = _irrep_table(job)[1]
        if not 1 <= c["istsym"] <= len(names):
            raise InputError("ISTSYM=%d: point group %s has %d irreps" % (c["istsym"], job.point_group, len(names)))
        mc.fcisolver = fci.direct_spin1_symm.FCI(mf.mol)
        mc.fcisolver.wfnsym = names[c["istsym"] - 1]
    if c["nstate"] > 1:
        w = c["wstate"] or [1.0 / c["nstate"]] * c["nstate"]
        w = list(np.asarray(w) / np.sum(w))
        mc.fix_spin_(ss=0.5 * s * (0.5 * s + 1))
        mc = mc.state_average_(w)
    return mc


def build_td(job, mf):
    ex = job.excited
    td = tdscf.TDA(mf) if ex["tda"] else tdscf.TDDFT(mf)
    td.nstates = ex["nstate"]
    td.conv_tol = 1e-9
    if ex.get("istsym"):
        names = _irrep_table(job)[1]
        if not 1 <= ex["istsym"] <= len(names):
            raise InputError("ISTSYM=%d: point group %s has %d irreps" % (ex["istsym"], job.point_group, len(names)))
        td.wfnsym = names[ex["istsym"] - 1]
    if job.scftyp == "RHF":
        td.singlet = not ex["triplet"]
    return td


def vv10_energy(job, mol, mf):
    """Non-self-consistent VV10 nonlocal correlation on the converged density (Firefly DFT-NL)."""
    b, c = job.dftnl
    grids = dft.gen_grid.Grids(mol)
    grids.atom_grid = (75, 302)
    grids.build()
    ni = mf._numint
    ni.nlc_coeff = lambda xc: [((b, c), 1.0)]
    dm = mf.make_rdm1()
    if getattr(dm, "ndim", 2) == 3:
        dm = dm[0] + dm[1]
    return float(ni.nr_nlc_vxc(mol, grids, "VV10", dm)[1])


_GAMESS_CART_D = {0: (0, 1.0), 1: (3, 1 / 3.0), 2: (4, 1 / 3.0), 3: (1, 1.0), 4: (5, 1 / 3.0), 5: (2, 1.0)}


def firefly_vec_to_pyscf(job, mol, C):
    """Rows of a Firefly $VEC (GAMESS AO order, Firefly atom order) -> PySCF AO order.

    s, p and Cartesian d are handled. GAMESS lists d as XX YY ZZ XY XZ YZ with every function
    normalized like XX, which makes the XY-type overlap one third of XX; PySCF orders XX XY XZ YY YZ ZZ.
    """
    if mol.nao != C.shape[0]:
        raise InputError("$VEC has %d AOs per orbital, the basis has %d" % (C.shape[0], mol.nao))
    if any(mol.bas_angular(i) > 2 for i in range(mol.nbas)) or (
            not mol.cart and any(mol.bas_angular(i) == 2 for i in range(mol.nbas))):
        raise UnsupportedError("a Firefly $VEC with spherical d or f functions is not supported")
    coords = mol.atom_coords()
    z = [mol.atom_charge(i) for i in range(mol.natm)]
    order, i = [], 0
    while i < mol.natm:
        j = i
        while j < mol.natm and z[j] == z[i]:
            j += 1
        # Firefly lists the images of a symmetry-unique atom with the smaller coordinates first
        order += sorted(range(i, j), key=lambda k: tuple(np.round(coords[k], 6))) if job.nsym_ops > 1 \
            else range(i, j)
        i = j
    out = np.zeros_like(C)
    ovl = np.diag(mol.intor("int1e_ovlp"))
    loc = mol.ao_loc_nr()
    src = 0  # GAMESS position, atoms in Firefly order
    for a in order:
        for ib in range(mol.nbas):
            if mol.bas_atom(ib) != a:
                continue
            l = mol.bas_angular(ib)
            n = (l + 1) * (l + 2) // 2 if mol.cart else 2 * l + 1
            for k in range(n):
                row = loc[ib] + k
                if l == 2:
                    g, rel = _GAMESS_CART_D[k]
                    out[row] = C[src + g] * np.sqrt(rel / ovl[row])
                else:
                    out[row] = C[src + k]
            src += n
    return out


def mf_from_vec1(job, mol):
    """A frozen 'SCF' object whose orbitals are the ones read from $VEC1 (SCFTYP=NONE)."""
    C = firefly_vec_to_pyscf(job, mol, job.vec1)
    mf = scf.RHF(mol) if job.mult == 1 else scf.ROHF(mol)
    mf.verbose = 0
    na, nb = (mol.nelectron + job.mult - 1) // 2, (mol.nelectron - job.mult + 1) // 2
    occ = np.zeros(C.shape[1])
    occ[:nb] = 2
    occ[nb:na] = 1
    mf.mo_coeff, mf.mo_occ = C, occ
    dm = mf.make_rdm1(C, occ)
    mf.e_tot = float(mf.energy_tot(dm))
    fock = C.T @ mf.get_fock(dm=dm) @ C
    mf.mo_energy = np.diag(fock).copy()
    mf.converged = True
    return mf


def compute(job, ctx, coords=None, dm0=None, strict=True, tight=False):
    """Build and run the full method at the given geometry."""
    mol = build_mol(job, ctx, coords)
    if job.ci and job.ci["vec1"]:
        mf = mf_from_vec1(job, mol)
        e_scf = mf.e_tot
    else:
        mf = build_scf(job, mol, ctx, tight=tight)
        e_scf = run_scf(job, mf, ctx, dm0=dm0, strict=strict)
    post, e_tot = None, e_scf
    m = job.method
    if m == "CI":
        from ffpy.ci import run_ci
        post = run_ci(job, mf, mol)
        e_tot = post.e_states[job.ci["iroot"] - 1]
    elif m == "MP2" and job.scftyp == "ROHF":
        post = run_rmp2(job, mf, mol)
        e_tot = post.e_tot
    elif m == "MP2":
        post, _ = build_mp2(job, mf, mol)
        post.kernel()
        e_tot = post.e_tot
    elif m in ("MP3", "MP4"):
        post = run_mpn(job, mf, mol)
        e_tot = post.e_tot
    elif m == "DH":
        post = run_dh(job, mf, mol)
        e_tot = e_scf + post.e_corr
    elif m == "CASSCF":
        post = build_cas(job, mf)
        if job.cas.get("open"):
            post.natorb = False
            post.kernel(reorder_orbitals(job, mf.mo_coeff))
        elif job.cas.get("pp") and job.cas.get("nopen"):
            post = best_open_pair(job, mf, ctx)
        elif job.cas.get("pp"):
            from ffpy.gvb import pair_orbitals
            post.kernel(pair_orbitals(mol, mf, job.cas["ncore"], job.cas["pp"]))
        elif job.guess == "MOREAD" and job.vec_firefly and job.cas["nstate"] == 1:
            post.kernel(casscf_guess(job, mf, mol))
        else:
            post.kernel()
        if not post.converged:
            msg = "CASSCF did not converge in %d macro-iterations" % job.cas["maxit"]
            if strict:
                raise SCFNotConverged(msg)
            ctx.log.warning(msg)
            ctx.soft_fail(SCFNotConverged.code, msg)
        e_tot = post.e_tot if job.cas["nstate"] == 1 else post.e_average
        if job.mrpt:
            post.pt2 = run_mrmp2(job, mf, post, mol)
            e_tot = post.pt2.e_tot
    elif m in ("TDDFT", "TDHF"):
        post = build_td(job, mf)
        post.kernel()
        if not all(np.atleast_1d(post.converged)):
            ctx.log.warning("some excited states did not converge")
        e_tot = e_scf
    e_disp = 0.0
    if job.disp:
        e_disp = d3bj_energy(job, mol)
        e_tot += e_disp
    e_nl = 0.0
    if job.dftnl:
        e_nl = vv10_energy(job, mol, mf)
        e_tot += e_nl
    return Result(mol=mol, mf=mf, post=post, e_scf=e_scf, e_tot=e_tot, e_nl=e_nl, e_disp=e_disp)


class NumGradScanner(lib.GradScanner):
    """Central-difference gradient of the full method (scanner protocol of PySCF)."""

    STEP = 0.001  # bohr

    def __init__(self, job, ctx, res):
        self.job, self.ctx = job, ctx
        self.mol = res.mol
        self.base = res.mf
        self.verbose = 0

    @property
    def converged(self):
        return True

    def _energy(self, coords):
        return compute(self.job, self.ctx, coords=coords, tight=True).e_tot

    def __call__(self, mol):
        coords = np.array(mol.atom_coords())
        shown = self.ctx.print_scf
        self.ctx.print_scf = False
        try:
            e0 = self._energy(coords)
            g = np.zeros_like(coords)
            for i in range(coords.shape[0]):
                for k in range(3):
                    cp, cm = coords.copy(), coords.copy()
                    cp[i, k] += self.STEP
                    cm[i, k] -= self.STEP
                    g[i, k] = (self._energy(cp) - self._energy(cm)) / (2 * self.STEP)
        finally:
            self.ctx.print_scf = shown
        return e0, g


def numerical_gradient(job, ctx, res):
    return NumGradScanner(job, ctx, res)(res.mol)[1]


def gradient_scanner(job, res, ctx=None):
    m = job.method
    if m in ("MP3", "MP4") or job.runtyp == "NUMGRAD" or (m == "MP2" and job.scftyp == "ROHF") or m == "CI" or job.scrf:
        return NumGradScanner(job, ctx, res)
    if m in ("HF", "DFT"):
        return res.mf.nuc_grad_method().as_scanner()
    if m == "MP2":
        return res.post.nuc_grad_method().as_scanner()
    if m == "CASSCF":
        if job.cas["nstate"] > 1:
            raise UnsupportedError("state-specific gradients of state-averaged CASSCF (NSTATE>1, needs CP-MCSCF) are not supported")
        return res.post.nuc_grad_method().as_scanner()
    if m in ("TDDFT", "TDHF"):
        return res.post.nuc_grad_method().as_scanner(state=job.excited["iroot"])
    raise UnsupportedError("no gradient for method %s" % m)
