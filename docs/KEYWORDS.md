# Поддерживаемые группы и ключи ffpy 0.2.0

> Ключи и значения по умолчанию записаны по документации GAMESS (US) / Firefly.
> Перед использованием в учебных расчётах каждую группу нужно сверить с
> официальным руководством Firefly из дистрибутива.

## Правила разбора

* Группа начинается с `$ИМЯ` и заканчивается `$END`, регистр не важен. По
  правилам Firefly `$` стоит со 2-й позиции строки; группа с 1-й позиции
  принимается, но с WARNING.
* Внутри группы — пары `КЛЮЧ=ЗНАЧЕНИЕ` через пробелы, можно на нескольких
  строках; массивы — `TEMP(1)=298.15,373.15`.
* Логические значения: `.TRUE.`, `.T.`, `.FALSE.`, `.F.`; числа можно писать
  с фортрановской экспонентой `1.0D-5`.
* `!` до конца строки — комментарий.
* Неизвестная группа или ключ — ошибка (код 1). Ключи из списка «Accepted
  with a WARNING» принимаются для совместимости и ни на что не влияют.
* Каждое применённое значение по умолчанию печатается в `.out` строкой
  `WARNING: default applied: ...`.

## $DATA

```
 $DATA
Заголовок
ГРУППА [порядок оси]
                                  <- пустая строка, если группа не C1
имя  Z  x  y  z                   <- только симметрически уникальные атомы
 $END
```

* Координаты в Å (`UNITS=ANGS`, по умолчанию) или бор (`UNITS=BOHR`);
  Å переводятся в бор с константой Firefly 8.2: 1 бор = 0.52917721067 Å.
* Элемент определяется по заряду ядра Z (1–54), имя атома — только метка.
* Группы: C1, CS, CI, CN n, CNV n, CNH n, DN n, DNH n, DND n, S2N n, T, TH,
  TD, O, OH. Ориентация — «master frame» GAMESS: главная ось z, ось C2′ в
  группах D — x, плоскость σv в CNV — xz, плоскость CS — xy. Атомы
  размножаются операциями группы, сам расчёт всегда идёт в C1.
* Базис внутри $DATA не поддерживается — нужна группа $BASIS.

## $VEC и GUESS=MOREAD

Файл `имя.dat` содержит итоговую геометрию (`$DATA`, C1) и орбитали (`$VEC`).
Чтобы продолжить расчёт с этих орбиталей, вставьте оба блока в новый вход и
добавьте `$GUESS GUESS=MOREAD NORB=n $END` (n напечатано в первой строке
.dat). Коэффициенты записаны в порядке АО PySCF, поэтому `$VEC` из
настоящего Firefly/GAMESS не подходит. Для UHF в `$VEC` идут сначала
α-, затем β-орбитали.

## Соответствие методов и RUNTYP

| Метод | ENERGY | GRADIENT | OPTIMIZE | HESSIAN |
|---|---|---|---|---|
| RHF / UHF | да | да | да | да |
| ROHF | да | да | да | нет |
| DFT (RKS / UKS) | да | да | да | да |
| DFT (ROKS) | да | да | да | нет |
| MP2 (RHF, UHF) | да | да | да | нет |
| CASSCF (1 состояние) | да | да | да | нет |
| CASSCF (NSTATE>1, усреднение) | да | нет | нет | нет |
| TDHF / CIS / TDDFT / TDA (RHF, UHF) | да | да (IROOT) | да (IROOT) | нет |
| $PCM | с HF, DFT, TDHF/TDDFT | с HF, DFT | с HF, DFT | с RHF/UHF, RKS/UKS |

Неподдерживаемая комбинация — ошибка с кодом 2; метод не подменяется.

## Особенности, о которых стоит помнить

* `ISPHER=-1` (по умолчанию, как в GAMESS): d- и f-функции декартовы
  (6D/10F). Для cc-pVXZ обычно ставят `ISPHER=1`.
* MP2 по умолчанию с замороженным химическим остовом (как в GAMESS);
  `$MP2 NACORE=0` — все электроны.
* `DFTTYP=B3LYP` → `b3lyp5` (VWN5, как в GAMESS/Firefly);
  `B3LYP1` / `B3LYPV1R` → `b3lypg` (VWN1-RPA, как в Gaussian). Таблицу нужно
  проверить на одной молекуле против настоящего Firefly.
* DFT-сетка — по умолчанию PySCF (`grids.level=3`); `$DFT NRAD=, NLEB=`
  задают радиальную и угловую сетку. Поэтому энергии DFT расходятся с
  Firefly примерно в 4-м знаке.
* Частоты: массы самых распространённых изотопов; ИК-интенсивности — из
  производных дипольного момента численным дифференцированием (6N SCF).
* Оптимизация: geomeTRIC; критерий Firefly `OPTTOL` (максимальный
  градиент) плюс RMS-градиент < OPTTOL/3, плюс собственные критерии
  geomeTRIC по энергии и смещению.
* По умолчанию считается в min(8, число ядер) потоков: для молекул
  учебного размера больше 8 потоков не ускоряет расчёт. Изменить:
  `ffpy -n 4 water.inp`. MKL работает в последовательном режиме
  (`MKL_THREADING_LAYER=SEQUENTIAL`), параллелит сам PySCF.

## Таблицы ключей

### $CONTRL

| Key | Values | Default | Meaning |
|---|---|---|---|
| SCFTYP | RHF, UHF, ROHF, MCSCF | RHF | reference wavefunction |
| RUNTYP | ENERGY, GRADIENT, OPTIMIZE, HESSIAN | ENERGY | job type |
| DFTTYP | see below | NONE | DFT functional |
| MPLEVL | 0, 2 | 0 | MP2 when 2 |
| CITYP | NONE, CIS | NONE | CIS excited states |
| TDDFT | NONE, EXCITE | NONE | TDDFT excited states |
| ICHARG | integer | 0 | molecular charge |
| MULT | integer | 1 | spin multiplicity |
| UNITS | ANGS, BOHR | ANGS | units of $DATA coordinates |
| MAXIT | integer | 30 | max SCF iterations |
| ISPHER | -1, 0, 1 | -1 | -1/0 Cartesian d,f; 1 spherical |
| COORD | UNIQUE, CART | UNIQUE | coordinate input style |
| NZVAR | 0 | 0 | internal coordinates (only 0) |
| EXETYP | RUN, CHECK | RUN | CHECK: parse input only |

Accepted with a WARNING, no effect: AIMPAC, D5, FRIEND, ICUT, INTTYP, ITOL, MOLPLT, NORMF, NORMP, NOSYM, NPRINT, NUMGRD, PLTORB, QMTTOL

### $SYSTEM

| Key | Values | Default | Meaning |
|---|---|---|---|
| MWORDS | number | — | memory in 10^6 words (8 MB); not set = PySCF default 4000 MB |
| TIMLIM | number | 525600 | time limit, minutes |

Accepted with a WARNING, no effect: KDIAG, MEMDDI, MKLNP, NOJAC, NP, PARALL

### $BASIS

| Key | Values | Default | Meaning |
|---|---|---|---|
| GBASIS | text | — | basis family (required) |
| NGAUSS | integer | — | number of Gaussians |
| NDFUNC | 0, 1, 2, 3 | 0 | d functions on heavy atoms |
| NFFUNC | 0, 1 | 0 | f functions on heavy atoms |
| NPFUNC | 0, 1, 2, 3 | 0 | p functions on H |
| DIFFSP | .TRUE./.FALSE. | .FALSE. | diffuse sp on heavy atoms |
| DIFFS | .TRUE./.FALSE. | .FALSE. | diffuse s on H |
| POLAR | POPLE | POPLE | polarization exponents |

### $GUESS

| Key | Values | Default | Meaning |
|---|---|---|---|
| GUESS | HUCKEL, HCORE, MOREAD | HUCKEL | initial orbitals |
| NORB | integer | — | number of orbitals in $VEC (MOREAD) |

Accepted with a WARNING, no effect: MIX, PRTMO, PUNMO, TOLE, TOLZ

### $SCF

| Key | Values | Default | Meaning |
|---|---|---|---|
| DIRSCF | .TRUE./.FALSE. | .FALSE. | direct SCF |
| NCONV | integer | 5 | density convergence 10^-NCONV |
| CONV | number | — | density convergence (overrides NCONV) |
| DIIS | .TRUE./.FALSE. | .TRUE. | DIIS extrapolation |
| SOSCF | .TRUE./.FALSE. | .FALSE. | second-order SCF (PySCF newton) |
| DAMP | .TRUE./.FALSE. | .FALSE. | density damping |
| SHIFT | .TRUE./.FALSE. | .FALSE. | level shift |

Accepted with a WARNING, no effect: DIRTHR, EXTRAP, FDIFF, NPREO, NPUNCH, RSTRCT

### $DFT

| Key | Values | Default | Meaning |
|---|---|---|---|
| NRAD | integer | — | radial points per atom (with NLEB) |
| NLEB | integer | — | Lebedev angular points (with NRAD) |

Accepted with a WARNING, no effect: DC, IDCVER, METHOD

### $MP2

| Key | Values | Default | Meaning |
|---|---|---|---|
| NACORE | integer | — | frozen core orbitals; not set = chemical core |

Accepted with a WARNING, no effect: CODE, CUTOFF, METHOD, MP2PRP, NBCORE

### $STATPT

| Key | Values | Default | Meaning |
|---|---|---|---|
| NSTEP | integer | 20 | max optimization steps |
| OPTTOL | number | 0.0001 | max gradient, Hartree/Bohr |
| HSSEND | .TRUE./.FALSE. | .FALSE. | hessian at the optimized geometry |

Accepted with a WARNING, no effect: HESS, IFOLOW, IHREP, METHOD, NPRT, NPUN, STPT

### $FORCE

| Key | Values | Default | Meaning |
|---|---|---|---|
| TEMP | numbers, KEY(1)=a,b,... | 298.15 | thermochemistry temperatures, K |
| METHOD | ANALYTIC, SEMINUM, FULLNUM | ANALYTIC | hessian method (always analytic in ffpy) |
| VIBANL | .TRUE./.FALSE. | .TRUE. | normal mode analysis |

Accepted with a WARNING, no effect: NVIB, PRTIFC, PURIFY, VIBSIZ

### $TDDFT

| Key | Values | Default | Meaning |
|---|---|---|---|
| NSTATE | integer | 1 | number of excited states |
| IROOT | integer | 1 | state for gradient/optimization |
| MULT | 1, 3 | 1 | excited-state multiplicity (closed shell) |
| TDA | .TRUE./.FALSE. | .FALSE. | Tamm-Dancoff approximation |

Accepted with a WARNING, no effect: NLEB, NRAD, PRTTOL

### $CIS

| Key | Values | Default | Meaning |
|---|---|---|---|
| NSTATE | integer | 1 | number of excited states |
| IROOT | integer | 1 | state for gradient/optimization |
| MULT | 1, 3 | 1 | excited-state multiplicity (closed shell) |

### $DET

| Key | Values | Default | Meaning |
|---|---|---|---|
| NCORE | integer | — | doubly occupied core orbitals (required) |
| NACT | integer | — | active orbitals (required) |
| NELS | integer | — | active electrons (required) |
| NSTATE | integer | 1 | CI roots; >1 = state-averaged CASSCF |
| WSTATE | numbers, KEY(1)=a,b,... | — | state-averaging weights; not set = equal |

Accepted with a WARNING, no effect: CVGTOL, ITERMX, NHGSS, NSTGSS, PURES

### $MCSCF

| Key | Values | Default | Meaning |
|---|---|---|---|
| CISTEP | ALDET | ALDET | CI solver |
| FORS | .TRUE./.FALSE. | .TRUE. | full optimized reaction space (only .TRUE.) |
| MAXIT | integer | 100 | max macro-iterations |
| ACURCY | number | 1e-05 | orbital gradient convergence |

Accepted with a WARNING, no effect: FOCAS, FULLNR, JACOBI, QUAD, SOSCF

### $PCM

| Key | Values | Default | Meaning |
|---|---|---|---|
| SOLVNT | see below | — | solvent name |
| EPS | number | — | dielectric constant (overrides SOLVNT) |
| IEF | integer | -10 | IEF-PCM flavour (ffpy always uses IEF-PCM) |

Accepted with a WARNING, no effect: EPSINF, ICAV, ICOMP, IDISP, IDP, RSOLV

### DFTTYP values

| DFTTYP | PySCF xc |
|---|---|
| SLATER | `slater` |
| SVWN | `lda,vwn5` |
| SVWN5 | `lda,vwn5` |
| SVWN1RPA | `lda,vwn_rpa` |
| B88 | `b88,` |
| BLYP | `b88,lyp` |
| BP86 | `b88,p86` |
| BPW91 | `b88,pw91` |
| PW91 | `pw91,pw91` |
| PBE | `pbe,pbe` |
| REVPBE | `revpbe,pbe` |
| PBE0 | `pbe0` |
| PBE1PBE | `pbe0` |
| B3LYP | `b3lyp5` |
| B3LYP5 | `b3lyp5` |
| B3LYP1 | `b3lypg` |
| B3LYPV1R | `b3lypg` |
| B3PW91 | `b3pw91` |
| B3P86 | `b3p86` |
| X3LYP | `x3lyp` |
| BHHLYP | `bhandhlyp` |
| TPSS | `tpss,tpss` |
| TPSSH | `tpssh` |
| M05 | `m05` |
| M052X | `m052x` |
| M06 | `m06` |
| M06L | `m06l,m06l` |
| M062X | `m062x` |
| M06HF | `m06hf` |
| CAMB3LYP | `camb3lyp` |
| WB97X | `wb97x` |
| B97 | `b97` |
| B971 | `b97_1` |
| B972 | `b97_2` |
| HCTH | `hcth407,hcth407` |

### SOLVNT values

ACETONE (20.7), ACETONITRILE (35.7), ANILINE (6.89), BENZENE (2.25), C2H5OH (24.6), C6H6 (2.25), CCL4 (2.23), CH2CL2 (8.93), CH3CN (35.7), CH3OH (32.6), CHCL3 (4.9), CHLOROFORM (4.9), CLBENZ (5.62), CLFORM (4.9), CTCL (2.23), CYCHEX (2.02), CYCLOHEXANE (2.02), DICHLOROMETHANE (8.93), DMF (37.2), DMSO (46.7), ETHANOL (24.6), H2O (78.4), HEPTANE (1.92), METHANOL (32.6), METHYCL (8.93), NEPTANE (1.92), NITMET (38.2), THF (7.58), TOLUENE (2.38), WATER (78.4)

### Groups rejected with a clear error

$ZMAT (internal coordinates), $EFRAG (EFP), $EFP (EFP), $FMO (FMO), $XMCQDPT (XMCQDPT2), $MCQDPT (MCQDPT), $CIDRT (GUGA CI), $ECP (effective core potentials), $TDHF (TDHF polarizabilities), $CCINP (coupled cluster), $EOMINP (EOM-CC), $RAMAN (Raman), $HESS (reading a $HESS group), $GRAD (reading a $GRAD group), $ELPOT (electrostatic potential), $LIBE (LIBE), $P2P (P2P parallelism), $DRT (GUGA)

### Exit codes

| Code | Meaning |
|---|---|
| 0 | normal termination |
| 1 | input error (unknown group/key, bad value, bad $DATA) |
| 2 | unsupported method x RUNTYP combination or feature |
| 3 | SCF (or CASSCF) did not converge |
| 4 | geometry optimization did not converge in NSTEP steps |
| 5 | time limit ($SYSTEM TIMLIM) exceeded |
| 9 | internal error |
