"""$BASIS (GBASIS/NGAUSS/NDFUNC/...) -> PySCF basis name."""

import copy
from typing import Any, Optional, Set

from ffpy.errors import InputError, UnsupportedError

POPLE = {"STO", "N21", "N31", "N311"}
NAMED = {
    "CCD": "cc-pvdz", "CCT": "cc-pvtz", "CCQ": "cc-pvqz", "CC5": "cc-pv5z",
    "ACCD": "aug-cc-pvdz", "ACCT": "aug-cc-pvtz", "ACCQ": "aug-cc-pvqz",
    "PCSEG0": "pcseg-0", "PCSEG1": "pcseg-1", "PCSEG2": "pcseg-2",
    "SBKJC": "sbkjc", "DEF2SVP": "def2-svp", "DEF2TZVP": "def2-tzvp",
}
VALID_NGAUSS = {"STO": (2, 3, 4, 5, 6), "N21": (3, 6), "N31": (4, 5, 6), "N311": (6,)}

# Fully optimized 6-31G sp basis set for Silicon (Si).
# Ref: M. S. Gordon, Chem. Phys. Lett. 76, 163-168 (1980).
# Exponents and contraction coefficients as used in GAMESS/Firefly.
GORDON_SI_631G_SP = [
    [0,  # 1s
        [16192.1, 0.001949],
        [2436.09, 0.014856],
        [556.001, 0.072569],
        [156.813, 0.245655],
        [50.1692, 0.486060],
        [17.0300, 0.325720],
    ],
    [0,  # 2s
        [293.350, -0.002830],
        [70.1173, -0.036074],
        [22.4301, -0.116808],
        [8.19425,  0.093577],
        [3.14768,  0.601705],
        [1.21515,  0.422072],
    ],
    [1,  # 2p
        [293.350,  0.004433],
        [70.1173,  0.032440],
        [22.4301,  0.133719],
        [8.19425,  0.326780],
        [3.14768,  0.451139],
        [1.21515,  0.264105],
    ],
    [0,  # 3s (inner)
        [1.653700, -0.240600],
        [0.540760,  0.073795],
        [0.204406,  1.040940],
    ],
    [1,  # 3p (inner)
        [1.653700, -0.015177],
        [0.540760,  0.275139],
        [0.204406,  0.783008],
    ],
    [0,  # 3s (outer)
        [0.072384, 1.000000],
    ],
    [1,  # 3p (outer)
        [0.072384, 1.000000],
    ],
]

# Polarization d exponent for Silicon in GAMESS/Firefly: zeta = 0.395
# (Ref: M. S. Gordon, Chem. Phys. Lett. 76, 163 (1980); Firefly manual POLAR=POPLE table)
GORDON_SI_D_EXP = 0.395


class BasisDict(dict):
    """Dictionary mapping element symbols to PySCF basis sets, with a canonical name."""

    def __init__(self, mapping: dict, name: str):
        super().__init__(mapping)
        self.name = name

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return self.name

    def upper(self) -> str:
        return self.name.upper()

    def lower(self) -> str:
        return self.name.lower()

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, str):
            return self.name == other or self.name.upper() == other.upper()
        return super().__eq__(other)

    def __hash__(self) -> int:
        return hash(self.name)


# d polarization exponents that Firefly adds for GBASIS=N21 NGAUSS=3 NDFUNC=1 on heavy atoms
# which PySCF's 3-21G* lacks (read from a Firefly run; only elements actually seen are listed)
# STO-2G, H-Ne: published tables (Hehre, Stewart, Pople 1969; as distributed by the Basis Set Exchange).
# PySCF does not ship STO-2G.
STO2G = {
    "H": [[0, [1.309756377, 0.4301284983], [0.2331359749, 0.6789135305]]],
    "He": [[0, [2.432879285, 0.4301284983], [0.4330512863, 0.6789135305]]],
    "Li": [[0, [6.163845031, 0.4301284983], [1.097161308, 0.6789135305]], [0, [0.245916322, 0.0494717692], [0.06237087296, 0.9637824081]], [1, [0.245916322, 0.5115407076], [0.06237087296, 0.6128198961]]],
    "Be": [[0, [11.53566907, 0.4301284983], [2.053343279, 0.6789135305]], [0, [0.5081630247, 0.0494717692], [0.1288835617, 0.9637824081]], [1, [0.5081630247, 0.5115407076], [0.1288835617, 0.6128198961]]],
    "B": [[0, [18.6568731, 0.4301284983], [3.320914006, 0.6789135305]], [0, [0.8645495695, 0.0494717692], [0.2192726003, 0.9637824081]], [1, [0.8645495695, 0.5115407076], [0.2192726003, 0.6128198961]]],
    "C": [[0, [27.38503303, 0.4301284983], [4.874522075, 0.6789135305]], [0, [1.136748198, 0.0494717692], [0.2883093603, 0.9637824081]], [1, [1.136748198, 0.5115407076], [0.2883093603, 0.6128198961]]],
    "N": [[0, [37.89647534, 0.4301284983], [6.745553507, 0.6789135305]], [0, [1.461088772, 0.0494717692], [0.3705706944, 0.9637824081]], [1, [1.461088772, 0.5115407076], [0.3705706944, 0.6128198961]]],
    "O": [[0, [49.98097117, 0.4301284983], [8.896587673, 0.6789135305]], [0, [1.945236531, 0.0494717692], [0.4933633506, 0.9637824081]], [1, [1.945236531, 0.5115407076], [0.4933633506, 0.6128198961]]],
    "F": [[0, [63.73520195, 0.4301284983], [11.34483382, 0.6789135305]], [0, [2.498548256, 0.0494717692], [0.6336978147, 0.9637824081]], [1, [2.498548256, 0.5115407076], [0.6336978147, 0.6128198961]]],
    "Ne": [[0, [79.15916767, 0.4301284983], [14.09029194, 0.6789135305]], [0, [3.187075533, 0.0494717692], [0.8083265136, 0.9637824081]], [1, [3.187075533, 0.5115407076], [0.8083265136, 0.6128198961]]],
}


def sto2g_shells(element):
    """STO-2G shells in PySCF format (H-Ne)."""
    if element not in STO2G:
        raise UnsupportedError("basis STO-2G is available for H-Ne only, not %s" % element)
    return copy.deepcopy(STO2G[element])


GAMESS_321G_D = {"Sb": 0.211}


def make_element_basis(canonical_name: str, elements: Set[str], gbasis: str,
                       ngauss: Optional[int], ndfunc: int = 0) -> Any:
    """Return PySCF basis specification (str or BasisDict) considering GAMESS/Firefly defaults.

    For Silicon with 6-31G (GBASIS=N31, NGAUSS=6), GAMESS/Firefly uses Mark Gordon's
    fully optimized sp basis set (1980) and d-polarization exponent 0.395, unlike Pople's
    re-used 6-21G core and d-exponent 0.45 used in Gaussian/PySCF.
    """
    g = gbasis.upper()
    if g in ("DH", "DZV"):
        from ffpy import dh_basis
        mapping = {"default": canonical_name}
        for el in elements:
            if el not in dh_basis.DZ:
                raise UnsupportedError("GBASIS=%s is not available for %s" % (g, el))
            sh = dh_basis.shells(el)
            if "d" in canonical_name[2:] and el in dh_basis.D_EXP:
                sh.append([2, [dh_basis.D_EXP[el], 1.0]])
            if "p" in canonical_name[2:] and el == "H":
                sh.append([1, [dh_basis.P_EXP["H"], 1.0]])
            mapping[el] = sh
        return BasisDict(mapping, canonical_name)
    if "Si" in elements and g == "N31" and ngauss == 6:
        si_shells = copy.deepcopy(GORDON_SI_631G_SP)
        if ndfunc == 1:
            si_shells.append([2, [GORDON_SI_D_EXP, 1.0]])
        mapping = {"default": canonical_name, "Si": si_shells}
        for el in elements:
            if el != "Si":
                mapping[el] = canonical_name
        return BasisDict(mapping, canonical_name)
    if canonical_name == "sto-2g":
        mapping = {"default": canonical_name}
        for el in elements:
            mapping[el] = sto2g_shells(el)
        return BasisDict(mapping, canonical_name)
    if g == "N21" and ngauss == 3 and ndfunc == 1:
        extra = {el: exp for el, exp in GAMESS_321G_D.items() if el in elements}
        if extra:
            from pyscf import gto
            mapping = {"default": canonical_name}
            for el in elements:
                mapping[el] = canonical_name
            for el, exp in extra.items():
                mapping[el] = gto.basis.load("3-21g", el) + [[2, [exp, 1.0]]]
            return BasisDict(mapping, canonical_name)
    return canonical_name


def _mult(n, letter):
    return "" if n == 0 else (letter if n == 1 else "%d%s" % (n, letter))


def basis_name(gbasis, ngauss=None, ndfunc=0, npfunc=0, nffunc=0,
               diffsp=False, diffs=False):
    g = gbasis.upper()
    if g in NAMED:
        if ndfunc or npfunc or nffunc or diffsp or diffs:
            raise InputError("NDFUNC/NPFUNC/NFFUNC/DIFFSP/DIFFS cannot be combined "
                             "with GBASIS=%s" % g)
        return NAMED[g]
    if g in ("DH", "DZV"):
        if nffunc or diffsp or diffs or ndfunc > 1 or npfunc > 1:
            raise UnsupportedError("GBASIS=%s supports only NDFUNC<=1, NPFUNC<=1 without f/diffuse functions" % g)
        return "dh%s%s" % ("d" if ndfunc else "", "p" if npfunc else "")
    if g not in POPLE:
        raise UnsupportedError(
            "GBASIS=%s is not supported. Supported: %s"
            % (g, ", ".join(sorted(POPLE | set(NAMED)))))
    if ngauss is None:
        raise InputError("GBASIS=%s requires NGAUSS" % g)
    if ngauss not in VALID_NGAUSS[g]:
        raise InputError("NGAUSS=%d is not valid for GBASIS=%s (allowed: %s)"
                         % (ngauss, g, VALID_NGAUSS[g]))
    if g == "STO":
        if ndfunc or npfunc or nffunc or diffsp or diffs:
            raise InputError("polarization/diffuse functions are not defined for STO-NG")
        return "sto-%dg" % ngauss
    base = {"N21": "%d-21", "N31": "%d-31", "N311": "%d-311"}[g] % ngauss
    if diffs and not diffsp:
        raise InputError("DIFFS=.TRUE. (diffuse s on H) requires DIFFSP=.TRUE.")
    plus = "++" if diffs else ("+" if diffsp else "")
    heavy = _mult(ndfunc, "d") + _mult(nffunc, "f")
    light = _mult(npfunc, "p")
    if light and not heavy:
        raise UnsupportedError("NPFUNC without NDFUNC (6-31G(,p)-type basis) is not supported")
    pol = ""
    if heavy:
        pol = "(%s,%s)" % (heavy, light) if light else "(%s)" % heavy
    name = "%s%sg%s" % (base, plus, pol)
    # PySCF ships 3-21G* only under its file name
    return {"3-21g(d)": "3-21gs", "3-21++g(d)": "3-21++gs"}.get(name, name)
