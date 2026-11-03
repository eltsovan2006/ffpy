"""RUNTYP=GRADIENT: energy plus analytic nuclear gradient."""

from ffpy.errors import UnsupportedError
from ffpy.methods import compute, numerical_gradient
from ffpy.runners.report import report
from ffpy.writers import out


def nuclear_gradient(job, res, ctx=None):
    m = job.method
    if m in ("MP3", "MP4") or job.runtyp == "NUMGRAD" or (m == "MP2" and job.scftyp == "ROHF") or m == "CI":
        return numerical_gradient(job, ctx, res)
    if m in ("HF", "DFT"):
        return res.mf.nuc_grad_method().kernel()
    if m == "MP2":
        return res.post.nuc_grad_method().kernel()
    if m == "CASSCF":
        if job.cas["nstate"] > 1:
            raise UnsupportedError("state-specific gradients of state-averaged CASSCF (NSTATE>1, needs CP-MCSCF) are not supported")
        return res.post.nuc_grad_method().kernel()
    if m in ("TDDFT", "TDHF"):
        return res.post.nuc_grad_method().kernel(state=job.excited["iroot"])
    raise UnsupportedError("no gradient for %s" % m)


def run(job, ctx):
    ctx.log.section("SCF iterations")
    res = compute(job, ctx)
    report(job, ctx, res)
    g = nuclear_gradient(job, res, ctx)
    if job.excited:
        ctx.log("")
        ctx.log("  gradient of excited state IROOT=%d (total energy %.10f)"
                % (job.excited["iroot"], res.e_scf + res.post.e[job.excited["iroot"] - 1]))
    out.gradient(ctx.log, job.labels, g)
    return res
