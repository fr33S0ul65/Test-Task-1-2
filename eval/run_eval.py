"""Прогін класифікатора на тестовому наборі.

Запуск з кореня проєкту, наприклад:
    .venv/bin/python eval/run_eval.py --provider anthropic --model <назва моделі> --prompt v1 [--effort low]

Результати: eval/results/<час>_<провайдер>_<модель>_<промпт>.md (таблиця) і .json (усі деталі).
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.classify import classify  # noqa: E402
from src.pricing import PRICES_CHECKED, cost_usd  # noqa: E402

COMPARED = ["category", "refund_requested", "priority", "needs_human"]


def fmt(v):
    return "—" if v is None else str(v).lower() if isinstance(v, bool) else str(v)


def short(text, n=60):
    t = text.replace("\n", " ").replace("|", "\\|")
    return t if len(t) <= n else t[:n - 1] + "…"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", required=True, choices=["anthropic", "openai"])
    ap.add_argument("--model", required=True)
    ap.add_argument("--prompt", default="v1")
    ap.add_argument("--effort", default=None, choices=["none", "low", "medium", "high"],
                    help="глибина роздумів; без параметра = значення моделі за замовчуванням")
    ap.add_argument("--tickets", default="data/ticketsTest1.json")
    ap.add_argument("--holdout", choices=["exclude", "only", "all"], default="exclude",
                    help="exclude: без прихованих тікетів (за замовчуванням); only: тільки приховані; all: усі")
    args = ap.parse_args()

    tickets = json.loads((ROOT / args.tickets).read_text(encoding="utf-8"))
    if args.holdout == "exclude":
        tickets = [t for t in tickets if not t.get("holdout")]
    elif args.holdout == "only":
        tickets = [t for t in tickets if t.get("holdout")]

    rows = []
    for t in tickets:
        result, meta = classify(t["text"], args.provider, args.model, args.prompt, args.effort)
        checks = {}
        for f in COMPARED:
            exp = t.get(f"expected_{f}")
            if exp is not None:
                checks[f] = (result.get(f) == exp)
        passed = all(checks.values()) and not meta["fallback"]
        rows.append({"ticket": t, "result": result, "meta": meta, "checks": checks, "pass": passed})
        mark = "PASS" if passed else "FAIL"
        extra = f"  [fallback: {meta['error']}]" if meta["fallback"] else ""
        print(f"{t['id']}: {mark}  {fmt(result['category'])} / {fmt(result['priority'])} / "
              f"human={fmt(result['needs_human'])}  ({meta['latency_s']} с){extra}")
        time.sleep(0.5)

    n = len(rows)
    if n == 0:
        print("Немає тікетів для прогону.")
        return
    field_acc = {}
    for f in COMPARED:
        relevant = [r for r in rows if f in r["checks"]]
        if relevant:
            ok = sum(r["checks"][f] for r in relevant)
            field_acc[f] = f"{ok}/{len(relevant)}"
    passed = sum(r["pass"] for r in rows)
    fallbacks = sum(r["meta"]["fallback"] for r in rows)
    tin = sum(r["meta"]["input_tokens"] for r in rows)
    tout = sum(r["meta"]["output_tokens"] for r in rows)
    avg_lat = round(sum(r["meta"]["latency_s"] for r in rows) / n, 2)
    total_cost = cost_usd(args.model, tin, tout)
    per_ticket = total_cost / n if total_cost is not None else None
    effort_label = args.effort or "default"

    summary = {
        "date": datetime.now().isoformat(timespec="seconds"),
        "provider": args.provider, "model": args.model, "prompt": args.prompt, "effort": effort_label,
        "tickets_file": args.tickets, "holdout": args.holdout,
        "tickets": n, "passed": passed, "accuracy": f"{passed}/{n} ({round(100 * passed / n)}%)",
        "field_accuracy": field_acc, "fallbacks": fallbacks,
        "input_tokens": tin, "output_tokens": tout, "avg_latency_s": avg_lat,
        "cost_total_usd": total_cost, "cost_per_ticket_usd": per_ticket,
        "cost_10k_tickets_usd": per_ticket * 10_000 if per_ticket is not None else None,
        "prices_checked": PRICES_CHECKED,
    }

    print("\n=== Підсумок ===")
    print(f"Повністю правильно: {summary['accuracy']}")
    for f, v in field_acc.items():
        print(f"  {f}: {v}")
    print(f"Fallback (збої): {fallbacks}")
    print(f"Токени: вхід {tin}, вихід {tout}; середній час {avg_lat} с")
    if per_ticket is not None:
        print(f"Вартість: ${per_ticket:.6f} за тікет, ~${per_ticket * 10_000:.2f} за 10 000 тікетів "
              f"(ціни станом на {PRICES_CHECKED})")
    else:
        print("Вартість: ціни цієї моделі немає в src/pricing.py")

    out_dir = ROOT / "eval" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    safe_model = args.model.replace("/", "-")
    base = out_dir / f"{stamp}_{args.provider}_{safe_model}_{args.prompt}_effort-{effort_label}"
    if args.holdout != "exclude":
        base = Path(str(base) + f"_holdout-{args.holdout}")

    Path(str(base) + ".json").write_text(
        json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# Прогін: {args.provider} / {args.model} / промпт {args.prompt} / effort {effort_label}",
        "",
        f"Дата: {summary['date']}. Тікетів: {n}. Повністю правильно: **{summary['accuracy']}**. "
        f"Fallback: {fallbacks}. Токени: вхід {tin}, вихід {tout}. Середній час: {avg_lat} с.",
        "",
        (f"Вартість: ${per_ticket:.6f} за тікет, ~${per_ticket * 10_000:.2f} за 10 000 тікетів "
         f"(ціни станом на {PRICES_CHECKED})." if per_ticket is not None else "Вартість: ціни моделі немає в таблиці."),
        "",
        "Точність по полях: " + ", ".join(f"{f} {v}" for f, v in field_acc.items()),
        "",
        "| ID | Тікет | Категорія (очік. → факт) | Refund | Пріоритет | Людина | Результат |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        t, res = r["ticket"], r["result"]

        def cell(f):
            exp = t.get(f"expected_{f}")
            got = res.get(f)
            if exp is None:
                return f"— → {fmt(got)}"
            mark = "" if exp == got else " ❌"
            return f"{fmt(exp)} → {fmt(got)}{mark}"

        status = "PASS" if r["pass"] else ("FAIL (fallback)" if r["meta"]["fallback"] else "FAIL")
        lines.append(f"| {t['id']} | {short(t['text'])} | {cell('category')} | {cell('refund_requested')} | "
                     f"{cell('priority')} | {cell('needs_human')} | {status} |")
    Path(str(base) + ".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nЗбережено: {base.relative_to(ROOT)}.md і .json")


if __name__ == "__main__":
    main()
