"""Error types. Each carries the exit code printed on the last line of the log."""


class FfpyError(Exception):
    code = 9
    label = "INTERNAL ERROR"


class InputError(FfpyError):
    code = 1
    label = "INPUT ERROR"


class UnsupportedError(FfpyError):
    code = 2
    label = "UNSUPPORTED"


class SCFNotConverged(FfpyError):
    code = 3
    label = "SCF NOT CONVERGED"


class OptNotConverged(FfpyError):
    code = 4
    label = "OPTIMIZATION NOT CONVERGED"


class TimeLimitExceeded(FfpyError):
    code = 5
    label = "TIME LIMIT EXCEEDED"


EXIT_CODES = {
    0: "normal termination",
    1: "input error (unknown group/key, bad value, bad $DATA)",
    2: "unsupported method x RUNTYP combination or feature",
    3: "SCF (or CASSCF) did not converge",
    4: "geometry optimization did not converge in NSTEP steps",
    5: "time limit ($SYSTEM TIMLIM) exceeded",
    9: "internal error",
}
