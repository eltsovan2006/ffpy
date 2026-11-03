"""Supported input groups and keys.

Keys and defaults follow the GAMESS (US) / Firefly documentation as far as
it was available when writing this; every entry should be re-checked
against the Firefly manual shipped with the distribution.

Each key: Key(type, default, choices, help). default=None means "no
default" (either required, or "not set" with the behaviour described in
help). Keys in IGNORED are accepted for compatibility, have no effect in
ffpy, and produce a WARNING. Anything else is an input error.
"""

from collections import namedtuple

from ffpy.xc_map import XC_MAP

Key = namedtuple("Key", "type default choices help")


def K(type_, default=None, choices=None, help=""):
    return Key(type_, default, choices, help)


SOLVENTS = {
    # name: dielectric constant (values as commonly tabulated for PCM)
    "WATER": 78.39, "H2O": 78.39,
    "CH3OH": 32.63, "METHANOL": 32.63,
    "C2H5OH": 24.55, "ETHANOL": 24.55,
    "CH3CN": 35.69, "ACETONITRILE": 35.69,
    "DMSO": 46.7,
    "ACETONE": 20.7,
    "CH2CL2": 8.93, "METHYCL": 8.93, "DICHLOROMETHANE": 8.93,
    "CHCL3": 4.9, "CLFORM": 4.9, "CHLOROFORM": 4.9,
    "CCL4": 2.228, "CTCL": 2.228,
    "THF": 7.58,
    "BENZENE": 2.247, "C6H6": 2.247,
    "TOLUENE": 2.379,
    "CLBENZ": 5.621,
    "NITMET": 38.2,
    "NEPTANE": 1.92, "HEPTANE": 1.92,
    "CYCHEX": 2.023, "CYCLOHEXANE": 2.023,
    "ANILINE": 6.89,
    "DMF": 37.219,
}

RAW_GROUPS = {"DATA", "VEC", "AUXBAS"}

SCHEMA = {
    "CONTRL": {
        "SCFTYP": K("str", "RHF", ("RHF", "UHF", "ROHF", "MCSCF", "GVB"), "reference wavefunction"),
        "RUNTYP": K("str", "ENERGY", ("ENERGY", "GRADIENT", "OPTIMIZE", "HESSIAN", "NUMGRAD"), "job type"),
        "DFTTYP": K("str", "NONE", ("NONE", "DPBEP86") + tuple(sorted(XC_MAP)), "DFT functional"),
        "MPLEVL": K("int", 0, (0, 2, 3, 4), "MP2/MP3/MP4 (MP3 and MP4 are RHF only)"),
        "CITYP": K("str", "NONE", ("NONE", "CIS", "TDHF", "TDDFT"), "CIS/TDHF/TDDFT excited states"),
        "TDDFT": K("str", "NONE", ("NONE", "EXCITE"), "TDDFT excited states"),
        "ICHARG": K("int", 0, None, "molecular charge"),
        "MULT": K("int", 1, None, "spin multiplicity"),
        "UNITS": K("str", "ANGS", ("ANGS", "BOHR"), "units of $DATA coordinates"),
        "MAXIT": K("int", 30, None, "max SCF iterations"),
        "DFTNL": K("bool", False, None, "add the non-self-consistent VV10 nonlocal term (DFT-NL)"),
        "DFTD": K("bool", False, None, "empirical dispersion (only D3BJ with explicit $DFTD parameters)"),
        "ECP": K("str", "NONE", ("NONE", "SBK"), "effective core potentials (SBK = SBKJC)"),
        "D5": K("bool", False, None, "spherical (pure) d and f functions, like ISPHER=1"),
        "ISPHER": K("int", -1, (-1, 0, 1), "-1/0 Cartesian d,f; 1 spherical"),
        "COORD": K("str", "UNIQUE", ("UNIQUE", "CART", "ZMT", "ZMTMPC"), "coordinate input style"),
        "NZVAR": K("int", 0, None, "internal coordinates (0=Cartesian, >0=internals)"),
        "EXETYP": K("str", "RUN", ("RUN", "CHECK"), "CHECK: parse input only"),
    },
    "SYSTEM": {
        "MWORDS": K("float", None, None, "memory in 10^6 words (8 MB); not set = PySCF default 4000 MB"),
        "MEMORY": K("float", None, None, "memory in words (8 bytes per word); converted to MWORDS"),
        "TIMLIM": K("float", 525600.0, None, "time limit, minutes"),
    },
    "BASIS": {
        "GBASIS": K("str", None, None, "basis family (required)"),
        "NGAUSS": K("int", None, None, "number of Gaussians"),
        "NDFUNC": K("int", 0, (0, 1, 2, 3), "d functions on heavy atoms"),
        "NFFUNC": K("int", 0, (0, 1), "f functions on heavy atoms"),
        "NPFUNC": K("int", 0, (0, 1, 2, 3), "p functions on H"),
        "DIFFSP": K("bool", False, None, "diffuse sp on heavy atoms"),
        "DIFFS": K("bool", False, None, "diffuse s on H"),
        "POLAR": K("str", "POPLE", ("POPLE",), "polarization exponents"),
    },
    "GUESS": {
        "GUESS": K("str", "HUCKEL", ("HUCKEL", "HCORE", "MOREAD"), "initial orbitals"),
        "NORB": K("int", None, None, "number of orbitals in $VEC (MOREAD)"),
    },
    "SCF": {
        "DIRSCF": K("bool", False, None, "direct SCF"),
        "NCONV": K("int", 5, None, "density convergence 10^-NCONV"),
        "CONV": K("float", None, None, "density convergence (overrides NCONV)"),
        "DIIS": K("bool", True, None, "DIIS extrapolation"),
        "SOSCF": K("bool", False, None, "second-order SCF (PySCF newton)"),
        "DAMP": K("bool", False, None, "density damping"),
        "SHIFT": K("bool", False, None, "level shift"),
        "NCO": K("int", 0, None, "GVB: doubly occupied orbitals"),
        "NSETO": K("int", 0, None, "GVB: open shells (not supported)"),
        "NPAIR": K("int", 0, None, "GVB: geminal pairs (only 1 supported, = CASSCF(2,2))"),
        "CICOEF": K("floatlist", None, None, "GVB: initial pair CI coefficients (ignored)"),
    },
    "DFTD": {
        "VERSN": K("int", 3, (3, 4), "DFT-D version; only 4 (D3 with Becke-Johnson damping) is supported"),
        "S6": K("float", None, None, "D3BJ s6"),
        "RS6": K("float", None, None, "D3BJ a1"),
        "S18": K("float", None, None, "D3BJ s8"),
        "RS18": K("float", None, None, "D3BJ a2 (bohr)"),
        "ALP": K("float", 14.0, None, "D3BJ alpha6"),
    },
    "DFTNL": {
        "B": K("float", None, None, "VV10 b parameter (default: optimized value of the functional, else 4.8)"),
        "C": K("float", 0.0093, None, "VV10 C parameter"),
    },
    "DFT": {
        "NRAD": K("int", None, None, "radial points per atom (with NLEB)"),
        "NLEB": K("int", None, None, "Lebedev angular points (with NRAD)"),
        "B3LYP": K("str", "NWCHEM", ("NWCHEM", "GAMESS"), "VWN formula of DFTTYP=B3LYP: NWCHEM = 1 RPA (default), GAMESS = 5"),
        "HFX": K("floatlist", None, None, "double hybrid (D-PBEP86): fraction of exact exchange"),
        "CPT2": K("float", None, None, "double hybrid: total weight of the MP2-like term"),
        "SCS": K("floatlist", None, None, "double hybrid: opposite-spin and same-spin scaling of CPT2"),
    },
    "MP4": {
        "SDTQ": K("bool", False, None, "MP4(SDTQ) instead of MP4(SDQ)"),
        "TONLY": K("bool", False, None, "only the MP4(T) triples term"),
    },
    "RIMP2": {
        "AUXBAS": K("str", None, None, "name of the auxiliary basis given in $AUXBAS"),
    },
    "MP2": {
        "NACORE": K("int", None, None, "frozen core orbitals; not set = chemical core"),
        "RI": K("bool", False, None, "RI-MP2 with the auxiliary basis from $AUXBAS"),
    },
    "STATPT": {
        "NSTEP": K("int", 20, None, "max optimization steps"),
        "OPTTOL": K("float", 1e-4, None, "max gradient, Hartree/Bohr"),
        "HSSEND": K("bool", False, None, "hessian at the optimized geometry"),
    },
    "FORCE": {
        "TEMP": K("floatlist", [298.15], None, "thermochemistry temperatures, K"),
        "METHOD": K("str", "ANALYTIC", ("ANALYTIC", "SEMINUM", "FULLNUM"), "hessian method (always analytic in ffpy)"),
        "VIBANL": K("bool", True, None, "normal mode analysis"),
        "PROJCT": K("bool", True, None, "project translation and rotation out of hessian"),
    },
    "TDDFT": {
        "NSTATE": K("int", 1, None, "number of excited states"),
        "IROOT": K("int", 1, None, "state for gradient/optimization"),
        "ISTATE": K("int", 1, None, "state for gradient/properties (negative: state tracking)"),
        "ISTSYM": K("int", 0, None, "irrep index of the states (0: all symmetries)"),
        "MULT": K("int", 1, (1, 3), "excited-state multiplicity (closed shell)"),
        "TDA": K("bool", False, None, "Tamm-Dancoff approximation"),
    },
    "TDHF": {
        "NSTATE": K("int", 1, None, "number of excited states"),
        "ISTATE": K("int", 1, None, "state for gradient/properties (negative: state tracking)"),
        "ISTSYM": K("int", 0, None, "irrep index of the states (0: all symmetries)"),
        "MULT": K("int", 1, (1, 3), "excited-state multiplicity (closed shell)"),
        "TDA": K("bool", False, None, "Tamm-Dancoff approximation"),
    },
    "CIS": {
        "ISTSYM": K("int", 0, None, "irrep index of the states (0: all symmetries)"),
        "NSTATE": K("int", 1, None, "number of excited states"),
        "IROOT": K("int", 1, None, "state for gradient/optimization"),
        "MULT": K("int", 1, (1, 3), "excited-state multiplicity (closed shell)"),
    },
    "DRT": {
        "GROUP": K("str", "C1", None, "point group"),
        "FORS": K("bool", False, None, "full optimized reaction space CAS (only .TRUE.)"),
        "NMCC": K("int", 0, None, "doubly occupied core orbitals"),
        "NDOC": K("int", 0, None, "doubly occupied active orbitals"),
        "NALP": K("int", 0, None, "singly occupied (alpha) active orbitals"),
        "NVAL": K("int", 0, None, "empty (virtual) active orbitals"),
        "ISTSYM": K("int", 1, None, "irrep index of the CI states"),
    },
    "GUGDIA": {
        "NSTATE": K("int", 1, None, "CI roots; >1 = state-averaged MCSCF"),
    },
    "GUGDM2": {
        "WSTATE": K("floatlist", None, None, "state-averaging weights; not set = equal"),
    },
    "DET": {
        "ISTSYM": K("int", 1, None, "irrep index of the CI states"),
        "NCORE": K("int", None, None, "doubly occupied core orbitals (required)"),
        "NACT": K("int", None, None, "active orbitals (required)"),
        "NELS": K("int", None, None, "active electrons (required)"),
        "NSTATE": K("int", 1, None, "CI roots; >1 = state-averaged CASSCF"),
        "WSTATE": K("floatlist", None, None, "state-averaging weights; not set = equal"),
    },
    "MCSCF": {
        "CISTEP": K("str", "ALDET", ("ALDET", "GUGA"), "CI solver (GUGA is run as the same full CI in the active space)"),
        "ISTATE": K("int", 1, None, "state followed in geometry optimization"),
        "FORS": K("bool", True, None, "full optimized reaction space (only .TRUE.)"),
        "MAXIT": K("int", 100, None, "max macro-iterations"),
        "ACURCY": K("float", 1e-5, None, "orbital gradient convergence"),
    },
    "PCM": {
        "SOLVNT": K("str", None, tuple(sorted(SOLVENTS)), "solvent name"),
        "EPS": K("float", None, None, "dielectric constant (overrides SOLVNT)"),
        "IEF": K("int", -10, None, "IEF-PCM flavour (ffpy always uses IEF-PCM)"),
    },
    "ZMAT": {
        "IZMAT": K("floatlist", None, None, "simple internal coordinates"),
        "DLC": K("bool", False, None, "delocalized internal coordinates"),
        "AUTO": K("bool", False, None, "automatic redundant internal coordinates"),
        "IFREEZ": K("floatlist", None, None, "frozen internal coordinates"),
        "SCAN": K("str", None, None, "potential energy surface scan"),
    },
    "SMP": {},
    "ELMOM": {},
}

IGNORED = {
    "CONTRL": {"NPRINT", "ICUT", "ITOL", "INTTYP", "QMTTOL", "NOSYM", "NORMF",
               "NORMP", "MOLPLT", "PLTORB", "AIMPAC", "FRIEND", "NUMGRD", "WIDE",
               "NUMDER", "LOCAL"},
    "SYSTEM": {"MEMDDI", "KDIAG", "NOJAC", "PARALL", "MKLNP", "NP", "CORE", "BALNCS", "XDLB"},
    "SMP": {"HTTNP", "MKLNP", "NP", "CALL64"},
    "GUESS": {"PRTMO", "PUNMO", "MIX", "TOLZ", "TOLE", "ASIS"},
    "SCF": {"FDIFF", "NPUNCH", "EXTRAP", "RSTRCT", "DIRTHR", "NPREO"},
    "DFT": {"METHOD", "DC", "IDCVER"},
    "MP2": {"MP2PRP", "CODE", "CUTOFF", "METHOD", "NBCORE", "LMOMP2"},
    "STATPT": {"METHOD", "HESS", "NPRT", "NPUN", "IHREP", "IFOLOW", "STPT",
               "DXMAX", "TRMAX", "TRMIN", "IDUMP", "PURIFY", "PROJCT", "LET",
               "ITBMX", "GMIN", "GMAX", "NPRTR", "NPUNR", "KDIAG", "SCHM"},
    "FORCE": {"NVIB", "VIBSIZ", "PURIFY", "PRTIFC"},
    "TDDFT": {"NRAD", "NLEB", "PRTTOL", "RDTDVC", "ALTER", "MAXIT", "TOL"},
    "TDHF": {"PRTTOL", "RDTDVC", "ALTER", "MAXIT", "TOL"},
    "DET": {"PURES", "ITERMX", "CVGTOL", "NHGSS", "NSTGSS", "GROUP", "ISPIN"},
    "DRT": {"MXNINT", "FOCI", "SDCI", "NEXT", "NFZC", "NINT", "IEXCIT", "ITOL", "NAOS", "NBOS"},
    "GUGDIA": {"ITERMX", "CVGTOL", "PRTTOL", "MEMMAX", "NHGSS", "NSTGSS"},
    "GUGDM2": {"CUTOFF", "NSTATE"},
    "MCSCF": {"SOSCF", "FULLNR", "FOCAS", "QUAD", "JACOBI", "NPFLG"},
    "PCM": {"ICOMP", "ICAV", "IDISP", "RSOLV", "EPSINF", "IDP"},
    "ELMOM": {"IEMOM", "WHERE"},
    "ZMAT": {"NONVDW", "AUTOFV", "DLCTOL", "IFRZAT", "SIJ", "IJS", "FVALUE", "IXZMAT", "IRZMAT", "IFZMAT"},
}

# whole groups that only tune Firefly's parallel runtime / memory: accepted with a WARNING
IGNORED_GROUPS = {"P2P", "TRANS", "GUGEM", "MCQFIT"}

UNSUPPORTED_GROUPS = {
    "EFRAG": "EFP", "EFP": "EFP",
    "FMO": "FMO", "XMCQDPT": "XMCQDPT2", "MCQDPT": "MCQDPT",
    "CIDRT": "GUGA CI", "ECP": "effective core potentials",
    "CCINP": "coupled cluster",
    "EOMINP": "EOM-CC", "RAMAN": "Raman", "HESS": "reading a $HESS group",
    "GRAD": "reading a $GRAD group", "ELPOT": "electrostatic potential",
    "LIBE": "LIBE",
    "IRC": "IRC", "DRC": "DRC", "TRUDGE": "TRUDGE", "SURF": "surface scan",
    "MOROKM": "Morokuma", "SCRF": "SCRF", "CPHF": "CPHF",
}
