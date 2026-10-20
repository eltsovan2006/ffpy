"""RUNTYP=ENERGY: single point, orbitals, populations, dipole."""

from ffpy.methods import compute
from ffpy.runners.report import report


def run(job, ctx):
    ctx.log.section("SCF iterations")
    res = compute(job, ctx, strict=False)
    report(job, ctx, res)
    return res
