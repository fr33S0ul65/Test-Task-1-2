"""Єдиний шар виклику LLM.

call_llm(provider, model, system, user, effort=None) -> dict:
    text, input_tokens, output_tokens, latency_s, attempts, error

Особливості моделей (перевірено в офіційній документації 16.10.2026):
- Claude 5.5 і GPT-6 думають перед відповіддю за замовчуванням, і thinking/reasoning-токени
  входять у ліміт вихідних токенів, тому MAX_TOKENS із запасом.
- temperature для цих моделей не передається (Claude 5.5 повертає на неї помилку 400,
  GPT-6 не підтримує її, коли reasoning effort не "none").
- Кешування промпту (рішення 16.10.2026): для Claude системний промпт позначається
  cache_control з TTL 1 година. Перший запит пише промпт у кеш (2x ціни входу),
  наступні читають його (0.1x для Haiku). У OpenAI кешування автоматичне.
- Глибину роздумів задає effort: у Claude це output_config.effort,
  у OpenAI це reasoning_effort. None = значення моделі за замовчуванням.

Обробка збоїв:
- rate limit, таймаут, помилка з'єднання чи сервера (5xx): повтор із паузою (до MAX_RETRIES спроб);
- інші помилки (невірний ключ, невідома модель, невалідний параметр): без повторів;
- якщо всі спроби невдалі: text = None, error = опис помилки.
  Що робити далі (fallback у чергу людини), вирішує classify.py.
"""
import os
import time

from dotenv import load_dotenv

load_dotenv()

TIMEOUT_S = 60
MAX_RETRIES = 3
MAX_TOKENS = 4000

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


def _call(provider, model, system, user, effort, cache):
    c = _client(provider)
    if provider == "anthropic":
        extra = {"output_config": {"effort": effort}} if effort else None
        system_param = system
        if cache:
            system_param = [{"type": "text", "text": system,
                             "cache_control": {"type": "ephemeral", "ttl": "1h"}}]
        r = c.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=system_param,
            messages=[{"role": "user", "content": user}],
            extra_body=extra,
        )
        text = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
        u = r.usage
        return (text, u.input_tokens, u.output_tokens,
                getattr(u, "cache_creation_input_tokens", 0) or 0,
                getattr(u, "cache_read_input_tokens", 0) or 0)
    # openai
    extra = {"reasoning_effort": effort} if effort else None
    r = c.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        max_completion_tokens=MAX_TOKENS,
        extra_body=extra,
    )
    # У OpenAI кешовані токени входять у prompt_tokens; окремо їх не рахуємо
    return r.choices[0].message.content or "", r.usage.prompt_tokens, r.usage.completion_tokens, 0, 0


def call_llm(provider, model, system, user, effort=None, cache=True):
    start = time.perf_counter()
    error = None
    attempt = 0
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            text, tin, tout, cwrite, cread = _call(provider, model, system, user, effort, cache)
            return {
                "text": text,
                "input_tokens": tin,
                "output_tokens": tout,
                "cache_write_tokens": cwrite,
                "cache_read_tokens": cread,
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
        "cache_write_tokens": 0,
        "cache_read_tokens": 0,
        "latency_s": round(time.perf_counter() - start, 2),
        "attempts": attempt,
        "error": error,
    }
