"""Job: everything the dispatcher needs, built from a parsed Deck.

This is the last layer that knows about the input format; the runners
below only see a Job and PySCF objects.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

from ffpy import symmetry
from ffpy.basis_map import basis_name
from ffpy.constants import ANG_BOHR
from ffpy.errors import InputError, UnsupportedError
from ffpy.schema import SOLVENTS
from ffpy.xc_map import xc_for

ELEMENTS = [
    "X", "H", "He", "Li", "Be", "B", "C", "N", "O", "F", "Ne", "Na", "Mg", "Al", "Si", "P",
    "S", "Cl", "Ar", "K", "Ca", "Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn",
    "Ga", "Ge", "As", "Se", "Br", "Kr", "Rb", "Sr", "Y", "Zr", "Nb", "Mo", "Tc", "Ru", "Rh",
    "Pd", "Ag", "Cd", "In", "Sn", "Sb", "Te", "I", "Xe"]


@dataclass
class Job:
    title: str
    point_group: str
    labels: List[str]
    charges: List[int]            # nuclear charges
    coords: np.ndarray            # Bohr, (natm, 3)
    charge: int
    mult: int
    scftyp: str
    runtyp: str
    dfttyp: Optional[str]
    xc: Optional[str]
    mplevl: int
    basis: str
    cart: bool
    guess: str
    vec: Optional[Tuple[np.ndarray, Optional[np.ndarray]]]
    maxit: int
    nconv_density: float
    direct: bool
    diis: bool
    soscf: bool
    damp: bool
    shift: bool
    memory_mb: Optional[float]
    timlim_s: float
    grid: Optional[Tuple[int, int]]
    mp2_frozen: Optional[int]
    excited: Optional[dict]       # {"kind": TDDFT|TDHF|CIS, nstate, iroot, triplet, tda}
    cas: Optional[dict]
    pcm: Optional[dict]
    nstep: int
    opttol: float
    hssend: bool
    temps: List[float]
    exetyp: str
    projct: bool = True
    defaults: List[str] = field(default_factory=list)
    nsym_ops: int = 1

    @property
    def symbols(self):
        return [ELEMENTS[z] for z in self.charges]

    @property
    def method(self):
        """Key used by the dispatcher."""
        if self.scftyp == "MCSCF":
            return "CASSCF"
        if self.mplevl == 2:
            return "MP2"
        if self.excited:
            return "TDDFT" if self.xc else "TDHF"
        return "DFT" if self.xc else "HF"

    def describe(self):
        ref = self.scftyp
        if self.xc:
            ref = {"RHF": "RKS", "UHF": "UKS", "ROHF": "ROKS"}[self.scftyp] + "/" + self.dfttyp
        if self.method == "MP2":
            ref = "MP2 (" + ref + " reference)"
        if self.excited:
            ref = "%s on %s" % (self.excited["kind"], ref)
        if self.cas:
            ref = "CASSCF(%d,%d)" % (self.cas["nels"], self.cas["nact"])
        return "%s/%s" % (ref, self.basis.upper())


def _parse_data(lines, units):
    body = [l for l in lines]
    while body and not body[0].strip():
        body.pop(0)
    if len(body) < 2:
        raise InputError("$DATA: expected a title line, a point group line and atoms")
    title = body[0].strip()
    grp_tokens = body[1].split()
    if not grp_tokens:
        raise InputError("$DATA line 2: point group is missing")
    group = grp_tokens[0].upper()
    order = None
    if len(grp_tokens) > 1:
        try:
            order = int(grp_tokens[1])
        except ValueError:
            raise InputError("$DATA line 2: bad axis order '%s'" % grp_tokens[1])
    rest = body[2:]
    if group != "C1" and rest and not rest[0].strip():
        rest = rest[1:]     # the blank line after a non-C1 group
    unique = []
    scale = ANG_BOHR if units == "ANGS" else 1.0
    for i, line in enumerate(rest):
        if not line.strip():
            if any(l.strip() for l in rest[i + 1:]):
                raise UnsupportedError(
                    "$DATA: blank line between atoms. Basis sets written inside $DATA are "
                    "not supported; use the $BASIS group")
            break
        tok = line.split()
        if len(tok) < 5:
            raise InputError("$DATA: atom line must be 'name Z x y z': %s" % line.strip())
        if len(tok) > 5:
            raise UnsupportedError("$DATA: extra fields on atom line are not supported: %s"
                                   % line.strip())
        try:
            z = float(tok[1].upper().replace("D", "E"))
            xyz = [float(t.upper().replace("D", "E")) * scale for t in tok[2:5]]
        except ValueError:
            raise InputError("$DATA: cannot read numbers in: %s" % line.strip())
        if abs(z - round(z)) > 1e-6 or not (1 <= round(z) < len(ELEMENTS)):
            raise UnsupportedError("$DATA: nuclear charge %s of atom %s is not supported "
                                   "(dummy/ghost atoms and Z>54 are not supported)" % (tok[1], tok[0]))
        unique.append((tok[0], int(round(z)), xyz))
    if not unique:
        raise InputError("$DATA: no atoms found")
    atoms, nops = symmetry.expand(unique, group, order)
    grp_name = group if order is None else "%s %d" % (group, order)
    return title, grp_name, atoms, nops


def _parse_vec(lines, norb):
    """$VEC as written by ffpy (.dat): I2,I3 then 5E15.8 per line, PySCF AO order."""
    rows = []
    for line in lines:
        if not line.strip():
            continue
        try:
            iorb = int(line[0:2])
            body = line[5:].rstrip()
            vals = [float(body[i:i + 15].replace("D", "E")) for i in range(0, len(body), 15)]
        except ValueError:
            raise InputError("$VEC: cannot read line: %s" % line.rstrip())
        rows.append((iorb, vals))
    # consecutive rows with the same label belong to one orbital (labels wrap at 100)
    orbs = []
    last = None
    for iorb, vals in rows:
        if iorb != last:
            orbs.append([])
            last = iorb
        orbs[-1].extend(vals)
    if not orbs:
        raise InputError("$VEC group is empty")
    nao = len(orbs[0])
    if any(len(o) != nao for o in orbs):
        raise InputError("$VEC: orbitals have different lengths")
    if norb is None:
        norb = len(orbs) if len(orbs) <= nao else nao
    C = np.array(orbs, float).T
    if C.shape[1] == norb:
        return C, None
    if C.shape[1] == 2 * norb:
        return C[:, :norb], C[:, norb:]
    raise InputError("$VEC: found %d orbitals, NORB=%d" % (C.shape[1], norb))


def build_job(deck):
    g = deck.get
    contrl = {k: g("CONTRL", k) for k in ("SCFTYP", "RUNTYP", "ICHARG", "MULT", "UNITS",
                                         "MAXIT", "ISPHER", "EXETYP")}
    dfttyp = g("CONTRL", "DFTTYP", report_default=False)
    mplevl = g("CONTRL", "MPLEVL", report_default=False)
    cityp = g("CONTRL", "CITYP", report_default=False)
    tddft = g("CONTRL", "TDDFT", report_default=False)
    if deck.explicit("CONTRL", "COORD"):
        g("CONTRL", "COORD")
    scftyp, runtyp = contrl["SCFTYP"], contrl["RUNTYP"]
    xc = None if dfttyp == "NONE" else xc_for(dfttyp)

    title, pgroup, atoms, nops = _parse_data(deck.groups["DATA"].lines, contrl["UNITS"])

    if not deck.has("BASIS") or not deck.explicit("BASIS", "GBASIS"):
        raise InputError("$BASIS GBASIS=... is required (basis sets inside $DATA are not supported)")
    b = deck.groups["BASIS"].keys
    basis = basis_name(b["GBASIS"], b.get("NGAUSS"), b.get("NDFUNC", 0), b.get("NPFUNC", 0),
                       b.get("NFFUNC", 0), b.get("DIFFSP", False), b.get("DIFFS", False))

    mult, charge = contrl["MULT"], contrl["ICHARG"]
    nelec = sum(z for _, z, _ in atoms) - charge
    if mult < 1:
        raise InputError("$CONTRL MULT must be >= 1")
    if (nelec + mult - 1) % 2 != 0 or mult - 1 > nelec:
        raise InputError("MULT=%d is impossible with %d electrons (ICHARG=%d)"
                         % (mult, nelec, charge))
    if scftyp == "RHF" and mult != 1:
        raise InputError("SCFTYP=RHF requires MULT=1; use UHF or ROHF for open shells")

    guess = g("GUESS", "GUESS")
    vec = None
    if guess == "MOREAD":
        if "VEC" not in deck.groups:
            raise InputError("GUESS=MOREAD requires a $VEC group")
        vec = _parse_vec(deck.groups["VEC"].lines, g("GUESS", "NORB", report_default=False))
    elif "VEC" in deck.groups:
        deck.notes.append(("warning", "$VEC is present but GUESS is not MOREAD; it is ignored"))

    conv = g("SCF", "CONV", report_default=False)
    nconv = 10.0 ** -g("SCF", "NCONV") if conv is None else conv

    mwords = g("SYSTEM", "MWORDS")
    memory_mb = None if mwords is None else mwords * 8.0

    grid = None
    if xc:
        nrad, nleb = g("DFT", "NRAD", False), g("DFT", "NLEB", False)
        if (nrad is None) != (nleb is None):
            raise InputError("$DFT NRAD and NLEB must be given together")
        if nrad:
            grid = (nrad, nleb)

    mp2_frozen = None
    if mplevl == 2:
        mp2_frozen = g("MP2", "NACORE", False)

    excited = None
    if tddft == "EXCITE" or deck.has("TDDFT"):
        if cityp == "CIS":
            raise InputError("CITYP=CIS and TDDFT cannot be combined")
        if not xc:
            deck.notes.append(("warning", "TDDFT requested without DFTTYP: running TDHF (RPA)"))
        tda = g("TDDFT", "TDA")
        excited = {"kind": ("TDA" if tda else "TDDFT") if xc else ("CIS" if tda else "TDHF"),
                   "nstate": g("TDDFT", "NSTATE"), "iroot": g("TDDFT", "IROOT"),
                   "triplet": g("TDDFT", "MULT") == 3, "tda": tda}
    elif cityp == "CIS":
        if xc:
            raise InputError("CITYP=CIS cannot be combined with DFTTYP; use $TDDFT TDA=.TRUE.")
        excited = {"kind": "CIS", "nstate": g("CIS", "NSTATE"), "iroot": g("CIS", "IROOT"),
                   "triplet": g("CIS", "MULT") == 3, "tda": True}
    if excited:
        if excited["nstate"] < 1:
            raise InputError("NSTATE must be >= 1")
        if not 1 <= excited["iroot"] <= excited["nstate"]:
            raise InputError("IROOT must be between 1 and NSTATE")
        if excited["triplet"] and scftyp != "RHF":
            raise InputError("triplet excited states (MULT=3 in $TDDFT/$CIS) need SCFTYP=RHF")

    cas = None
    if scftyp == "MCSCF":
        if not deck.has("DET"):
            raise InputError("SCFTYP=MCSCF requires a $DET group (NCORE, NACT, NELS)")
        for k in ("NCORE", "NACT", "NELS"):
            if not deck.explicit("DET", k):
                raise InputError("$DET %s is required" % k)
        if not g("MCSCF", "FORS"):
            raise UnsupportedError("$MCSCF FORS=.FALSE. is not supported")
        d = deck.groups["DET"].keys
        cas = {"ncore": d["NCORE"], "nact": d["NACT"], "nels": d["NELS"],
               "nstate": g("DET", "NSTATE"), "wstate": g("DET", "WSTATE", False),
               "maxit": g("MCSCF", "MAXIT"), "acurcy": g("MCSCF", "ACURCY")}
        g("MCSCF", "CISTEP")
        if 2 * cas["ncore"] + cas["nels"] != nelec:
            raise InputError("$DET: 2*NCORE + NELS = %d, but the molecule has %d electrons"
                             % (2 * cas["ncore"] + cas["nels"], nelec))
        if cas["nels"] > 2 * cas["nact"] or (cas["nels"] + mult - 1) % 2:
            raise InputError("$DET: NELS=%d does not fit NACT=%d with MULT=%d"
                             % (cas["nels"], cas["nact"], mult))
        if cas["wstate"] is not None and len(cas["wstate"]) != cas["nstate"]:
            raise InputError("$DET WSTATE must have NSTATE values")
        if xc or mplevl or excited:
            raise UnsupportedError("SCFTYP=MCSCF cannot be combined with DFTTYP/MPLEVL/TDDFT/CIS")
    elif deck.has("DET") or deck.has("MCSCF"):
        deck.notes.append(("warning", "$DET/$MCSCF given but SCFTYP is not MCSCF; ignored"))

    pcm = None
    if deck.has("PCM"):
        eps = g("PCM", "EPS", False)
        solv = g("PCM", "SOLVNT", False)
        if eps is None and solv is None:
            raise InputError("$PCM needs SOLVNT=... or EPS=...")
        if eps is None:
            eps = SOLVENTS[solv]
        g("PCM", "IEF")
        pcm = {"eps": eps, "solvent": solv or "EPS=%g" % eps}

    if runtyp == "OPTIMIZE":
        nstep, opttol, hssend = g("STATPT", "NSTEP"), g("STATPT", "OPTTOL"), g("STATPT", "HSSEND")
    else:
        nstep, opttol, hssend = 20, 1e-4, False
    temps = [298.15]
    projct = True
    if runtyp == "HESSIAN" or hssend:
        temps = g("FORCE", "TEMP")
        projct = g("FORCE", "PROJCT", True)
        if g("FORCE", "METHOD") != "ANALYTIC":
            deck.notes.append(("warning", "$FORCE METHOD=%s: ffpy always uses the analytic hessian"
                               % deck.groups["FORCE"].keys["METHOD"]))

    timlim = g("SYSTEM", "TIMLIM") * 60.0
    labels = [a[0] for a in atoms]
    return Job(
        title=title, point_group=pgroup, labels=labels,
        charges=[a[1] for a in atoms], coords=np.array([a[2] for a in atoms], float),
        charge=charge, mult=mult, scftyp=scftyp, runtyp=runtyp,
        dfttyp=None if dfttyp == "NONE" else dfttyp, xc=xc, mplevl=mplevl,
        basis=basis, cart=contrl["ISPHER"] != 1, guess=guess, vec=vec,
        maxit=contrl["MAXIT"], nconv_density=nconv, direct=g("SCF", "DIRSCF"),
        diis=g("SCF", "DIIS", False), soscf=g("SCF", "SOSCF", False),
        damp=g("SCF", "DAMP", False), shift=g("SCF", "SHIFT", False),
        memory_mb=memory_mb, timlim_s=timlim, grid=grid, mp2_frozen=mp2_frozen,
        excited=excited, cas=cas, pcm=pcm, nstep=nstep, opttol=opttol, hssend=hssend,
        temps=temps, exetyp=contrl["EXETYP"], projct=projct, defaults=list(deck.defaults_used),
        nsym_ops=nops)
