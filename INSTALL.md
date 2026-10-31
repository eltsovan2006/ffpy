# ffpy: Antigravity кодит, Claude Code принимает

## Установка (один раз)
1. Распакуйте архив в корень папки ffpy, скрытые папки `.agents`, `.claude`, `.ai` тоже.
2. Откройте эту папку и в Antigravity, и в Claude Code.
3. В Claude Code выполните `/model sonnet`.

## Первый запуск
| Куда | Что отправить |
|---|---|
| Antigravity | `Прочитай .agents/skills/ffpy-coder/SKILL.md и выполни режим SETUP.` |
| Claude Code | `ffpy setup` |

## Цикл одной задачи
| Шаг | Куда | Что отправить |
|---|---|---|
| 1 | Antigravity | `Прочитай .agents/skills/ffpy-coder/SKILL.md, режим ЧЕРНОВИК: <описание бага или фичи>` |
| 2* | Claude Code | `ffpy: проверь спеку NNN` |
| 3 | Antigravity | `Прочитай .agents/skills/ffpy-coder/SKILL.md и выполни задачу .ai/tasks/NNN.md` |
| 4 | Claude Code | `ffpy: прими NNN` |
| 4а | Antigravity (если не принято) | `Прочитай .agents/skills/ffpy-coder/SKILL.md. Задача NNN не принята, замечания в .ai/feedback/NNN.md — исправь` → снова шаг 4 |
| 5 | Claude Code | `ffpy: слей NNN`, затем `/clear` |

\* Шаг 2 нужен только для задач с физикой или архитектурой: Antigravity сам напишет «нужна проверка Claude: да». Рутину (UI, рефакторинг) можно сразу отдавать на шаг 3.

Шаги 4 и 5 можно делать вообще без Claude: `python tools/accept.py NNN` и `python tools/accept.py NNN --merge` в терминале.

## Авторежим через Gemini CLI (без ручной пересылки)
Нужен Gemini CLI на той машине, где лежит репозиторий. Один раз запустите `gemini` и войдите через Google.

| Команда в терминале (в папке ffpy) | Что делает |
|---|---|
| `python tools/auto.py --setup` | SETUP вместо сообщения в Antigravity |
| `python tools/auto.py --draft "описание"` | черновик спецификации |
| `python tools/auto.py NNN` | Gemini кодит, скрипт проверяет; при проблемах Gemini получает замечания и переделывает (до 6 раз) |
| `python tools/auto.py --queue` | все задачи `todo` подряд, можно оставить на ночь |

Когда лимит Gemini кончается, скрипт останавливается и всё сохраняет. Запустите ту же команду позже.
Claude нужен только для `ffpy: проверь спеку NNN` (физика), для задач, не принятых за 6 попыток (`ffpy: прими NNN`), и для `ffpy: слей NNN` (можно и без него: `python tools/accept.py NNN --merge`).

## Где экономится лимит Claude
- Setup, черновики спецификаций, код, отладка до зелёных тестов и самопроверка делаются в Antigravity.
- Claude не читает исходники и не гоняет тесты. `tools/accept.py` печатает ему готовый вердикт на ~8 строк.
- Сабагентов нет: даже на Haiku они расходуют лимит Claude.
- Claude работает на Sonnet. После каждой задачи `/clear`, иначе вся история пересылается заново в каждом сообщении.
- Gemini app подходит для вопросов по теории (метод, формулы): там лимит тоже не Claude.

## Важно
Не запускайте обоих одновременно на одной задаче. Antigravity работает в ветке `gemini/NNN`, Claude трогает только `.ai/`.
