"""$BASIS (GBASIS/NGAUSS/NDFUNC/...) -> PySCF basis name."""

from ffpy.errors import InputError, UnsupportedError

POPLE = {"STO", "N21", "N31", "N311"}
NAMED = {
    "CCD": "cc-pvdz", "CCT": "cc-pvtz", "CCQ": "cc-pvqz", "CC5": "cc-pv5z",
    "ACCD": "aug-cc-pvdz", "ACCT": "aug-cc-pvtz", "ACCQ": "aug-cc-pvqz",
    "PCSEG0": "pcseg-0", "PCSEG1": "pcseg-1", "PCSEG2": "pcseg-2",
    "DEF2SVP": "def2-svp", "DEF2TZVP": "def2-tzvp",
}
VALID_NGAUSS = {"STO": (2, 3, 4, 5, 6), "N21": (3, 6), "N31": (4, 5, 6), "N311": (6,)}


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
    return "%s%sg%s" % (base, plus, pol)
