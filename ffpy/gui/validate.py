"""Check an input text the same way ffpy does before a run (no PySCF needed)."""

import re
from dataclasses import dataclass, field
from typing import List, Optional

from ffpy.errors import FfpyError


@dataclass
class Check:
    ok: bool
    message: str
    line: Optional[int] = None
    warnings: List[str] = field(default_factory=list)


def check_text(text):
    from ffpy.dispatcher import select
    from ffpy.job import build_job
    from ffpy.parser import parse_input

    if not text.strip():
        return Check(False, "Пустой файл")
    try:
        deck = parse_input(text)
        job = build_job(deck)
        select(job)
    except FfpyError as e:
        m = re.search(r"line (\d+)", str(e))
        return Check(False, "%s: %s" % (e.label, e), int(m.group(1)) if m else None)
    except Exception as e:  # a bug in ffpy should not take the editor down
        return Check(False, "внутренняя ошибка проверки: %s: %s" % (type(e).__name__, e))
    summary = "%s · %s · атомов: %d · заряд %d · мультиплетность %d" % (
        job.describe(), job.runtyp, len(job.labels), job.charge, job.mult)
    return Check(True, summary, None, [n for _, n in deck.notes])
