"""Semiempirical NDDO methods (GBASIS=MNDO, AM1, PM3, RM1): ENERGY, GRADIENT and OPTIMIZE.

The calculation is done by ffpy.nddo; there is no PySCF object, so the result is a small record
with the total energy (hartree, MOPAC's convention: electronic plus core-core energy) and the heat
of formation (kcal/mol).  Gradients are central finite differences of the energy.
"""

import os
import tempfile
from dataclasses import dataclass
from typing import Any

import numpy as np

from ffpy import nddo
from ffpy.errors import OptNotConverged, SCFNotConverged, TimeLimitExceeded, UnsupportedError
from ffpy.writers import out

BOHR_FF = 0.52917721067        # Firefly's bohr (coordinates in the job are in this bohr)
DEBYE = 2.541746               # e*bohr in Debye
EV_OUT = 27.211652             # eV per hartree in the energies Firefly prints for these methods
FD_STEP = 2.0e-3               # bohr


@dataclass
class SemiResult:
    mol: Any
    e_scf: float          # hartree
    e_tot: float
    heat: float           # kcal/mol
    mf: Any = None
    post: Any = None


def _check(job):
    if job.scftyp == "ROHF":
        raise UnsupportedError("SCFTYP=ROHF is not supported for semiempirical methods (use UHF)")
    if job.pcm or job.scrf or job.xc or job.mplevl or job.excited:
        raise UnsupportedError("semiempirical methods are not combined with PCM, DFT, MPn or TD")


def build(job, coords_bohr_ff):
    angstrom = np.asarray(coords_bohr_ff) * BOHR_FF
    return nddo.NDDO(job.semi, job.charges, angstrom / nddo.A0, job.charge, job.mult)


def single_point(job, ctx, coords=None, guess=None, verbose=True):
    coords = job.coords if coords is None else coords
    mol = build(job, coords)
    mol.scf(guess=guess)
    if not mol.converged:
        raise SCFNotConverged("semiempirical SCF did not converge")
    res = SemiResult(mol, mol.etot_ev / EV_OUT, mol.etot_ev / EV_OUT, mol.heat_kcal)
    return res


def gradient(job, ctx, res, coords=None):
    """d E / d x in hartree/bohr (central differences, 6N SCFs started from the reference density)."""
    coords = np.array(job.coords if coords is None else coords, float)
    g = np.zeros_like(coords)
    guess = (res.mol.Pa, res.mol.Pb)
    for i in range(len(coords)):
        for k in range(3):
            ep = []
            for s in (+1, -1):
                c = coords.copy()
                c[i, k] += s * FD_STEP
                ep.append(single_point(job, ctx, c, guess=guess).e_tot)
            g[i, k] = (ep[0] - ep[1]) / (2 * FD_STEP)
    return g


def dipole(mol):
    """Dipole (Debye) about the centre of mass: point charges plus the s-p hybridisation term."""
    from ffpy.runners.hessian import COMMON_ISOTOPE_MASSES
    q = mol.charges()
    m = np.array([COMMON_ISOTOPE_MASSES[z] for z in mol.z], float)
    xyz = mol.xyz - (m[:, None] * mol.xyz).sum(axis=0) / m.sum()
    mu = (q[:, None] * xyz).sum(axis=0)
    P = mol.Pa + mol.Pb
    for i, a in enumerate(mol.atoms):
        if a.norb == 4:
            o = mol.off[i]
            mu += -2.0 * a.dd * P[o, o + 1:o + 4]       # <s|r|p> = dd along each p axis
    return mu * DEBYE


def report(job, ctx, res, suffix=""):
    log = ctx.log
    mol = res.mol
    rows = [
        ("ELECTRONIC ENERGY", mol.eel / EV_OUT),
        ("CORE-CORE REPULSION ENERGY", mol.enuc / EV_OUT),
        ("TOTAL %s ENERGY" % ("RHF" if job.scftyp == "RHF" else "UHF"), res.e_tot),
        ("HEAT OF FORMATION (KCAL/MOL)", res.heat),
    ]
    out.energies(log, "energies (hartree, %s)%s" % (job.semi, suffix), rows)
    log("")
    log("  ORBITAL ENERGIES (EV)%s" % ("" if job.scftyp == "RHF" else ", ALPHA"))
    na = mol.na
    for i, e in enumerate(mol.eps_a):
        tag = "  HOMO" if i == na - 1 else ("  LUMO" if i == na else "")
        log("  %5d %14.6f%s" % (i + 1, e, tag))
    if job.scftyp != "RHF":
        log("  BETA")
        for i, e in enumerate(mol.eps_b):
            log("  %5d %14.6f" % (i + 1, e))
    q = mol.charges()
    log("")
    log("  NET ATOMIC CHARGES")
    for lab, z, c in zip(job.labels, job.charges, q):
        log("  %-8s %10.4f" % (lab, c))
    mu = dipole(mol)
    log("")
    log("  DIPOLE MOMENT (DEBYE)  X %10.5f  Y %10.5f  Z %10.5f  TOTAL %10.5f"
        % (mu[0], mu[1], mu[2], np.linalg.norm(mu)))
    log("")
    log("  %-34s %20.5f" % ("HEAT OF FORMATION (KCAL/MOL)", res.heat))


def run(job, ctx):
    _check(job)
    log = ctx.log
    log.section("SCF (%s)" % job.semi)
    res = single_point(job, ctx)
    report(job, ctx, res)
    if job.runtyp == "GRADIENT":
        g = gradient(job, ctx, res)
        out.gradient(log, job.labels, g)
    elif job.runtyp == "OPTIMIZE":
        res = optimize(job, ctx, res)
    return res


def optimize(job, ctx, res0):
    import geometric.engine
    import geometric.molecule
    import geometric.optimize
    from geometric.errors import GeomOptNotConvergedError

    log = ctx.log
    molecule = geometric.molecule.Molecule()
    molecule.elem = list(job.symbols)
    molecule.xyzs = [np.array(job.coords) * BOHR_FF]
    last = {"E": None, "guess": (res0.mol.Pa, res0.mol.Pb)}

    class Engine(geometric.engine.Engine):
        def __init__(self):
            super().__init__(molecule)

        def calc_new(self, coords, dirname):
            ctx.check_time()
            c = np.asarray(coords).reshape(-1, 3)
            res = single_point(job, ctx, c, guess=last["guess"])
            last["guess"] = (res.mol.Pa, res.mol.Pb)
            g = gradient(job, ctx, res, c)
            step = len(ctx.trajectory)
            ctx.trajectory.append((res.e_tot, c.copy()))
            de = 0.0 if last["E"] is None else res.e_tot - last["E"]
            last["E"] = res.e_tot
            log("  %4d %20.10f %14.6E %14.6E %14.6E %16.5f"
                % (step, res.e_tot, de, np.abs(g).max(), np.sqrt(np.mean(g ** 2)), res.heat))
            return {"energy": res.e_tot, "gradient": g.ravel()}

    params = {
        "convergence_gmax": job.opttol,
        "convergence_grms": job.opttol / 3.0,
        "convergence_energy": 1e-6,
        "convergence_drms": 1.2e-3,
        "convergence_dmax": 1.8e-3,
        "coordsys": "tric",
    }
    log.section("geometry optimization (geomeTRIC)")
    log("  NSTEP = %d, OPTTOL = %.2E hartree/bohr (max gradient), RMS gradient < OPTTOL/3"
        % (job.nstep, job.opttol))
    log("")
    log("  %4s %20s %14s %14s %14s %16s" % ("STEP", "ENERGY", "DELTA E", "MAX GRAD", "RMS GRAD", "HEAT (KCAL/MOL)"))
    ctx.print_scf = False
    engine = Engine()
    from ffpy.runners.optimize import _log_ini
    ini = _log_ini(None)
    final = np.array(job.coords)
    conv = True
    with tempfile.TemporaryDirectory() as tmp:
        try:
            geometric.optimize.run_optimizer(customengine=engine, input=os.path.join(tmp, "g"),
                                             maxiter=job.nstep, logIni=ini, **params)
        except GeomOptNotConvergedError:
            conv = False
        finally:
            try:
                os.remove(ini)
            except OSError:
                pass
    if ctx.trajectory:
        final = ctx.trajectory[-1][1]
    # geomeTRIC evaluates the converged geometry last, so the trajectory ends there
    if conv:
        log("")
        log("  OPTIMIZATION CONVERGED in %d steps" % len(ctx.trajectory))
    else:
        msg = "geometry optimization did not converge in NSTEP=%d steps" % job.nstep
        log.warning(msg)
        ctx.soft_fail(OptNotConverged.code, msg)
    ctx.print_scf = True
    out.geometry(log, job.labels, job.charges, final, "optimized geometry" if conv else "last geometry (not converged)")
    out.distances(log, job.labels, final)
    log.section("SCF at the final geometry")
    res = single_point(job, ctx, final)
    report(job, ctx, res, " at the final geometry")
    return res
