import json
import logging

import anthropic

from src.config import Config

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"

_MACRO_SYSTEM = (
    "Eres analista financiero. Identificas temas macro/sectoriales desde headlines "
    "y determinas qué sectores se ven afectados positiva o negativamente. "
    "Respondes en JSON estricto, sin texto adicional."
)

_RECOMMENDATION_SYSTEM = (
    "Eres analista financiero. Combinas señales técnicas, sentimiento de Reddit y "
    "contexto macro para emitir una recomendación accionable por activo. Cuando la "
    "evidencia lo respalda, das recomendaciones claras y decisivas — incluyendo BUY "
    "y SELL — y reservas HOLD/WATCH/AVOID para cuando la evidencia es mixta, débil o "
    "insuficiente. No te refugies por defecto en la opción neutral. "
    "Respondes en JSON estricto con el schema dado, sin texto adicional."
)

_SUMMARY_SYSTEM = (
    "Generas resúmenes bursátiles breves y útiles del día en formato markdown. "
    "Respondes en JSON estricto, sin texto adicional."
)


class ClaudeClient:
    def __init__(self, cfg: Config):
        self._client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)

    def analyze_macro(self, headlines: list[dict]) -> list[dict]:
        headline_text = "\n".join(
            f"- [{h.get('source', '')}] {h['title']}" for h in headlines
        )
        user_msg = f"""Headlines del día:
{headline_text}

Identifica 0-5 temas macro relevantes. Responde SOLO con un array JSON (puede ser []).
Para cada tema usa exactamente este schema:
{{
  "theme": "...",
  "affected_sectors": ["Energy", "Utilities"],
  "direction": {{"Energy": "POSITIVE", "Airlines": "NEGATIVE"}},
  "summary": "...",
  "source_headlines": ["..."]
}}"""

        response = self._client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=[{"type": "text", "text": _MACRO_SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_msg}],
        )
        return _parse_json(response.content[0].text, default=[])

    def analyze_ticker(self, ticker_data: dict, macro_signals: list[dict]) -> dict:
        tech = ticker_data.get("technical", {})
        sent = ticker_data.get("sentiment", {})

        relevant_macro = [
            s for s in macro_signals
            if ticker_data.get("sector") in (s.get("affected_sectors") or [])
        ]
        macro_text = (
            "\n".join(f"- {s['theme']}: {s['summary']}" for s in relevant_macro)
            if relevant_macro
            else "Sin señales macro relevantes para el sector."
        )

        top_posts = sent.get("top_posts", [])
        posts_text = (
            "\n".join(f"  - \"{p['title']}\" (score: {p['score']})" for p in top_posts[:3])
            if top_posts else "  Sin posts relevantes."
        )

        user_msg = f"""Ticker: {ticker_data['symbol']} ({ticker_data.get('name', '')}, sector: {ticker_data.get('sector', 'N/A')})
Posición actual: {ticker_data.get('phase', 'sin posición')}

Datos técnicos:
- Precio actual: ${tech.get('price', 'N/A')}
- RSI(14): {tech.get('rsi', 'N/A')}
- SMA 20/50/200: {tech.get('sma20', 'N/A')} / {tech.get('sma50', 'N/A')} / {tech.get('sma200', 'N/A')}
- Cambio 1d/7d/30d: {_pct(tech.get('change_1d'))} / {_pct(tech.get('change_7d'))} / {_pct(tech.get('change_30d'))}
- Posición en rango 52w: {_pct(tech.get('pos_52w'))}
- Volumen vs avg: {tech.get('volume_ratio', 'N/A')}x

Sentimiento Reddit:
- Menciones: {sent.get('mention_count', 0)} posts
- Score promedio: {sent.get('avg_score', 0):.1f}
- Posts más relevantes:
{posts_text}

Contexto macro relevante:
{macro_text}

Reglas de decisión según la posición:
- Si YA tienes posición (HOLDING): elige SELL cuando hay señales bajistas claras
  (deterioro técnico, ruptura de SMAs/soportes, RSI sobrecomprado revirtiendo, macro
  negativo para el sector) o HOLD cuando la tendencia sigue intacta o las señales son
  mixtas.
- Si NO tienes posición (WATCHLIST): elige BUY cuando hay una entrada atractiva
  (confluencia alcista: precio recuperando SMAs, RSI saliendo de sobreventa, momentum
  y/o macro a favor), WATCH cuando es interesante pero sin un punto de entrada claro
  todavía, o AVOID cuando las señales son negativas y no conviene entrar.

Calibración de confidence (0.0–1.0):
- 0.80–1.00: señales fuertemente alineadas en una dirección.
- 0.60–0.79: alineación moderada con alguna señal en contra.
- 0.40–0.59: señales mixtas o débiles.
- 0.00–0.39: poca evidencia / dominado por ruido.

Toma la acción decisiva (BUY/SELL) cuando la evidencia la respalde; no la evites por
prudencia. Responde SOLO con este JSON (sin texto adicional):
{{
  "action": "BUY|SELL|HOLD|WATCH|AVOID",
  "confidence": 0.0,
  "reasoning": "2-4 frases máximo, citando las señales concretas que pesaron"
}}"""

        response = self._client.messages.create(
            model=MODEL,
            max_tokens=512,
            system=[{"type": "text", "text": _RECOMMENDATION_SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_msg}],
        )
        return _parse_json(
            response.content[0].text,
            default={"action": "HOLD", "confidence": 0.5, "reasoning": "Error al parsear respuesta."},
        )

    def generate_daily_summary(self, analysis_data: dict) -> dict:
        tickers = analysis_data.get("tickers_analyzed", [])
        macro_signals = analysis_data.get("macro_signals", [])
        recommendations = analysis_data.get("recommendations", [])
        top_posts = analysis_data.get("top_reddit_posts", [])
        trending = analysis_data.get("trending_suggestions", [])

        recs_text = "\n".join(
            f"- {r['symbol']}: {r['action']} (confianza: {r.get('confidence', 0):.0%}) — {r.get('reasoning', '')}"
            for r in recommendations
        ) or "(ninguna)"
        macro_text = "\n".join(f"- {s['theme']}: {s['summary']}" for s in macro_signals) or "(ninguna)"
        posts_text = "\n".join(f"- \"{p['title']}\" (score: {p['score']})" for p in top_posts[:10]) or "(ninguno)"
        trending_text = ", ".join(t["symbol"] for t in trending) if trending else "(ninguno)"

        user_msg = f"""Tickers analizados: {', '.join(tickers) or '(ninguno)'}

Señales macro detectadas:
{macro_text}

Posts más relevantes de Reddit:
{posts_text}

Recomendaciones generadas:
{recs_text}

Tickers trending (no en watchlist/holdings): {trending_text}

Responde SOLO con este JSON (sin texto adicional):
{{
  "summary": "resumen markdown de 3-5 párrafos",
  "hot_tickers": ["NVDA", "TSLA"],
  "overall_sentiment": "BULLISH|BEARISH|MIXED|NEUTRAL"
}}"""

        response = self._client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=[{"type": "text", "text": _SUMMARY_SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_msg}],
        )
        return _parse_json(
            response.content[0].text,
            default={"summary": "Error generando resumen.", "hot_tickers": [], "overall_sentiment": "NEUTRAL"},
        )


def _parse_json(text: str, default):
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON from Claude: {e}\nText: {text[:300]}")
        return default


def _pct(v) -> str:
    return f"{v:+.1%}" if v is not None else "N/A"
