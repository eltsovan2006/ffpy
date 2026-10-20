"""RUNTYP=OPTIMIZE: minimum search with geomeTRIC, $STATPT parameters."""

import os
import tempfile

import numpy as np

from ffpy.errors import OptNotConverged, SCFNotConverged, TimeLimitExceeded
from ffpy.methods import compute, gradient_scanner
from ffpy.runners import hessian
from ffpy.runners.report import report
from ffpy.writers import gamess, out

_INI = """[loggers]
keys=root
[handlers]
keys=h
[formatters]
keys=f
[logger_root]
level=INFO
handlers=h
[handler_h]
class=%s
level=INFO
formatter=f
args=%s
[formatter_f]
format=%%(message)s
"""


def _log_ini(debug_path):
    """geomeTRIC talks through the logging module; keep it out of the .out."""
    if debug_path:
        text = _INI % ("FileHandler", repr((debug_path, "a")).replace("%", "%%"))
    else:
        text = _INI % ("NullHandler", "()")
    fd, path = tempfile.mkstemp(suffix=".ini", prefix="ffpy_geometric_")
    with os.fdopen(fd, "w") as f:
        f.write(text)
    return path


def run(job, ctx):
    from pyscf.geomopt import geometric_solver

    log = ctx.log
    log.section("SCF iterations (initial geometry)")
    res = compute(job, ctx)
    report(job, ctx, res, " at the initial geometry")
    scanner = gradient_scanner(job, res)

    params = {
        "convergence_gmax": job.opttol,
        "convergence_grms": job.opttol / 3.0,
        "convergence_energy": 1e-6,
        "convergence_drms": 1.2e-3,
        "convergence_dmax": 1.8e-3,
    }
    log.section("geometry optimization (geomeTRIC)")
    log("  NSTEP = %d, OPTTOL = %.2E hartree/bohr (max gradient), RMS gradient < OPTTOL/3"
        % (job.nstep, job.opttol))
    log("  geomeTRIC also requires |dE| < 1E-6 and displacement rms/max < 1.2E-3/1.8E-3 A")
    log("")
    log("  %4s %20s %14s %14s %14s" % ("STEP", "ENERGY", "DELTA E", "MAX GRAD", "RMS GRAD"))
    ctx.print_scf = False
    last = [None]

    def callback(env):
        ctx.check_time()
        e = float(env["energy"])
        g = np.asarray(env["gradients"]).reshape(-1, 3)
        coords = np.asarray(env["coords"]).reshape(-1, 3).copy()
        step = len(ctx.trajectory)
        ctx.trajectory.append((e, coords))
        de = 0.0 if last[0] is None else e - last[0]
        last[0] = e
        log("  %4d %20.10f %14.6E %14.6E %14.6E"
            % (step, e, de, np.abs(g).max(), np.sqrt(np.mean(g ** 2))))
        if ctx.gamess:
            gamess.nserch(log, step, e, g)

    debug_path = None
    if ctx.pyscf_fh is not None:
        debug_path = os.path.splitext(ctx.pyscf_fh.name)[0] + ".geometric.log"
    ini = _log_ini(debug_path)
    try:
        conv, mol_final = geometric_solver.kernel(
            scanner, callback=callback, maxsteps=job.nstep, logIni=ini, **params)
    except TimeLimitExceeded:
        raise
    except RuntimeError as e:
        if "not converged" in str(e):
            raise SCFNotConverged("SCF did not converge during the optimization: %s" % e)
        raise
    finally:
        try:
            os.remove(ini)
        except OSError:
            pass

    final = mol_final.atom_coords()
    if conv:
        log("")
        log("  OPTIMIZATION CONVERGED in %d steps" % len(ctx.trajectory))
    else:
        msg = "geometry optimization did not converge in NSTEP=%d steps" % job.nstep
        log.warning(msg)
        ctx.soft_fail(OptNotConverged.code, msg)
    ctx.print_scf = True
    title = "optimized geometry" if conv else "last geometry (not converged)"
    out.geometry(log, job.labels, job.charges, final, title)
    out.distances(log, job.labels, final)
    if ctx.gamess and conv:
        gamess.equilibrium(log, job.symbols, job.charges, final)
    log.section("SCF at the final geometry")
    res = compute(job, ctx, coords=final, tight=job.hssend)
    report(job, ctx, res, " at the final geometry")
    if job.hssend and conv:
        hessian.analyze(job, ctx, res)
    elif job.hssend:
        log.warning("HSSEND=.TRUE. skipped because the optimization did not converge")
    return res
