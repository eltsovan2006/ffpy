"""name.xyz: optimization trajectory (multi-frame XYZ, Angstrom)."""

from ffpy.constants import BOHR_ANG


def write(path, symbols, trajectory):
    with open(path, "w", encoding="ascii", newline="\n") as f:
        for k, (e, coords) in enumerate(trajectory):
            f.write("%d\n" % len(symbols))
            f.write("step %d  E = %.10f\n" % (k, e))
            for s, c in zip(symbols, coords * BOHR_ANG):
                f.write("%-3s %16.10f %16.10f %16.10f\n" % (s, c[0], c[1], c[2]))
