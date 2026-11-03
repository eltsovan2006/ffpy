"""Job: everything the dispatcher needs, built from a parsed Deck.

This is the last layer that knows about the input format; the runners
below only see a Job and PySCF objects.
"""

from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

import numpy as np

from ffpy import symmetry
from ffpy.basis_map import BasisDict, basis_name, make_element_basis
from ffpy.constants import ANG_BOHR
from ffpy.errors import InputError, UnsupportedError
from ffpy.schema import SOLVENTS
from ffpy.xc_map import xc_for
from ffpy.zmatrix import parse_zmatrix

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
    basis: Any
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
    mp4: dict
    excited: Optional[dict]       # {"kind": TDDFT|TDHF|CIS, nstate, iroot, triplet, tda}
    cas: Optional[dict]
    pcm: Optional[dict]
    nstep: int
    opttol: float
    hssend: bool
    temps: List[float]
    exetyp: str
    projct: bool = True
    coord: str = "UNIQUE"
    nzvar: int = 0
    dlc: bool = False
    auto: bool = False
    defaults: List[str] = field(default_factory=list)
    nsym_ops: int = 1
    dftnl: Optional[Tuple[float, float]] = None   # VV10 (b, C)
    dh: Optional[dict] = None                     # double hybrid: hfx, cpt2, os, ss
    disp: Optional[dict] = None                   # D3BJ parameters
    auxbas: Optional[dict] = None                 # RI-MP2 auxiliary basis {element: shells}
    ecp: Optional[str] = None                     # PySCF ECP name (SBKJC)
    atom_tags: Optional[List[str]] = None   # per-atom names when $DATA carries its own basis

    @property
    def symbols(self):
        return [ELEMENTS[z] for z in self.charges]

    @property
    def method(self):
        """Key used by the dispatcher."""
        if self.scftyp == "MCSCF":
            return "CASSCF"
        if self.dh:
            return "DH"
        if self.mplevl == 2:
            return "MP2"
        if self.mplevl in (3, 4):
            return "MP%d" % self.mplevl
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


# optimized VV10 b (Hujo & Grimme); only values confirmed against Firefly output are listed
_VV10_B = {"PBE0": 6.9}

_SHELL_L = {"S": 0, "P": 1, "D": 2, "F": 3, "G": 4}


_LIBRARY_KEYS = {"SBK": "sbkjc", "N21": "%d-21g", "N31": "%d-31g", "N311": "%d-311g", "STO": "sto-%dg"}


def _shell_header(tok):
    if len(tok) == 1 and tok[0].upper() == "SBK":
        return True
    if len(tok) == 2 and tok[0].upper() in _LIBRARY_KEYS and tok[1].isdigit():
        return True
    return (len(tok) in (2, 3) and tok[0].upper() in _SHELL_L.keys() | {"L"} and tok[1].isdigit())


def _read_shells(rest, i, z):
    """Read the shells of one atom starting at rest[i]; returns (pyscf shells, next index).
    A library line such as 'N21 3' loads that basis for the element; shells after it are added."""
    shells = []
    n = len(rest)
    while i < n and rest[i].strip():
        tok = rest[i].split()
        if not _shell_header(tok):
            raise InputError("$DATA: bad shell header '%s'" % rest[i].strip())
        kind = tok[0].upper()
        nprim = int(tok[1]) if len(tok) > 1 else 0
        if kind in _LIBRARY_KEYS:
            name = _LIBRARY_KEYS[kind] if kind == "SBK" else _LIBRARY_KEYS[kind] % nprim
            if name in ("sto-4g", "sto-5g"):
                raise UnsupportedError("basis %s is not supported by PySCF" % name)
            try:
                from pyscf import gto
                shells.extend(gto.basis.load(name, ELEMENTS[z]))
            except ImportError:
                raise UnsupportedError("library basis %s in $DATA needs PySCF" % name)
            except Exception as e:
                raise InputError("$DATA: basis %s is not available for %s: %s" % (name, ELEMENTS[z], e))
            i += 1
            continue
        if len(tok) == 3:
            raise UnsupportedError("$DATA: scale factors on shell lines are not supported")
        rows = []
        for j in range(nprim):
            i += 1
            if i >= n or not rest[i].strip():
                raise InputError("$DATA: shell %s %d has fewer than %d primitives" % (kind, nprim, nprim))
            f = rest[i].replace("D", "E").replace("d", "e").split()
            try:
                vals = [float(x) for x in f[1:]]
            except ValueError:
                raise InputError("$DATA: cannot read primitive: %s" % rest[i].strip())
            if len(vals) != (3 if kind == "L" else 2):
                raise InputError("$DATA: primitive needs %d numbers: %s"
                                 % (3 if kind == "L" else 2, rest[i].strip()))
            rows.append(vals)
        if kind == "L":
            shells.append([0] + [[r[0], r[1]] for r in rows])
            shells.append([1] + [[r[0], r[2]] for r in rows])
        else:
            shells.append([_SHELL_L[kind]] + [[r[0], r[1]] for r in rows])
        i += 1
    return shells, i + 1


def _parse_auxbas(lines):
    """$AUXBAS: 'El  name' header, then shells 'S n' followed by n 'exponent coefficient' lines."""
    basis, sym, i = {}, None, 0
    lines = [l for l in lines if l.strip()]
    while i < len(lines):
        parts = lines[i].split()
        if len(parts) == 2 and parts[0].upper() in "SPDFGHIL" and parts[1].isdigit() and sym:
            l = "SPDFGHI".index(parts[0].upper())
            n = int(parts[1])
            rows = [lines[i + 1 + k].replace("D", "E").replace("d", "e").split() for k in range(n)]
            basis[sym].append([l] + [[float(r[0]), float(r[1])] for r in rows])
            i += n + 1
        else:
            sym = parts[0].capitalize()
            if sym not in ELEMENTS:
                raise InputError("$AUXBAS: unknown element %r" % parts[0])
            basis.setdefault(sym, [])
            i += 1
    return basis


def _parse_data(lines, units, coord="UNIQUE", custom=None):
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

    grp_name = group if order is None else "%s %d" % (group, order)

    if coord in ("ZMT", "ZMTMPC"):
        atoms, _ = parse_zmatrix(rest, units, coord_style=coord)
        return title, grp_name, atoms, 1

    unique, shells_of = [], []
    scale = ANG_BOHR if units == "ANGS" else 1.0
    i = 0
    while i < len(rest):
        line = rest[i]
        if not line.strip():
            if any(l.strip() for l in rest[i + 1:]):
                raise InputError("$DATA: blank line between atoms")
            break
        i += 1
        tok = line.split()
        if len(tok) < 2:
            raise InputError("$DATA: atom line must be 'name Z [x [y [z]]]': %s" % line.strip())
        if len(tok) > 5:
            raise UnsupportedError("$DATA: extra fields on atom line are not supported: %s"
                                   % line.strip())
        coords_tok = tok[2:] + ["0.0"] * (5 - len(tok))
        try:
            z = float(tok[1].upper().replace("D", "E"))
            xyz = [float(t.upper().replace("D", "E")) * scale for t in coords_tok]
        except ValueError:
            raise InputError("$DATA: cannot read numbers in: %s" % line.strip())
        if abs(z - round(z)) > 1e-6 or not (1 <= round(z) < len(ELEMENTS)):
            raise UnsupportedError("$DATA: nuclear charge %s of atom %s is not supported "
                                   "(dummy/ghost atoms and Z>54 are not supported)" % (tok[1], tok[0]))
        unique.append((tok[0], int(round(z)), xyz))
        if i < len(rest) and _shell_header(rest[i].split()):
            sh, i = _read_shells(rest, i, int(round(z)))
            shells_of.append(sh)
        else:
            shells_of.append(None)
    if not unique:
        raise InputError("$DATA: no atoms found")
    atoms, nops = symmetry.expand(unique, group, order)
    if any(s is not None for s in shells_of):
        if any(s is None for s in shells_of):
            raise InputError("$DATA: basis functions must be given for all atoms or for none")
        if custom is not None:
            for k, (u, sh) in enumerate(zip(unique, shells_of)):
                n_img = len(symmetry.expand([u], group, order)[0])
                custom.extend([(k + 1, sh)] * n_img)   # symmetry images share one basis tag
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
    coord = g("CONTRL", "COORD")
    nzvar = g("CONTRL", "NZVAR")
    if nzvar < 0:
        raise InputError("$CONTRL NZVAR must be non-negative")

    dlc = False
    auto = False
    if deck.has("ZMAT"):
        if deck.explicit("ZMAT", "IFREEZ"):
            raise UnsupportedError("$ZMAT IFREEZ: coordinate freezing is not supported by ffpy")
        if deck.explicit("ZMAT", "SCAN"):
            raise UnsupportedError("$ZMAT SCAN: potential energy surface scans are not supported by ffpy")
        dlc = g("ZMAT", "DLC", False)
        auto = g("ZMAT", "AUTO", False)
    if deck.has("STATPT") and deck.explicit("STATPT", "IFREEZ"):
        raise UnsupportedError("$STATPT IFREEZ: coordinate freezing is not supported by ffpy")

    scftyp, runtyp = contrl["SCFTYP"], contrl["RUNTYP"]
    dh = None
    if dfttyp == "DPBEP86":
        hfx, cpt2, scs = (g("DFT", k, report_default=False) for k in ("HFX", "CPT2", "SCS"))
        if hfx is None or cpt2 is None or scs is None or len(scs) != 2:
            raise UnsupportedError("DFTTYP=D-PBEP86 is supported only with explicit $DFT HFX(1)=, CPT2= and "
                                   "SCS(1)=os,ss (DSD-PBEP86 parameters) and $DFTD VERSN=4")
        cx, cc = 1.0 - hfx[0], 1.0 - cpt2
        # PBE exchange; P86 correlation with the modified Perdew-Zunger local part (matches Firefly)
        xc = ("%.10g*HF + %.10g*GGA_X_PBE + %.10g*GGA_C_P86 + %.10g*LDA_C_PZ_MOD - %.10g*LDA_C_PZ"
              % (hfx[0], cx, cc, cc, cc))
        dh = {"hfx": hfx[0], "cpt2": cpt2, "os": cpt2 * scs[0], "ss": cpt2 * scs[1]}
    else:
        xc = None if dfttyp == "NONE" else xc_for(dfttyp, g("DFT", "B3LYP", report_default=False))
    disp = None
    if g("CONTRL", "DFTD", report_default=False):
        if not xc:
            raise InputError("DFTD=.T. needs DFTTYP")
        pars = [g("DFTD", k, report_default=False) for k in ("S6", "RS6", "S18", "RS18")]
        if g("DFTD", "VERSN", report_default=False) != 4 or None in pars:
            raise UnsupportedError("DFTD=.T. is supported only as D3BJ: $DFTD VERSN=4 with S6, RS6, S18, RS18 "
                                   "(and ALP) given explicitly")
        disp = {"s6": pars[0], "a1": pars[1], "s8": pars[2], "a2": pars[3], "alp": g("DFTD", "ALP")}
        if runtyp != "ENERGY":
            raise UnsupportedError("DFT-D is supported only for RUNTYP=ENERGY")

    custom = []
    title, pgroup, atoms, nops = _parse_data(deck.groups["DATA"].lines, contrl["UNITS"], coord=coord,
                                             custom=custom)

    atom_tags = None
    if custom:
        atom_tags = ["%s%d" % (ELEMENTS[a[1]], c[0]) for a, c in zip(atoms, custom)]
        basis = BasisDict({t: c[1] for t, c in zip(atom_tags, custom)}, "CUSTOM")
    else:
        if not deck.has("BASIS") or not deck.explicit("BASIS", "GBASIS"):
            raise InputError("$BASIS GBASIS=... is required (or give basis functions in $DATA)")
        b = deck.groups["BASIS"].keys
        canonical = basis_name(b["GBASIS"], b.get("NGAUSS"), b.get("NDFUNC", 0), b.get("NPFUNC", 0),
                               b.get("NFFUNC", 0), b.get("DIFFSP", False), b.get("DIFFS", False))
        if canonical in ("sto-4g", "sto-5g"):
            raise UnsupportedError("basis %s is not supported by PySCF" % canonical)
        elements = {ELEMENTS[z] for _, z, _ in atoms}
        basis = make_element_basis(canonical, elements, b["GBASIS"], b.get("NGAUSS"), b.get("NDFUNC", 0))

    dftnl = None
    if g("CONTRL", "DFTNL", report_default=False):
        if not xc:
            raise InputError("DFTNL=.T. needs DFTTYP")
        b = g("DFTNL", "B", report_default=False)
        if b is None:
            b = _VV10_B.get(dfttyp, 4.8 if dfttyp in ("B3LYP", "B3LYP1") else None)
            if b is None:
                raise UnsupportedError("DFTNL: no optimized VV10 b value known for DFTTYP=%s; set $DFTNL B=" % dfttyp)
        dftnl = (b, g("DFTNL", "C"))

    mult, charge = contrl["MULT"], contrl["ICHARG"]
    ecp = g("CONTRL", "ECP", report_default=False)
    ecp = None if ecp == "NONE" else "sbkjc"
    ncore_ecp = 0
    if ecp:
        from pyscf import gto
        for _, z, _ in atoms:
            e = gto.basis.load_ecp(ecp, ELEMENTS[z])
            ncore_ecp += e[0] if e else 0
    nelec = sum(z for _, z, _ in atoms) - charge - ncore_ecp
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
        if any("D" in l.upper()[5:] for l in deck.groups["VEC"].lines):
            # Firefly/GAMESS punch format: coefficients are in GAMESS AO order and cannot be
            # mapped onto PySCF's AO order; start from the default guess instead
            deck.notes.append(("warning", "$VEC from Firefly/GAMESS is not read (AO order differs): "
                                          "using the HUCKEL guess; the SCF should converge to the same state"))
            guess = "HUCKEL"
        else:
            vec = _parse_vec(deck.groups["VEC"].lines, g("GUESS", "NORB", report_default=False))
    elif "VEC" in deck.groups:
        deck.notes.append(("warning", "$VEC is present but GUESS is not MOREAD; it is ignored"))

    conv = g("SCF", "CONV", report_default=False)
    nconv = 10.0 ** -g("SCF", "NCONV") if conv is None else conv

    mwords = g("SYSTEM", "MWORDS")
    mem_words = g("SYSTEM", "MEMORY", report_default=False)
    if mem_words is not None:
        if mwords is None:
            mwords = mem_words / 1e6
            deck.notes.append(("warning", "$SYSTEM MEMORY=%g converted to MWORDS=%g" % (mem_words, mwords)))
        else:
            deck.notes.append(("warning", "$SYSTEM MWORDS=%g takes precedence over MEMORY=%g" % (mwords, mem_words)))
    memory_mb = None if mwords is None else mwords * 8.0

    grid = None
    if xc:
        nrad, nleb = g("DFT", "NRAD", False), g("DFT", "NLEB", False)
        if (nrad is None) != (nleb is None):
            raise InputError("$DFT NRAD and NLEB must be given together")
        if nrad:
            grid = (nrad, nleb)

    mp2_frozen = None
    auxbas = None
    mp4 = {}
    if mplevl in (3, 4):
        if scftyp != "RHF":
            raise UnsupportedError("MP%d is implemented only for SCFTYP=RHF" % mplevl)
        if xc:
            raise UnsupportedError("MPLEVL=%d cannot be combined with DFTTYP" % mplevl)
        mp2_frozen = g("MP2", "NACORE", False)
        if mplevl == 4:
            mp4 = {"sdtq": g("MP4", "SDTQ", False), "tonly": g("MP4", "TONLY", False)}
    if mplevl == 2 and scftyp == "ROHF" and g("MP2", "OSPT", report_default=False) == "ZAPT":
        raise UnsupportedError("$MP2 OSPT=ZAPT is not supported (only OSPT=RMP for ROHF)")
    if mplevl == 2 or dh:
        if deck.has("MP2") and g("MP2", "RI", report_default=False):
            if "AUXBAS" not in deck.groups:
                raise UnsupportedError("RI-MP2 ($MP2 RI=.TRUE.) is supported only with the auxiliary basis "
                                       "written out in an $AUXBAS group")
            auxbas = _parse_auxbas(deck.groups["AUXBAS"].lines)
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
                   "triplet": g("TDDFT", "MULT") == 3, "tda": tda, "istsym": g("TDDFT", "ISTSYM")}
    elif cityp in ("TDHF", "TDDFT"):
        if cityp == "TDDFT" and not xc:
            raise InputError("CITYP=TDDFT needs DFTTYP")
        if cityp == "TDHF" and xc:
            raise InputError("CITYP=TDHF cannot be combined with DFTTYP; use CITYP=TDDFT")
        grp = cityp
        tda = g(grp, "TDA")
        excited = {"kind": ("TDA" if tda else "TDDFT") if xc else ("CIS" if tda else "TDHF"),
                   "nstate": g(grp, "NSTATE"), "iroot": abs(g(grp, "ISTATE")) or 1,
                   "triplet": g(grp, "MULT") == 3, "tda": tda, "istsym": g(grp, "ISTSYM")}
    elif cityp == "CIS":
        if xc:
            raise InputError("CITYP=CIS cannot be combined with DFTTYP; use $TDDFT TDA=.TRUE.")
        excited = {"kind": "CIS", "nstate": g("CIS", "NSTATE"), "iroot": g("CIS", "IROOT"),
                   "triplet": g("CIS", "MULT") == 3, "tda": True, "istsym": g("CIS", "ISTSYM")}
    if excited:
        if excited["nstate"] < 1:
            raise InputError("NSTATE must be >= 1")
        if not 1 <= excited["iroot"] <= excited["nstate"]:
            raise InputError("IROOT must be between 1 and NSTATE")
        if excited["triplet"] and scftyp != "RHF":
            raise InputError("triplet excited states (MULT=3 in $TDDFT/$CIS) need SCFTYP=RHF")

    cas = None
    if scftyp == "GVB":
        # one perfect-pairing geminal = full CI in two orbitals = CASSCF(2,2)
        nco, nseto, npair = g("SCF", "NCO"), g("SCF", "NSETO"), g("SCF", "NPAIR")
        if nseto or npair != 1:
            raise UnsupportedError("SCFTYP=GVB is supported only with NSETO=0 and NPAIR=1 "
                                   "(one geminal pair, equivalent to CASSCF(2,2)); got NSETO=%d NPAIR=%d"
                                   % (nseto, npair))
        if mult != 1:
            raise UnsupportedError("SCFTYP=GVB with MULT>1 is not supported")
        if xc or mplevl or excited:
            raise UnsupportedError("SCFTYP=GVB cannot be combined with DFTTYP/MPLEVL/TDDFT/CIS")
        cas = {"ncore": nco, "nact": 2, "nels": 2, "nstate": 1, "wstate": None,
               "maxit": g("MCSCF", "MAXIT"), "acurcy": g("MCSCF", "ACURCY"), "istsym": 1}
        scftyp = "MCSCF"
        if 2 * nco + 2 != nelec:
            raise InputError("$SCF: 2*NCO + 2*NPAIR = %d, but the molecule has %d electrons"
                             % (2 * nco + 2, nelec))
    elif scftyp == "MCSCF":
        if not g("MCSCF", "FORS"):
            raise UnsupportedError("$MCSCF FORS=.FALSE. is not supported")
        if g("MCSCF", "CISTEP") == "GUGA" or (deck.has("DRT") and not deck.has("DET")):
            # full-CI-in-the-active-space (FORS) described with $DRT, solved like $DET
            if not deck.has("DRT") or not deck.explicit("DRT", "FORS") or not g("DRT", "FORS"):
                raise UnsupportedError("CISTEP=GUGA is supported only with $DRT FORS=.TRUE.")
            if g("DRT", "NALP") and g("DRT", "NALP") != mult - 1:
                raise InputError("$DRT NALP=%d does not match MULT=%d" % (g("DRT", "NALP"), mult))
            nact = g("DRT", "NDOC") + g("DRT", "NALP") + g("DRT", "NVAL")
            cas = {"ncore": g("DRT", "NMCC"), "nact": nact, "nels": 2 * g("DRT", "NDOC") + g("DRT", "NALP"),
                   "nstate": g("GUGDIA", "NSTATE", False), "wstate": g("GUGDM2", "WSTATE", False),
                   "maxit": g("MCSCF", "MAXIT"), "acurcy": g("MCSCF", "ACURCY"),
                   "istsym": g("DRT", "ISTSYM", False) if deck.explicit("DRT", "ISTSYM") else 0}
        else:
            if not deck.has("DET"):
                raise InputError("SCFTYP=MCSCF requires a $DET group (NCORE, NACT, NELS)")
            for k in ("NCORE", "NACT", "NELS"):
                if not deck.explicit("DET", k):
                    raise InputError("$DET %s is required" % k)
            d = deck.groups["DET"].keys
            cas = {"ncore": d["NCORE"], "nact": d["NACT"], "nels": d["NELS"],
                   "nstate": g("DET", "NSTATE"), "wstate": g("DET", "WSTATE", False),
                   "maxit": g("MCSCF", "MAXIT"), "acurcy": g("MCSCF", "ACURCY"),
                   "istsym": g("DET", "ISTSYM", False) if deck.explicit("DET", "ISTSYM") else 0}
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
        basis=basis, cart=contrl["ISPHER"] != 1 and not g("CONTRL", "D5", report_default=False), guess=guess, vec=vec,
        maxit=contrl["MAXIT"], nconv_density=nconv, direct=g("SCF", "DIRSCF"),
        diis=g("SCF", "DIIS", False), soscf=g("SCF", "SOSCF", False),
        damp=g("SCF", "DAMP", False), shift=g("SCF", "SHIFT", False),
        memory_mb=memory_mb, timlim_s=timlim, grid=grid, mp2_frozen=mp2_frozen, mp4=mp4,
        excited=excited, cas=cas, pcm=pcm, nstep=nstep, opttol=opttol, hssend=hssend,
        temps=temps, exetyp=contrl["EXETYP"], projct=projct,
        coord=coord, nzvar=nzvar, dlc=dlc, auto=auto,
        defaults=list(deck.defaults_used), nsym_ops=nops, atom_tags=atom_tags, dftnl=dftnl, ecp=ecp, dh=dh, disp=disp, auxbas=auxbas)
