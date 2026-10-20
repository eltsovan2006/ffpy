"""DFTTYP -> PySCF xc string.

Assumption (to be checked against the Firefly manual and one Firefly run):
Firefly/GAMESS "B3LYP" uses VWN formula 5 in the LDA correlation part,
while the Gaussian flavour uses VWN1-RPA. PySCF names them B3LYP5 and
B3LYPG. Firefly's Gaussian-compatible variant is mapped from B3LYP1 /
B3LYPV1R.
"""

from ffpy.errors import InputError

XC_MAP = {
    "SLATER": "slater",
    "SVWN": "lda,vwn5",
    "SVWN5": "lda,vwn5",
    "SVWN1RPA": "lda,vwn_rpa",
    "B88": "b88,",
    "BLYP": "b88,lyp",
    "BP86": "b88,p86",
    "BPW91": "b88,pw91",
    "PW91": "pw91,pw91",
    "PBE": "pbe,pbe",
    "REVPBE": "revpbe,pbe",
    "PBE0": "pbe0",
    "PBE1PBE": "pbe0",
    "B3LYP": "b3lyp5",
    "B3LYP5": "b3lyp5",
    "B3LYP1": "b3lypg",
    "B3LYPV1R": "b3lypg",
    "B3PW91": "b3pw91",
    "B3P86": "b3p86",
    "X3LYP": "x3lyp",
    "BHHLYP": "bhandhlyp",
    "TPSS": "tpss,tpss",
    "TPSSH": "tpssh",
    "M05": "m05",
    "M052X": "m052x",
    "M06": "m06",
    "M06L": "m06l,m06l",
    "M062X": "m062x",
    "M06HF": "m06hf",
    "CAMB3LYP": "camb3lyp",
    "WB97X": "wb97x",
    "B97": "b97",
    "B971": "b97_1",
    "B972": "b97_2",
    "HCTH": "hcth407,hcth407",
}


def xc_for(dfttyp):
    key = dfttyp.upper().replace("-", "")
    if key not in XC_MAP:
        raise InputError(
            "DFTTYP=%s is not supported. Supported: %s"
            % (dfttyp, ", ".join(sorted(XC_MAP))))
    return XC_MAP[key]
