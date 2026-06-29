import json
import logging

import anthropic

from src.analysis.actions import allowed_actions, coerce_action
from src.config import Config

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"

# Haiku 4.5 list pricing, USD per million tokens (see /claude-api → models table).
# cache_control was removed in session 08 (min cacheable prefix is 4096 tokens),
# so cache_write/cache_read should stay at 0 — tracked anyway to confirm that.
_PRICE_PER_MTOK = {
    "input": 1.00,
    "output": 5.00,
    "cache_write": 1.25,  # 1.25x input
    "cache_read": 0.10,   # 0.1x input
}

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
        # Token usage accumulated across the 2+N calls of a run (cost telemetry).
        self._usage = {"calls": 0, "input": 0, "output": 0, "cache_write": 0, "cache_read": 0}

    def _record_usage(self, response) -> None:
        u = getattr(response, "usage", None)
        if u is None:
            return
        self._usage["calls"] += 1
        self._usage["input"] += getattr(u, "input_tokens", 0) or 0
        self._usage["output"] += getattr(u, "output_tokens", 0) or 0
        self._usage["cache_write"] += getattr(u, "cache_creation_input_tokens", 0) or 0
        self._usage["cache_read"] += getattr(u, "cache_read_input_tokens", 0) or 0

    def estimated_cost_usd(self) -> float:
        return sum(
            self._usage[k] * _PRICE_PER_MTOK[k] for k in _PRICE_PER_MTOK
        ) / 1_000_000

    def log_usage(self) -> None:
        u = self._usage
        logger.info(
            f"Claude usage: {u['calls']} calls — "
            f"input={u['input']} output={u['output']} "
            f"cache_write={u['cache_write']} cache_read={u['cache_read']} tokens; "
            f"estimated cost ${self.estimated_cost_usd():.4f} ({MODEL})"
        )

    def analyze_macro(self, headlines: list[dict]) -> list[dict]:
        headline_text = "\n".join(
            f"- [{h.get('source', '')}] {h['title']}" for h in headlines
        )
        user_msg = f"""Headlines del día:
{headline_text}

Identifica 0-5 temas macro relevantes (el array `themes` puede quedar vacío).
Para cada tema:
- `affected_sectors`: sectores afectados.
- `direction`: un item por sector con su sentimiento (POSITIVE/NEGATIVE/NEUTRAL).
- `source_headlines`: los titulares concretos que respaldan el tema."""

        response = self._client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=_MACRO_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "themes": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "theme": {"type": "string"},
                                        "affected_sectors": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                        # A free-form {sector: sentiment} map can't be
                                        # expressed under additionalProperties:false, so
                                        # the model returns a list and we fold it back
                                        # into the stored map below.
                                        "direction": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "sector": {"type": "string"},
                                                    "sentiment": {
                                                        "type": "string",
                                                        "enum": ["POSITIVE", "NEGATIVE", "NEUTRAL"],
                                                    },
                                                },
                                                "required": ["sector", "sentiment"],
                                                "additionalProperties": False,
                                            },
                                        },
                                        "summary": {"type": "string"},
                                        "source_headlines": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                    },
                                    "required": [
                                        "theme", "affected_sectors", "direction",
                                        "summary", "source_headlines",
                                    ],
                                    "additionalProperties": False,
                                },
                            }
                        },
                        "required": ["themes"],
                        "additionalProperties": False,
                    },
                }
            },
        )
        self._record_usage(response)
        result = _structured_json(response, default={"themes": []})
        themes = result.get("themes", []) if result else []
        for theme in themes:
            # Persist `direction` as the original {sector: sentiment} map.
            theme["direction"] = {
                d["sector"]: d["sentiment"] for d in theme.get("direction", [])
            }
        return themes

    def analyze_ticker(self, ticker_data: dict, macro_signals: list[dict]) -> dict | None:
        tech = ticker_data.get("technical", {})
        sent = ticker_data.get("sentiment", {})

        # The action set is constrained by the position phase (HOLDING -> HOLD/SELL,
        # WATCHLIST -> BUY/WATCH/AVOID). Both the prompt wording and the structured
        # output schema below reflect this allowed set for the ticker.
        phase = ticker_data.get("phase") or "WATCHLIST"
        allowed = allowed_actions(phase)

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

        # Optional blocks: omitted entirely when there's nothing to show, so
        # tickers without news/earnings (e.g. ETFs) keep the original prompt.
        news_titles = [n["title"] for n in (ticker_data.get("news") or []) if n.get("title")]
        news_block = (
            "\nNoticias recientes del ticker:\n"
            + "\n".join(f"- {t}" for t in news_titles[:5])
            + "\n"
        ) if news_titles else ""

        next_earnings = ticker_data.get("next_earnings")
        earnings_block = (
            f"\nPróximo reporte de earnings: {next_earnings} — si es inminente, "
            "considera el riesgo del evento en la acción y el confidence.\n"
        ) if next_earnings else ""

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
{news_block}{earnings_block}
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

Toma la decisión más decisiva que la evidencia respalde; no te refugies en la
opción neutral por prudencia. Para esta posición ({phase}) la acción DEBE ser
una de: {", ".join(allowed)}. Responde SOLO con este JSON (sin texto adicional):
{{
  "action": "{"|".join(allowed)}",
  "confidence": 0.0,
  "reasoning": "2-4 frases máximo, citando las señales concretas que pesaron"
}}"""

        response = self._client.messages.create(
            model=MODEL,
            max_tokens=512,
            system=_RECOMMENDATION_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": {
                        "type": "object",
                        "properties": {
                            # enum pins the action to the phase's allowed set, so
                            # an out-of-set action is structurally impossible.
                            "action": {"type": "string", "enum": list(allowed)},
                            "confidence": {"type": "number"},
                            "reasoning": {"type": "string"},
                        },
                        "required": ["action", "confidence", "reasoning"],
                        "additionalProperties": False,
                    },
                }
            },
        )
        self._record_usage(response)
        # Structured output guarantees schema-valid JSON. A refusal or truncation
        # still surfaces as None so the caller skips persistence (no fake HOLD).
        result = _structured_json(response, default=None)
        if result is None:
            return None
        # Defensive backstop: the enum already constrains the action, but coerce
        # (and log) anything out-of-set in case the constraint is ever bypassed.
        result["action"] = coerce_action(result.get("action", ""), phase)
        return result

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

Genera:
- `summary`: resumen markdown de 3-5 párrafos.
- `hot_tickers`: los tickers más relevantes del día.
- `overall_sentiment`: el sentimiento general del mercado."""

        response = self._client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=_SUMMARY_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "summary": {"type": "string"},
                            "hot_tickers": {"type": "array", "items": {"type": "string"}},
                            "overall_sentiment": {
                                "type": "string",
                                "enum": ["BULLISH", "BEARISH", "MIXED", "NEUTRAL"],
                            },
                        },
                        "required": ["summary", "hot_tickers", "overall_sentiment"],
                        "additionalProperties": False,
                    },
                }
            },
        )
        self._record_usage(response)
        return _structured_json(
            response,
            default={"summary": "Error generando resumen.", "hot_tickers": [], "overall_sentiment": "NEUTRAL"},
        )


def _structured_json(response, default):
    """Parse a response produced with ``output_config.format`` (json_schema).

    The format constraint guarantees the first text block is schema-valid JSON,
    so no ```-fence stripping is needed. Stays defensive anyway: a refusal,
    truncation (``max_tokens``), or empty content returns ``default``.
    """
    if getattr(response, "stop_reason", None) == "refusal":
        logger.error("Claude refused the structured request (stop_reason=refusal)")
        return default
    text = next(
        (b.text for b in response.content if getattr(b, "type", None) == "text"),
        None,
    )
    if not text:
        logger.error("Structured response had no text block")
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse structured JSON from Claude: {e}\nText: {text[:300]}")
        return default


def _pct(v) -> str:
    return f"{v:+.1%}" if v is not None else "N/A"
