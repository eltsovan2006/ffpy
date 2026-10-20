"""Command line: ffpy water.inp"""

import argparse
import os
import sys
import time
import traceback

from ffpy import PROGRAM, __version__
from ffpy.errors import EXIT_CODES, FfpyError

DEFAULT_MAX_THREADS = 8

USAGE_EXAMPLE = """examples:
  ffpy water.inp                 writes water.out, water.molden, water.dat (+ water.xyz)
  ffpy water.inp -n 8 -o results
  ffpy water.inp --check         read and validate the input only
  ffpy --keywords                list supported groups and keys
"""


def _read_text(path):
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "cp1251", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", "replace")


def _launched_from_explorer():
    """True when Windows created a console just for us (double-click / drag&drop)."""
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return False
    try:
        import ctypes
        buf = (ctypes.c_uint * 4)()
        return ctypes.windll.kernel32.GetConsoleProcessList(buf, 4) <= 1
    except Exception:
        return False


def _pause():
    try:
        input("\nPress Enter to close this window...")
    except EOFError:
        pass


def print_keywords():
    from ffpy.schema import IGNORED, SCHEMA
    from ffpy.parser import fmt_value
    print("Supported input groups (see docs/KEYWORDS.md for details):\n")
    print(" $DATA   title / point group / atoms: name Z x y z")
    print(" $VEC    orbitals from an ffpy .dat file (GUESS=MOREAD)\n")
    for g, keys in SCHEMA.items():
        print(" $%s" % g)
        for k, spec in keys.items():
            d = "" if spec.default is None else " [default %s]" % fmt_value(spec.default)
            ch = "" if not spec.choices or len(spec.choices) > 8 else \
                " {%s}" % ",".join(fmt_value(c) for c in spec.choices)
            print("    %-8s %s%s%s" % (k, spec.help, ch, d))
        if IGNORED.get(g):
            print("    accepted, no effect: %s" % ", ".join(sorted(IGNORED[g])))
        print()
    print("Exit codes:")
    for c, m in EXIT_CODES.items():
        print("  %d  %s" % (c, m))


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog=PROGRAM, formatter_class=argparse.RawDescriptionHelpFormatter,
        description="%s %s: runs Firefly/GAMESS-style inputs with PySCF" % (PROGRAM, __version__),
        epilog=USAGE_EXAMPLE)
    ap.add_argument("input", nargs="?", help="input file (.inp)")
    ap.add_argument("-o", "--outdir", help="directory for output files (default: next to the input)")
    ap.add_argument("-n", "--nproc", type=int, default=0, help="number of threads (default: min(8, cores))")
    ap.add_argument("--gamess", action="store_true", help="add GAMESS-like blocks to the .out")
    ap.add_argument("--check", action="store_true", help="only read and validate the input")
    ap.add_argument("--debug", action="store_true", help="also write the PySCF log (name.pyscf.log)")
    ap.add_argument("-q", "--quiet", action="store_true", help="do not echo the log to the console")
    ap.add_argument("--keywords", action="store_true", help="list supported groups and keys")
    ap.add_argument("--version", action="version", version="%s %s" % (PROGRAM, __version__))
    args = ap.parse_args(argv)

    explorer = _launched_from_explorer()
    if args.keywords:
        print_keywords()
        if explorer:
            _pause()
        return 0
    if not args.input:
        ap.print_help()
        if explorer:
            print("\nDrag an .inp file onto ffpy.exe, or run it from a terminal: ffpy water.inp")
            _pause()
        return 1
    code = run_file(args)
    if explorer:
        _pause()
    return code


def run_file(args):
    t0, c0 = time.time(), time.process_time()
    path = args.input
    if not os.path.isfile(path):
        print("%s: input file not found: %s" % (PROGRAM, path), file=sys.stderr)
        return 1
    base = os.path.splitext(os.path.basename(path))[0]
    outdir = args.outdir or os.path.dirname(os.path.abspath(path))
    os.makedirs(outdir, exist_ok=True)
    stem = os.path.join(outdir, base)

    from ffpy.log import Log
    log = Log(stem + ".out", echo=not args.quiet)
    pyscf_fh = open(stem + ".pyscf.log", "w") if args.debug else None
    code, msg = 0, ""
    try:
        code, msg = _run(args, path, stem, log, pyscf_fh, t0)
    except FfpyError as e:
        code, msg = e.code, "%s: %s" % (e.label, e)
        log.blank()
        log(" ERROR: " + msg)
    except KeyboardInterrupt:
        code, msg = 9, "interrupted by user"
        log(" ERROR: " + msg)
    except Exception as e:
        code, msg = 9, "INTERNAL ERROR: %s: %s" % (type(e).__name__, e)
        log.blank()
        log(" ERROR: " + msg)
        for line in traceback.format_exc().splitlines():
            log("   " + line)
    wall, cpu = time.time() - t0, time.process_time() - c0
    log.blank()
    log(" wall time %.2f s, cpu time %.2f s, %d warning(s)" % (wall, cpu, len(log.warnings)))
    if code == 0:
        log(" %s TERMINATED NORMALLY" % PROGRAM)
    else:
        log(" %s TERMINATED ABNORMALLY: ERROR CODE %d (%s)" % (PROGRAM, code, msg))
    log.close()
    if pyscf_fh:
        pyscf_fh.close()
    return code


def _run(args, path, stem, log, pyscf_fh, t0):
    text = _read_text(path)
    from pyscf import lib

    from ffpy.writers import out
    # Course-size molecules gain nothing beyond ~8 threads; on hybrid (P+E
    # core) CPUs using every logical core is even slightly slower.
    nthreads = args.nproc or min(DEFAULT_MAX_THREADS, os.cpu_count() or 1)
    lib.num_threads(nthreads)
    out.header(log, path, lib.num_threads())
    out.echo_input(log, text)

    from ffpy.dispatcher import select
    from ffpy.job import build_job
    from ffpy.methods import Context, build_mol
    from ffpy.parser import parse_input

    deck = parse_input(text)
    job = build_job(deck)
    log.section("input check")
    for kind, note in deck.notes:
        log.warning(note)
    for d in job.defaults:
        log.warning("default applied: %s" % d)
    handler = select(job)
    log("  handler: %s" % handler.__name__)

    ctx = Context(job, log, t0=t0, pyscf_fh=pyscf_fh, gamess=args.gamess)
    mol = build_mol(job, ctx)
    out.job_summary(log, job, mol)
    out.geometry(log, job.labels, job.charges, job.coords, "input geometry")
    out.distances(log, job.labels, job.coords)
    if args.gamess:
        from ffpy.writers import gamess
        gamess.coordinates_bohr(log, job.symbols, job.charges, job.coords)
    if args.check or job.exetyp == "CHECK":
        log.blank()
        log("  input check only (%s): no calculation"
            % ("--check" if args.check else "EXETYP=CHECK"))
        return 0, ""

    res = handler(job, ctx)

    from ffpy.writers import dat, molden, xyz
    log.section("output files")
    molden.write(stem + ".molden", res, job.method, freq=ctx.freq,
                 trajectory=ctx.trajectory, symbols=job.symbols)
    log("  %s.molden   orbitals%s" % (os.path.basename(stem),
                                       ", frequencies" if ctx.freq is not None else ""))
    dat.write(stem + ".dat", job, res, res.e_tot, job.method)
    log("  %s.dat      final $DATA and $VEC (GUESS=MOREAD)" % os.path.basename(stem))
    if ctx.trajectory:
        xyz.write(stem + ".xyz", job.symbols, ctx.trajectory)
        log("  %s.xyz      optimization trajectory (%d frames)"
            % (os.path.basename(stem), len(ctx.trajectory)))
    if pyscf_fh:
        log("  %s.pyscf.log  PySCF debug log" % os.path.basename(stem))
    log.section("final result")
    log("  %-34s %20.10f" % ("FINAL ENERGY (HARTREE)", res.e_tot))
    return ctx.status, ctx.status_msg
