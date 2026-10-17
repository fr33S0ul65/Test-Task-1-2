# Nebula AI Support

Тестове завдання OBRIO (AI Ops Specialist): два прототипи для команди підтримки Nebula.

- **Task 1 — AI-класифікатор тікетів.** Приймає текст звернення і повертає категорію, пріоритет, рекомендований наступний крок і ознаку, чи потрібна людина. **Готово.**
- **Task 2 — AI-асистент для агента.** Summary звернення, варіанти відповіді різного тону, цитата з бази знань. *В роботі.*

## Task 1 коротко

| | |
| --- | --- |
| Фінальна модель | `claude-haiku-5-5`, промпт `v3`, effort `medium`, кешування промпту |
| Точність | 16/16 на основному наборі, 5/5 на прихованому (разом 21/21) |
| Вартість | ~$0.000115 за тікет, ~$1.15 за 10 000 тікетів на місяць (ціни станом на 16.10.2026) |
| Порівняно моделей | 4: `claude-haiku-5-5`, `gpt-6-luna`, `claude-sonnet-5-5`, `gpt-6.1-sol` |

Документація:
- [docs/architecture.md](docs/architecture.md) — модель і чому, структура промпту, категорії, обробка збоїв, де система помиляється.
- [docs/evaluation.md](docs/evaluation.md) — тестовий набір, таблиці результатів, порівняння моделей, вартість, кешування.
- [docs/prompt_evolution.md](docs/prompt_evolution.md) — як промпт змінювався від v1 до v3 і чому.
- [docs/edge_cases.md](docs/edge_cases.md) — випадки, де AI дав неочікуваний результат, і що з цим зроблено.
- [docs/automation_limits.md](docs/automation_limits.md) — які тікети не обробляються автоматично і механізм human-in-the-loop.
- [decisions.md](decisions.md) — усі рішення з датами й причинами, зокрема ті, що я ухвалив сам.

## Структура

```
data/ticketsTest1.json      16 тестових тікетів з очікуваними відповідями
data/ticketsHoldout.json    5 прихованих тікетів (на них промпт не підганявся)
prompts/classify_v1..v3.txt версії промпту класифікатора
src/llm.py                  єдиний шар виклику моделей (Claude, GPT), повтори при збоях
src/classify.py             класифікатор: промпт → модель → перевірка JSON → fallback
src/pricing.py              ціни моделей і розрахунок вартості
eval/run_eval.py            прогін на тестовому наборі, таблиця результатів
eval/results/               результати всіх прогонів (.md — таблиця, .json — деталі)
```

## Запуск

Потрібен Python 3.10+ і ключі API Anthropic (і OpenAI, якщо порівнювати з GPT).

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # встав свої ключі в .env
```

Класифікувати один тікет (фінальна конфігурація):

```bash
.venv/bin/python -m src.classify "I was charged twice for my weekly plan this morning."
```

Прогнати тестовий набір:

```bash
.venv/bin/python eval/run_eval.py --provider anthropic --model claude-haiku-5-5 --prompt v3 --effort medium
.venv/bin/python eval/run_eval.py --provider anthropic --model claude-haiku-5-5 --prompt v3 --effort medium \
    --tickets data/ticketsHoldout.json --holdout only
```

Для GPT: `--provider openai --model gpt-6-luna`. Прапорець `--no-cache` вимикає кешування промпту.

Ключі зберігаються лише в `.env`, який є в `.gitignore`. Тестові тікети синтетичні, реальних даних у репозиторії немає.
