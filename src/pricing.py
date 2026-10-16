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
}


def cost_usd(model, input_tokens, output_tokens):
    """Вартість у доларах або None, якщо ціни моделі немає в таблиці."""
    if model not in PRICES:
        return None
    pin, pout = PRICES[model]
    return (input_tokens * pin + output_tokens * pout) / 1_000_000
