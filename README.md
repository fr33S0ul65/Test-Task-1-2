# Nebula AI Support

Тестове завдання OBRIO (AI Ops Specialist): два прототипи для команди підтримки Nebula.

- **Task 1 — AI-класифікатор тікетів.** Приймає текст звернення і повертає категорію, пріоритет, рекомендований наступний крок і ознаку, чи потрібна людина. **Готово.**
- **Task 2 — AI-асистент для агента.** Summary звернення, три варіанти відповіді різного тону, цитата з бази знань з перевіркою. **Готово.**

Обидва інструменти доступні в простому веб-інтерфейсі: `.venv/bin/streamlit run app.py`.

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

## Task 2 коротко

| | |
| --- | --- |
| Підхід | Пошук за змістом (OpenAI `text-embedding-3-small`) по 20 статтях симульованої бази → один запит до `claude-haiku-5-5` з промптом `reply_v3` |
| Результат | Summary українською, три тони мовою клієнта, цитата зі статті, яку код перевіряє дослівно |
| Оцінка (10 тікетів) | Пошук 9/10, правильна стаття 10/10, цитата 10/10, формат 10/10, summary українською 10/10 |
| Вартість | ~$4.45 за 10 000 тікетів (з класифікатором у вкладці — ~$5.60) |

Документація:
- [docs/task2_assistant.md](docs/task2_assistant.md) — архітектура, чому embeddings, як структурований промпт для тонів, оцінка, приклад поганого output і що з ним зроблено, компроміси.
- [docs/task2_prompt_evolution.md](docs/task2_prompt_evolution.md) — промпт асистента v1 → v3, що не спрацювало з першого разу.
- [docs/automation_limits.md](docs/automation_limits.md) — сценарії, де агент вирішує сам, і як це позначено в інтерфейсі.

## Структура

```
data/ticketsTest1.json      16 тестових тікетів з очікуваними відповідями
data/ticketsHoldout.json    5 прихованих тікетів (на них промпт не підганявся)
data/assistantTickets.json  10 тестових тікетів для асистента з очікуваними статтями
data/knowledge_base/        20 статей симульованої бази знань (MyTestBase)
prompts/classify_v1..v3.txt версії промпту класифікатора
prompts/reply_v1..v3.txt    версії промпту асистента
src/llm.py                  єдиний шар виклику моделей (Claude, GPT), повтори при збоях
src/classify.py             класифікатор: промпт → модель → перевірка JSON → fallback
src/kb.py                   база знань: embeddings, кеш векторів у .cache/, пошук
src/assistant.py            асистент: пошук → summary і три тони → перевірки цитати й мови
src/pricing.py              ціни моделей і розрахунок вартості
app.py                      веб-інтерфейс Streamlit: класифікатор і асистент
eval/run_eval.py            прогін на тестовому наборі, таблиця результатів
eval/show_next_steps.py     next_step моделі поруч з очікуваним, для ручного перегляду
eval/run_assistant.py       прогін асистента: пошук, стаття, цитата, формат + тексти для ручного перегляду
eval/results/               результати всіх прогонів (.md — таблиця, .json — деталі)
```

## Запуск

Потрібен Python 3.10+ і ключі API Anthropic та OpenAI (OpenAI — для embeddings у Task 2 і для порівняння моделей у Task 1).

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # встав свої ключі в .env
```

Веб-інтерфейс (обидві задачі):

```bash
.venv/bin/streamlit run app.py
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

Асистент (Task 2):

```bash
.venv/bin/python -m src.assistant "I was charged twice for my weekly plan this morning."
.venv/bin/python eval/run_assistant.py --prompt v3
```

Ключі зберігаються лише в `.env`, який є в `.gitignore`. Тестові тікети синтетичні, реальних даних у репозиторії немає.
