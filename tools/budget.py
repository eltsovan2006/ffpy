#!/usr/bin/env python3
"""Бюджет Claude Code (5-часовое окно): не больше +25% за сессию, последние 35% не трогать.

  python tools/budget.py start PCT   # начало сессии: PCT = текущий % 5-часового окна (из get_usage)
  python tools/budget.py check PCT   # перед дорогим действием; выход 0 можно | 1 СТОП

PCT Claude берёт из mcp__ccd_session_mgmt__get_usage (plan -> 5-часовое окно, percent used).
Состояние: .ai/budget.json (не в git).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

STATE = Path(__file__).resolve().parent.parent / ".ai" / "budget.json"
SESSION_CAP = 25.0   # максимум прироста за сессию, п.п.
RESERVE = 35.0       # резерв: выше 100-35=65% не заходим


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] not in ("start", "check"):
        print(__doc__)
        return 2
    pct = float(argv[2])
    if argv[1] == "start":
        STATE.write_text(json.dumps({"baseline": pct}))
        print(f"OK baseline={pct:.0f}%  лимит сессии до {min(pct + SESSION_CAP, 100 - RESERVE):.0f}%")
        return 0
    base = json.loads(STATE.read_text())["baseline"] if STATE.exists() else pct
    ceiling = min(base + SESSION_CAP, 100 - RESERVE)
    if pct >= ceiling:
        why = "резерв 35% не трогаем" if ceiling == 100 - RESERVE else "исчерпан бюджет сессии +25%"
        print(f"STOP: {pct:.0f}% >= {ceiling:.0f}% ({why}). Остановись и сообщи пользователю.")
        return 1
    print(f"OK: {pct:.0f}% из {ceiling:.0f}% (осталось {ceiling - pct:.0f} п.п.)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
