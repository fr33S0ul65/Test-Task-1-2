"""Ціни моделей, USD за 1 млн токенів (стандартний тариф, короткий контекст).

Джерела, перевірено 16.10.2026:
- Anthropic: https://platform.claude.com/docs/en/about-claude/pricing
- OpenAI:    https://developers.openai.com/api/docs/pricing
Перед фінальним звітом звірити ще раз.
"""
PRICES_CHECKED = "2026-10-16"

PRICES = {
    # model: (input, output)
    "claude-haiku-5-5": (0.10, 0.50),   # для промптів до 100 000 токенів
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
    "claude-fable-5-1": (10.00, 50.00),
    "gpt-6-luna": (0.10, 0.50),
    "gpt-6.1-sol": (2.00, 10.00),
    "gpt-6-astra": (10.00, 50.00),
    # embeddings: лише вхідні токени (~62 500 сторінок по ~800 токенів за $1 = $0.02 за 1 млн)
    "text-embedding-3-small": (0.02, 0.0),
}


# Кешування промпту Claude, USD за 1 млн токенів: (запис у кеш на 1 год, читання з кешу)
CACHE_PRICES = {
    "claude-haiku-5-5": (0.20, 0.01),
    "claude-sonnet-5-5": (4.00, 0.10),
    "claude-opus-5-5": (8.00, 0.20),
    "claude-fable-5-1": (20.00, 0.25),
}


def cost_usd(model, input_tokens, output_tokens, cache_write_tokens=0, cache_read_tokens=0):
    """Вартість у доларах або None, якщо ціни моделі немає в таблиці."""
    if model not in PRICES:
        return None
    pin, pout = PRICES[model]
    total = input_tokens * pin + output_tokens * pout
    if cache_write_tokens or cache_read_tokens:
        cw, cr = CACHE_PRICES.get(model, (pin * 2, pin * 0.1))
        total += cache_write_tokens * cw + cache_read_tokens * cr
    return total / 1_000_000
