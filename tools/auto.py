#!/usr/bin/env python3
"""Автоматический режим ffpy через Antigravity CLI (agy), запасной вариант — gemini: Claude не нужен.

  python tools/auto.py --draft "баг/фича"   # Gemini пишет спецификацию .ai/tasks/NNN.md
  python tools/auto.py 007                  # Gemini выполняет задачу; при проблемах сам получает
                                            # замечания и переделывает (до --max попыток)
  python tools/auto.py --queue              # все задачи со статусом todo подряд
  python tools/auto.py --setup              # режим SETUP скилла ffpy-coder

  python tools/auto.py 007 --model gemini-3.8-flash-medium   # выбрать модель (или переменная GEMINI_MODEL)

Остановится сам, если кончится лимит Gemini (выход 3) — просто запустите позже.
При 503 («модель перегружена») ждёт 30/90/180/300 с и повторяет запрос, попытки не тратит.
Выход: 0 принято | 1 нужны люди/Claude | 2 ошибка | 3 лимит Gemini.
Полные логи Gemini — .ai/logs/ (в .gitignore).
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import accept  # noqa: E402

ROOT, AI = accept.ROOT, accept.AI
SKILL = "Прочитай .agents/skills/ffpy-coder/SKILL.md"
QUOTA_RE = re.compile(r"\b429\b|RESOURCE_EXHAUSTED|quota|rate.?limit|exhausted|usage limit|weekly limit|limit (reached|exceeded)", re.I)
TIMEOUT = 45 * 60


TRANSIENT_RE = re.compile(r"\b50[0-4]\b|UNAVAILABLE|overloaded|high demand|ECONNRESET|ETIMEDOUT|ENOTFOUND|network issue|"
                          r"\"retryable\":\s*true|socket is not connected|connection (reset|refused)|\bEOF\b", re.I)
BUSY_WAITS = tuple(int(x) for x in os.environ.get("FFPY_BUSY_WAITS", "0,30,90,180,300").split(","))


class Quota(Exception):
    pass


class Busy(Exception):
    """Сервер Gemini перегружен (503 и подобное): ждём и повторяем, попытка не тратится."""


def _backend() -> tuple[str, str]:
    """agy (Antigravity CLI) предпочтительнее: работает по тарифу Google AI. gemini — запасной вариант."""
    for name in ("agy", "gemini"):
        path = shutil.which(name)
        if not path:
            cand = Path.home() / ".local" / "bin" / name
            path = str(cand) if cand.exists() else None
        if path:
            return name, path
    print("STATUS: ERROR — не найден ни agy, ни gemini. "
          "agy: curl -fsSL https://antigravity.google/cli/install.sh | bash")
    sys.exit(2)


AGY_FAIL_RE = re.compile(r"AGY_ERROR|^\s*error:", re.I | re.M)


def _gemini_once(prompt: str, tag: str) -> str:
    name, g = _backend()
    model = os.environ.get("GEMINI_MODEL")
    env = dict(os.environ, GEMINI_CLI_TRUST_WORKSPACE="true")
    if name == "agy":
        cmd = [g, "-p", prompt, "--dangerously-skip-permissions", "--add-dir", str(ROOT)]
        if model:
            cmd += ["--model", model]
        if os.environ.get("GEMINI_EFFORT"):
            cmd += ["--effort", os.environ["GEMINI_EFFORT"]]
    else:
        cmd = [g, "-p", prompt, "--yolo", "--output-format", "json"] + (["-m", model] if model else [])
    (AI / "logs").mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return "[timeout]"
    out, errtxt = p.stdout or "", p.stderr or ""
    (AI / "logs" / f"{tag}-{time.strftime('%Y%m%d-%H%M%S')}.log").write_text(
        out + "\n--- STDERR ---\n" + errtxt, encoding="utf-8")
    resp, err = "", ""
    if name == "agy":
        resp = out
        failed = p.returncode != 0 or bool(AGY_FAIL_RE.search(out))
    else:
        try:
            d = json.loads(out)
            resp = d.get("response") or ""
            err = json.dumps(d.get("error") or "", ensure_ascii=False)
        except (json.JSONDecodeError, TypeError, AttributeError):
            resp = out
        failed = p.returncode != 0 or bool(err.strip('"'))
    blob = err + errtxt + (out if failed else "")
    if failed and QUOTA_RE.search(blob):
        raise Quota()
    no_answer = not resp.strip() or (name == "agy" and failed)
    if failed and no_answer and re.search(
            r"ModelNotFound|no longer available|is not found for API version|model.{0,40}not (found|available)|invalid model selection", blob, re.I):
        print("STATUS: ERROR — модель недоступна. Список: `agy models`. Укажите --model <имя>.\n"
              + accept.tail(blob, 3))
        sys.exit(2)
    if failed and no_answer and TRANSIENT_RE.search(blob):
        raise Busy()
    if failed and not resp.strip():
        resp = f"[{name} exit {p.returncode}] " + accept.tail(errtxt or out, 3)
    print(f"  {name} {tag}: {int(time.time() - t0)} c — {accept.tail(resp, 1)[:120]}")
    return resp


def gemini(prompt: str, tag: str) -> str:
    for wait in BUSY_WAITS:
        if wait:
            print(f"  Gemini перегружен (503), жду {wait} с и повторяю тот же запрос…")
            time.sleep(wait)
        try:
            return _gemini_once(prompt, tag)
        except Busy:
            continue
    raise Busy()


def check_quiet(tid: str) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = accept.accept(tid)
    return code, buf.getvalue()


def ensure_clean():
    if accept.run(["git", "status", "--porcelain", "--untracked-files=no"]).stdout.strip():
        print("STATUS: ERROR — есть незакоммиченные изменения (git commit / git stash)")
        sys.exit(2)


def do_task(tid: str, max_attempts: int) -> int:
    ensure_clean()
    main = accept.run(["git", "branch", "--show-current"]).stdout.strip()
    has_branch = accept.run(["git", "rev-parse", "--verify", "--quiet", f"gemini/{tid}"]).returncode == 0
    fb = AI / "feedback" / f"{tid}.md"
    out = ""
    for attempt in range(1, max_attempts + 1):
        if attempt == 1 and not (has_branch and fb.exists()):
            prompt = f"{SKILL} и выполни задачу .ai/tasks/{tid}.md"
        else:
            prompt = (f"{SKILL}. Задача {tid} не принята, замечания в .ai/feedback/{tid}.md "
                      f"(прочитай их ДО переключения на ветку) — исправь")
        gemini(prompt, f"{tid}-a{attempt}")
        accept.run(["git", "checkout", "-q", main])  # на случай, если Gemini не вернулся
        if accept.run(["git", "status", "--porcelain", "--untracked-files=no"]).stdout.strip():
            accept.commit(f"auto {tid}: остатки после попытки {attempt}")  # только .ai/
        code, out = check_quiet(tid)
        if code == 0:
            print(f"{tid}: ACCEPT после {attempt} попыт.")
            return 0
        if code == 2 and "ветки" not in out:
            print(out.strip())
            return 2
        fb.parent.mkdir(parents=True, exist_ok=True)
        fb.write_text(f"# Замечания к {tid} (автопроверка после попытки {attempt})\n\n```\n{out.strip()}\n```\n"
                      "Исправь всё перечисленное: тесты должны быть зелёными, файлы вне Scope — вернуть как было, "
                      "отчёт — STATUS: done без пунктов «Не сделано».\n", encoding="utf-8")
        accept.set_status(tid, "needs-fix", attempts_inc=True)
        accept.commit(f"auto {tid}: feedback {attempt}")
    print(f"{tid}: НЕ ПРИНЯТО за {max_attempts} попыток → «ffpy: прими {tid}» в Claude Code")
    print("\n".join(out.strip().splitlines()[:8]))
    return 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("task_id", nargs="?")
    ap.add_argument("--draft")
    ap.add_argument("--queue", action="store_true")
    ap.add_argument("--setup", action="store_true")
    ap.add_argument("--max", type=int, default=6, help="попыток Gemini на задачу (по умолч. 6)")
    ap.add_argument("--model", help="модель (список: agy models), например gemini-3.8-flash-medium; иначе GEMINI_MODEL или по умолчанию")
    ap.add_argument("--effort", help="усилие рассуждения agy: low|medium|high|xhigh|max")
    a = ap.parse_args()
    if a.effort:
        os.environ["GEMINI_EFFORT"] = a.effort
    if a.model:
        os.environ["GEMINI_MODEL"] = a.model
    start = accept.run(["git", "branch", "--show-current"]).stdout.strip()
    try:
        if a.setup:
            gemini(f"{SKILL} и выполни режим SETUP.", "setup")
            return accept.check()
        if a.draft:
            ensure_clean()
            r = gemini(f"{SKILL}, режим ЧЕРНОВИК: {a.draft}", "draft")
            print(accept.tail(r, 3))
            return 0
        if a.queue:
            todo = [l.split("|")[1].strip() for l in accept.TASKS.read_text(encoding="utf-8").splitlines()
                    if re.match(r"^\|\s*\d{3}\s*\|[^|]*\|\s*todo\s*\|", l)] if accept.TASKS.exists() else []
            todo = [t for t in todo if (AI / "tasks" / f"{t}.md").exists()]
            worst = 0
            for t in todo:
                worst = max(worst, do_task(t, a.max))
            print(f"QUEUE: обработано {len(todo)}")
            return worst
        if a.task_id:
            return do_task(a.task_id.zfill(3), a.max)
        ap.error("укажите NNN, --draft, --queue или --setup")
    except (Quota, Busy) as e:
        if start:
            accept.run(["git", "checkout", "-q", start])  # вернуться на основную ветку
        if isinstance(e, Busy):
            print("STATUS: GEMINI_BUSY — сервер Gemini перегружен, запустите ту же команду через 10–30 минут "
                  "(или попробуйте другую модель: --model gemini-3.8-flash-medium)")
        else:
            print("STATUS: GEMINI_QUOTA — лимит Gemini исчерпан, запустите позже (прогресс сохранён)")
        return 3


if __name__ == "__main__":
    sys.exit(main())
