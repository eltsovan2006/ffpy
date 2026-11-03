"""Onsager-Kirkwood self-consistent reaction field (Firefly $SCRF, Zerner's method A).

Spherical cavity of radius a, solute potential represented by its dipole;
reaction field R = G * mu with G = 2 (eps - 1) / ((2 eps + 1) a^3). The
solvation energy is -G mu.mu / 2 (plus a Born term for an ion, which is
not implemented: charged solutes are refused).
"""

import numpy as np
from pyscf import lib

ANGSTROM = 1.0 / 0.52917721067


def reaction_field_g(dielec, radius_angstrom):
    a = radius_angstrom * ANGSTROM
    return 2.0 * (dielec - 1.0) / ((2.0 * dielec + 1.0) * a ** 3)


def attach(mf, g):
    """Return a copy of the SCF object that includes the reaction field."""
    mol = mf.mol
    dip = mol.intor("int1e_r", comp=3)
    nuc = np.einsum("i,ix->x", mol.atom_charges(), mol.atom_coords())

    def field(dm):
        d = np.asarray(dm)
        if d.ndim == 3:
            d = d[0] + d[1]
        mu = nuc - np.einsum("xij,ji->x", dip, d)
        return -0.5 * g * float(mu @ mu), g * np.einsum("x,xij->ij", mu, dip)

    class WithReactionField(mf.__class__):
        # same layout as PySCF's solvent models: the field is kept out of vhf and added to h1e
        def get_veff(self, mol=None, dm=None, *args, **kwargs):
            vhf = super().get_veff(mol, dm, *args, **kwargs)
            e, v = field(dm)
            return lib.tag_array(vhf, e_rf=e, v_rf=v)

        def get_fock(self, h1e=None, s1e=None, vhf=None, dm=None, *args, **kwargs):
            if h1e is not None and dm is not None and vhf is not None and hasattr(vhf, "v_rf"):
                h1e = h1e + vhf.v_rf
            return super().get_fock(h1e, s1e, vhf, dm, *args, **kwargs)

        def energy_elec(self, dm=None, h1e=None, vhf=None):
            e_tot, e2 = super().energy_elec(dm, h1e, vhf)
            return e_tot + vhf.e_rf, e2

    new = WithReactionField.__new__(WithReactionField)
    new.__dict__.update(mf.__dict__)
    return new
