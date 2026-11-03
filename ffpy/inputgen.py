"""Build a valid ffpy/Firefly input deck from plain parameters (no Qt).

Used by the MCP server so that a client does not have to remember the deck syntax; the GUI
builder writes the same layout.
"""

import re

from ffpy.job import ELEMENTS

BASES = {
    "STO-3G": ("GBASIS=STO NGAUSS=3", False),
    "3-21G": ("GBASIS=N21 NGAUSS=3", False),
    "6-31G": ("GBASIS=N31 NGAUSS=6", False),
    "6-31G*": ("GBASIS=N31 NGAUSS=6 NDFUNC=1", False),
    "6-31G**": ("GBASIS=N31 NGAUSS=6 NDFUNC=1 NPFUNC=1", False),
    "6-31+G*": ("GBASIS=N31 NGAUSS=6 NDFUNC=1 DIFFSP=.TRUE.", False),
    "6-31++G**": ("GBASIS=N31 NGAUSS=6 NDFUNC=1 NPFUNC=1 DIFFSP=.TRUE. DIFFS=.TRUE.", False),
    "6-311G**": ("GBASIS=N311 NGAUSS=6 NDFUNC=1 NPFUNC=1", False),
    "CC-PVDZ": ("GBASIS=CCD", True),
    "CC-PVTZ": ("GBASIS=CCT", True),
    "CC-PVQZ": ("GBASIS=CCQ", True),
    "AUG-CC-PVDZ": ("GBASIS=ACCD", True),
    "AUG-CC-PVTZ": ("GBASIS=ACCT", True),
    "DH(D)": ("GBASIS=DH NDFUNC=1 POLAR=DUNNING", False),
}
METHODS = ("HF", "DFT", "MP2", "CASSCF")
RUNTYPS = ("ENERGY", "GRADIENT", "OPTIMIZE", "HESSIAN")
_SYM = {s.upper(): z for z, s in enumerate(ELEMENTS) if z}


def parse_xyz(text):
    """'Sym x y z' lines (an .xyz header of two lines is skipped) -> [(symbol, Z, x, y, z)]."""
    lines = [l for l in text.splitlines() if l.strip()]
    if len(lines) >= 2 and re.fullmatch(r"\s*\d+\s*", lines[0]):
        lines = lines[2:]
    atoms = []
    for i, l in enumerate(lines, 1):
        t = l.split()
        if len(t) < 4:
            raise ValueError("geometry line %d: expected 'Symbol x y z'" % i)
        sym = re.sub(r"[^A-Za-z]", "", t[0])
        sym = sym[:1].upper() + sym[1:2].lower() if sym else sym
        if sym.upper() not in _SYM:
            if t[0].isdigit() and 0 < int(t[0]) < len(ELEMENTS):
                sym = ELEMENTS[int(t[0])]
            else:
                raise ValueError("geometry line %d: unknown element '%s'" % (i, t[0]))
        try:
            x, y, z = (float(v) for v in t[1:4])
        except ValueError:
            raise ValueError("geometry line %d: coordinates must be numbers" % i)
        atoms.append((sym, float(_SYM[sym.upper()]), x, y, z))
    if not atoms:
        raise ValueError("no atoms in the geometry")
    return atoms


def build_input(geometry, method="HF", runtyp="ENERGY", basis="6-31G*", charge=0, mult=1,
                functional="B3LYP", title="ffpy job", scftyp=None, nstep=50, hssend=False,
                excited=None, nstate=5, solvent=None, ncore=0, nact=2, nels=2):
    """Deck text. method: HF, DFT, MP2 or CASSCF; excited: None, TDDFT, TDA or CIS."""
    method, runtyp = method.upper(), runtyp.upper()
    if method not in METHODS:
        raise ValueError("method must be one of %s" % ", ".join(METHODS))
    if runtyp not in RUNTYPS:
        raise ValueError("runtyp must be one of %s" % ", ".join(RUNTYPS))
    key = basis.upper()
    if key not in BASES:
        raise ValueError("basis must be one of %s" % ", ".join(BASES))
    basis_line, spherical = BASES[key]
    atoms = parse_xyz(geometry)
    if scftyp is None:
        scftyp = "RHF" if mult == 1 else "UHF"
    contrl = ["SCFTYP=MCSCF" if method == "CASSCF" else "SCFTYP=%s" % scftyp.upper()]
    if method == "DFT":
        contrl.append("DFTTYP=%s" % functional.strip().upper())
    if method == "MP2":
        contrl.append("MPLEVL=2")
    if excited and excited.upper() == "CIS":
        contrl.append("CITYP=CIS")
    contrl += ["RUNTYP=%s" % runtyp, "ICHARG=%d MULT=%d" % (charge, mult)]
    if spherical:
        contrl.append("ISPHER=1")
    out = ["! %s, %s/%s" % (title, functional.upper() if method == "DFT" else method, basis),
           " $CONTRL %s $END" % " ".join(contrl),
           " $BASIS  %s $END" % basis_line]
    if runtyp == "OPTIMIZE":
        out.append(" $STATPT NSTEP=%d%s $END" % (nstep, " HSSEND=.TRUE." if hssend else ""))
    if excited:
        ex = excited.upper()
        if ex in ("TDDFT", "TDA"):
            out.append(" $TDDFT  NSTATE=%d%s $END" % (nstate, " TDA=.TRUE." if ex == "TDA" else ""))
        elif ex == "CIS":
            out.append(" $CIS    NSTATE=%d $END" % nstate)
        else:
            raise ValueError("excited must be TDDFT, TDA or CIS")
    if method == "CASSCF":
        out.append(" $DET    NCORE=%d NACT=%d NELS=%d $END" % (ncore, nact, nels))
    if solvent:
        out.append(" $PCM    SOLVNT=%s $END" % solvent.upper())
    out += [" $DATA", title, "C1"]
    for sym, z, x, y, zz in atoms:
        out.append("%-4s %5.1f %14.6f %14.6f %14.6f" % (sym, z, x, y, zz))
    out.append(" $END")
    return "\n".join(out) + "\n"
