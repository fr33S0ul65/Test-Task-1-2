"""Показує next_step моделі поруч з очікуваним, щоб переглянути їх вручну.

Запуск:
    .venv/bin/python eval/show_next_steps.py eval/results/<файл прогону>.json
Без аргументу береться найновіший файл у eval/results/.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

if len(sys.argv) > 1:
    path = Path(sys.argv[1])
else:
    files = sorted((ROOT / "eval" / "results").glob("*.json"))
    if not files:
        sys.exit("У eval/results немає файлів .json")
    path = files[-1]

data = json.loads(path.read_text(encoding="utf-8"))
print(f"Файл: {path.name}\n")
for r in data["rows"]:
    t, res = r["ticket"], r["result"]
    print(f"{t['id']}  [{t.get('edge_case', '')}]")
    print(f"  тікет:       {t['text']}")
    print(f"  очікувано:   {t.get('expected_next_step')}")
    print(f"  модель:      {res.get('next_step')}")
    if res.get("needs_human"):
        print(f"  причина:     {res.get('human_reason')}")
    print()
