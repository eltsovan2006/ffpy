"""Properties printed after every converged calculation: energies,
orbital energies and occupations, Mulliken/Lowdin charges, dipole."""

import numpy as np

from ffpy.writers import gamess, out


def _ref_label(job):
    if job.xc:
        return {"RHF": "RKS", "UHF": "UKS", "ROHF": "ROKS"}[job.scftyp]
    return "RHF" if job.scftyp == "MCSCF" and job.mult == 1 else (
        "ROHF" if job.scftyp == "MCSCF" else job.scftyp)


def report(job, ctx, res, title_suffix=""):
    log = ctx.log
    mf, mol = res.mf, res.mol
    ref = _ref_label(job)
    niter = int(getattr(mf, "cycles", 0) or 0)
    rows = [("NUCLEAR REPULSION ENERGY", mol.energy_nuc())]
    summ = getattr(mf, "scf_summary", {}) or {}
    if "e1" in summ:
        rows.append(("ONE-ELECTRON ENERGY", summ["e1"]))
    if "coul" in summ:
        rows.append(("TWO-ELECTRON ENERGY (COULOMB+X)", summ["coul"]))
    if "exc" in summ and job.xc:
        rows.append(("EXCHANGE-CORRELATION ENERGY", summ["exc"]))
    if job.pcm and "e_solvent" in summ:
        rows.append(("SOLVATION ENERGY (PCM)", summ["e_solvent"]))
    rows.append(("TOTAL %s ENERGY" % ref, res.e_scf))
    m = job.method
    if m == "MP2":
        rows.append(("MP2 CORRELATION ENERGY", res.post.e_corr))
        rows.append(("TOTAL MP2 ENERGY", res.post.e_tot))
    if m == "CASSCF":
        mc = res.post
        if job.cas["nstate"] > 1:
            for i, e in enumerate(mc.e_states):
                rows.append(("CASSCF STATE %d ENERGY" % (i + 1), e))
            rows.append(("STATE-AVERAGED CASSCF ENERGY", mc.e_average))
        else:
            rows.append(("TOTAL CASSCF ENERGY", mc.e_tot))
    out.energies(log, "energies (hartree)%s" % title_suffix, rows)
    if niter:
        log("  SCF converged in %d iterations" % niter if mf.converged
            else "  SCF NOT converged after %d iterations" % niter)
    if ctx.gamess:
        gamess.final_energy(log, ref if not job.xc else "DFT", res.e_scf, niter)
        if m == "MP2":
            log("")
            log("     E(MP2)= %20.10f" % res.post.e_tot)
        if m == "CASSCF":
            log("")
            log(" FINAL MCSCF ENERGY IS %20.10f" % res.e_tot)

    # orbitals
    if m == "CASSCF":
        mc = res.post
        nmo = mc.mo_coeff.shape[1]
        occ = np.zeros(nmo)
        occ[:mc.ncore] = 2.0
        casdm1 = mc.fcisolver.make_rdm1(mc.ci, mc.ncas, mc.nelecas)
        occ[mc.ncore:mc.ncore + mc.ncas] = np.diag(casdm1)
        e = mc.mo_energy if mc.mo_energy is not None else np.zeros(nmo)
        out.orbitals(log, e, occ, "CASSCF (NATURAL OCCUPATIONS IN ACTIVE SPACE)")
    else:
        e, occ = np.asarray(mf.mo_energy), np.asarray(mf.mo_occ)
        if e.ndim == 2:
            out.orbitals(log, e[0], occ[0], "ALPHA")
            out.orbitals(log, e[1], occ[1], "BETA")
        else:
            out.orbitals(log, e, occ)
        if ctx.gamess:
            C = np.asarray(mf.mo_coeff)
            if C.ndim == 3:
                gamess.eigenvectors(log, mol, e[0], C[0], "ALPHA SET EIGENVECTORS")
                gamess.eigenvectors(log, mol, e[1], C[1], "BETA SET EIGENVECTORS")
            else:
                gamess.eigenvectors(log, mol, e, C)

    # density for properties
    if m == "CASSCF":
        mc = res.post
        dm = np.array(mc.make_rdm1s()) if job.mult > 1 else mc.make_rdm1()
        note = "CASSCF density"
    else:
        dm = mf.make_rdm1()
        note = "%s density" % ref
        if m == "MP2":
            note += " (MP2 properties are not relaxed; the SCF reference is used)"
        if m in ("TDDFT", "TDHF"):
            note += " (ground state)"
    log("")
    log("  properties below use the %s" % note)
    out.populations(log, mol, job.labels, dm)
    out.bond_orders_and_valences(log, mol, job.labels, dm)
    out.dipole(log, mol, dm)
    if m in ("TDDFT", "TDHF"):
        out.excited_states(log, res.post, res.e_scf, job.excited["kind"])
