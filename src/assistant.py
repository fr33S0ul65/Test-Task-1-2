"""Асистент для агента підтримки (Task 2).

Тікет → пошук у базі знань (embeddings) → один запит до моделі →
summary українською, три варіанти відповіді мовою користувача, цитата з бази.

Перевірки в коді (не покладаємось лише на модель):
- цитата має дослівно бути в статті, на яку посилається модель;
- стаття має бути серед знайдених пошуком;
- три варіанти мають бути непорожні й різні.
Якщо щось не так, у результаті з'являється попередження для агента.
"""
import json
import re

from src import kb, llm
from src.classify import DEFAULT_EFFORT, DEFAULT_MODEL, DEFAULT_PROVIDER, ROOT, parse_json

DEFAULT_REPLY_PROMPT = "v1"
TOP_K = 3
TONES = ("formal", "empathetic", "short")


def load_prompt(version):
    return (ROOT / "prompts" / f"reply_{version}.txt").read_text(encoding="utf-8")


def _norm(text):
    t = text.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    t = re.sub(r"\s+", " ", t).strip()
    return t.rstrip(".!?;: ").lower()


def _fallback(reason):
    return {
        "summary": None, "language": None,
        "replies": {t: None for t in TONES},
        "source": None, "retrieved": [],
        "warnings": [f"Генерація не вдалася: {reason}. Відповідь агент пише сам."],
    }


def assist(ticket_text, provider=DEFAULT_PROVIDER, model=DEFAULT_MODEL,
           prompt_version=DEFAULT_REPLY_PROMPT, effort=DEFAULT_EFFORT, k=TOP_K):
    meta = {"provider": provider, "model": model, "prompt": prompt_version, "effort": effort,
            "input_tokens": 0, "output_tokens": 0, "cache_write_tokens": 0, "cache_read_tokens": 0,
            "embed_index_tokens": 0, "embed_query_tokens": 0, "latency_s": 0,
            "raw": None, "error": None, "fallback": False}

    if not ticket_text or not ticket_text.strip():
        meta.update(error="порожній тікет", fallback=True)
        return _fallback("порожній тікет"), meta

    warnings = []
    try:
        hits, smeta = kb.search(ticket_text, k)
        meta["embed_index_tokens"] = smeta["index_tokens"]
        meta["embed_query_tokens"] = smeta["query_tokens"]
    except RuntimeError as e:
        hits = []
        warnings.append(f"База знань недоступна ({e}). Відповіді без опори на базу — перевір їх особливо уважно.")

    if hits:
        articles = "\n\n".join(
            f'<article id="{h["id"]}" title="{h["title"]}">\n{h["text"]}\n</article>' for h in hits)
    else:
        articles = "<no_articles/>"
    user = f"<ticket>\n{ticket_text}\n</ticket>\n\n<knowledge_base>\n{articles}\n</knowledge_base>"

    resp = llm.call_llm(provider, model, load_prompt(prompt_version), user, effort=effort)
    for key in ("input_tokens", "output_tokens", "cache_write_tokens", "cache_read_tokens", "latency_s"):
        meta[key] = resp.get(key, 0)
    meta["raw"] = resp["text"]
    if resp["error"]:
        meta.update(error=resp["error"], fallback=True)
        out = _fallback(resp["error"])
        out["retrieved"] = [{"id": h["id"], "title": h["title"], "score": h["score"]} for h in hits]
        return out, meta

    try:
        d = parse_json(resp["text"])
        replies = d["replies"]
        if not all(isinstance(replies.get(t), str) and replies[t].strip() for t in TONES):
            raise ValueError("немає одного з трьох варіантів відповіді")
        if not isinstance(d.get("summary"), str) or not d["summary"].strip():
            raise ValueError("немає summary")
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
        meta.update(error=f"невалідна відповідь: {e}", fallback=True)
        out = _fallback(f"невалідна відповідь моделі ({e})")
        out["retrieved"] = [{"id": h["id"], "title": h["title"], "score": h["score"]} for h in hits]
        return out, meta

    if len({_norm(replies[t]) for t in TONES}) < 3:
        warnings.append("Деякі варіанти відповіді однакові.")

    source = d.get("source")
    src_out = None
    if source:
        art = next((h for h in hits if h["id"] == source.get("article_id")), None)
        quote = source.get("quote") or ""
        verified = bool(art and quote and _norm(quote) in _norm(art["text"]))
        src_out = {"article_id": source.get("article_id"), "title": art["title"] if art else None,
                   "quote": quote, "verified": verified}
        if not art:
            warnings.append(f"Модель послалася на статтю {source.get('article_id')}, якої немає серед знайдених.")
        elif not verified:
            warnings.append("Цитату не знайдено дослівно в статті — перевір, чи модель її не вигадала.")
    else:
        warnings.append("Модель не знайшла в базі статті, що відповідає на тікет.")

    result = {
        "summary": d["summary"],
        "language": d.get("language"),
        "replies": {t: replies[t] for t in TONES},
        "source": src_out,
        "retrieved": [{"id": h["id"], "title": h["title"], "score": h["score"]} for h in hits],
        "warnings": warnings,
    }
    return result, meta


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Підготувати summary і варіанти відповіді для одного тікета")
    ap.add_argument("text")
    ap.add_argument("--prompt", default=DEFAULT_REPLY_PROMPT)
    a = ap.parse_args()
    res, meta = assist(a.text, prompt_version=a.prompt)
    print(json.dumps(res, ensure_ascii=False, indent=2))
