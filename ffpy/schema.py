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

RAW_GROUPS = {"DATA", "VEC"}

SCHEMA = {
    "CONTRL": {
        "SCFTYP": K("str", "RHF", ("RHF", "UHF", "ROHF", "MCSCF"), "reference wavefunction"),
        "RUNTYP": K("str", "ENERGY", ("ENERGY", "GRADIENT", "OPTIMIZE", "HESSIAN"), "job type"),
        "DFTTYP": K("str", "NONE", ("NONE",) + tuple(sorted(XC_MAP)), "DFT functional"),
        "MPLEVL": K("int", 0, (0, 2), "MP2 when 2"),
        "CITYP": K("str", "NONE", ("NONE", "CIS"), "CIS excited states"),
        "TDDFT": K("str", "NONE", ("NONE", "EXCITE"), "TDDFT excited states"),
        "ICHARG": K("int", 0, None, "molecular charge"),
        "MULT": K("int", 1, None, "spin multiplicity"),
        "UNITS": K("str", "ANGS", ("ANGS", "BOHR"), "units of $DATA coordinates"),
        "MAXIT": K("int", 30, None, "max SCF iterations"),
        "ISPHER": K("int", -1, (-1, 0, 1), "-1/0 Cartesian d,f; 1 spherical"),
        "COORD": K("str", "UNIQUE", ("UNIQUE", "CART"), "coordinate input style"),
        "NZVAR": K("int", 0, (0,), "internal coordinates (only 0)"),
        "EXETYP": K("str", "RUN", ("RUN", "CHECK"), "CHECK: parse input only"),
    },
    "SYSTEM": {
        "MWORDS": K("float", None, None, "memory in 10^6 words (8 MB); not set = PySCF default 4000 MB"),
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
    },
    "DFT": {
        "NRAD": K("int", None, None, "radial points per atom (with NLEB)"),
        "NLEB": K("int", None, None, "Lebedev angular points (with NRAD)"),
    },
    "MP2": {
        "NACORE": K("int", None, None, "frozen core orbitals; not set = chemical core"),
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
        "MULT": K("int", 1, (1, 3), "excited-state multiplicity (closed shell)"),
        "TDA": K("bool", False, None, "Tamm-Dancoff approximation"),
    },
    "CIS": {
        "NSTATE": K("int", 1, None, "number of excited states"),
        "IROOT": K("int", 1, None, "state for gradient/optimization"),
        "MULT": K("int", 1, (1, 3), "excited-state multiplicity (closed shell)"),
    },
    "DET": {
        "NCORE": K("int", None, None, "doubly occupied core orbitals (required)"),
        "NACT": K("int", None, None, "active orbitals (required)"),
        "NELS": K("int", None, None, "active electrons (required)"),
        "NSTATE": K("int", 1, None, "CI roots; >1 = state-averaged CASSCF"),
        "WSTATE": K("floatlist", None, None, "state-averaging weights; not set = equal"),
    },
    "MCSCF": {
        "CISTEP": K("str", "ALDET", ("ALDET",), "CI solver"),
        "FORS": K("bool", True, None, "full optimized reaction space (only .TRUE.)"),
        "MAXIT": K("int", 100, None, "max macro-iterations"),
        "ACURCY": K("float", 1e-5, None, "orbital gradient convergence"),
    },
    "PCM": {
        "SOLVNT": K("str", None, tuple(sorted(SOLVENTS)), "solvent name"),
        "EPS": K("float", None, None, "dielectric constant (overrides SOLVNT)"),
        "IEF": K("int", -10, None, "IEF-PCM flavour (ffpy always uses IEF-PCM)"),
    },
}

IGNORED = {
    "CONTRL": {"NPRINT", "ICUT", "ITOL", "INTTYP", "QMTTOL", "NOSYM", "NORMF",
               "NORMP", "MOLPLT", "PLTORB", "AIMPAC", "FRIEND", "D5", "NUMGRD"},
    "SYSTEM": {"MEMDDI", "KDIAG", "NOJAC", "PARALL", "MKLNP", "NP"},
    "GUESS": {"PRTMO", "PUNMO", "MIX", "TOLZ", "TOLE"},
    "SCF": {"FDIFF", "NPUNCH", "EXTRAP", "RSTRCT", "DIRTHR", "NPREO"},
    "DFT": {"METHOD", "DC", "IDCVER"},
    "MP2": {"MP2PRP", "CODE", "CUTOFF", "METHOD", "NBCORE"},
    "STATPT": {"METHOD", "HESS", "NPRT", "NPUN", "IHREP", "IFOLOW", "STPT",
               "DXMAX", "TRMAX", "TRMIN", "IDUMP", "PURIFY", "PROJCT", "LET",
               "ITBMX", "GMIN", "GMAX", "NPRTR", "NPUNR", "KDIAG", "SCHM"},
    "FORCE": {"NVIB", "VIBSIZ", "PURIFY", "PRTIFC"},
    "TDDFT": {"NRAD", "NLEB", "PRTTOL"},
    "DET": {"PURES", "ITERMX", "CVGTOL", "NHGSS", "NSTGSS"},
    "MCSCF": {"SOSCF", "FULLNR", "FOCAS", "QUAD", "JACOBI"},
    "PCM": {"ICOMP", "ICAV", "IDISP", "RSOLV", "EPSINF", "IDP"},
}

UNSUPPORTED_GROUPS = {
    "ZMAT": "internal coordinates", "EFRAG": "EFP", "EFP": "EFP",
    "FMO": "FMO", "XMCQDPT": "XMCQDPT2", "MCQDPT": "MCQDPT",
    "CIDRT": "GUGA CI", "ECP": "effective core potentials",
    "TDHF": "TDHF polarizabilities", "CCINP": "coupled cluster",
    "EOMINP": "EOM-CC", "RAMAN": "Raman", "HESS": "reading a $HESS group",
    "GRAD": "reading a $GRAD group", "ELPOT": "electrostatic potential",
    "LIBE": "LIBE", "P2P": "P2P parallelism", "DRT": "GUGA",
}
