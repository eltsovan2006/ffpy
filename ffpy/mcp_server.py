"""MCP server for ffpy (stdio). Works with any MCP client.

    ffpy-mcp --workdir ~/ffpy-work            # read-only tools + file tools
    ffpy-mcp --workdir ~/ffpy-work --allow-run  # also run calculations

All file names are relative to the work directory; nothing outside it is
read or written.
"""

import argparse
import os
import sys

from ffpy import api, inputgen

try:  # mcp 2.x
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server

INSTRUCTIONS = (
    "ffpy runs Firefly/GAMESS-style quantum-chemistry inputs (.inp) with PySCF. "
    "Typical flow: build_input (or write the deck yourself; list_keywords shows what is supported), validate_input, "
    "write_input to save it in the work directory, run_calculation (if enabled), "
    "job_status until finished, then parse_output or read_file for details. "
    "Energies are in hartree, lengths in angstrom unless stated."
)


def build_server(workdir, allow_run=False, max_jobs=1, timeout=3600):
    mcp = _Server("ffpy", instructions=INSTRUCTIONS)
    jobs = api.JobManager(workdir, max_jobs=max_jobs, default_timeout=timeout)

    @mcp.tool()
    def list_keywords(group: str = "") -> dict:
        """List supported $GROUPs and keys (type, default, allowed values, help). Pass a group name such as CONTRL to see only that group."""
        return api.keywords(group or None)

    @mcp.tool()
    def validate_input(text: str) -> dict:
        """Check input deck text without running it. Returns ok, a one-line summary or the error (with line number when known), and warnings."""
        return api.validate(text)

    @mcp.tool()
    def write_input(name: str, text: str) -> dict:
        """Save an input deck as name (e.g. water.inp) in the work directory. Overwrites an existing file."""
        if not name.lower().endswith(".inp"):
            raise ValueError("input file names must end with .inp")
        path = api.safe_path(jobs.workdir, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return {"saved": name, "validation": api.validate(text)}

    @mcp.tool()
    def build_input(geometry: str, method: str = "HF", runtyp: str = "ENERGY", basis: str = "6-31G*",
                    charge: int = 0, mult: int = 1, functional: str = "B3LYP", title: str = "ffpy job",
                    nstep: int = 50, hssend: bool = False, excited: str = "", nstate: int = 5,
                    solvent: str = "", ncore: int = 0, nact: int = 2, nels: int = 2) -> dict:
        """Make an input deck from plain parameters (no Firefly syntax needed). geometry: 'Symbol x y z' lines or .xyz text, angstrom. method HF|DFT|MP2|CASSCF; runtyp ENERGY|GRADIENT|OPTIMIZE|HESSIAN (HESSIAN gives frequencies and thermochemistry); basis e.g. 6-31G*, cc-pVDZ; excited TDDFT|TDA|CIS or empty; solvent a PCM name such as WATER. Returns the deck text and its validation; save it with write_input."""
        text = inputgen.build_input(geometry, method, runtyp, basis, charge, mult, functional, title,
                                    nstep=nstep, hssend=hssend, excited=excited or None, nstate=nstate,
                                    solvent=solvent or None, ncore=ncore, nact=nact, nels=nels)
        return {"text": text, "validation": api.validate(text)}

    @mcp.tool()
    def geometry_from_output(name: str) -> str:
        """Last geometry of a finished .out file as .xyz text (angstrom); use it as the start geometry of the next calculation, e.g. frequencies after an optimization."""
        return api.geometry_xyz(api.safe_path(jobs.workdir, name))

    @mcp.tool()
    def compare_outputs(names: list[str]) -> dict:
        """Energies of several .out files with differences to the first one in hartree and kcal/mol (reaction energies, isomer or method comparison)."""
        return {"rows": api.compare_energies([api.safe_path(jobs.workdir, n) for n in names])}

    @mcp.tool()
    def list_files() -> list:
        """List files in the work directory (inputs, outputs, molden, restart, trajectories)."""
        res = []
        for root, _, files in os.walk(jobs.workdir):
            for f in sorted(files):
                full = os.path.join(root, f)
                res.append({"name": os.path.relpath(full, jobs.workdir),
                            "bytes": os.path.getsize(full)})
        return res

    @mcp.tool()
    def read_file(name: str, tail_lines: int = 0) -> str:
        """Read a text file from the work directory (e.g. water.out). tail_lines > 0 returns only the last lines."""
        path = api.safe_path(jobs.workdir, name)
        if tail_lines > 0:
            return "\n".join(api.tail(path, tail_lines))
        with open(path, encoding="utf-8", errors="replace") as f:
            data = f.read(2_000_000)
        return data

    @mcp.tool()
    def parse_output(name: str) -> dict:
        """Parse a finished .out file: status, energies, geometry bonds/angles, charges, frequencies, excited states."""
        return api.run_summary(api.safe_path(jobs.workdir, name))

    if allow_run:
        @mcp.tool()
        def run_calculation(name: str, threads: int = 0, timeout_s: int = 0) -> dict:
            """Queue a calculation of an .inp file from the work directory; it runs in the background (several can be queued, max_jobs run at once). Returns a job_id; use wait_for_job. threads 0 = automatic."""
            job_id = jobs.start(name, nproc=threads, timeout=timeout_s or None)
            return {"job_id": job_id, "state": jobs.status(job_id)["state"]}

        @mcp.tool()
        def job_status(job_id: str) -> dict:
            """State of a started job: queued, running (with the log tail) or finished/cancelled/timeout (with parsed results, exit code, thermochemistry)."""
            return jobs.status(job_id)

        @mcp.tool()
        def wait_for_job(job_id: str, timeout_s: int = 50) -> dict:
            """Wait up to timeout_s seconds (max 300) for a job to finish and return its status; call again if it is still running. Prefer this over polling job_status."""
            return jobs.wait(job_id, timeout_s)

        @mcp.tool()
        def cancel_job(job_id: str) -> dict:
            """Stop a running job."""
            return jobs.cancel(job_id)

    return mcp, jobs


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ffpy-mcp", description="MCP server (stdio) for ffpy")
    ap.add_argument("--workdir", default=os.environ.get("FFPY_MCP_WORKDIR", os.path.expanduser("~/ffpy-work")),
                    help="folder for inputs and results (default: ~/ffpy-work or $FFPY_MCP_WORKDIR)")
    ap.add_argument("--allow-run", action="store_true",
                    default=os.environ.get("FFPY_MCP_ALLOW_RUN") == "1",
                    help="also expose run_calculation/job_status/cancel_job (off by default)")
    ap.add_argument("--max-jobs", type=int, default=1, help="parallel calculations (default 1)")
    ap.add_argument("--timeout", type=int, default=3600, help="default time limit per job, seconds")
    args = ap.parse_args(argv)
    os.makedirs(args.workdir, exist_ok=True)
    server, jobs = build_server(args.workdir, args.allow_run, args.max_jobs, args.timeout)
    try:
        server.run(transport="stdio")
    finally:
        jobs.shutdown()


if __name__ == "__main__":
    sys.exit(main())
