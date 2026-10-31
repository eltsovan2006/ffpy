#!/usr/bin/env python3
"""Компактная приёмка задач ffpy для Claude (экономия лимита).

  python tools/accept.py --check       # готово ли окружение (≤ 8 строк)
  python tools/accept.py 007           # проверить ветку gemini/007: тесты, scope, отчёт (≤ 12 строк)
  python tools/accept.py 007 --merge   # слить gemini/007 в текущую ветку, статус merged
  python tools/accept.py 007 --reject  # статус needs-fix (замечания Claude пишет в .ai/feedback/007.md)

Выход: 0 — принять/успех, 1 — есть проблемы, 2 — ошибка.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AI = ROOT / ".ai"
TASKS = AI / "TASKS.md"
ALWAYS_ALLOWED = ("tests/", "test/", ".ai/")


def run(cmd, timeout=None):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def tail(text, n):
    lines = [l for l in (text or "").strip().splitlines() if l.strip()]
    return "\n".join(lines[-n:])


def py() -> str:
    env = __import__("os").environ.get("FFPY_PYTHON")
    if env:
        return env
    for p in (ROOT / ".venv" / "Scripts" / "python.exe", ROOT / ".venv" / "bin" / "python"):
        if p.exists():
            return str(p)
    return sys.executable


def test_cmd() -> list[str]:
    """Команда тестов из AGENTS.md (строка «- Тесты: `...`»), иначе pytest."""
    a = ROOT / "AGENTS.md"
    if a.exists():
        m = re.search(r"Тесты:\s*`([^`]+)`", a.read_text(encoding="utf-8"))
        if m and "TODO" not in m.group(1):
            cmd = m.group(1).split()
            if cmd[0] in ("python", "python3", "py"):
                cmd[0] = py()
            return cmd
    return [py(), "-m", "pytest", "-q", "--tb=line"]


def set_status(tid, status, attempts_inc=False):
    if not TASKS.exists():
        return
    lines = TASKS.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells and cells[0] == tid:
            cells += ["—"] * (5 - len(cells))
            cells[2] = status
            cells[3] = f"gemini/{tid}"
            if attempts_inc:
                cells[4] = str(int(cells[4]) + 1 if cells[4].isdigit() else 1)
            lines[i] = "| " + " | ".join(cells[:5]) + " |"
    TASKS.write_text("\n".join(lines) + "\n", encoding="utf-8")


def commit(msg):
    run(["git", "add", "-A", ".ai"])
    if run(["git", "diff", "--cached", "--quiet"]).returncode:
        run(["git", "commit", "-qm", msg])


def check() -> int:
    ok = True
    for name, cmd in (("git", ["git", "--version"]), ("python", [py(), "--version"])):
        p = run(cmd) if shutil.which(cmd[0]) or Path(cmd[0]).exists() else None
        good = p is not None and p.returncode == 0
        ok &= good
        print(f"{name}: {'ok ' + (p.stdout or p.stderr).strip() if good else 'НЕТ'}")
    repo = run(["git", "rev-parse", "--is-inside-work-tree"]).returncode == 0
    print(f"repo: {'ok' if repo else 'НЕТ (выполните setup в Antigravity)'}")
    print(f"venv: {'ok' if (ROOT / '.venv').exists() else 'нет'}")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8") if (ROOT / "AGENTS.md").exists() else ""
    print(f"AGENTS.md: {'ok' if 'Протокол обмена' in agents else 'нет раздела «Протокол обмена» (ИИ-workflow)'}")
    print(f"ENV.md: {'есть' if (AI / 'ENV.md').exists() else 'нет'}")
    if TASKS.exists():
        st = re.findall(r"^\|\s*\d{3}\s*\|[^|]*\|\s*([\w-]+)", TASKS.read_text(encoding="utf-8"), re.M)
        print("TASKS: " + (", ".join(f"{s}={st.count(s)}" for s in sorted(set(st))) or "пусто"))
    return 0 if ok and repo else 1


def scope_of(spec):
    m = re.search(r"^##\s*Scope.*?$(.*?)(?=^##\s|\Z)", spec, re.S | re.M)
    if not m:
        return []
    items = re.findall(r"^\s*[-*]\s*`?([^`\s]+)`?", m.group(1), re.M)
    return [i.replace("\\", "/") for i in items if "/" in i or "." in i]


def accept(tid) -> int:
    branch = f"gemini/{tid}"
    if run(["git", "rev-parse", "--verify", "--quiet", branch]).returncode:
        print(f"ERROR: ветки {branch} нет — Antigravity ещё не выполнил задачу")
        return 2
    if run(["git", "status", "--porcelain", "--untracked-files=no"]).stdout.strip():
        print("ERROR: есть незакоммиченные изменения — закоммитьте их или сделайте stash")
        return 2
    cur = run(["git", "branch", "--show-current"]).stdout.strip()
    base = run(["git", "merge-base", cur, branch]).stdout.strip()
    spec_p = AI / "tasks" / f"{tid}.md"
    spec = spec_p.read_text(encoding="utf-8") if spec_p.exists() else ""
    scope = scope_of(spec)
    changed = [l for l in run(["git", "diff", "--name-only", base, branch]).stdout.splitlines() if l]
    oos = [c for c in changed if scope and not c.startswith(ALWAYS_ALLOWED)
           and not any(c == s or c.startswith(s.rstrip("/") + "/") for s in scope)]
    report = run(["git", "show", f"{branch}:.ai/reports/{tid}.md"]).stdout

    run(["git", "checkout", "-q", branch])
    try:
        t = run(test_cmd(), timeout=30 * 60)
    finally:
        run(["git", "checkout", "-q", cur])
    tests_ok = t.returncode in (0, 5)

    rs = re.search(r"STATUS:\s*(\w+)", report)
    rep_status = rs.group(1) if rs else "нет отчёта"
    issues = []
    for sec in ("Не сделано", "Нужно вне scope"):
        m = re.search(rf"^##\s*{sec}.*?$(.*?)(?=^##\s|\Z)", report, re.S | re.M)
        items = [l.strip() for l in (m.group(1) if m else "").splitlines() if l.strip() not in ("", "-")]
        issues += [f"{sec}: {i.lstrip('- ')}" for i in items[:3]]

    ok = tests_ok and not oos and rep_status == "done" and not issues
    print(f"VERDICT: {'ACCEPT' if ok else 'PROBLEMS'}")
    print(f"REPORT: {rep_status}")
    print(f"TESTS: {'pass' if tests_ok else 'FAIL'} | {tail(t.stdout, 1)}")
    if not tests_ok:
        print(tail(t.stdout + t.stderr, 4))
    print(f"DIFF: {tail(run(['git', 'diff', '--stat', base, branch]).stdout, 1)}")
    if oos:
        print("OUT_OF_SCOPE: " + ", ".join(oos))
    for i in issues:
        print("ISSUE: " + i)
    if ok:
        set_status(tid, "accepted")
        commit(f"tasks: {tid} accepted")
    return 0 if ok else 1


def merge(tid) -> int:
    p = run(["git", "merge", "--no-ff", "-m", f"merge gemini/{tid}", f"gemini/{tid}"])
    if p.returncode:
        run(["git", "merge", "--abort"])
        print("ERROR: конфликт при слиянии, слияние отменено:\n" + tail(p.stdout + p.stderr, 5))
        return 2
    set_status(tid, "merged")
    commit(f"tasks: {tid} merged")
    print(f"MERGED: gemini/{tid}")
    return 0


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if args[0] == "--check":
        return check()
    tid = args[0].zfill(3)
    if "--merge" in args:
        return merge(tid)
    if "--reject" in args:
        set_status(tid, "needs-fix", attempts_inc=True)
        commit(f"tasks: {tid} needs-fix")
        print(f"{tid}: needs-fix. Передайте в Antigravity: «Задача {tid} не принята, см. .ai/feedback/{tid}.md»")
        return 0
    return accept(tid)


if __name__ == "__main__":
    sys.exit(main())
