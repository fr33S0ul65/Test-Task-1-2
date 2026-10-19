"""Прогін асистента (Task 2) на тестовому наборі.

Запуск з кореня проєкту:
    .venv/bin/python eval/run_assistant.py --prompt v1

Автоматичні перевірки для кожного тікета:
- retrieval: хоча б одна очікувана стаття серед знайдених (top-3);
- cited: модель послалась на одну з очікуваних статей;
- quote: цитата дослівно є в статті;
- format: валідний JSON, summary і три різні варіанти.
Тон і зміст відповідей оцінюються вручну — для цього весь текст відповідей
зберігається в .md поруч із таблицею.
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.assistant import DEFAULT_REPLY_PROMPT, TONES, assist  # noqa: E402
from src.classify import DEFAULT_EFFORT, DEFAULT_MODEL, DEFAULT_PROVIDER  # noqa: E402
from src.pricing import PRICES_CHECKED, cost_usd  # noqa: E402
from src import llm  # noqa: E402


def yn(v):
    return "✅" if v else "❌"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default=DEFAULT_PROVIDER, choices=["anthropic", "openai"])
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--prompt", default=DEFAULT_REPLY_PROMPT)
    ap.add_argument("--effort", default=DEFAULT_EFFORT)
    ap.add_argument("--tickets", default="data/assistantTickets.json")
    args = ap.parse_args()

    tickets = json.loads((ROOT / args.tickets).read_text(encoding="utf-8"))
    rows = []
    for t in tickets:
        res, meta = assist(t["text"], args.provider, args.model, args.prompt, args.effort)
        ids = [r["id"] for r in res["retrieved"] if not r.get("pinned")]  # пошук без закріплених статей
        shown = [r["id"] + ("*" if r.get("pinned") else "") for r in res["retrieved"]]
        src = res["source"] or {}
        checks = {
            "retrieval": any(a in ids for a in t["expected_articles"]),
            "cited": src.get("article_id") in t["expected_articles"],
            "quote": bool(src.get("verified")),
            "format": not meta["fallback"] and not any("однакові" in w for w in res["warnings"]),
            "summary_uk": not meta["fallback"] and not any("не українською" in w for w in res["warnings"]),
        }
        rows.append({"ticket": t, "result": res, "meta": meta, "checks": checks})
        flags = " ".join(f"{k}={yn(v)}" for k, v in checks.items())
        print(f"{t['id']}: {flags}  знайдено {shown}  ({meta['latency_s']} с)")
        time.sleep(0.5)

    n = len(rows)
    acc = {k: sum(r["checks"][k] for r in rows) for k in ("retrieval", "cited", "quote", "format", "summary_uk")}
    tin = sum(r["meta"]["input_tokens"] for r in rows)
    tout = sum(r["meta"]["output_tokens"] for r in rows)
    cw = sum(r["meta"]["cache_write_tokens"] for r in rows)
    cr = sum(r["meta"]["cache_read_tokens"] for r in rows)
    eq = sum(r["meta"]["embed_query_tokens"] for r in rows)
    ei = sum(r["meta"]["embed_index_tokens"] for r in rows)
    gen_cost = cost_usd(args.model, tin, tout, cw, cr) or 0.0
    emb_query_cost = cost_usd(llm.EMBED_MODEL, eq, 0) or 0.0
    emb_index_cost = cost_usd(llm.EMBED_MODEL, ei, 0) or 0.0
    per_ticket = (gen_cost + emb_query_cost) / n
    avg_lat = round(sum(r["meta"]["latency_s"] for r in rows) / n, 2)

    print("\n=== Підсумок ===")
    for k, v in acc.items():
        print(f"  {k}: {v}/{n}")
    print(f"Fallback: {sum(r['meta']['fallback'] for r in rows)}")
    print(f"Токени генерації: вхід {tin}, вихід {tout}, запис у кеш {cw}, читання з кешу {cr}; середній час {avg_lat} с")
    print(f"Токени embeddings: запити {eq}, індексування бази {ei} (одноразово)")
    print(f"Вартість: ${per_ticket:.6f} за тікет, ~${per_ticket * 10_000:.2f} за 10 000 тікетів; "
          f"індексування бази ${emb_index_cost:.6f} (ціни станом на {PRICES_CHECKED})")

    out_dir = ROOT / "eval" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    base = out_dir / f"{datetime.now().strftime('%Y%m%d_%H%M')}_assistant_{args.model}_reply-{args.prompt}"
    summary = {"date": datetime.now().isoformat(timespec="seconds"), "model": args.model, "prompt": args.prompt,
               "effort": args.effort, "embed_model": llm.EMBED_MODEL, "tickets": n,
               "checks": {k: f"{v}/{n}" for k, v in acc.items()},
               "gen_tokens": {"input": tin, "output": tout, "cache_write": cw, "cache_read": cr},
               "embed_tokens": {"query": eq, "index": ei}, "avg_latency_s": avg_lat,
               "cost_per_ticket_usd": per_ticket, "cost_10k_usd": per_ticket * 10_000,
               "index_cost_usd": emb_index_cost, "prices_checked": PRICES_CHECKED}
    Path(str(base) + ".json").write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2),
                                         encoding="utf-8")

    L = [f"# Прогін асистента: {args.model} / reply {args.prompt} / effort {args.effort}", "",
         f"Дата: {summary['date']}. Тікетів: {n}. " + ", ".join(f"{k} {v}/{n}" for k, v in acc.items()) + ".",
         f"Вартість: ${per_ticket:.6f} за тікет (~${per_ticket * 10_000:.2f} за 10 000). Середній час: {avg_lat} с.", "",
         r"\* — закріплена стаття, додається завжди; у перевірці пошуку не враховується.", "",
         "| ID | Тікет | Очікувані статті | Знайдено (score) | Цитує | Пошук | Стаття | Цитата | Формат | Summary укр. |",
         "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        t, res, c = r["ticket"], r["result"], r["checks"]
        found = ", ".join(f"{h['id']}{'*' if h.get('pinned') else ''} ({h['score']})" for h in res["retrieved"])
        txt = t["text"].replace("|", "\\|")
        txt = txt if len(txt) <= 50 else txt[:49] + "…"
        L.append(f"| {t['id']} | {txt} | {', '.join(t['expected_articles'])} | {found} | "
                 f"{(res['source'] or {}).get('article_id', '—')} | {yn(c['retrieval'])} | {yn(c['cited'])} | "
                 f"{yn(c['quote'])} | {yn(c['format'])} | {yn(c['summary_uk'])} |")
    L += ["", "## Відповіді для ручного перегляду", ""]
    for r in rows:
        t, res = r["ticket"], r["result"]
        L += [f"### {t['id']} — {t['edge_case']}", "", f"> {t['text']}", "",
              f"**Summary:** {res['summary']}", "", f"**Мова:** {res['language']}", ""]
        for tone in TONES:
            L += [f"**{tone}:**", "", (res["replies"][tone] or "—"), ""]
        s = res["source"]
        if s:
            L += [f"**Джерело:** {s['article_id']} ({s['title']}), цитата {'перевірена' if s['verified'] else 'НЕ знайдена в статті'}:",
                  "", f"> {s['quote']}", ""]
        if res["warnings"]:
            L += ["**Попередження:** " + " ".join(res["warnings"]), ""]
    Path(str(base) + ".md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"\nЗбережено: {base.relative_to(ROOT)}.md і .json")


if __name__ == "__main__":
    main()
