"""Text blocks of the .out log (ffpy's own format)."""

import datetime
import os
import platform

import numpy as np

from ffpy import PROGRAM, __version__
from ffpy.constants import AU_DEBYE, BOHR_ANG, EV_NM, HARTREE_EV, HARTREE_KCAL, HARTREE_KJ


def header(log, input_path, nthreads):
    import geometric
    import pyscf
    log(" " + "=" * 72)
    log("  %s %s  -  Firefly/GAMESS-style input, computed with PySCF" % (PROGRAM, __version__))
    log("  PySCF %s   geomeTRIC %s   NumPy %s   Python %s"
        % (pyscf.__version__, geometric.__version__, np.__version__, platform.python_version()))
    log("  input : %s" % os.path.abspath(input_path))
    log("  start : %s   host: %s   threads: %d"
        % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), platform.node(), nthreads))
    log(" " + "=" * 72)


def echo_input(log, text):
    log.section("input file")
    for line in text.splitlines():
        log("  | " + line)


def job_summary(log, job, mol):
    log.section("job")
    log("  title            : %s" % job.title)
    log("  method           : %s" % job.describe())
    log("  RUNTYP           : %s" % job.runtyp)
    log("  charge / mult    : %d / %d" % (job.charge, job.mult))
    na, nb = mol.nelec
    log("  electrons        : %d (alpha %d, beta %d)" % (na + nb, na, nb))
    log("  basis            : %s, %s d/f functions, %d basis functions, %d shells"
        % (job.basis, "Cartesian" if job.cart else "spherical", mol.nao, mol.nbas))
    log("  point group      : %s in $DATA (%d operations); calculation runs in C1"
        % (job.point_group, job.nsym_ops))
    if job.xc:
        log("  xc (PySCF)       : %s" % job.xc)
    if job.pcm:
        log("  solvent          : IEF-PCM, %s, eps = %.4f" % (job.pcm["solvent"], job.pcm["eps"]))
    log("  memory           : %s" % ("%.0f MB" % job.memory_mb if job.memory_mb
                                       else "PySCF default (%d MB)" % mol.max_memory))


def geometry(log, labels, charges, coords, title="molecular geometry"):
    log.section(title)
    log("  %-8s %6s %15s %15s %15s   %15s %15s %15s"
        % ("ATOM", "Z", "X (ANGS)", "Y (ANGS)", "Z (ANGS)", "X (BOHR)", "Y (BOHR)", "Z (BOHR)"))
    for lab, z, c in zip(labels, charges, coords):
        a = c * BOHR_ANG
        log("  %-8s %6.1f %15.10f %15.10f %15.10f   %15.10f %15.10f %15.10f"
            % (lab, z, a[0], a[1], a[2], c[0], c[1], c[2]))


def distances(log, labels, coords, cutoff=3.5):
    """Bonded distances (< cutoff Angstrom) and angles between them."""
    n = len(labels)
    xyz = coords * BOHR_ANG
    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            d = np.linalg.norm(xyz[i] - xyz[j])
            if d < cutoff and d < 1.3 * _cov(labels[i], labels[j]):
                pairs.append((i, j, d))
    if not pairs:
        return
    log("")
    log("  bond lengths (ANGS):")
    for i, j, d in pairs:
        log("    %-6s - %-6s %12.6f" % (_lab(labels, i), _lab(labels, j), d))
    bonded = {}
    for i, j, _ in pairs:
        bonded.setdefault(i, []).append(j)
        bonded.setdefault(j, []).append(i)
    ang = []
    for c, nb in sorted(bonded.items()):
        for a in range(len(nb)):
            for b in range(a + 1, len(nb)):
                v1, v2 = xyz[nb[a]] - xyz[c], xyz[nb[b]] - xyz[c]
                cosv = np.dot(v1, v2) / np.linalg.norm(v1) / np.linalg.norm(v2)
                ang.append((nb[a], c, nb[b], np.degrees(np.arccos(np.clip(cosv, -1, 1)))))
    if ang:
        log("  bond angles (DEG):")
        for a, c, b, t in ang:
            log("    %-6s - %-6s - %-6s %10.4f" % (_lab(labels, a), _lab(labels, c), _lab(labels, b), t))


_COV = {"H": 0.31, "C": 0.76, "N": 0.71, "O": 0.66, "F": 0.57, "S": 1.05, "P": 1.07,
        "CL": 1.02, "B": 0.84, "SI": 1.11, "BR": 1.20, "LI": 1.28, "NA": 1.66, "BE": 0.96}


def _sym(label):
    s = "".join(ch for ch in label if ch.isalpha()).upper()
    return s if s in _COV else s[:1]


def _cov(a, b):
    return _COV.get(_sym(a), 1.2) + _COV.get(_sym(b), 1.2)


def _lab(labels, i):
    return "%s%d" % (labels[i], i + 1)


def energies(log, title, rows):
    log.section(title)
    for name, val in rows:
        log("  %-34s %20.10f" % (name, val))


def orbitals(log, mo_energy, mo_occ, spin=""):
    log("")
    log("  %s ORBITAL ENERGIES AND OCCUPATIONS" % spin if spin else "  ORBITAL ENERGIES AND OCCUPATIONS")
    log("  %5s %8s %18s %14s" % ("MO", "OCC", "ENERGY (EH)", "ENERGY (EV)"))
    occ = np.asarray(mo_occ)
    e_arr = np.asarray(mo_energy)
    n = max(len(e_arr), len(occ))
    if len(e_arr) < n:
        e_arr = np.pad(e_arr, (0, n - len(e_arr)), constant_values=0.0)
    if len(occ) < n:
        occ = np.pad(occ, (0, n - len(occ)), constant_values=0.0)
    homo = np.where(occ > 1e-8)[0]
    integer = np.allclose(occ, np.round(occ))
    hi = homo[-1] if len(homo) and integer else -10
    for i in range(n):
        e, o = e_arr[i], occ[i]
        tag = "  HOMO" if i == hi else ("  LUMO" if i == hi + 1 else "")
        log("  %5d %8.4f %18.10f %14.6f%s" % (i + 1, o, e, e * HARTREE_EV, tag))


def _normalize_ao(S, dm):
    """Normalize Cartesian AOs so S_ii == 1, matching Firefly/GAMESS Lowdin and Mayer."""
    diag_s = np.diag(S)
    d = 1.0 / np.sqrt(np.maximum(diag_s, 1e-15))
    D = np.diag(d)
    Dinv = np.diag(1.0 / d)
    S_norm = D @ S @ D
    dm = np.asarray(dm)
    if dm.ndim == 3:
        P_norm = np.array([Dinv @ dm[0] @ Dinv, Dinv @ dm[1] @ Dinv])
    else:
        P_norm = Dinv @ dm @ Dinv
    return S_norm, P_norm


def _lowdin(S, dm):
    w, v = np.linalg.eigh(S)
    w = np.maximum(w, 1e-14)
    s12 = (v * np.sqrt(w)) @ v.T
    return np.einsum("ij,jk,ki->i", s12, dm, s12)


def _atom_sum(mol, ao_pop):
    out = np.zeros(mol.natm)
    for i, (sh0, sh1, p0, p1) in enumerate(mol.aoslice_by_atom()):
        out[i] = ao_pop[p0:p1].sum()
    return out


def populations(log, mol, labels, dm):
    """dm: total AO density, or (alpha, beta) for open shells."""
    S = mol.intor_symmetric("int1e_ovlp")
    dm = np.asarray(dm)
    spin = dm.ndim == 3
    dmt = dm[0] + dm[1] if spin else dm
    Z = mol.atom_charges()
    mull = Z - _atom_sum(mol, np.einsum("ij,ji->i", dmt, S))
    S_norm, P_norm = _normalize_ao(S, dm)
    P_norm_t = P_norm[0] + P_norm[1] if spin else P_norm
    low = Z - _atom_sum(mol, _lowdin(S_norm, P_norm_t))
    log.section("population analysis")
    if spin:
        dms = dm[0] - dm[1]
        P_norm_s = P_norm[0] - P_norm[1]
        smull = _atom_sum(mol, np.einsum("ij,ji->i", dms, S))
        slow = _atom_sum(mol, _lowdin(S_norm, P_norm_s))
        log("  %-10s %14s %14s %14s %14s" % ("ATOM", "MULLIKEN", "LOWDIN", "SPIN(MULL)", "SPIN(LOWD)"))
        for i in range(mol.natm):
            log("  %-10s %14.6f %14.6f %14.6f %14.6f" % (_lab(labels, i), mull[i], low[i], smull[i], slow[i]))
    else:
        log("  %-10s %14s %14s" % ("ATOM", "MULLIKEN", "LOWDIN"))
        for i in range(mol.natm):
            log("  %-10s %14.6f %14.6f" % (_lab(labels, i), mull[i], low[i]))
    log("  %-10s %14.6f %14.6f" % ("TOTAL", mull.sum(), low.sum()))
    return mull, low


def bond_orders_and_valences(log, mol, labels, dm, threshold=0.050):
    """Mayer bond orders and Coulson/Mayer atomic valences matching Firefly/GAMESS."""
    S = mol.intor_symmetric("int1e_ovlp")
    S_norm, P_norm = _normalize_ao(S, dm)
    spin = P_norm.ndim == 3

    if spin:
        Pa_S = P_norm[0] @ S_norm
        Pb_S = P_norm[1] @ S_norm
        K = 2.0 * ((Pa_S * Pa_S.T) + (Pb_S * Pb_S.T))
        Pt = P_norm[0] + P_norm[1]
        Pt_S = Pt @ S_norm
        Ps_S = (P_norm[0] - P_norm[1]) @ S_norm
    else:
        Pt = P_norm
        Pt_S = Pt @ S_norm
        K = Pt_S * Pt_S.T

    slices = mol.aoslice_by_atom()
    natm = mol.natm
    B = np.zeros((natm, natm))
    for i in range(natm):
        p0, p1 = slices[i][2], slices[i][3]
        for j in range(natm):
            q0, q1 = slices[j][2], slices[j][3]
            B[i, j] = np.sum(K[p0:p1, q0:q1])

    B = 0.5 * (B + B.T)

    v_bonded = np.zeros(natm)
    v_total = np.zeros(natm)
    v_free = np.zeros(natm)

    for i in range(natm):
        p0, p1 = slices[i][2], slices[i][3]
        v_bonded[i] = np.sum([B[i, j] for j in range(natm) if j != i])
        q_A = np.trace(Pt_S[p0:p1, p0:p1])
        X_A = np.sum(Pt_S[p0:p1, p0:p1] * Pt_S[p0:p1, p0:p1].T)
        v_total[i] = 2.0 * q_A - X_A
        if spin:
            v_free[i] = np.sum(Ps_S[p0:p1, p0:p1] * Ps_S[p0:p1, p0:p1].T)
        else:
            v_free[i] = 0.0

    log.section("bond order and valence analysis")
    log("  BOND ORDER THRESHOLD = %.3f" % threshold)
    log("  BOND PAIRS WITH ORDER GREATER THAN %.3f:" % threshold)

    pairs = []
    for i in range(natm):
        for j in range(i + 1, natm):
            if B[i, j] > threshold:
                pairs.append((i, j, B[i, j]))

    if not pairs:
        log("  (no bond pairs with order greater than threshold)")
    else:
        chunks = [pairs[k:k + 3] for k in range(0, len(pairs), 3)]
        for chunk in chunks:
            parts = []
            for i, j, b in chunk:
                parts.append("%3d( %-2s ) - %3d( %-2s ) %6.3f" % (i + 1, _sym(labels[i]), j + 1, _sym(labels[j]), b))
            log("   " + "   ".join(parts))

    log("")
    log("  %-10s %15s %15s %15s" % ("ATOM", "TOTAL VALENCE", "BONDED VALENCE", "FREE VALENCE"))
    for i in range(natm):
        log("  %-10s %15.3f %15.3f %15.3f" % (_lab(labels, i), v_total[i], v_bonded[i], v_free[i]))

    return B, v_total, v_bonded, v_free


def dipole(log, mol, dm):
    from pyscf.scf import hf
    dm = np.asarray(dm)
    dmt = dm[0] + dm[1] if dm.ndim == 3 else dm
    mu = hf.dip_moment(mol, dmt, unit="AU", verbose=0)
    mud = mu * AU_DEBYE
    log.section("dipole moment")
    log("  %14s %14s %14s %14s" % ("DX", "DY", "DZ", "|D|  (DEBYE)"))
    log("  %14.6f %14.6f %14.6f %14.6f" % (mud[0], mud[1], mud[2], np.linalg.norm(mud)))
    if mol.charge:
        log("  (charged molecule: the dipole depends on the origin, here (0,0,0))")
    return mud


def gradient(log, labels, g):
    log.section("nuclear gradient (hartree/bohr)")
    log("  %-10s %16s %16s %16s" % ("ATOM", "DE/DX", "DE/DY", "DE/DZ"))
    for i, row in enumerate(g):
        log("  %-10s %16.10f %16.10f %16.10f" % (_lab(labels, i), row[0], row[1], row[2]))
    log("  MAXIMUM GRADIENT = %14.10f    RMS GRADIENT = %14.10f"
        % (np.abs(g).max(), np.sqrt(np.mean(g ** 2))))


def excited_states(log, td, e_ground, kind):
    e = np.atleast_1d(td.e)
    try:
        f = np.atleast_1d(td.oscillator_strength(gauge="length"))
    except Exception:
        f = [float("nan")] * len(e)
    log.section("%s excited states" % kind)
    log("  %5s %16s %12s %12s %10s %20s" % ("STATE", "EXC (EH)", "EXC (EV)", "WAVEL (NM)", "F(LEN)", "TOTAL E (EH)"))
    for i, (ei, fi) in enumerate(zip(e, f)):
        ev = ei * HARTREE_EV
        log("  %5d %16.10f %12.6f %12.3f %10.6f %20.10f"
            % (i + 1, ei, ev, EV_NM / ev if ev > 0 else 0.0, fi, e_ground + ei))
    _transitions(log, td)


def _transitions(log, td, thresh=0.1):
    try:
        mo_occ = td._scf.mo_occ
        log("")
        log("  dominant excitations (|amplitude| > %.2f):" % thresh)
        for i, (x, y) in enumerate(td.xy):
            parts = []
            for spin, xs in enumerate(x if isinstance(x, tuple) else (x,)):
                occ = np.asarray(mo_occ[spin] if np.asarray(mo_occ).ndim == 2 else mo_occ)
                nocc = int((occ > 0).sum())
                xs = np.asarray(xs)
                for a, b in zip(*np.where(np.abs(xs) > thresh)):
                    tag = ("A" if spin == 0 else "B") if isinstance(x, tuple) else ""
                    parts.append("%d%s -> %d%s (%.3f)" % (a + 1, tag, nocc + b + 1, tag, xs[a, b]))
            log("    state %3d: %s" % (i + 1, ", ".join(parts) if parts else "(diffuse, no dominant term)"))
    except Exception:
        pass


def frequencies(log, freq, labels):
    """freq: dict from runners.hessian."""
    wn = freq["wavenumbers"]
    log.section("vibrational analysis")
    log("  masses: most abundant isotopes (AMU): " +
        " ".join("%s=%.5f" % (_lab(labels, i), m) for i, m in enumerate(freq["masses"])))
    log("")
    log("  %5s %14s %14s %14s %16s %16s" % ("MODE", "FREQ (CM-1)", "RED.MASS(AMU)", "FORCE(MDYN/A)",
                                           "IR (D2/AMU-A2)", "IR (KM/MOL)"))
    for k in range(len(wn)):
        w = wn[k]
        ws = "%13.4fi" % (-w) if w < 0 else "%14.4f" % w
        log("  %5d %s %14.6f %14.6f %16.6f %16.4f"
            % (k + 1, ws, freq["reduced_mass"][k], freq["force_const"][k],
               freq["ir_d2"][k], freq["ir_km"][k]))
    modes = freq["modes"]
    log("")
    log("  normal modes (cartesian displacements, mass-weighted modes normalized):")
    for c0 in range(0, len(wn), 5):
        cols = range(c0, min(c0 + 5, len(wn)))
        log("")
        log("  %-12s" % "MODE" + "".join("%14d" % (k + 1) for k in cols))
        log("  %-12s" % "FREQ" + "".join(("%13.2fi" % -wn[k]) if wn[k] < 0 else "%14.2f" % wn[k] for k in cols))
        for a in range(len(labels)):
            for x, ax in enumerate("XYZ"):
                log("  %-8s %-3s" % (_lab(labels, a), ax) + "".join("%14.8f" % modes[k][a][x] for k in cols))


def thermochem(log, th_list):
    for th in th_list:
        T, P = th["temperature"][0], th["pressure"][0]
        log.section("thermochemistry at %.2f K, %.1f Pa" % (T, P))
        log("  rotational symmetry number: %d" % th["sym_number"][0])
        log("  zero-point energy  : %16.10f EH  %14.4f KJ/MOL  %14.4f KCAL/MOL"
            % (th["ZPE"][0], th["ZPE"][0] * HARTREE_KJ, th["ZPE"][0] * HARTREE_KCAL))
        log("")
        log("  %-8s %16s %16s %16s %16s" % ("", "E (KJ/MOL)", "H (KJ/MOL)", "S (J/MOL-K)", "CV (J/MOL-K)"))
        e0 = th["E0"][0]
        for part in ("elec", "trans", "rot", "vib"):
            e = th["E_" + part][0] - (e0 if part == "elec" else 0.0)
            h = th["H_" + part][0] - (e0 if part == "elec" else 0.0)
            log("  %-8s %16.4f %16.4f %16.4f %16.4f"
                % (part.upper(), e * HARTREE_KJ, h * HARTREE_KJ,
                   th["S_" + part][0] * HARTREE_KJ * 1000, th["Cv_" + part][0] * HARTREE_KJ * 1000))
        log("")
        log("  E(electronic)              %20.10f EH" % e0)
        log("  E + ZPE                    %20.10f EH" % th["E_0K"][0])
        log("  E (internal, T)            %20.10f EH" % th["E_tot"][0])
        log("  H = E + kT                 %20.10f EH" % th["H_tot"][0])
        log("  G = H - TS                 %20.10f EH" % th["G_tot"][0])
        log("  S total                    %20.4f J/MOL-K" % (th["S_tot"][0] * HARTREE_KJ * 1000))
