# ffpy — handoff notes for AI agents and new sessions

Read this before changing anything. User-facing docs are in Russian
(README.md, docs/KEYWORDS.md); this file is English to save context.
Talk to the user (Andrei, GitHub `eltsovan2006`) in Russian.

## What it is
Own re-implementation of the Firefly (GAMESS-like) quantum-chemistry front
end: reads Firefly/GAMESS `.inp`, computes with **PySCF**, writes `.out`
(own format), `.molden` (Chemcraft/Avogadro), `.dat` (restart: `$DATA`+`$VEC`),
`.xyz` (opt trajectory). Plus `ffpy-gui` (PySide6) editor/runner. Built from a
spec the user wrote (docx, not in repo) for a quantum-chemistry course.
Repo: github.com/eltsovan2006/ffpy (private). Releases v0.1.0, v0.2.0 carry
`ffpy-<ver>-win64.zip` (PyInstaller, no Python needed). Installed copy on the
user's PC: `C:\ffpy` (+ user PATH + desktop shortcut to ffpy-gui.exe).

**Legal frame from the spec (do not violate):** behaviour comes only from
docs, example I/O and running Firefly as a black box. Never disassemble
Firefly, never commit Firefly distribution files or full Firefly outputs, do
not imitate the Firefly header.

## Environment (Windows 11, PowerShell 5.1)
- conda env `C:\Users\User\miniforge3\envs\ffpy` (python 3.11, pyscf 2.14.0
  conda-forge win-64, geometric, pyside6, pyinstaller, pytest). Recreate:
  `conda env create -f environment.yml`.
- Without `conda activate` you must prepend to PATH:
  `$e;$e\Library\mingw-w64\bin;$e\Library\usr\bin;$e\Library\bin;$e\Scripts`
  or PySCF DLL loading fails (exit 127 / "DLL not found").
- Commands (repo root): `python -m ffpy examples\water_opt.inp`,
  `python -m ffpy.gui`, `python -m pytest` (~50 s, 57 tests),
  `powershell -ExecutionPolicy Bypass -File packaging\build.ps1` (~5 min).
- git/gh: `C:\Program Files\Git\cmd\git.exe`, `C:\Program Files\GitHub CLI\gh.exe`
  (gh is logged in). Commit messages end with the Co-Authored-By line the
  harness specifies. Long temp paths break `git commit -F`; put the message
  in `.git/MSG` instead.
- PowerShell 5.1 traps: a one-element pipeline result is a scalar (wrap in
  `@()`; this once corrupted the user's PATH via add_to_path.ps1);
  here-strings passed to native exes lose quotes (write a file instead);
  native stderr shows as red "errors" even on exit 0; `Compress-Archive`
  writes `\` in zip paths (use .NET `ZipFile`).

## Pipeline and modules (`ffpy/`)
```
.inp -> parser.parse_input -> Deck -> job.build_job -> Job
     -> dispatcher.select(job) -> handler -> runners/* (PySCF via methods.py)
     -> writers/* (.out log, .molden, .dat, .xyz)
```
- `schema.py` — every supported group/key: type, default, allowed values.
  `IGNORED` keys are accepted with a WARNING; anything unknown is an error
  (spec: never skip silently). `UNSUPPORTED_GROUPS` give a clear message.
- `parser.py` — `$GROUP ... $END` scanning; `$DATA`/`$VEC` kept raw; `!`
  comments; Fortran `1.0D-5`, `.T.`; `KEY(1)=a,b`. `Deck.get()` records every
  default actually used -> printed as `WARNING: default applied` (spec asks
  for that, hence many warnings per run).
- `job.py` — `Job` dataclass + `$DATA` parsing (element from nuclear charge,
  Å->bohr with **Firefly's 0.52917721067**), `$VEC` parsing, all cross-checks
  (charge/mult parity, RHF needs MULT=1, `$DET` electron count...).
  `job.method` is the dispatcher key: HF/DFT/MP2/CASSCF/TDHF/TDDFT.
- `symmetry.py` — expands symmetry-unique atoms in the GAMESS master frame
  (z principal axis, C2' on x for D groups, Cs plane = xy, Cnv sigma_v = xz).
  The calculation itself always runs in C1.
- `basis_map.py` (`GBASIS/NGAUSS/NDFUNC/...` -> e.g. `6-31g(d,p)`),
  `xc_map.py` (`DFTTYP` -> PySCF xc).
- `dispatcher.py` — one handler per (method, RUNTYP) + `_BLOCKED` combos.
  Unsupported pair -> UnsupportedError (exit 2); never substitute a method.
  Runners are imported lazily so `select()` works without PySCF (the GUI
  validates as you type).
- `methods.py` — the only PySCF-building code: `build_mol/build_scf/
  build_mp2/build_cas/build_td`, `compute()` (full method at a geometry ->
  `Result`), `gradient_scanner()`, `Context` (log, time limit, soft-fail
  status, trajectory, freq).
- `runners/` — `energy`, `gradient`, `optimize` (geomeTRIC), `hessian`,
  `report` (energies, orbitals, Mulliken+Löwdin, dipole, excited states).
- `writers/` — `out.py` (text blocks), `molden.py` (PySCF molden + `[FREQ]`,
  `[FR-NORM-COORD]`, `[INT]`, `[GEOCONV]`), `dat.py`, `xyz.py`, `gamess.py`
  (`--gamess` GAMESS-like blocks, written from memory, unverified).
- `cli.py` — argparse, exit codes (`errors.EXIT_CODES`: 0 ok, 1 input,
  2 unsupported, 3 SCF, 4 opt, 5 time, 9 internal). Last `.out` line is
  always `ffpy TERMINATED NORMALLY` or `... ABNORMALLY: ERROR CODE n (...)`.
  Hidden `--pipe` (UTF-8 line-buffered stdout, no pause) is for the GUI.
  Pauses on exit only when launched by double-click/drag&drop.
- `outparse.py` — parses `.out` back (tests + GUI results panel). **Coupled
  to the text layout in writers/out.py and report.py: change both together.**
- `__init__.py` sets `MKL_THREADING_LAYER=SEQUENTIAL` before NumPy loads (see below).

## Non-obvious decisions (and why)
- **MKL**: both conda-forge win-64 PySCF builds link `mkl_rt.3.dll` directly
  (OpenBLAS swap breaks `libnp_helper.dll`). Threaded MKL nested inside
  PySCF's OpenMP made DFT response/TDDFT up to 20x slower -> sequential MKL.
  Default threads `min(8, cores)`: no gain above ~8 on course-size molecules.
- `ISPHER=-1` default -> Cartesian d/f (`mol.cart=True`), as GAMESS; this is
  what makes RHF/6-31G* water match GAMESS (-76.0107465).
- MP2 freezes the chemical core by default (GAMESS behaviour), `$MP2 NACORE`.
- `B3LYP` -> `b3lyp5` (VWN5, GAMESS/Firefly style); `B3LYP1`/`B3LYPV1R` -> `b3lypg`.
  Assumption from memory — must be checked against Firefly.
- SCF convergence: `NCONV` (density, 1e-5) -> `conv_tol_grad=10^-NCONV`,
  `conv_tol=min(1e-9, that^2)`; `tight=True` for hessian/FD runs.
- Frequencies: PySCF `atom_mass_list(isotope_avg=False)` returns *integer
  mass numbers*; use `runners.hessian.isotope_masses()` (most abundant
  isotopes, like GAMESS). Thermo uses the `_MassMol` proxy for the same reason.
  IR intensities = central finite differences of the dipole (6N SCFs,
  0.005 bohr), since PySCF core has no analytic dipole derivatives.
- Optimization: geomeTRIC via `pyscf.geomopt.geometric_solver.kernel`,
  OPTTOL -> gmax, OPTTOL/3 -> grms, geomeTRIC's own energy/displacement
  criteria kept. geomeTRIC logging is silenced through a temp `logIni`
  (NullHandler). After convergence the full method is recomputed at the
  final geometry to print properties (costs one extra SCF).
- ENERGY with unconverged SCF finishes with outputs and exit 3 (soft fail);
  GRADIENT/OPTIMIZE/HESSIAN stop immediately (strict).
- `$VEC` in `.dat` is in **PySCF AO order**, not GAMESS order: only ffpy can
  read it back (MOREAD). UHF: alpha block then beta block.

## GUI (`ffpy/gui/`, PySide6)
`app.py` MainWindow (tabs, file tree dock, results dock, log + "Проверка
входа" docks, menus, QSettings `ffpy/ffpy-gui`); `editor.py` (CodeEditor
with gutter, FindBar, `FileTab`: `.inp` editable, `.out/.log/.dat/.xyz`
read-only with outline/copy/save-copy); `highlight.py`; `validate.py`
(`check_text` = parse+build_job+select); `runner.py` (queue; child process
`ffpy.exe --pipe` next to the GUI exe, or `python -m ffpy` from source;
CREATE_NO_WINDOW; reader thread -> Qt signals); `results.py` (HTML summary
from outparse); `builder.py` ("Новый расчёт" form -> validated `.inp`).
UI strings are Russian; the `.out` log stays English/ASCII. GUI tests run
offscreen (`QT_QPA_PLATFORM=offscreen`, `QT_QPA_FONTDIR=C:\Windows\Fonts`
for readable screenshots via `widget.grab()`); stub `QMessageBox` in
unattended runs or a modal box hangs the test.

## Packaging (`packaging/`)
`ffpy.spec`: two Analyses -> `ffpy.exe` (console) + `ffpy-gui.exe` (windowed)
in one COLLECT sharing `_internal`. Gotchas encoded there:
- `pyscf.lib.load_library` looks next to `pyscf\lib\*.dll` or in
  `sys.prefix\Library\bin` -> libcint/xc/xcfun are copied into `pyscf/lib`
  (root duplicates dropped).
- Dropped DLLs: MKL threading layers, scalapack/blacs/cdft/vml, TBB, hwloc,
  libxml2, unused Qt modules. **Keep ICU**: Qt6Core imports icuuc/icuin
  (dropping it broke 0.2.0's first build).
- `build.ps1` runs every example through the frozen exe without conda on
  PATH, smoke-tests the GUI (`--smoke-test`, 60 s timeout), zips via .NET.
- Release: `gh release create vX.Y.Z dist\ffpy-X.Y.Z-win64.zip ...`; uploads
  of ~280 MB sometimes drop: retry; note `--clobber` deletes the old asset
  first. Bump version in `ffpy/__init__.py`, `pyproject.toml`,
  `packaging/version_info.txt`, README/KEYWORDS headers.

## Tests (`tests/`)
`test_input.py` (parser/basis/xc/symmetry/dispatcher, no SCF),
`test_reference.py` (end-to-end on `tests/inputs/*.inp` vs `reference.json`
with the spec tolerances: HF/MP2 1e-6 Eh, DFT 1e-4, bonds 1e-3 Å, angles 0.1°,
freq 5 cm-1, Mulliken 0.01), `test_gui.py`. `make_reference.py` regenerates
entries whose `source` is `ffpy-regression` and keeps hand-entered ones.

## Status / open items
- **Not compared with real Firefly yet** — all reference numbers are ffpy's
  own. Next step: user runs `tests/inputs` in Firefly; put numbers into
  `reference.json` with `"source": "firefly"`. Check B3LYP/VWN choice there.
- Not supported (errors out): SA-CASSCF gradients, ROHF/ROKS hessian,
  MP2/CASSCF/TD hessian, ECP, z-matrix, XMCQDPT2/FMO/P2P.
- MP2 properties use the SCF density (unrelaxed). `--gamess` layout unverified.
- GUI was tested offscreen + screenshots; not click-tested by a human yet.
- Spec stages 1–5 are implemented; stage-5 "GAMESS-like mode" is best effort.
