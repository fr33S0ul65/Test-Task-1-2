"""Інтерфейс для агента підтримки: класифікатор (Task 1) і асистент (Task 2).

Запуск з кореня проєкту:
    .venv/bin/streamlit run app.py
"""
import json
from pathlib import Path

import streamlit as st

from src.assistant import TONES, assist
from src.classify import classify, DEFAULT_EFFORT, DEFAULT_MODEL, DEFAULT_PROMPT, DEFAULT_PROVIDER

ROOT = Path(__file__).resolve().parent
TONE_LABELS = {"formal": "Формальний", "empathetic": "Емпатійний", "short": "Короткий"}
PRIORITY_LABELS = {"high": "🔴 high", "medium": "🟠 medium", "low": "🟢 low"}

# Попередження асистента, після яких рішення теж лишається за агентом
SERIOUS_WARNINGS = ("Генерація не вдалася", "База знань недоступна", "Цитату не знайдено",
                    "якої немає серед знайдених", "не знайшла в базі")


def load_examples():
    ex = {}
    for name in ("assistantTickets.json", "ticketsTest1.json"):
        p = ROOT / "data" / name
        if p.exists():
            for t in json.loads(p.read_text(encoding="utf-8")):
                ex[f"{t['id']}: {t['text'][:60]}"] = t["text"]
    return ex


def ticket_input(key):
    examples = load_examples()
    choice = st.selectbox("Приклад тікета", ["— свій текст —"] + list(examples), key=f"{key}_ex")
    default = examples.get(choice, "")
    return st.text_area("Текст тікета", value=default, height=120, key=f"{key}_text_{choice}")


def show_classification(res, meta):
    c1, c2, c3 = st.columns(3)
    c1.metric("Категорія", res["category"] or "—")
    c2.metric("Пріоритет", PRIORITY_LABELS.get(res["priority"], "—"))
    c3.metric("Повернення коштів", "так" if res["refund_requested"] else "ні")
    st.markdown(f"**Рекомендований наступний крок:** {res['next_step']}")
    if meta.get("fallback"):
        st.caption(f"Збій класифікації: {meta['error']}")


st.set_page_config(page_title="AI-асистент підтримки", page_icon="🎧", layout="centered")
st.title("AI-асистент підтримки")
st.caption(f"Модель: {DEFAULT_MODEL} · промпт класифікатора {DEFAULT_PROMPT} · база знань симульована (MyTestBase)")

tab1, tab2 = st.tabs(["Класифікатор (Task 1)", "Асистент для агента (Task 2)"])

with tab1:
    text = ticket_input("cls")
    if st.button("Класифікувати", type="primary", key="cls_btn") and text.strip():
        with st.spinner("Класифікую…"):
            res, meta = classify(text, DEFAULT_PROVIDER, DEFAULT_MODEL, DEFAULT_PROMPT, DEFAULT_EFFORT)
        if res["needs_human"]:
            st.error(f"🧑‍💼 **Потрібна людина:** {res['human_reason']}")
        else:
            st.success("Можна обробити автоматично")
        show_classification(res, meta)
        with st.expander("JSON"):
            st.json(res)

with tab2:
    text = ticket_input("ast")
    if st.button("Підготувати відповідь", type="primary", key="ast_btn") and text.strip():
        with st.spinner("Класифікую тікет, шукаю в базі знань, готую варіанти…"):
            cls, cls_meta = classify(text, DEFAULT_PROVIDER, DEFAULT_MODEL, DEFAULT_PROMPT, DEFAULT_EFFORT)
            res, meta = assist(text)

        reasons = []
        if cls["needs_human"]:
            reasons.append(cls["human_reason"])
        reasons += [w for w in res["warnings"] if w.startswith(SERIOUS_WARNINGS) or any(s in w for s in SERIOUS_WARNINGS)]
        other_warnings = [w for w in res["warnings"] if w not in reasons]
        agent_decides = bool(reasons)

        if agent_decides:
            st.error("🧑‍💼 **Рішення за агентом.** Варіанти нижче — лише чернетка, не надсилай без перевірки.\n\n"
                     + "\n".join(f"- {r}" for r in reasons))
        for w in other_warnings:
            st.warning(w)

        st.subheader("Summary")
        st.info(res["summary"] or "—")
        show_classification(cls, cls_meta)

        st.subheader("Джерело в базі знань")
        src = res["source"]
        if src:
            mark = "✅ цитата знайдена в статті" if src["verified"] else "⚠️ цитату не знайдено в статті"
            st.markdown(f"**{src['article_id']} · {src['title']}** — {mark}")
            st.markdown(f"> {src['quote']}")
        else:
            st.markdown("Доречної статті не знайдено.")
        with st.expander("Знайдені статті"):
            for h in res["retrieved"]:
                pin = " (закріплена)" if h.get("pinned") else ""
                st.markdown(f"- {h['id']} · {h['title']} — схожість {h['score']}{pin}")

        st.subheader(f"Варіанти відповіді ({res['language'] or '—'})")

        def show_replies():
            tabs = st.tabs([TONE_LABELS[t] for t in TONES])
            for tab, tone in zip(tabs, TONES):
                with tab:
                    st.text_area(TONE_LABELS[tone], value=res["replies"][tone] or "", height=200,
                                 key=f"reply_{tone}", label_visibility="collapsed")

        if agent_decides:
            with st.expander("Показати чернетку"):
                show_replies()
        else:
            show_replies()
