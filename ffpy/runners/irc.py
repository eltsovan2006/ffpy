"""RUNTYP=IRC: intrinsic reaction path from a saddle point, Gonzalez-Schlegel second-order (GS2).

Mass-weighted coordinates q = sqrt(m) x. Each path point is the lowest-energy point on the
hypersphere of radius STRIDE/2 around the pivot q_k - (STRIDE/2) g_k/|g_k|; the first pivot lies
STRIDE/2 away from the saddle along the imaginary normal mode (the direction with the largest
component negative for FORWRD=.FALSE.).
"""

import numpy as np
from scipy.optimize import minimize

from ffpy.errors import InputError, UnsupportedError
from ffpy.methods import compute
from ffpy.runners.gradient import nuclear_gradient
from ffpy.runners.hessian import isotope_masses
from ffpy.runners.report import report
from ffpy.writers import out


def _vibrational_basis(x, masses):
    n = len(masses)
    xc = x.reshape(-1, 3)
    com = (masses[:, None] * xc).sum(0) / masses.sum()
    sq = np.sqrt(masses)[:, None]
    rows = []
    for k in range(3):
        t = np.zeros((n, 3))
        t[:, k] = 1
        rows.append((t * sq).ravel())
        rows.append((np.cross(np.eye(3)[k], xc - com) * sq).ravel())
    q, r = np.linalg.qr(np.array(rows).T)
    q = q[:, np.abs(np.diag(r)) > 1e-8]
    u = np.linalg.svd(np.eye(3 * n) - q @ q.T)[0]
    return u[:, :3 * n - q.shape[1]]


def run(job, ctx):
    log = ctx.log
    log.section("SCF iterations (saddle point)")
    res0 = compute(job, ctx, tight=True)
    report(job, ctx, res0, " at the saddle point")
    mol = res0.mol
    n = mol.natm
    masses = isotope_masses(mol)
    sq = np.repeat(np.sqrt(masses), 3)
    x0 = mol.atom_coords().ravel()
    q0 = x0 * sq

    try:
        hess = res0.mf.Hessian().kernel()
    except (AttributeError, NotImplementedError) as e:
        raise UnsupportedError("analytic hessian is not available for %s: %s" % (job.describe(), e))
    hm = hess.transpose(0, 2, 1, 3).reshape(3 * n, 3 * n) / np.outer(sq, sq)
    w, v = np.linalg.eigh(hm)
    if w[0] >= 0:
        raise InputError("IRC: the geometry has no imaginary frequency; it is not a saddle point")
    mode = v[:, 0]
    big = int(np.argmax(np.abs(mode)))
    if (mode[big] > 0) == (not job.irc["forward"]):
        mode = -mode        # FORWRD=.FALSE.: the largest component of the displacement is negative
    delta = job.irc["stride"] / 2.0
    basis = _vibrational_basis(x0, masses)

    def evaluate(q, want_res=False):
        res = compute(job, ctx, coords=(q / sq).reshape(-1, 3), tight=True)
        g = np.asarray(nuclear_gradient(job, res, ctx)).ravel()
        return (res, g / sq) if want_res else (res.e_tot, g / sq)

    log.section("intrinsic reaction path (GS2)")
    log("  STRIDE = %.5f bohr*sqrt(amu), NPOINT = %d, %s direction" %
        (job.irc["stride"], job.irc["npoint"], "forward" if job.irc["forward"] else "backward"))
    log("  imaginary mode: %.1f cm-1" % (np.sqrt(abs(w[0]) * 4.3597447222071e-18 /
                                                  (1.66053906660e-27 * (5.29177210903e-11) ** 2))
                                         / (2 * np.pi * 2.99792458e10)))
    log("")
    log("  %5s %16s %22s" % ("POINT", "PATH DISTANCE", "ENERGY"))
    log("  %5s %16.5f %22.10f" % ("TS", 0.0, res0.e_tot))
    ctx.print_scf = False
    cur, stot, res = q0.copy(), 0.0, res0
    for k in range(job.irc["npoint"]):
        ctx.check_time()
        if k == 0:
            pivot = q0 + delta * mode
        else:
            _, g = evaluate(cur)
            g = basis @ (basis.T @ g)
            pivot = cur - delta * g / np.linalg.norm(g)
        d = pivot - cur
        start = pivot + delta * d / np.linalg.norm(d)

        def fun(y):
            e, g = evaluate(q0 + basis @ y)
            return e, basis.T @ g

        cons = {"type": "eq", "fun": lambda y: np.sum((q0 + basis @ y - pivot) ** 2) - delta ** 2,
                "jac": lambda y: 2 * basis.T @ (q0 + basis @ y - pivot)}
        sol = minimize(fun, basis.T @ (start - q0), jac=True, constraints=[cons], method="SLSQP",
                       options={"ftol": 1e-13, "maxiter": 100})
        new = q0 + basis @ sol.x
        stot += np.linalg.norm(new - cur)
        cur = new
        log("  %5d %16.5f %22.10f" % (k + 1, stot, sol.fun))
    ctx.print_scf = True
    res = compute(job, ctx, coords=(cur / sq).reshape(-1, 3))
    final = (cur / sq).reshape(-1, 3)
    out.geometry(log, job.labels, job.charges, final, "geometry of the last path point")
    log.section("SCF at the last path point")
    report(job, ctx, res, " at the last path point")
    return res
