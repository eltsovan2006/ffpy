"""RUNTYP=TRANSITN: CI energies and radiative transition moments between CI states.

One orbital set ($VEC1) gives the usual orthogonal moments; with $TRANST NUMVEC=2 the first state
is taken from the CI built on $VEC1 and the second from the CI built on $VEC2, and the moment is
the non-orthogonal one (Lengsfield et al., JCP 74, 6849 (1981)).
"""

import numpy as np

from ffpy.ci import nonorthogonal_moments, run_ci
from ffpy.errors import InputError
from ffpy.methods import compute, mf_from_vec1
from ffpy.runners.report import report

AU_DEBYE = 2.541766
HARTREE_HZ = 6.579683920502e15       # hartree in 1/s
HARTREE_CM = 219474.6313705
HARTREE_EV = 27.211386245988


def _com(mol):
    m = mol.atom_mass_list(isotope_avg=False)
    from ffpy.runners.hessian import COMMON_ISOTOPE_MASSES
    m = np.array([COMMON_ISOTOPE_MASSES[z] for z in mol.atom_charges()], float)
    return (m[:, None] * mol.atom_coords()).sum(0) / m.sum()


def run(job, ctx):
    ctx.log.section("SCF iterations")
    res = compute(job, ctx, strict=False)
    report(job, ctx, res)
    roots = job.ci.get("iroots")
    if not roots or len(roots) < 2:
        return res
    if len(roots) > 2:
        raise InputError("$TRANST IROOTS: only transitions between two states are computed")
    mol, post_a, mf_a = res.mol, res.post, res.mf
    if job.vec2 is not None:
        mf_b = mf_from_vec1(job, mol, job.vec2)
        post_b = run_ci(job, mf_b, mol)
    else:
        mf_b, post_b = mf_a, post_a
    ra, rb = roots
    res.e_tot = post_a.e_states[ra - 1]
    ea, eb = post_a.e_states[ra - 1], post_b.e_states[rb - 1]
    origin = _com(mol)
    mu, vel = nonorthogonal_moments(mol, mf_a.mo_coeff, post_a, ra, mf_b.mo_coeff, post_b, rb,
                                    job.ci["nfzc"], origin)
    de = abs(eb - ea)
    log = ctx.log
    log.section("transition moments")
    if job.vec2 is not None:
        log("  non-orthogonal orbital sets: state %d of $VEC1 and state %d of $VEC2" % (ra, rb))
    log("  CI STATE NUMBER = %d %d" % (ra, rb))
    log("  STATE ENERGIES  %20.10f %20.10f" % (ea, eb))
    log("  TRANSITION ENERGY = %.2f [1/CM] = %.2f [EV]" % (de * HARTREE_CM, de * HARTREE_EV))
    log("  CENTER OF MASS = %12.6f %12.6f %12.6f BOHR" % tuple(origin))
    n = float(np.linalg.norm(mu))
    log("  TRANSITION DIPOLE = %12.6f %12.6f %12.6f %12.6f E*BOHR" % (*mu, n))
    log("  TRANSITION DIPOLE = %12.6f %12.6f %12.6f %12.6f DEBYE" % (*(mu * AU_DEBYE), n * AU_DEBYE))
    log("  OSCILLATOR STRENGTH = %.6f" % (2.0 / 3.0 * de * n * n))
    nv = float(np.linalg.norm(vel))
    log("  DIPOLE VELOCITY <D/DQ> = %9.6f %9.6f %9.6f %9.6f E/BOHR" % (*vel, nv))
    log("  OSCILLATOR STRENGTH (VELOCITY) = %.6f" % (2.0 / (3.0 * de) * nv * nv if de > 1e-12 else 0.0))
    return res
