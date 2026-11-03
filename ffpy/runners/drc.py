"""RUNTYP=DRC: classical trajectory on the quantum-chemical potential energy surface.

Velocity Verlet in Cartesian coordinates with the forces of the chosen method (semiempirical,
HF, DFT or MP2).  The initial velocity is the direction VEL with the centre-of-mass motion removed,
scaled to EKIN (kcal/mol), or VEL itself when NVEL=.TRUE. (restarts).
"""

import numpy as np

from ffpy.errors import InputError
from ffpy.runners.hessian import COMMON_ISOTOPE_MASSES

KCAL_EH = 627.5095
# 1 amu * bohr^2 / fs^2 in hartree
AMU_BOHR2_FS2 = 1.66053906660e-27 * (5.29177210903e-11 ** 2) / 1e-30 / 4.3597447222071e-18
BOHR_ANG = 0.52917721067


def _energy_gradient(job, ctx, x, state):
    """Potential energy (hartree) and gradient (hartree/bohr) at x (bohr)."""
    if job.semi:
        from ffpy.runners import semi
        res = semi.single_point(job, ctx, x, guess=state.get("guess"))
        state["guess"] = (res.mol.Pa, res.mol.Pb)
        g = semi.gradient(job, ctx, res, x)
        return res.e_tot, g, res
    from ffpy.methods import compute
    from ffpy.runners.gradient import nuclear_gradient
    res = compute(job, ctx, coords=x, tight=True)
    return res.e_tot, np.asarray(nuclear_gradient(job, res, ctx)), res


def run(job, ctx):
    log = ctx.log
    d = job.drc
    m = np.array([COMMON_ISOTOPE_MASSES[z] for z in job.charges], float)
    natm = len(m)
    x = np.array(job.coords, float)
    v = np.array(d["vel"], float).reshape(natm, 3)
    dt = d["dt"]

    if d["nvel"]:
        ekin0 = 0.5 * np.sum(m[:, None] * v * v) * AMU_BOHR2_FS2
    else:
        v = v - (m[:, None] * v).sum(0) / m.sum()
        ke = 0.5 * np.sum(m[:, None] * v * v) * AMU_BOHR2_FS2
        if ke <= 0:
            raise InputError("$DRC: the initial velocity vector is zero after removing the translation")
        ekin0 = d["ekin"] / KCAL_EH
        v *= np.sqrt(ekin0 / ke)
    log.section("DRC parameters")
    log("  NSTEP = %d   DELTAT = %.4f fs   TOTIME = %.4f fs" % (d["nstep"], dt, d["t0"]))
    log("  initial kinetic energy %.6f hartree (%.4f kcal/mol)" % (ekin0, ekin0 * KCAL_EH))
    log("  masses (amu): " + " ".join("%.6f" % a for a in m))
    log("  normal-mode analysis of the trajectory is not printed by ffpy")

    state = {}
    acc_unit = 1.0 / AMU_BOHR2_FS2         # (hartree/bohr)/amu -> bohr/fs^2

    def snapshot(t, x, v, e_pot, g):
        ke = 0.5 * np.sum(m[:, None] * v * v) * AMU_BOHR2_FS2
        ctx.trajectory.append((e_pot, x.copy()))
        log("")
        log("  TIME %10.4f fs   KINETIC %.8f   POTENTIAL %.8f   TOTAL %.8f" % (t, ke, e_pot, ke + e_pot))
        log("  %-3s %12s %12s %12s   %12s %12s %12s" % ("", "X (BOHR)", "Y", "Z", "VX (BOHR/FS)", "VY", "VZ"))
        for z, c, w in zip(job.symbols, x, v):
            log("  %-3s %12.6f %12.6f %12.6f   %12.6f %12.6f %12.6f" % (z, *c, *w))
        return ke

    e_pot, g, res = _energy_gradient(job, ctx, x, state)
    t = d["t0"]
    ke = snapshot(t, x, v, e_pot, g)
    e_tot0 = ke + e_pot
    for step in range(1, d["nstep"] + 1):
        ctx.check_time()
        a = -g / m[:, None] * acc_unit
        x = x + v * dt + 0.5 * a * dt * dt
        e_pot, g_new, res = _energy_gradient(job, ctx, x, state)
        a_new = -g_new / m[:, None] * acc_unit
        v = v + 0.5 * (a + a_new) * dt
        g = g_new
        t = d["t0"] + step * dt
        ke = snapshot(t, x, v, e_pot, g)
        if abs(ke + e_pot - e_tot0) > d["engtol"]:
            log.warning("total energy drifted by %.2E hartree (ENGTOL %.1E)" % (ke + e_pot - e_tot0, d["engtol"]))
            break
    log("")
    log("  RESTART INFORMATION FOR THE NEXT DRC RUN:")
    log("  $DRC NSTEP=?? DELTAT=%.4f TOTIME=%.4f NVEL=.TRUE." % (dt, t))
    log("   VEL(1)= " + " ".join("%.12f" % c for c in v.ravel()))
    log("  coordinates (angstrom):")
    for z, zz, c in zip(job.symbols, job.charges, x):
        log("   %-3s %5.1f %18.10f %18.10f %18.10f" % (z, zz, *(c * BOHR_ANG)))
    log("  .... DONE WITH DRC SEGMENT ....")
    return res
