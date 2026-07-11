import json
import logging
import time

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

from src.analysis.actions import allowed_actions, coerce_action
from src.config import Config

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"

# The per-ticker calls go through the Message Batches API (50% discount).
# A batch of ~63 tiny Haiku requests normally ends within a few minutes;
# the deadline guards the cron job against a wedged batch (API max is 24h).
BATCH_POLL_SECONDS = 30
BATCH_DEADLINE_SECONDS = 45 * 60

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
    "Eres analista financiero de un inversor de largo plazo: sus posiciones se "
    "mantienen meses o años, no días. Combinas señales técnicas, sentimiento de "
    "Reddit y contexto macro para emitir una recomendación accionable por activo, "
    "evaluando la tesis de inversión a un horizonte de un mes a un año o más. "
    "Cuando la evidencia lo respalda, das recomendaciones claras y decisivas — "
    "incluyendo BUY y SELL — y reservas HOLD/WATCH/AVOID para cuando la evidencia "
    "es mixta, débil o insuficiente. No te refugies por defecto en la opción "
    "neutral, y no cambies de opinión por ruido de corto plazo: revertir una "
    "recomendación reciente exige información nueva y material, no un movimiento "
    "de precio de pocos días. "
    "Respondes en JSON estricto con el schema dado, sin texto adicional."
)

_SUMMARY_SYSTEM = (
    "Generas resúmenes bursátiles breves y útiles del día en formato markdown. "
    "Respondes en JSON estricto, sin texto adicional."
)

_RETRO_SYSTEM = (
    "Eres analista financiero de un inversor de largo plazo (posiciones de meses "
    "o años). Escribes retrospectivas semanales honestas en markdown: qué "
    "predicciones funcionaron, cuáles no, y qué patrones se repiten — sin "
    "maquillar los fallos. Respondes en JSON estricto, sin texto adicional."
)


class ClaudeClient:
    def __init__(self, cfg: Config):
        if not cfg.anthropic_api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is not set — required for recommendation runs "
                "(only evaluate_outcomes works without it)"
            )
        self._client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)
        # Token usage accumulated across the calls of a run (cost telemetry).
        # Batched tokens are tracked separately: the Batches API bills at 50%.
        self._usage = {
            "calls": 0, "input": 0, "output": 0,
            "batch_input": 0, "batch_output": 0,
            "cache_write": 0, "cache_read": 0,
        }

    def _record_usage(self, response, batch: bool = False) -> None:
        u = getattr(response, "usage", None)
        if u is None:
            return
        self._usage["calls"] += 1
        in_key, out_key = ("batch_input", "batch_output") if batch else ("input", "output")
        self._usage[in_key] += getattr(u, "input_tokens", 0) or 0
        self._usage[out_key] += getattr(u, "output_tokens", 0) or 0
        self._usage["cache_write"] += getattr(u, "cache_creation_input_tokens", 0) or 0
        self._usage["cache_read"] += getattr(u, "cache_read_input_tokens", 0) or 0

    def estimated_cost_usd(self) -> float:
        u = self._usage
        plain = sum(u[k] * _PRICE_PER_MTOK[k] for k in _PRICE_PER_MTOK)
        batched = 0.5 * (
            u["batch_input"] * _PRICE_PER_MTOK["input"]
            + u["batch_output"] * _PRICE_PER_MTOK["output"]
        )
        return (plain + batched) / 1_000_000

    def log_usage(self) -> None:
        u = self._usage
        logger.info(
            f"Claude usage: {u['calls']} calls — "
            f"input={u['input']} output={u['output']} "
            f"batch_input={u['batch_input']} batch_output={u['batch_output']} (50% rate) "
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

    def _ticker_request_params(self, ticker_data: dict, macro_signals: list[dict]) -> dict:
        """Builds the messages.create kwargs for one ticker recommendation.

        Shared between the single-call path (analyze_ticker) and the Batches
        path (analyze_tickers_batch) so both send byte-identical requests.
        """
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

        # Flip-stability (session 16): the model sees its own standing call and
        # how long it's held, and must name material new information to flip it.
        # Omitted on a ticker's first-ever run (no previous action exists).
        prev_action = ticker_data.get("prev_action")
        held_days = ticker_data.get("prev_held_days")
        held_txt = (
            f" (mantenida {held_days} día{'' if held_days == 1 else 's'})"
            if held_days is not None else ""
        )
        prev_block = (
            f"\nRecomendación vigente: {prev_action}{held_txt}. Cambiarla exige nombrar "
            "en el reasoning la información nueva y material que invalida la tesis "
            "anterior (earnings/guidance, ruptura técnica sostenida, cambio macro "
            "estructural). Si no existe esa información, mantén la recomendación "
            "vigente: un movimiento de precio de pocos días es ruido, no una tesis "
            "nueva.\n"
        ) if prev_action else ""

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

Horizonte de inversión: mínimo un mes, típicamente un año o más. Evalúa la tesis
de fondo a ese plazo; usa los indicadores de corto plazo (RSI, cambios 1d/7d) solo
como timing de entrada/salida, nunca como razón principal. Un movimiento semanal
no invalida una tesis de meses.
{prev_block}
Reglas de decisión según la posición:
- Si YA tienes posición (HOLDING): elige SELL cuando la tesis de largo plazo se
  deterioró (deterioro técnico sostenido, ruptura de SMAs/soportes relevantes, macro
  estructuralmente negativo para el sector) o HOLD cuando la tesis sigue intacta o
  las señales son mixtas.
- Si NO tienes posición (WATCHLIST): elige BUY cuando es un punto de entrada
  atractivo para una posición de varios meses (confluencia alcista: precio
  recuperando SMAs, RSI saliendo de sobreventa, momentum y/o macro a favor), WATCH
  cuando la tesis es interesante pero sin un punto de entrada claro todavía, o AVOID
  cuando las señales son negativas y no conviene entrar.

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
  "reasoning": "2-4 frases máximo, citando las señales concretas que pesaron y la tesis al horizonte de 1+ mes"
}}"""

        return {
            "model": MODEL,
            "max_tokens": 512,
            "system": _RECOMMENDATION_SYSTEM,
            "messages": [{"role": "user", "content": user_msg}],
            "output_config": {
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
        }

    def _parse_ticker_response(self, response, phase: str) -> dict | None:
        # Structured output guarantees schema-valid JSON. A refusal or truncation
        # still surfaces as None so the caller skips persistence (no fake HOLD).
        result = _structured_json(response, default=None)
        if result is None:
            return None
        # Defensive backstop: the enum already constrains the action, but coerce
        # (and log) anything out-of-set in case the constraint is ever bypassed.
        result["action"] = coerce_action(result.get("action", ""), phase)
        return result

    def analyze_ticker(self, ticker_data: dict, macro_signals: list[dict]) -> dict | None:
        """Single-ticker recommendation (ad-hoc/debug path; the run uses the batch)."""
        response = self._client.messages.create(
            **self._ticker_request_params(ticker_data, macro_signals)
        )
        self._record_usage(response)
        return self._parse_ticker_response(response, ticker_data.get("phase") or "WATCHLIST")

    def analyze_tickers_batch(
        self, ticker_items: list[dict], macro_signals: list[dict]
    ) -> dict[str, dict | None]:
        """Runs all per-ticker recommendations through the Message Batches API.

        Returns {symbol: recommendation-or-None}. Symbols can contain characters
        that custom_id forbids (e.g. "XESC.DE"), so requests are keyed "t<index>".
        A wedged batch is canceled at BATCH_DEADLINE_SECONDS and every ticker
        comes back None (the caller counts them as failures).
        """
        if not ticker_items:
            return {}

        requests = [
            Request(
                custom_id=f"t{i}",
                params=MessageCreateParamsNonStreaming(
                    **self._ticker_request_params(td, macro_signals)
                ),
            )
            for i, td in enumerate(ticker_items)
        ]
        batch = self._client.messages.batches.create(requests=requests)
        logger.info(f"Submitted message batch {batch.id} ({len(requests)} ticker requests)")

        deadline = time.monotonic() + BATCH_DEADLINE_SECONDS
        while True:
            batch = self._client.messages.batches.retrieve(batch.id)
            if batch.processing_status == "ended":
                break
            if time.monotonic() > deadline:
                logger.error(
                    f"Batch {batch.id} still {batch.processing_status} after "
                    f"{BATCH_DEADLINE_SECONDS}s — canceling"
                )
                self._client.messages.batches.cancel(batch.id)
                return {td["symbol"]: None for td in ticker_items}
            time.sleep(BATCH_POLL_SECONDS)

        counts = batch.request_counts
        logger.info(
            f"Batch {batch.id} ended: {counts.succeeded} succeeded, "
            f"{counts.errored} errored, {counts.canceled} canceled, {counts.expired} expired"
        )

        by_id = {f"t{i}": td for i, td in enumerate(ticker_items)}
        results: dict[str, dict | None] = {td["symbol"]: None for td in ticker_items}
        for entry in self._client.messages.batches.results(batch.id):
            td = by_id.get(entry.custom_id)
            if td is None:
                continue
            if entry.result.type != "succeeded":
                logger.error(f"{td['symbol']}: batch request {entry.result.type}")
                continue
            message = entry.result.message
            self._record_usage(message, batch=True)
            results[td["symbol"]] = self._parse_ticker_response(
                message, td.get("phase") or "WATCHLIST"
            )
        return results

    def generate_daily_summary(self, analysis_data: dict) -> dict | None:
        tickers = analysis_data.get("tickers_analyzed", [])
        macro_signals = analysis_data.get("macro_signals", [])
        recommendations = analysis_data.get("recommendations", [])
        action_flips = analysis_data.get("action_flips", [])
        top_posts = analysis_data.get("top_reddit_posts", [])
        trending = analysis_data.get("trending_suggestions", [])

        recs_text = "\n".join(
            f"- {r['symbol']}: {r['action']} (confianza: {r.get('confidence', 0):.0%}) — {r.get('reasoning', '')}"
            for r in recommendations
        ) or "(ninguna)"
        flips_text = "\n".join(
            f"- {f['symbol']}: {f['prev_action']} → {f['new_action']}" for f in action_flips
        ) or "(ninguno)"
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

Cambios de recomendación vs la corrida anterior:
{flips_text}

Tickers trending (no en watchlist/holdings): {trending_text}

Genera:
- `summary`: resumen markdown de 3-5 párrafos para un inversor de largo plazo (horizonte de un mes a un año o más) — enfócate en implicaciones a ese plazo, no en movimientos intradía. Si hubo cambios de recomendación, destácalos explícitamente (qué cambió y por qué es relevante).
- `hot_tickers`: los tickers más relevantes del día.
- `overall_sentiment`: el sentimiento general del mercado."""

        response = self._client.messages.create(
            model=MODEL,
            max_tokens=2048,
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
        # None on failure — the caller must skip persistence rather than upsert
        # an error placeholder over the day's row (same rule as analyze_ticker).
        return _structured_json(response, default=None)

    def generate_weekly_retrospective(self, retro_data: dict) -> dict | None:
        """Week-in-review for a long-term investor (S5; Fridays, 1 extra call).

        `retro_data` is the pre-aggregated payload from
        src.analysis.retrospective.build_retro_data — counts + highlights, not
        raw rows, so the prompt stays small at any outcome volume.
        """
        o = retro_data.get("outcomes", {})
        horizon = retro_data.get("horizon_days", 30)

        def _calls_text(calls: list[dict]) -> str:
            return "\n".join(
                f"- {c['symbol']}: {c['action']} del {c['called_on']}, "
                f"retorno {c['forward_return']:+.1%}"
                for c in calls
            ) or "(ninguna)"

        hit_rate = o.get("hit_rate_pct")
        outcomes_line = (
            f"{o.get('total', 0)} llamadas maduraron: {o.get('correct', 0)} CORRECT / "
            f"{o.get('incorrect', 0)} INCORRECT / {o.get('neutral', 0)} NEUTRAL"
            + (f" — hit rate {hit_rate}% sobre las decididas" if hit_rate is not None else "")
        )

        flips = retro_data.get("flips", [])
        flips_text = "\n".join(
            f"- {f['day']} {f['symbol']}: {f['prev_action']} → {f['new_action']}"
            for f in flips
        ) or "(ninguno)"

        exposure = retro_data.get("sector_exposure", {})
        exposure_text = "\n".join(
            f"- {phase}: " + ", ".join(f"{sector} {n}" for sector, n in sectors.items())
            for phase, sectors in exposure.items()
        ) or "(sin posiciones)"

        user_msg = f"""Retrospectiva de la semana del {retro_data.get('week_start', '?')} (horizonte de evaluación: {horizon} días).

Resultados a {horizon} días que maduraron esta semana:
{outcomes_line}

Mejores aciertos de la semana:
{_calls_text(o.get('best', []))}

Peores fallos de la semana:
{_calls_text(o.get('worst', []))}

Cambios de recomendación durante la semana:
{flips_text}

Exposición sectorial actual (tickers por sector):
{exposure_text}

Genera `retrospective`: una retrospectiva en markdown de 3-5 párrafos para un
inversor de largo plazo — qué acertaron y qué fallaron las recomendaciones al
horizonte de {horizon} días (con los tickers concretos), si los cambios de
recomendación de la semana parecen tesis reales o ruido de corto plazo, qué
sesgos o patrones se repiten (por acción o sector), y qué implica todo esto
para las posiciones a 1+ mes vista. Sé honesto con los fallos."""

        response = self._client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=_RETRO_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": {
                        "type": "object",
                        "properties": {"retrospective": {"type": "string"}},
                        "required": ["retrospective"],
                        "additionalProperties": False,
                    },
                }
            },
        )
        self._record_usage(response)
        return _structured_json(response, default=None)


def _structured_json(response, default):
    """Parse a response produced with ``output_config.format`` (json_schema).

    The format constraint guarantees the first text block is schema-valid JSON,
    so no ```-fence stripping is needed. Stays defensive anyway: a refusal,
    truncation (``max_tokens``), or empty content returns ``default``.
    """
    stop_reason = getattr(response, "stop_reason", None)
    if stop_reason == "refusal":
        logger.error("Claude refused the structured request (stop_reason=refusal)")
        return default
    if stop_reason == "max_tokens":
        logger.error("Structured response truncated (stop_reason=max_tokens) — raise max_tokens")
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
