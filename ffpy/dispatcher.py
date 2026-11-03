"""Dispatcher: the one place where the Firefly view of a job meets PySCF.

Every supported (method, RUNTYP) pair has its own handler. A pair that is
not in the table stops the run with an error; methods are never swapped
silently.
"""

import importlib

from ffpy.errors import UnsupportedError


def _run(module, job, ctx):
    # Runners pull in PySCF; importing them only when a job actually runs
    # keeps select() cheap for input checking (the GUI validates as you type).
    return importlib.import_module("ffpy.runners." + module).run(job, ctx)


def energy_hf(job, ctx): return _run("energy", job, ctx)
def energy_dft(job, ctx): return _run("energy", job, ctx)
def energy_mp2(job, ctx): return _run("energy", job, ctx)
def surface_scan(job, ctx): return _run("surface", job, ctx)
def trudge_opt(job, ctx): return _run("trudge", job, ctx)
def irc_path(job, ctx): return _run("irc", job, ctx)
def energy_ci(job, ctx): return _run("energy", job, ctx)
def gradient_ci(job, ctx): return _run("gradient", job, ctx)
def energy_dh(job, ctx): return _run("energy", job, ctx)
def energy_mp3(job, ctx): return _run("energy", job, ctx)
def energy_mp4(job, ctx): return _run("energy", job, ctx)
def energy_casscf(job, ctx): return _run("energy", job, ctx)
def energy_tdhf(job, ctx): return _run("energy", job, ctx)
def energy_tddft(job, ctx): return _run("energy", job, ctx)

def numgrad(job, ctx): return _run("gradient", job, ctx)
def optimize_mp3(job, ctx): return _run("optimize", job, ctx)

def gradient_hf(job, ctx): return _run("gradient", job, ctx)
def gradient_dft(job, ctx): return _run("gradient", job, ctx)
def gradient_mp2(job, ctx): return _run("gradient", job, ctx)
def gradient_casscf(job, ctx): return _run("gradient", job, ctx)
def gradient_tdhf(job, ctx): return _run("gradient", job, ctx)
def gradient_tddft(job, ctx): return _run("gradient", job, ctx)

def optimize_hf(job, ctx): return _run("optimize", job, ctx)
def optimize_dft(job, ctx): return _run("optimize", job, ctx)
def optimize_mp2(job, ctx): return _run("optimize", job, ctx)
def optimize_casscf(job, ctx): return _run("optimize", job, ctx)
def optimize_tdhf(job, ctx): return _run("optimize", job, ctx)
def optimize_tddft(job, ctx): return _run("optimize", job, ctx)

def hessian_hf(job, ctx): return _run("hessian", job, ctx)
def hessian_dft(job, ctx): return _run("hessian", job, ctx)


HANDLERS = {
    ("HF", "ENERGY"): energy_hf,
    ("DFT", "ENERGY"): energy_dft,
    ("MP2", "ENERGY"): energy_mp2,
    ("MP3", "ENERGY"): energy_mp3,
    ("DH", "ENERGY"): energy_dh,
    ("HF", "TRUDGE"): trudge_opt,
    ("HF", "IRC"): irc_path,
    ("DFT", "IRC"): irc_path,
    ("DFT", "TRUDGE"): trudge_opt,
    ("HF", "SURFACE"): surface_scan,
    ("DFT", "SURFACE"): surface_scan,
    ("MP2", "SURFACE"): surface_scan,
    ("MP3", "SURFACE"): surface_scan,
    ("MP4", "SURFACE"): surface_scan,
    ("DH", "SURFACE"): surface_scan,
    ("CASSCF", "SURFACE"): surface_scan,
    ("CI", "SURFACE"): surface_scan,
    ("CI", "ENERGY"): energy_ci,
    ("CI", "TRANSITN"): energy_ci,
    ("CI", "GRADIENT"): gradient_ci,
    ("CI", "NUMGRAD"): numgrad,
    ("HF", "NUMGRAD"): numgrad,
    ("DFT", "NUMGRAD"): numgrad,
    ("MP2", "NUMGRAD"): numgrad,
    ("MP3", "NUMGRAD"): numgrad,
    ("MP4", "NUMGRAD"): numgrad,
    ("MP3", "OPTIMIZE"): optimize_mp3,
    ("MP4", "OPTIMIZE"): optimize_mp3,
    ("MP4", "ENERGY"): energy_mp4,
    ("CASSCF", "ENERGY"): energy_casscf,
    ("TDHF", "ENERGY"): energy_tdhf,
    ("TDDFT", "ENERGY"): energy_tddft,
    ("HF", "GRADIENT"): gradient_hf,
    ("DFT", "GRADIENT"): gradient_dft,
    ("MP2", "GRADIENT"): gradient_mp2,
    ("CASSCF", "GRADIENT"): gradient_casscf,
    ("TDHF", "GRADIENT"): gradient_tdhf,
    ("TDDFT", "GRADIENT"): gradient_tddft,
    ("HF", "OPTIMIZE"): optimize_hf,
    ("DFT", "OPTIMIZE"): optimize_dft,
    ("MP2", "OPTIMIZE"): optimize_mp2,
    ("CASSCF", "OPTIMIZE"): optimize_casscf,
    ("TDHF", "OPTIMIZE"): optimize_tdhf,
    ("TDDFT", "OPTIMIZE"): optimize_tddft,
    ("HF", "HESSIAN"): hessian_hf,
    ("CASSCF", "HESSIAN"): hessian_hf,
    ("DFT", "HESSIAN"): hessian_dft,
}

# (method, SCFTYP, RUNTYP or None for all) combinations PySCF cannot do
_BLOCKED = [
    ("TDHF", "ROHF", None, "TDHF/CIS with an ROHF reference"),
    ("TDDFT", "ROHF", None, "TDDFT with an ROKS reference"),
    ("DFT", "ROHF", "HESSIAN", "analytic hessian for ROKS"),
]


def select(job):
    key = (job.method, job.runtyp)
    if key not in HANDLERS:
        raise UnsupportedError(
            "%s with RUNTYP=%s is not supported. Supported pairs: %s"
            % (job.method, job.runtyp, ", ".join("%s/%s" % k for k in HANDLERS)))
    for method, scftyp, runtyp, what in _BLOCKED:
        if job.method == method and job.scftyp == scftyp and runtyp in (None, job.runtyp):
            raise UnsupportedError("%s is not supported" % what)
    if job.hssend and job.method not in ("HF", "DFT"):
        raise UnsupportedError("HSSEND=.TRUE. needs an analytic hessian (HF or DFT only)")
    if job.hssend and job.scftyp == "ROHF":
        raise UnsupportedError("HSSEND=.TRUE.: analytic hessian for ROHF/ROKS is not supported")
    if job.dftnl and (job.method != "DFT" or job.runtyp != "ENERGY" or job.pcm):
        raise UnsupportedError("DFTNL=.T. is available for plain DFT ENERGY runs only (no gradients, TD or PCM)")
    if job.pcm and job.method not in ("HF", "DFT", "TDHF", "TDDFT"):
        raise UnsupportedError("$PCM is supported only with HF and DFT (and TDHF/TDDFT energies)")
    if job.pcm and job.method in ("TDHF", "TDDFT") and job.runtyp != "ENERGY":
        raise UnsupportedError("$PCM with excited-state gradients is not supported")
    return HANDLERS[key]
