"""Builders that turn a Job into PySCF objects. The only module (with the
runners) that touches the PySCF API."""

import time
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
from pyscf import dft, gto, mcscf, mp, scf, tdscf
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


def build_mol(job, ctx, coords=None):
    coords = job.coords if coords is None else coords
    mol = gto.Mole()
    mol.atom = [(s, tuple(float(x) for x in c)) for s, c in zip(job.symbols, coords)]
    mol.unit = "Bohr"
    mol.basis = job.basis
    mol.charge = job.charge
    mol.spin = job.mult - 1
    mol.cart = job.cart
    mol.symmetry = False
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
    if job.soscf:
        mf = mf.newton()
    mf.callback = _scf_callback(ctx)
    return mf


def moread_dm(job, mf, mol):
    Ca, Cb = job.vec
    nao = mol.nao
    if Ca.shape[0] != nao:
        raise InputError("$VEC has %d AO coefficients per orbital, the basis has %d "
                         "(the $VEC must come from an ffpy .dat with the same basis and ISPHER)"
                         % (Ca.shape[0], nao))
    na, nb = mol.nelec
    if job.scftyp == "UHF":
        Cb = Ca if Cb is None else Cb
        return np.array([Ca[:, :na] @ Ca[:, :na].T, Cb[:, :nb] @ Cb[:, :nb].T])
    if job.scftyp == "ROHF" or (job.scftyp == "MCSCF" and job.mult > 1):
        return np.array([Ca[:, :na] @ Ca[:, :na].T, Ca[:, :nb] @ Ca[:, :nb].T])
    return 2.0 * Ca[:, :na] @ Ca[:, :na].T


def run_scf(job, mf, ctx, dm0=None, strict=True):
    log = ctx.log
    if dm0 is None and job.guess == "MOREAD":
        dm0 = moread_dm(job, mf, mf.mol)
    mf.kernel(dm0=dm0)
    if not mf.converged:
        msg = "SCF did not converge in MAXIT=%d iterations" % job.maxit
        if strict:
            raise SCFNotConverged(msg)
        log.warning(msg)
        ctx.soft_fail(SCFNotConverged.code, msg)
    return mf.e_tot


def build_mp2(job, mf, mol):
    nfrz = job.mp2_frozen if job.mp2_frozen is not None else chemcore(mol)
    pt = mp.MP2(mf, frozen=nfrz if nfrz else None)
    pt.verbose = mol.verbose
    return pt, nfrz


def build_cas(job, mf):
    c = job.cas
    s = job.mult - 1
    nelecas = ((c["nels"] + s) // 2, (c["nels"] - s) // 2)
    mc = mcscf.CASSCF(mf, c["nact"], nelecas)
    mc.max_cycle_macro = c["maxit"]
    mc.conv_tol = 1e-9
    mc.conv_tol_grad = c["acurcy"]
    mc.natorb = True
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
    if job.scftyp == "RHF":
        td.singlet = not ex["triplet"]
    return td


def compute(job, ctx, coords=None, dm0=None, strict=True, tight=False):
    """Build and run the full method at the given geometry."""
    mol = build_mol(job, ctx, coords)
    mf = build_scf(job, mol, ctx, tight=tight)
    e_scf = run_scf(job, mf, ctx, dm0=dm0, strict=strict)
    post, e_tot = None, e_scf
    m = job.method
    if m == "MP2":
        post, _ = build_mp2(job, mf, mol)
        post.kernel()
        e_tot = post.e_tot
    elif m == "CASSCF":
        post = build_cas(job, mf)
        post.kernel()
        if not post.converged:
            msg = "CASSCF did not converge in %d macro-iterations" % job.cas["maxit"]
            if strict:
                raise SCFNotConverged(msg)
            ctx.log.warning(msg)
            ctx.soft_fail(SCFNotConverged.code, msg)
        e_tot = post.e_tot if job.cas["nstate"] == 1 else post.e_average
    elif m in ("TDDFT", "TDHF"):
        post = build_td(job, mf)
        post.kernel()
        if not all(np.atleast_1d(post.converged)):
            ctx.log.warning("some excited states did not converge")
        e_tot = e_scf
    return Result(mol=mol, mf=mf, post=post, e_scf=e_scf, e_tot=e_tot)


def gradient_scanner(job, res):
    m = job.method
    if m in ("HF", "DFT"):
        return res.mf.nuc_grad_method().as_scanner()
    if m == "MP2":
        return res.post.nuc_grad_method().as_scanner()
    if m == "CASSCF":
        if job.cas["nstate"] > 1:
            raise UnsupportedError("gradients of state-averaged CASSCF (NSTATE>1) are not supported")
        return res.post.nuc_grad_method().as_scanner()
    if m in ("TDDFT", "TDHF"):
        return res.post.nuc_grad_method().as_scanner(state=job.excited["iroot"])
    raise UnsupportedError("no gradient for method %s" % m)
