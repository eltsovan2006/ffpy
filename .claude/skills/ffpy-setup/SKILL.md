---
name: ffpy-setup
description: Проверка готовности окружения ffpy со стороны Claude. Используй при первом запросе по ffpy в новой сессии или машине, по слову "setup" или если tools/accept.py падает. Всю настройку делает Antigravity, Claude только проверяет.
---

# ffpy-setup (Claude)

Тяжёлую настройку (venv, зависимости, заполнение AGENTS.md, базовые тесты) делает Antigravity в режиме SETUP скилла ffpy-coder. Claude настройку не делает, чтобы не тратить лимит.

1. Выполни одну команду: `python tools/accept.py --check`.
2. Если есть «НЕТ» или «TODO», ничего не чини сам. Ответь пользователю:
   «Отправьте в Antigravity: `Прочитай .agents/skills/ffpy-coder/SKILL.md и выполни режим SETUP.` Потом снова напишите мне "ffpy setup"».
   Если нет git или python, назови команду установки (`winget install Git.Git` / `winget install Python.Python.3.12`).
3. Если всё ok, ответь 2–3 строками: окружение готово, сколько задач в каждом статусе, что делать дальше.

Не читай исходники, ENV.md и AGENTS.md целиком: хватает вывода `--check`.
