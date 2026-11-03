"""RUNTYP=SURFACE: rigid potential-energy scan along one or two group translations."""

import itertools

import numpy as np

from ffpy.methods import compute
from ffpy.runners.report import report

ANGSTROM = 1.0 / 0.52917721067


def run(job, ctx):
    log = ctx.log
    coords0 = np.array(job.coords, float)
    axes = []
    for c in job.surface:
        a, b = c["ivec"]
        u = coords0[b - 1] - coords0[a - 1]
        axes.append(u / np.linalg.norm(u))
    values = [[c["orig"] + k * c["disp"] for k in range(c["n"])] for c in job.surface]

    log.section("potential surface scan")
    for i, c in enumerate(job.surface, 1):
        log("  COORD %d lies along atoms %d -> %d, moves atoms %s, origin %.4f, step %.4f, %d points (angstrom)"
            % (i, c["ivec"][0], c["ivec"][1], " ".join(map(str, c["igrp"])), c["orig"], c["disp"], c["n"]))
    log("")
    first, rows = None, []
    ctx.print_scf = False
    for point in itertools.product(*values):
        coords = coords0.copy()
        for c, u, d in zip(job.surface, axes, point):
            for atom in c["igrp"]:
                coords[atom - 1] += d * ANGSTROM * u
        ctx.check_time()
        res = compute(job, ctx, coords=coords, strict=False)
        if first is None:
            first = res
        rows.append((point, res.e_tot))
        log("  " + "  ".join("COORD %d= %9.5f" % (i + 1, d) for i, d in enumerate(point))
            + "   ENERGY = %20.10f" % res.e_tot)
    ctx.print_scf = True
    log("")
    log.section("SCF at the first scan point")
    report(job, ctx, first, " at the first scan point")
    return first
