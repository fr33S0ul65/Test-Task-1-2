"""Класифікатор тікетів: текст тікета -> категорія, пріоритет, наступний крок.

Якщо модель не відповіла або відповіла невалідно (не JSON, невідома категорія,
неправильні типи), тікет не губиться: повертається fallback з needs_human = true.
"""
import json
import re
from pathlib import Path

from src import llm

ROOT = Path(__file__).resolve().parent.parent
CATEGORIES = {"subscription", "payment_issue", "technical", "account", "product", "expert"}
PRIORITIES = {"high", "medium", "low"}
FIELDS = ["category", "refund_requested", "priority", "next_step", "needs_human", "human_reason"]


def load_prompt(version):
    return (ROOT / "prompts" / f"classify_{version}.txt").read_text(encoding="utf-8")


def parse_json(text):
    """Витягує JSON-об'єкт з відповіді моделі (навіть якщо він у ```json ... ```)."""
    if not text:
        raise ValueError("порожня відповідь")
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("у відповіді немає JSON")
    return json.loads(cleaned[start:end + 1])


def validate(d):
    missing = [f for f in FIELDS if f not in d]
    if missing:
        raise ValueError(f"немає полів: {missing}")
    if d["category"] not in CATEGORIES:
        raise ValueError(f"невідома категорія: {d['category']!r}")
    if d["priority"] not in PRIORITIES:
        raise ValueError(f"невідомий пріоритет: {d['priority']!r}")
    for f in ("refund_requested", "needs_human"):
        if not isinstance(d[f], bool):
            raise ValueError(f"{f} має бути true/false, а не {d[f]!r}")
    return {f: d[f] for f in FIELDS}


def fallback(reason):
    return {
        "category": None,
        "refund_requested": None,
        "priority": None,
        "next_step": "Передати людині: автоматична класифікація не вдалася",
        "needs_human": True,
        "human_reason": f"Збій класифікації: {reason}",
    }


def classify(ticket_text, provider, model, prompt_version="v1"):
    meta = {"provider": provider, "model": model, "prompt": prompt_version,
            "input_tokens": 0, "output_tokens": 0, "latency_s": 0, "attempts": 0,
            "raw": None, "error": None, "fallback": False}

    if not ticket_text or not ticket_text.strip():
        meta.update(error="порожній тікет", fallback=True)
        return fallback("порожній тікет"), meta

    resp = llm.call_llm(provider, model, load_prompt(prompt_version),
                        f"<ticket>\n{ticket_text}\n</ticket>")
    meta.update({k: resp[k] for k in ("input_tokens", "output_tokens", "latency_s", "attempts")})
    meta["raw"] = resp["text"]

    if resp["error"]:
        meta.update(error=resp["error"], fallback=True)
        return fallback(resp["error"]), meta
    try:
        return validate(parse_json(resp["text"])), meta
    except (ValueError, json.JSONDecodeError) as e:
        meta.update(error=f"невалідна відповідь: {e}", fallback=True)
        return fallback(f"невалідна відповідь моделі ({e})"), meta
