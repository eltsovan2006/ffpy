"""RUNTYP=HESSIAN: analytic hessian, frequencies, IR intensities, thermochemistry.

IR intensities come from dipole derivatives by central finite differences
(6N extra SCF runs, step 0.005 bohr), since PySCF core has no analytic
dipole derivatives.
"""

import numpy as np
from pyscf.data.elements import COMMON_ISOTOPE_MASSES
from pyscf.hessian import thermo
from pyscf.scf import hf

from ffpy.constants import E_TO_DEBYE_PER_ANG, IR_KMMOL
from ffpy.errors import UnsupportedError
from ffpy.methods import build_mol, build_scf, compute, run_scf
from ffpy.runners.report import report
from ffpy.writers import gamess, out

FD_STEP = 5e-3   # bohr


def isotope_masses(mol):
    """Most abundant isotope masses, as GAMESS/Firefly use. (PySCF's
    atom_mass_list(isotope_avg=False) returns integer mass numbers.)"""
    return np.array([COMMON_ISOTOPE_MASSES[z] for z in mol.atom_charges()], float)


class _MassMol:
    """Mole proxy with most-abundant-isotope masses for thermochemistry."""

    def __init__(self, mol):
        self._mol = mol

    def atom_mass_list(self, isotope_avg=False):
        return isotope_masses(self._mol)

    def __getattr__(self, name):
        return getattr(self._mol, name)


class _Model:
    def __init__(self, mol, e_tot):
        self.mol = mol
        self.e_tot = e_tot


def run(job, ctx):
    ctx.log.section("SCF iterations")
    res = compute(job, ctx, tight=True)
    report(job, ctx, res)
    analyze(job, ctx, res)
    return res


def dipole_derivatives(job, ctx, res):
    coords0 = res.mol.atom_coords()
    dm0 = res.mf.make_rdm1()
    natm = len(coords0)
    D = np.zeros((natm, 3, 3))
    printing, ctx.print_scf = ctx.print_scf, False
    total = natm * 6
    done = 0
    try:
        for a in range(natm):
            for x in range(3):
                mus = []
                for s in (1.0, -1.0):
                    c = coords0.copy()
                    c[a, x] += s * FD_STEP
                    mol = build_mol(job, ctx, c)
                    mf = build_scf(job, mol, ctx, tight=True)
                    run_scf(job, mf, ctx, dm0=dm0)
                    dm = np.asarray(mf.make_rdm1())
                    if dm.ndim == 3:
                        dm = dm[0] + dm[1]
                    mus.append(hf.dip_moment(mol, dm, unit="AU", verbose=0))
                    done += 1
                    ctx.log("    dipole derivatives: %d/%d" % (done, total))
                D[a, x] = (mus[0] - mus[1]) / (2 * FD_STEP)
    finally:
        ctx.print_scf = printing
    return D


def analyze(job, ctx, res):
    log = ctx.log
    mol, mf = res.mol, res.mf
    log.section("hessian")
    log("  analytic hessian (PySCF), IR intensities from finite-difference dipole derivatives")
    try:
        hobj = mf.Hessian()
    except (AttributeError, NotImplementedError) as e:
        raise UnsupportedError("analytic hessian is not available for %s: %s" % (job.describe(), e))
    h = hobj.kernel()
    ctx.check_time()
    masses = isotope_masses(mol)
    proj = getattr(job, "projct", True)
    ha = thermo.harmonic_analysis(mol, h, mass=masses, exclude_trans=proj, exclude_rot=proj)
    w = np.asarray(ha["freq_wavenumber"])
    wn = np.where(np.abs(w.imag) > np.abs(w.real), -np.abs(w.imag), w.real).astype(float)
    nm = np.asarray(ha["norm_mode"])                   # (nmode, natm, 3), amu^-1/2
    D = dipole_derivatives(job, ctx, res)              # (natm, 3, 3), e
    dmu_dq = np.einsum("axm,kax->km", D, nm)           # e / amu^1/2
    ir_d2 = np.sum(dmu_dq ** 2, axis=1) * E_TO_DEBYE_PER_ANG ** 2
    modes = nm / np.linalg.norm(nm.reshape(len(nm), -1), axis=1)[:, None, None]
    freq = {"wavenumbers": wn, "modes": modes, "reduced_mass": np.asarray(ha["reduced_mass"]),
            "force_const": np.asarray(ha["force_const_dyne"]), "ir_d2": ir_d2,
            "ir_km": ir_d2 * IR_KMMOL, "masses": masses, "hessian": h}
    ctx.freq = freq
    out.frequencies(log, freq, job.labels)
    if ctx.gamess:
        gamess.frequencies(log, job.symbols, freq)
    nimag = int((wn < 0).sum())
    if nimag:
        log.warning("%d imaginary frequenc%s: %s cm-1 (not a minimum, or the geometry is not "
                    "converged tightly enough)" % (nimag, "y" if nimag == 1 else "ies",
                                                  ", ".join("%.2fi" % -x for x in wn[wn < 0])))
        if proj:
            log.warning("translation/rotation projection at non-stationary points shifts frequencies; "
                        "use $FORCE PROJCT=.F. to obtain unprojected 3N modes")
    th_list = []
    for T in job.temps:
        model = _Model(_MassMol(mol), res.e_tot)
        try:
            th = thermo.thermo(model, ha["freq_au"], T, 101325)
        except Exception:
            th = thermo.thermo(_Model(mol, res.e_tot), ha["freq_au"], T, 101325)
        th_list.append(th)
    out.thermochem(log, th_list)
    if nimag:
        log("  (imaginary modes are excluded from the vibrational partition function)")
    return freq
