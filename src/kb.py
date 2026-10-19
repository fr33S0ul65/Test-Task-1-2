"""База знань і пошук за змістом через embeddings (Task 2).

- Статті: data/knowledge_base/kb*.md (симульований довідковий центр MyTestBase).
- Вектори статей рахуються один раз і зберігаються в .cache/kb_embeddings.json.
  Кеш перераховується для статті, якщо змінився її текст або модель embeddings.
- Пошук: вектор тікета порівнюється з векторами статей (косинусна схожість), повертаються top-k.
"""
import hashlib
import json
import math
from pathlib import Path

from src import llm

ROOT = Path(__file__).resolve().parent.parent
KB_DIR = ROOT / "data" / "knowledge_base"
CACHE = ROOT / ".cache" / "kb_embeddings.json"

# Статті, які додаються до результатів пошуку завжди (рішення 19.10.2026):
# kb10 про самопочуття й кризову допомогу, бо пошук пропустив її в тікеті з ознаками кризи.
PINNED = ["kb10"]


def load_articles():
    articles = []
    for p in sorted(KB_DIR.glob("kb*.md")):
        text = p.read_text(encoding="utf-8").strip()
        first = text.splitlines()[0] if text else p.stem
        articles.append({
            "id": p.stem.split("_")[0],
            "file": p.name,
            "title": first.lstrip("# ").strip(),
            "text": text,
        })
    return articles


def _hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_cache():
    if CACHE.exists():
        try:
            return json.loads(CACHE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"model": llm.EMBED_MODEL, "items": {}}


def article_vectors(articles):
    """Вектори статей з кешу; відсутні чи застарілі дораховуються. Повертає (vectors, tokens)."""
    cache = _load_cache()
    if cache.get("model") != llm.EMBED_MODEL:
        cache = {"model": llm.EMBED_MODEL, "items": {}}
    items = cache["items"]
    stale = [a for a in articles if items.get(a["id"], {}).get("hash") != _hash(a["text"])]
    tokens = 0
    if stale:
        res = llm.embed([a["text"] for a in stale])
        if res["error"]:
            raise RuntimeError(f"не вдалося проіндексувати базу знань: {res['error']}")
        for a, v in zip(stale, res["vectors"]):
            items[a["id"]] = {"hash": _hash(a["text"]), "vector": v}
        tokens = res["tokens"]
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(cache), encoding="utf-8")
    return {a["id"]: items[a["id"]]["vector"] for a in articles}, tokens


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def search(query, k=3):
    """Повертає (top-k статей зі score + закріплені статті з pinned=True, meta). При збої кидає RuntimeError."""
    articles = load_articles()
    vectors, index_tokens = article_vectors(articles)
    q = llm.embed([query])
    if q["error"]:
        raise RuntimeError(f"не вдалося отримати вектор тікета: {q['error']}")
    qv = q["vectors"][0]
    scored = sorted(
        ({**a, "score": round(_cosine(qv, vectors[a["id"]]), 4)} for a in articles),
        key=lambda a: a["score"], reverse=True,
    )
    top = [{**a, "pinned": False} for a in scored[:k]]
    for pid in PINNED:
        if all(a["id"] != pid for a in top):
            art = next((a for a in scored if a["id"] == pid), None)
            if art:
                top.append({**art, "pinned": True})
    meta = {"index_tokens": index_tokens, "query_tokens": q["tokens"], "embed_latency_s": q["latency_s"]}
    return top, meta
