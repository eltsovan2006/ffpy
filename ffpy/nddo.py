"""NDDO semiempirical methods (MNDO, AM1, PM3, RM1) for s,p elements.

Formulation of Dewar and Thiel (MNDO): one-centre integrals from the parameters, two-centre
two-electron integrals from classical multipole charge configurations in the diatomic frame,
two-centre one-electron resonance integrals  beta_mu+beta_nu)/2 * S_munu  over Slater orbitals,
core-core repulsion with the method specific exponential and Gaussian terms.  Units are eV and
Angstrom inside; the public functions return Hartree and Bohr where noted.
"""

import numpy as np

from ffpy.errors import UnsupportedError
from ffpy.nddo_params import ELEMENTS, PARAMS

EV = 27.21            # eV per Hartree used by MOPAC/Firefly
A0 = 0.529167         # Angstrom per bohr used by MOPAC/Firefly
KCAL = 23.061         # kcal/mol per eV

METHODS = ("MNDO", "AM1", "PM3", "RM1")

# valence s, p electrons of the neutral atom ground state
def _config(z):
    sym = ELEMENTS[z - 1]
    if sym in ("H", "Li", "Na", "K", "Rb"):
        return (1, 0)
    if sym in ("He",):
        return (2, 0)
    group = {"Be": 2, "Mg": 2, "Ca": 2, "Sr": 2, "Zn": 2, "Cd": 2}
    if sym in group:
        return (2, 0)
    p = {"B": 1, "Al": 1, "Ga": 1, "In": 1, "C": 2, "Si": 2, "Ge": 2, "Sn": 2, "N": 3, "P": 3,
         "As": 3, "Sb": 3, "O": 4, "S": 4, "Se": 4, "Te": 4, "F": 5, "Cl": 5, "Br": 5, "I": 5,
         "Ne": 6, "Ar": 6, "Kr": 6, "Xe": 6}
    if sym in p:
        return (2, p[sym])
    raise UnsupportedError("semiempirical methods: element %s is not supported" % sym)


def _principal(z):
    return 1 if z <= 2 else 2 if z <= 10 else 3 if z <= 18 else 4 if z <= 36 else 5


# heats of formation of the free atoms, kcal/mol (the values MOPAC uses)
EHEAT = {1: 52.102, 3: 38.410, 4: 76.960, 5: 135.700, 6: 170.890, 7: 113.000, 8: 59.559,
         9: 18.890, 11: 25.650, 12: 35.000, 13: 79.490, 14: 108.390, 15: 75.570, 16: 66.400,
         17: 28.990, 30: 31.170, 31: 66.000, 32: 89.500, 33: 72.300, 34: 54.300, 35: 26.740,
         48: 26.670, 49: 58.000, 50: 72.200, 51: 63.200, 52: 47.000, 53: 25.517, 80: 14.690}

# ----------------------------------------------------------------------------------------------
# atomic parameters


class Atom:
    """Parameters of one element for one method, including the derived multipole data."""

    def __init__(self, method, z):
        try:
            p = PARAMS[method][z]
        except KeyError:
            raise UnsupportedError("%s has no parameters for element %s" % (method, ELEMENTS[z - 1])) from None
        self.z = z
        self.method = method
        ios, iop = _config(z)
        self.ios, self.iop = ios, iop
        self.tore = ios + iop
        self.uss, self.upp = p["uss"], p.get("upp", 0.0)
        self.zs, self.zp = p["zs"], p.get("zp", 0.0)
        self.bs, self.bp = p["bs"], p.get("bp", 0.0)
        self.gss, self.gsp, self.gpp = p["gss"], p.get("gsp", 0.0), p.get("gpp", 0.0)
        self.gp2, self.hsp = p.get("gp2", 0.0), p.get("hsp", 0.0)
        self.alp = p["alp"]
        self.gauss = p.get("g", [])
        self.norb = 1 if z == 1 else 4
        self.n = _principal(z)
        # derived multipole parameters (Dewar & Thiel), atomic units
        self.dd = self.qq = 0.0
        am = self.gss / EV
        self.am = am
        if z == 1:
            self.ad = self.aq = am
        else:
            self._derive()
        self.rho0 = 0.5 / self.am
        self.rho1 = 0.5 / self.ad
        self.rho2 = 0.5 / self.aq
        # energy of the free atom, eV
        k = iop
        l = min(k, 6 - k)
        gssc = max(ios - 1, 0)
        gspc = ios * k
        gp2c = (k * (k - 1)) // 2 + 0.5 * (l * (l - 1)) / 2
        gppc = -0.5 * (l * (l - 1)) / 2
        hspc = -k * ios * 0.5
        self.eisol = (self.uss * ios + self.upp * iop + self.gss * gssc + self.gpp * gppc
                      + self.gsp * gspc + self.gp2 * gp2c + self.hsp * hspc)
        if z == 1:
            self.eisol = self.uss

    def _derive(self):
        qn = self.n
        zs, zp = self.zs, self.zp
        self.dd = (2 * qn + 1) * (4 * zs * zp) ** (qn + 0.5) / (zs + zp) ** (2 * qn + 2) / np.sqrt(3.0)
        self.qq = np.sqrt((4 * qn * qn + 6 * qn + 2) / 20.0) / zp
        hsp = max(1e-7, self.hsp)
        hpp = max(0.1, 0.5 * (self.gpp - self.gp2))
        dd, qq = self.dd, self.qq
        d1 = (hsp / (EV * dd ** 2)) ** (1.0 / 3.0)
        d2 = d1 + 0.04
        for _ in range(5):
            df = d2 - d1
            h1 = 0.5 * d1 - 0.5 / np.sqrt(4 * dd ** 2 + 1.0 / d1 ** 2)
            h2 = 0.5 * d2 - 0.5 / np.sqrt(4 * dd ** 2 + 1.0 / d2 ** 2)
            if abs(h2 - h1) < 1e-25:
                break
            d3 = d1 + df * (hsp / EV - h1) / (h2 - h1)
            d1, d2 = d2, d3
        self.ad = d2
        q1 = (16.0 * hpp / (EV * 48.0 * qq ** 4)) ** 0.2
        q2 = q1 + 0.04
        for _ in range(5):
            qf = q2 - q1
            h1 = 0.25 * q1 - 0.5 / np.sqrt(4 * qq ** 2 + 1.0 / q1 ** 2) + 0.25 / np.sqrt(8 * qq ** 2 + 1.0 / q1 ** 2)
            h2 = 0.25 * q2 - 0.5 / np.sqrt(4 * qq ** 2 + 1.0 / q2 ** 2) + 0.25 / np.sqrt(8 * qq ** 2 + 1.0 / q2 ** 2)
            if abs(h2 - h1) < 1e-25:
                break
            q3 = q1 + qf * (hpp / EV - h1) / (h2 - h1)
            q1, q2 = q2, q3
        self.aq = q2

    def one_center(self):
        """(mu nu|lambda sigma) of the atom as a 4x4x4x4 tensor, orbitals s,x,y,z (eV)."""
        n = self.norb
        w = np.zeros((n,) * 4)
        w[0, 0, 0, 0] = self.gss
        if n == 1:
            return w
        for i in (1, 2, 3):
            w[0, 0, i, i] = w[i, i, 0, 0] = self.gsp
            w[i, i, i, i] = self.gpp
            w[0, i, 0, i] = w[i, 0, 0, i] = w[0, i, i, 0] = w[i, 0, i, 0] = self.hsp
            for j in (1, 2, 3):
                if i != j:
                    w[i, i, j, j] = self.gp2
                    w[i, j, i, j] = w[i, j, j, i] = 0.5 * (self.gpp - self.gp2)
        return w


# ----------------------------------------------------------------------------------------------
# two-centre two-electron integrals in the local frame


def local_integrals(a, b, r):
    """(mu nu|lambda sigma), mu nu on atom a, lambda sigma on atom b, in the diatomic frame with
    the order (s, z, x, y); z points from b to a (the convention of MOPAC); r in bohr; eV."""
    ev = EV
    ev1, ev2, ev3, ev4 = ev / 2, ev / 4, ev / 8, ev / 16
    da, db = a.dd, b.dd
    qa, qb = 2.0 * a.qq, 2.0 * b.qq
    qa1, qb1 = a.qq, b.qq
    sq = np.sqrt
    aee = (a.rho0 + b.rho0) ** 2
    ade = (a.rho1 + b.rho0) ** 2
    aqe = (a.rho2 + b.rho0) ** 2
    aed = (a.rho0 + b.rho1) ** 2
    aeq = (a.rho0 + b.rho2) ** 2
    axx = (a.rho1 + b.rho1) ** 2
    adq = (a.rho1 + b.rho2) ** 2
    aqd = (a.rho2 + b.rho1) ** 2
    aqq = (a.rho2 + b.rho2) ** 2
    ri = np.zeros(23)
    ee = ev / sq(r ** 2 + aee)
    dze = -ev1 / sq((r + da) ** 2 + ade) + ev1 / sq((r - da) ** 2 + ade)
    e1dsqr6 = ev1 / sq(r ** 2 + aqe)
    qzze = ev2 / sq((r - qa) ** 2 + aqe) + ev2 / sq((r + qa) ** 2 + aqe) - e1dsqr6
    qxxe = ev1 / sq(r ** 2 + qa ** 2 + aqe) - e1dsqr6
    edz = -ev1 / sq((r - db) ** 2 + aed) + ev1 / sq((r + db) ** 2 + aed)
    e1dsqr12 = ev1 / sq(r ** 2 + aeq)
    eqzz = ev2 / sq((r - qb) ** 2 + aeq) + ev2 / sq((r + qb) ** 2 + aeq) - e1dsqr12
    eqxx = ev1 / sq(r ** 2 + qb ** 2 + aeq) - e1dsqr12
    e2s20 = ev2 / sq((r + da) ** 2 + adq)
    e2s22 = ev2 / sq((r - da) ** 2 + adq)
    e2s24 = ev2 / sq((r - db) ** 2 + aqd)
    e2s26 = ev2 / sq((r + db) ** 2 + aqd)
    e2s36 = ev2 / sq(r ** 2 + aqq)
    e2s39 = ev2 / sq(r ** 2 + qa ** 2 + aqq)
    e2s40 = ev2 / sq(r ** 2 + qb ** 2 + aqq)
    e3s42 = ev3 / sq((r - qb) ** 2 + aqq)
    e3s44 = ev3 / sq((r + qb) ** 2 + aqq)
    e3s46 = ev3 / sq((r + qa) ** 2 + aqq)
    e3s48 = ev3 / sq((r - qa) ** 2 + aqq)
    ri[1] = ee
    ri[2] = -dze
    ri[3] = ee + qzze
    ri[4] = ee + qxxe
    ri[5] = -edz
    ri[6] = (ev2 / sq((r + da - db) ** 2 + axx) + ev2 / sq((r - da + db) ** 2 + axx)
             - ev2 / sq((r - da - db) ** 2 + axx) - ev2 / sq((r + da + db) ** 2 + axx))
    ri[7] = ev1 / sq(r ** 2 + (da - db) ** 2 + axx) - ev1 / sq(r ** 2 + (da + db) ** 2 + axx)
    ri[8] = (-edz + ev3 / sq((r + qa - db) ** 2 + aqd) - ev3 / sq((r + qa + db) ** 2 + aqd)
             + ev3 / sq((r - qa - db) ** 2 + aqd) - ev3 / sq((r - qa + db) ** 2 + aqd) - e2s24 + e2s26)
    ri[9] = (-edz - e2s24 + ev2 / sq((r - db) ** 2 + qa ** 2 + aqd) + e2s26
             - ev2 / sq((r + db) ** 2 + qa ** 2 + aqd))
    ri[10] = (ev2 / sq((qa1 - db) ** 2 + (r + qa1) ** 2 + aqd) - ev2 / sq((qa1 - db) ** 2 + (r - qa1) ** 2 + aqd)
              - ev2 / sq((qa1 + db) ** 2 + (r + qa1) ** 2 + aqd) + ev2 / sq((qa1 + db) ** 2 + (r - qa1) ** 2 + aqd))
    ri[11] = ee + eqzz
    ri[12] = ee + eqxx
    ri[13] = (-dze + ev3 / sq((r + da - qb) ** 2 + adq) - ev3 / sq((r - da - qb) ** 2 + adq)
              + ev3 / sq((r + da + qb) ** 2 + adq) - ev3 / sq((r - da + qb) ** 2 + adq) + e2s22 - e2s20)
    ri[14] = (-dze - e2s20 + ev2 / sq((r + da) ** 2 + qb ** 2 + adq) + e2s22
              - ev2 / sq((r - da) ** 2 + qb ** 2 + adq))
    ri[15] = (ev2 / sq((da - qb1) ** 2 + (r - qb1) ** 2 + adq) - ev2 / sq((da - qb1) ** 2 + (r + qb1) ** 2 + adq)
              - ev2 / sq((da + qb1) ** 2 + (r - qb1) ** 2 + adq) + ev2 / sq((da + qb1) ** 2 + (r + qb1) ** 2 + adq))
    ri[16] = (ee + eqzz + qzze + ev4 / sq((r + qa - qb) ** 2 + aqq) + ev4 / sq((r + qa + qb) ** 2 + aqq)
              + ev4 / sq((r - qa - qb) ** 2 + aqq) + ev4 / sq((r - qa + qb) ** 2 + aqq)
              - e3s48 - e3s46 - e3s42 - e3s44 + e2s36)
    ri[17] = (ee + eqzz + qxxe + ev3 / sq((r - qb) ** 2 + qa ** 2 + aqq) + ev3 / sq((r + qb) ** 2 + qa ** 2 + aqq)
              - e3s42 - e3s44 - e2s39 + e2s36)
    ri[18] = (ee + eqxx + qzze + ev3 / sq((r + qa) ** 2 + qb ** 2 + aqq) + ev3 / sq((r - qa) ** 2 + qb ** 2 + aqq)
              - e3s46 - e3s48 - e2s40 + e2s36)
    qxxqxx = (ev3 / sq(r ** 2 + (qa - qb) ** 2 + aqq) + ev3 / sq(r ** 2 + (qa + qb) ** 2 + aqq)
              - e2s39 - e2s40 + e2s36)
    ri[19] = ee + eqxx + qxxe + qxxqxx
    ri[20] = (ev3 / sq((r + qa1 - qb1) ** 2 + (qa1 - qb1) ** 2 + aqq)
              - ev3 / sq((r + qa1 + qb1) ** 2 + (qa1 - qb1) ** 2 + aqq)
              - ev3 / sq((r - qa1 - qb1) ** 2 + (qa1 - qb1) ** 2 + aqq)
              + ev3 / sq((r - qa1 + qb1) ** 2 + (qa1 - qb1) ** 2 + aqq)
              - ev3 / sq((r + qa1 - qb1) ** 2 + (qa1 + qb1) ** 2 + aqq)
              + ev3 / sq((r + qa1 + qb1) ** 2 + (qa1 + qb1) ** 2 + aqq)
              + ev3 / sq((r - qa1 - qb1) ** 2 + (qa1 + qb1) ** 2 + aqq)
              - ev3 / sq((r - qa1 + qb1) ** 2 + (qa1 + qb1) ** 2 + aqq))
    qxxqyy = ev2 / sq(r ** 2 + qa ** 2 + qb ** 2 + aqq) - e2s39 - e2s40 + e2s36
    ri[21] = ee + eqxx + qxxe + qxxqyy
    ri[22] = 0.5 * (qxxqxx - qxxqyy)

    # orbital order s, z, x, y -> 0, 1, 2, 3
    w = np.zeros((4, 4, 4, 4))
    s, z, x, y = 0, 1, 2, 3

    def put(i, j, k, l, v):
        for p, q in ((i, j), (j, i)):
            for u, t in ((k, l), (l, k)):
                w[p, q, u, t] = v

    put(s, s, s, s, ri[1])
    put(s, z, s, s, ri[2])
    put(z, z, s, s, ri[3])
    put(x, x, s, s, ri[4])
    put(y, y, s, s, ri[4])
    put(s, s, s, z, ri[5])
    put(s, z, s, z, ri[6])
    put(s, x, s, x, ri[7])
    put(s, y, s, y, ri[7])
    put(z, z, s, z, ri[8])
    put(x, x, s, z, ri[9])
    put(y, y, s, z, ri[9])
    put(z, x, s, x, ri[10])
    put(z, y, s, y, ri[10])
    put(s, s, z, z, ri[11])
    put(s, s, x, x, ri[12])
    put(s, s, y, y, ri[12])
    put(s, z, z, z, ri[13])
    put(s, z, x, x, ri[14])
    put(s, z, y, y, ri[14])
    put(s, x, z, x, ri[15])
    put(s, y, z, y, ri[15])
    put(z, z, z, z, ri[16])
    put(x, x, z, z, ri[17])
    put(y, y, z, z, ri[17])
    put(z, z, x, x, ri[18])
    put(z, z, y, y, ri[18])
    put(x, x, x, x, ri[19])
    put(y, y, y, y, ri[19])
    put(z, x, z, x, ri[20])
    put(z, y, z, y, ri[20])
    put(x, x, y, y, ri[21])
    put(y, y, x, x, ri[21])
    put(x, y, x, y, ri[22])
    return w, ri


def frame(u):
    """Rows: local axes (z along u, x and y perpendicular), as a 3x3 matrix."""
    u = u / np.linalg.norm(u)
    t = np.array([1.0, 0, 0]) if abs(u[0]) < 0.9 else np.array([0, 1.0, 0])
    x = t - u * (t @ u)
    x /= np.linalg.norm(x)
    y = np.cross(u, x)
    return np.array([x, y, u])


def orbital_rotation(u):
    """4x4 matrix R with local orbital a = sum_i R[a,i] molecular orbital i, local order (s,z,x,y),
    molecular order (s,x,y,z)."""
    f = frame(u)                      # rows x', y', z'
    r = np.zeros((4, 4))
    r[0, 0] = 1.0
    r[1, 1:] = f[2]
    r[2, 1:] = f[0]
    r[3, 1:] = f[1]
    return r


# ----------------------------------------------------------------------------------------------
# overlap of Slater orbitals


_GL = np.polynomial.laguerre.laggauss(40)
_GP = np.polynomial.legendre.leggauss(48)


def _norm(n, zeta):
    from math import factorial, sqrt
    return (2 * zeta) ** (n + 0.5) / sqrt(factorial(2 * n))


def sto_overlap(na, za, la, nb, zb, lb, r):
    """Overlap of two STOs in the frame with a at the origin and b at +r on z (bohr).
    la, lb: 0 = s, 1 = p sigma (p_z), 2 = p pi (p_x with p_x).  Returns the value."""
    alpha = 0.5 * r * (za + zb)
    beta = 0.5 * r * (za - zb)
    t, wt = _GL
    e, we = _GP
    xi = 1.0 + t / alpha
    XI, ETA = np.meshgrid(xi, e, indexing="ij")
    ra = 0.5 * r * (XI + ETA)
    rb = 0.5 * r * (XI - ETA)
    za_ = 0.5 * r * (1 + XI * ETA)            # z relative to a
    zb_ = 0.5 * r * (XI * ETA - 1)            # z relative to b
    rho2 = 0.25 * r * r * (XI ** 2 - 1) * (1 - ETA ** 2)
    cs, cp = 1 / np.sqrt(4 * np.pi), np.sqrt(3 / (4 * np.pi))

    def orb(n, l, rad, zz):
        if l == 0:
            return cs * rad ** (n - 1)
        if l == 1:
            return cp * rad ** (n - 2) * zz
        return cp * rad ** (n - 2) * np.sqrt(rho2)

    fa = orb(na, 0 if la == 0 else 1, ra, za_) if la != 2 else orb(na, 2, ra, za_)
    fb = orb(nb, 0 if lb == 0 else 1, rb, zb_) if lb != 2 else orb(nb, 2, rb, zb_)
    phi = np.pi if (la == 2 and lb == 2) else 2 * np.pi
    jac = (0.5 * r) ** 3 * (XI ** 2 - ETA ** 2)
    g = fa * fb * jac * np.exp(-beta * ETA) * phi
    val = np.einsum("i,j,ij->", wt, we, g) * np.exp(-alpha) / alpha
    return val * _norm(na, za) * _norm(nb, zb)


def overlap_block(a, b, r):
    """4x4 (or smaller) overlap block, molecular orbital order (s,x,y,z) of a vs b, for b along +z
    from a; returns the block in the diatomic frame ordered (s, z, x, y)."""
    sa = a.zs
    sb = b.zs
    s = np.zeros((a.norb, b.norb))
    s[0, 0] = sto_overlap(a.n, sa, 0, b.n, sb, 0, r)
    if b.norb == 4:
        s[0, 1] = sto_overlap(a.n, sa, 0, b.n, b.zp, 1, r)
    if a.norb == 4:
        s[1, 0] = sto_overlap(a.n, a.zp, 1, b.n, sb, 0, r)
    if a.norb == 4 and b.norb == 4:
        s[1, 1] = sto_overlap(a.n, a.zp, 1, b.n, b.zp, 1, r)
        pi = sto_overlap(a.n, a.zp, 2, b.n, b.zp, 2, r)
        s[2, 2] = s[3, 3] = pi
    return s


# ----------------------------------------------------------------------------------------------
# molecule


class NDDO:
    """Closed-shell or unrestricted NDDO calculation for fixed geometry."""

    def __init__(self, method, numbers, xyz_bohr, charge=0, mult=1):
        method = method.upper()
        if method not in METHODS:
            raise UnsupportedError("unknown semiempirical method %s" % method)
        self.method = method
        self.z = list(numbers)
        self.atoms = [Atom(method, z) for z in self.z]
        self.xyz = np.array(xyz_bohr, float)
        self.charge, self.mult = charge, mult
        self.nel = sum(a.tore for a in self.atoms) - charge
        if (self.nel - (mult - 1)) % 2:
            raise UnsupportedError("charge %d and multiplicity %d do not match %d valence electrons"
                                   % (charge, mult, self.nel))
        self.off = np.cumsum([0] + [a.norb for a in self.atoms])
        self.nbf = int(self.off[-1])

    # --- integrals ---------------------------------------------------------------------------
    def build(self):
        n = len(self.atoms)
        H = np.zeros((self.nbf, self.nbf))
        self.w1 = [a.one_center() for a in self.atoms]
        self.w2 = {}
        enuc = 0.0
        for i, a in enumerate(self.atoms):
            sl = slice(self.off[i], self.off[i + 1])
            H[sl, sl] += np.diag([a.uss] + [a.upp] * (a.norb - 1))
        for i in range(n):
            for j in range(i):
                a, b = self.atoms[i], self.atoms[j]
                vec = self.xyz[i] - self.xyz[j]
                r = np.linalg.norm(vec)
                u = vec / r
                wl, ri = local_integrals(a, b, r)
                if a.norb == 1 and b.norb == 1:
                    pass
                R = orbital_rotation(u)
                # restrict to the actual orbitals
                ra = R[:, :]
                wm = np.einsum("ai,bj,ck,dl,abcd->ijkl", R, R, R, R, wl, optimize=True)
                na, nb = a.norb, b.norb
                wm = wm[:na, :na, :nb, :nb]
                self.w2[(i, j)] = wm
                # electron on i attracts core j, and the reverse
                vi = -b.tore * wm[:, :, 0, 0]
                vj = -a.tore * wm[0, 0, :, :]
                si, sj = slice(self.off[i], self.off[i + 1]), slice(self.off[j], self.off[j + 1])
                H[si, si] += vi
                H[sj, sj] += vj
                # resonance integrals: overlap with b along +z' = direction j <- i seen from i
                Rs = orbital_rotation(-u)       # local z from i towards j
                sl = overlap_block(a, b, r)
                # local order (s,z,x,y) -> molecular via rotation of each atom's p functions
                S = np.zeros((na, nb))
                Ra = Rs[:na, :na] if na == 4 else Rs[:1, :1]
                Rb = Rs[:nb, :nb] if nb == 4 else Rs[:1, :1]
                S = Ra.T @ sl @ Rb
                bi = np.array([a.bs] + [a.bp] * (na - 1))
                bj = np.array([b.bs] + [b.bp] * (nb - 1))
                Hij = 0.5 * (bi[:, None] + bj[None, :]) * S
                H[si, sj] += Hij
                H[sj, si] += Hij.T
                enuc += self._core_core(a, b, r, ri[1])
        self.H = H
        self.enuc = enuc
        self.eisol = sum(a.eisol for a in self.atoms)
        self.eheat = sum(EHEAT.get(z, 0.0) for z in self.z)
        return self

    def _core_core(self, a, b, r_bohr, gab):
        r = r_bohr * A0
        enuc = a.tore * b.tore * gab
        scale = np.exp(-a.alp * r) + np.exp(-b.alp * r)
        if a.z + b.z in (8, 9):
            if a.z in (7, 8):
                scale += (r - 1.0) * np.exp(-a.alp * r)
            if b.z in (7, 8):
                scale += (r - 1.0) * np.exp(-b.alp * r)
        e = abs(scale * enuc) + enuc
        g = 0.0
        for at in (a, b):
            for ga, gb, gc in at.gauss:
                ax = gb * (r - gc) ** 2
                if ax <= 25.0:
                    g += a.tore * b.tore / r * ga * np.exp(-ax)
        return e + g

    # --- Fock matrix ----------------------------------------------------------------------------
    def fock(self, Pa, Pb):
        """Fock matrices (alpha, beta) from alpha and beta densities."""
        P = Pa + Pb
        Fa = self.H.copy()
        Fb = self.H.copy()
        n = len(self.atoms)
        off = self.off
        for i in range(n):
            si = slice(off[i], off[i + 1])
            w = self.w1[i]
            Pii, Paii, Pbii = P[si, si], Pa[si, si], Pb[si, si]
            J = np.einsum("mnls,ls->mn", w, Pii)
            Ka = np.einsum("mlns,ls->mn", w, Paii)
            Kb = np.einsum("mlns,ls->mn", w, Pbii)
            Fa[si, si] += J - Ka
            Fb[si, si] += J - Kb
        for (i, j), wm in self.w2.items():
            si, sj = slice(off[i], off[i + 1]), slice(off[j], off[j + 1])
            Jij = np.einsum("mnls,ls->mn", wm, P[sj, sj])
            Jji = np.einsum("mnls,mn->ls", wm, P[si, si])
            Fa[si, si] += Jij
            Fb[si, si] += Jij
            Fa[sj, sj] += Jji
            Fb[sj, sj] += Jji
            # exchange: F[mu in i, lam in j] -= sum_{nu in i, sig in j} P[nu,sig] (mu nu|lam sig)
            Ka = np.einsum("mnls,ns->ml", wm, Pa[si, sj])
            Kb = np.einsum("mnls,ns->ml", wm, Pb[si, sj])
            Fa[si, sj] -= Ka
            Fb[si, sj] -= Kb
            Fa[sj, si] -= Ka.T
            Fb[sj, si] -= Kb.T
        return Fa, Fb

    # --- SCF ------------------------------------------------------------------------------------
    def scf(self, conv=1e-10, maxit=200, guess=None):
        """RHF (mult 1) or UHF.  Returns energy in eV (electronic + core-core)."""
        self.build()
        nb_ = (self.nel - (self.mult - 1)) // 2
        na_ = self.nel - nb_
        closed = self.mult == 1
        H = self.H
        if guess is None:
            # core-Hamiltonian guess; the diagonal guess is tried too and the lower solution kept
            best = None
            for kind in ("core", "diag"):
                if kind == "core":
                    _, c0 = np.linalg.eigh(H)
                    Pa0 = c0[:, :na_] @ c0[:, :na_].T
                    Pb0 = c0[:, :nb_] @ c0[:, :nb_].T
                else:
                    d = np.concatenate([np.full(a.norb, a.tore / a.norb) for a in self.atoms])
                    Pa0 = Pb0 = np.diag(d) / 2
                try:
                    e = self._scf_loop(Pa0, Pb0, na_, nb_, closed, conv, maxit)
                except np.linalg.LinAlgError:
                    continue
                if best is None or e < best[0] - 1e-9:
                    best = (e, dict(self.__dict__))
            if best is None:
                raise np.linalg.LinAlgError("semiempirical SCF failed")
            self.__dict__.update(best[1])
            return self.etot_ev
        e = self._scf_loop(guess[0], guess[1], na_, nb_, closed, conv, maxit)
        return e

    def _scf_loop(self, Pa, Pb, na_, nb_, closed, conv, maxit):
        H = self.H
        diis_f, diis_e = [], []
        e_old = 0.0
        for it in range(maxit):
            Fa, Fb = self.fock(Pa, Pb)
            e = 0.5 * (np.einsum("mn,mn", Pa + Pb, H) + np.einsum("mn,mn", Pa, Fa) + np.einsum("mn,mn", Pb, Fb))
            # DIIS on the commutators
            Fa_d, Fb_d = Fa, Fb
            err = np.concatenate([(Fa @ Pa - Pa @ Fa).ravel(), (Fb @ Pb - Pb @ Fb).ravel()])
            diis_f.append((Fa.copy(), Fb.copy()))
            diis_e.append(err)
            if len(diis_f) > 8:
                diis_f.pop(0)
                diis_e.pop(0)
            if len(diis_f) > 2:
                m = len(diis_f)
                B = -np.ones((m + 1, m + 1))
                B[m, m] = 0
                for p in range(m):
                    for q in range(m):
                        B[p, q] = diis_e[p] @ diis_e[q]
                rhs = np.zeros(m + 1)
                rhs[m] = -1
                try:
                    c = np.linalg.solve(B, rhs)[:m]
                    Fa_d = sum(ci * f[0] for ci, f in zip(c, diis_f))
                    Fb_d = sum(ci * f[1] for ci, f in zip(c, diis_f))
                except np.linalg.LinAlgError:
                    pass
            ea, Ca = np.linalg.eigh(Fa_d)
            eb, Cb = (ea, Ca) if closed else np.linalg.eigh(Fb_d)
            Pa_new = Ca[:, :na_] @ Ca[:, :na_].T
            Pb_new = Pa_new if closed else Cb[:, :nb_] @ Cb[:, :nb_].T
            delta = np.abs(Pa_new - Pa).max() + np.abs(Pb_new - Pb).max()
            Pa, Pb = Pa_new, Pb_new
            if abs(e - e_old) < conv and delta < 1e-8 and it > 1:
                break
            e_old = e
        else:
            self.converged = False
        self.converged = it < maxit - 1
        Fa, Fb = self.fock(Pa, Pb)
        e = 0.5 * (np.einsum("mn,mn", Pa + Pb, H) + np.einsum("mn,mn", Pa, Fa) + np.einsum("mn,mn", Pb, Fb))
        ea, Ca = np.linalg.eigh(Fa)
        eb, Cb = (ea, Ca) if closed else np.linalg.eigh(Fb)
        self.Pa, self.Pb = Pa, Pb
        self.eps_a, self.C_a, self.eps_b, self.C_b = ea, Ca, eb, Cb
        self.na, self.nb = na_, nb_
        self.eel = e
        self.etot_ev = e + self.enuc
        return self.etot_ev

    # --- derived quantities ---------------------------------------------------------------------
    @property
    def heat_kcal(self):
        return (self.etot_ev - self.eisol) * KCAL + self.eheat

    @property
    def energy_hartree(self):
        """Total energy in Hartree relative to the 'free valence electrons' reference (MOPAC E_tot)."""
        return self.etot_ev / EV

    def charges(self):
        """Mulliken-like (Coulson, orthogonal basis) net atomic charges."""
        P = self.Pa + self.Pb
        q = []
        for i, a in enumerate(self.atoms):
            q.append(a.tore - np.trace(P[self.off[i]:self.off[i + 1], self.off[i]:self.off[i + 1]]))
        return np.array(q)
