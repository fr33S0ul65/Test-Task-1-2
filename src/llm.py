"""Єдиний шар виклику LLM.

call_llm(provider, model, system, user) -> dict:
    text, input_tokens, output_tokens, latency_s, attempts, error

Обробка збоїв:
- rate limit, таймаут, помилка сервера (5xx): повтор із паузою (до MAX_RETRIES спроб);
- інші помилки (невірний ключ, невідома модель): без повторів;
- якщо всі спроби невдалі: text = None, error = опис помилки.
  Що робити далі (fallback у чергу людини), вирішує classify.py.
"""
import os
import time

from dotenv import load_dotenv

load_dotenv()

TIMEOUT_S = 30
MAX_RETRIES = 3

_clients = {}


def _client(provider):
    if provider in _clients:
        return _clients[provider]
    if provider == "anthropic":
        import anthropic
        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY відсутній у .env")
        c = anthropic.Anthropic(api_key=key, timeout=TIMEOUT_S, max_retries=0)
    elif provider == "openai":
        import openai
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY відсутній у .env")
        c = openai.OpenAI(api_key=key, timeout=TIMEOUT_S, max_retries=0)
    else:
        raise ValueError(f"Невідомий провайдер: {provider}")
    _clients[provider] = c
    return c


def _error_kind(e):
    name = type(e).__name__
    status = getattr(e, "status_code", None)
    if "RateLimit" in name or status == 429:
        return "rate_limit"
    if "Timeout" in name:
        return "timeout"
    if "Connection" in name:
        return "connection"
    if status is not None and status >= 500:
        return "server"
    return "other"


def _call(provider, model, system, user, temperature, max_tokens):
    c = _client(provider)
    if provider == "anthropic":
        r = c.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
        return text, r.usage.input_tokens, r.usage.output_tokens
    # openai
    kwargs = dict(
        model=model,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        max_completion_tokens=max_tokens,
    )
    if temperature is not None:
        kwargs["temperature"] = temperature
    r = c.chat.completions.create(**kwargs)
    return r.choices[0].message.content or "", r.usage.prompt_tokens, r.usage.completion_tokens


def call_llm(provider, model, system, user, temperature=0.0, max_tokens=500):
    start = time.perf_counter()
    error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            text, tin, tout = _call(provider, model, system, user, temperature, max_tokens)
            return {
                "text": text,
                "input_tokens": tin,
                "output_tokens": tout,
                "latency_s": round(time.perf_counter() - start, 2),
                "attempts": attempt,
                "error": None,
            }
        except Exception as e:  # noqa: BLE001
            kind = _error_kind(e)
            error = f"{kind}: {type(e).__name__}: {e}"
            if kind in ("rate_limit", "timeout", "connection", "server") and attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)
                continue
            break
    return {
        "text": None,
        "input_tokens": 0,
        "output_tokens": 0,
        "latency_s": round(time.perf_counter() - start, 2),
        "attempts": attempt,
        "error": error,
    }
