"""RUNTYP=TRUDGE (OPTMIZ=BASIS): optimize basis-set exponents for the lowest SCF energy."""

import copy
import dataclasses

import numpy as np
from scipy.optimize import minimize

from ffpy.errors import InputError
from ffpy.methods import compute
from ffpy.runners.report import report


def _unique_exponents(basis):
    seen = []
    for tag in basis:
        for shell in basis[tag]:
            for prim in shell[1:]:
                if not any(abs(prim[0] - e) < 1e-12 for e in seen):
                    seen.append(prim[0])
    return seen


def _replace(basis, old, new):
    out = copy.deepcopy(basis)
    for tag in out:
        for shell in out[tag]:
            for prim in shell[1:]:
                if abs(prim[0] - old) < 1e-12:
                    prim[0] = new
    return out


def run(job, ctx):
    log = ctx.log
    exps = _unique_exponents(job.basis)
    for k in job.trudge["iex"]:
        if k < 1 or k > len(exps):
            raise InputError("$TRUDGE IEX=%d: the basis has only %d different exponents" % (k, len(exps)))
    start = [exps[k - 1] for k in job.trudge["iex"]]
    log.section("basis exponent optimization (TRUDGE)")
    log("  optimizing exponents number %s, starting values %s"
        % (" ".join(map(str, job.trudge["iex"])), " ".join("%.6f" % x for x in start)))
    log("")
    ctx.print_scf = False
    step = [0]

    def make_job(logx):
        basis = job.basis
        for old, lx in zip(start, logx):
            basis = _replace(basis, old, float(np.exp(lx)))
        return dataclasses.replace(job, basis=basis)

    def energy(logx):
        res = compute(make_job(logx), ctx, tight=True)
        ctx.check_time()
        log("  step %3d  exponents %s   ENERGY = %20.10f"
            % (step[0], " ".join("%.6f" % np.exp(x) for x in logx), res.e_tot))
        step[0] += 1
        return res.e_tot

    opt = minimize(energy, np.log(start), method="Nelder-Mead",
                   options={"xatol": 1e-6, "fatol": 1e-11, "maxiter": 200})
    ctx.print_scf = True
    best = make_job(opt.x)
    log("")
    log("  optimized exponents: %s" % " ".join("%.6f" % np.exp(x) for x in opt.x))
    log.section("SCF with the optimized exponents")
    res = compute(best, ctx)
    report(best, ctx, res, " with the optimized exponents")
    return res
