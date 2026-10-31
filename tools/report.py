#!/usr/bin/env python3
"""Сводный отчёт: что сделано (по очереди задач и отчётам) и что планируется (.ai/ROADMAP.md).

  python tools/report.py        # печатает и пишет .ai/REPORT.md
Расход Claude не нужен: скрипт только читает файлы.
"""
from __future__ import annotations

import datetime
from pathlib import Path

AI = Path(__file__).resolve().parent.parent / ".ai"


def rows() -> list[list[str]]:
    out = []
    for line in (AI / "TASKS.md").read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.startswith("|") and len(cells) >= 5 and cells[0].isdigit():
            out.append(cells)
    return out


def main() -> None:
    tasks = rows()
    parts = [f"# Отчёт ffpy, {datetime.date.today()}", ""]
    for title, states in (("Сделано", ("accepted", "merged")),
                          ("В работе", ("in-progress", "needs-fix")),
                          ("Очередь", ("todo", "draft"))):
        sel = [t for t in tasks if t[2] in states]
        parts.append(f"## {title} ({len(sel)})")
        parts += [f"- {t[0]} {t[1]} [{t[2]}, попыток {t[4]}]" for t in sel] or ["- пусто"]
        parts.append("")
    for rep in sorted((AI / "reports").glob("[0-9]*.md")):
        parts += [f"### Отчёт {rep.stem}", *rep.read_text(encoding="utf-8").splitlines()[:12], ""]
    road = AI / "ROADMAP.md"
    if road.exists():
        parts += ["## Планы", road.read_text(encoding="utf-8")]
    text = "\n".join(parts)
    (AI / "REPORT.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
