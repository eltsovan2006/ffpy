---
name: work
description: Один вход в воркфлоу ffpy. Используй на слово "work" (или "/work", "work: <задача>"): проверяет бюджет, окружение, ведёт очередь через Antigravity, принимает результат и выдаёт отчёт.
---

# work: запуск всего воркфлоу ffpy

Следуй правилам скилла `ffpy-orchestrate` (экономия, бюджет). Ответ пользователю ≤ 5 строк.

1. **Бюджет.** `get_usage` -> `python3 tools/budget.py start PCT` (если сессия новая) или `check PCT`. СТОП -> остановись.
2. **Состояние.** Субагент `ffpy-digest` (haiku): `python3 tools/accept.py --check` + `python3 tools/report.py`, вернуть ≤ 5 строк. Если окружение не готово -> `python3 tools/auto.py --setup` в фоне (`run_in_background`).
3. **Если указана задача** (`work: ...`): `python3 tools/auto.py --draft "..."` (Gemini пишет спеку) -> субагент `ffpy-spec-reviewer` проверяет физику -> статус `todo`.
4. **Очередь.** Есть `todo` -> `python3 tools/auto.py --queue` в фоне. По уведомлению: `python3 tools/accept.py NNN`; ACCEPT -> сообщи; PROBLEMS -> `.ai/feedback/NNN.md` + `--reject` (после 3-й попытки предложи разбить задачу).
5. **Слияние** только по слову пользователя: `python3 tools/accept.py NNN --merge`. Ничего не пушь.
6. **Итог.** Коротко: сделано / в работе / дальше (из `.ai/REPORT.md`) и остаток бюджета. В конце напомни `/clear`.

Нет задач и нет запроса -> покажи отчёт и предложи верхний пункт `.ai/ROADMAP.md`.
