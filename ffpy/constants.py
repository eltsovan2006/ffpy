"""Physical constants used for input/output conversions.

The Bohr radius matches the value Firefly 8.2 uses (CODATA 2014), so
geometries given in Angstrom are converted the same way as in Firefly.
PySCF itself works in Bohr internally; we always hand it Bohr coordinates.
"""

BOHR_ANG = 0.52917721067          # Angstrom per Bohr (Firefly 8.2)
ANG_BOHR = 1.0 / BOHR_ANG
HARTREE_EV = 27.211386245988
HARTREE_KCAL = 627.5094740631
HARTREE_KJ = 2625.4996394799
AU_DEBYE = 2.541746473
EV_NM = 1239.84198
# |d mu / d Q| in e/sqrt(amu) -> D/(A*sqrt(amu))
E_TO_DEBYE_PER_ANG = AU_DEBYE / BOHR_ANG
# 1 D^2/(A^2 amu) in km/mol
IR_KMMOL = 42.2561
