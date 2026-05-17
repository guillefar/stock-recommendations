# Stock Recommendations System — Specification

## Overview

Sistema automatizado que genera recomendaciones de compra/venta de acciones combinando:
- Datos técnicos (precios e indicadores)
- Sentimiento de Reddit (/r/stocks)
- Noticias macro/sectoriales (RSS feeds + yfinance news)
- Análisis con LLM (Claude API)

Corre **2 veces al día, lunes a viernes** en **GitHub Actions** (sin servidor propio).

---

## Sistema existente del que depende

Existe un proyecto separado (`stock-snapshots`) que ya maneja:
- Tabla `tickers`: catálogo de activos con campos `symbol`, `currency`, `name`, `sector`, `industry`, `long_business_summary`, etc.
- Tabla `holdings`: posiciones actuales (campo `quantity > 0` = posición viva)
- Tabla `watchlist`: activos observados (campo `active = 1` = activos)
- Tabla `transactions`: historial de BUY/SELL
- Tabla `price_snapshots`: serie temporal de precios alineada a rejilla canónica (`MINUTE(as_of_date) = 7`)
- Collector que corre periódicamente y guarda snapshots via yfinance
- Stored procedures: `sp_buy`, `sp_sell`, `sp_add_watch`, `sp_deactivate_watch`
- Las fases relevantes son `WATCHLIST` y `HOLDING`

**Este nuevo proyecto NO modifica esas tablas** — solo lee de ellas y escribe en tablas nuevas.

Hay un Grafana conectado a la misma DB que el usuario querría poder usar para visualizar las recomendaciones (nice-to-have).

---

## Arquitectura

```
GitHub Actions (cron 2x/día)
  │
  ├─ 1. Lee tickers desde MySQL (holdings.quantity>0 ∪ watchlist.active=1)
  ├─ 2. yfinance: precios + histórico 30d + news por ticker
  ├─ 3. PRAW: scraping /r/stocks front page (~25-50 hot posts)
  ├─ 4. RSS feeds: top headlines de noticias macro
  ├─ 5. Calcula indicadores técnicos (pandas)
  ├─ 6. Detecta tickers trending en Reddit fuera de holdings/watchlist
  ├─ 7. Claude API (Haiku):
  │       - Análisis macro: identifica temas y sectores afectados
  │       - Recomendación por ticker
  │       - Resumen diario
  └─ 8. Persiste en MySQL (4 tablas nuevas)
```

---

## Decisiones tomadas

| Decisión | Valor |
|---|---|
| Modelo LLM | `claude-haiku-4-5-20251001` |
| Schedule | 2x/día, lunes a viernes (ej. 13:00 y 21:00 UTC) |
| Subreddits | Solo `/r/stocks` por ahora |
| Filtro Reddit | hot posts, primera página, `score > 50` y `upvote_ratio > 0.7` |
| Hosting | GitHub Actions (cron) |
| Dashboard | Grafana existente (más adelante) |
| Lenguaje | Python 3.11+ |
| Tickers a analizar | Holdings activos + watchlist activa + tickers trending en Reddit |
| Output estructurado | JSON desde Claude → INSERT directo en MySQL |

---

## Schema de las tablas nuevas

```sql
-- Recomendaciones individuales por ticker
CREATE TABLE recommendations (
  id            BIGINT AUTO_INCREMENT PRIMARY KEY,
  ticker_id     INT NOT NULL,
  generated_at  DATETIME NOT NULL,
  action        ENUM('BUY','SELL','HOLD','WATCH','AVOID') NOT NULL,
  confidence    DECIMAL(3,2),
  reasoning     TEXT,
  technical     JSON,           -- {rsi, sma20, sma50, sma200, change_1d, ...}
  sentiment     JSON,           -- {reddit_score, mention_count, top_posts}
  macro_signal_id BIGINT NULL,  -- FK opcional a macro_signals
  model_used    VARCHAR(50),
  FOREIGN KEY (ticker_id) REFERENCES tickers(id),
  INDEX idx_ticker_date (ticker_id, generated_at)
);

-- Resumen diario de mercado / "rumores"
CREATE TABLE daily_market_summary (
  id                BIGINT AUTO_INCREMENT PRIMARY KEY,
  summary_date      DATE NOT NULL,
  generated_at      DATETIME NOT NULL,
  summary           TEXT,                -- markdown
  hot_tickers       JSON,                -- ["NVDA","TSLA",...]
  overall_sentiment VARCHAR(20),         -- BULLISH/BEARISH/MIXED/NEUTRAL
  source_post_count INT,
  UNIQUE KEY uq_summary_date (summary_date)
);

-- Posts de Reddit que mencionan tickers (auditoría + evolución de rumores)
CREATE TABLE reddit_mentions (
  id              BIGINT AUTO_INCREMENT PRIMARY KEY,
  ticker_id       INT,                   -- NULL si es un ticker no conocido
  post_id         VARCHAR(20) NOT NULL,
  post_title      TEXT,
  post_url        VARCHAR(500),
  post_score      INT,
  post_created_at DATETIME,
  sentiment       ENUM('POSITIVE','NEGATIVE','NEUTRAL','MIXED'),
  captured_at     DATETIME,
  FOREIGN KEY (ticker_id) REFERENCES tickers(id),
  UNIQUE KEY uq_post_ticker (post_id, ticker_id),
  INDEX idx_ticker_date (ticker_id, captured_at)
);

-- Señales macro detectadas en noticias (ej. "crisis petróleo → renovables")
CREATE TABLE macro_signals (
  id               BIGINT AUTO_INCREMENT PRIMARY KEY,
  detected_at      DATETIME NOT NULL,
  theme            VARCHAR(200),         -- "Oil supply crisis"
  affected_sectors JSON,                 -- ["Energy","Utilities"]
  direction        JSON,                 -- {"Energy":"POSITIVE","Airlines":"NEGATIVE"}
  source_headlines JSON,                 -- títulos de noticias usadas
  summary          TEXT
);
```

---

## Indicadores técnicos a calcular

Implementar con `pandas` desde data de yfinance (sin TA-Lib):

| Indicador | Fórmula resumida |
|---|---|
| RSI(14) | Standard 14-period RSI |
| SMA 20, 50, 200 | Simple moving averages |
| Cambio % 1d, 7d, 30d | `(price_now / price_then) - 1` |
| Posición vs 52w high/low | `(price - low_52w) / (high_52w - low_52w)` |
| Volume vs avg | `volume_today / avg_volume_30d` |

Estos van al campo `technical` (JSON) de `recommendations`.

---

## Fuentes de datos

### yfinance (precios + news por ticker)
```python
ticker = yfinance.Ticker("AAPL")
ticker.history(period="30d")  # OHLCV
ticker.news                    # headlines por ticker
```

### Reddit /r/stocks (PRAW)
- App tipo "script" en https://www.reddit.com/prefs/apps
- Variables: `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT`
- Traer `subreddit("stocks").hot(limit=50)`
- Filtrar `score > 50 and upvote_ratio > 0.7`
- Detectar tickers via regex: `\$[A-Z]{1,5}\b` y matching de palabras en mayúsculas contra la tabla `tickers`

### RSS feeds (noticias macro)
Usar `feedparser`:
```python
FEEDS = [
    "https://www.reutersagency.com/feed/?best-sectors=business-finance",
    "http://feeds.marketwatch.com/marketwatch/topstories/",
    "https://finance.yahoo.com/news/rssindex",
]
```
Traer top 20-30 headlines del día, dedup por título.

---

## Prompts de Claude (estructura)

### Prompt 1: Análisis macro (corre 1 vez por ejecución)

```
SYSTEM: Eres analista financiero. Identificas temas macro/sectoriales 
desde headlines y determinas qué sectores se ven afectados positiva o 
negativamente. Respondes en JSON estricto.

USER: Headlines del día:
[lista de 20-30 titulares con fuente]

Identifica 0-5 temas macro relevantes. Para cada uno:
{
  "theme": "...",
  "affected_sectors": ["Energy", "Utilities"],
  "direction": {"Energy": "POSITIVE", "Airlines": "NEGATIVE"},
  "summary": "...",
  "source_headlines": [...]
}
```

### Prompt 2: Recomendación por ticker (corre N veces, una por ticker)

```
SYSTEM: Eres analista financiero conservador. Combinas señales técnicas, 
sentimiento de Reddit y contexto macro. NUNCA das consejos absolutos.
Respondes en JSON estricto con el schema dado.

USER:
Ticker: {symbol} ({name}, sector: {sector})
Posición actual: {holding_info | "no posición"}

Datos técnicos:
- Precio actual: $X
- RSI(14): Y
- SMA 20/50/200: ...
- Cambio 1d/7d/30d: ...
- Posición en rango 52w: X%
- Volumen vs avg: X

Sentimiento Reddit (último día):
- Menciones: N posts
- Score promedio: X
- Posts más relevantes: [título + score + sentiment]

Contexto macro relevante:
[señales macro que afectan al sector del ticker]

Genera:
{
  "action": "BUY|SELL|HOLD|WATCH|AVOID",
  "confidence": 0.0-1.0,
  "reasoning": "..."  // 2-4 frases máximo
}
```

### Prompt 3: Resumen diario (corre 1 vez)

```
SYSTEM: Generas un resumen breve y útil del día en formato markdown.

USER: 
- Tickers analizados: [...]
- Señales macro detectadas: [...]
- Posts más relevantes de Reddit: [...]
- Recomendaciones generadas: [...]

Genera un resumen markdown breve (3-5 párrafos) de "lo interesante del día".
Identifica hot_tickers y overall_sentiment.
```

---

## Detección de tickers trending

Después de procesar los posts de Reddit:
1. Contar menciones por ticker (incluyendo los no conocidos)
2. Para tickers no presentes en `tickers` con > 3 menciones en posts con `score > 100`:
   - Marcarlos como "trending_suggestion"
   - Incluirlos en el resumen diario como sugerencias para agregar a watchlist
3. NO crear recomendaciones formales para tickers desconocidos (falta data técnica e info de la empresa)

---

## Estructura del proyecto sugerida

```
stock-recommendations/
├── SPEC.md                          # este archivo
├── README.md
├── pyproject.toml                   # o requirements.txt
├── .env.example
├── .gitignore
├── migrations/
│   └── 001_create_recommendation_tables.sql
├── src/
│   ├── __init__.py
│   ├── main.py                      # entrypoint: orquesta todo
│   ├── config.py                    # carga env vars
│   ├── db.py                        # conexión MySQL, helpers
│   ├── collectors/
│   │   ├── prices.py                # yfinance + indicadores técnicos
│   │   ├── reddit.py                # PRAW scraping y detección de tickers
│   │   └── news.py                  # RSS feeds + yfinance news
│   ├── analysis/
│   │   ├── claude_client.py         # wrapper de Anthropic SDK con caching
│   │   ├── macro.py                 # análisis de señales macro
│   │   ├── recommendation.py        # recomendación por ticker
│   │   └── summary.py               # resumen diario
│   └── persistence/
│       └── writers.py               # INSERTs a las 4 tablas
├── tests/
└── .github/workflows/
    └── run_recommendations.yml      # cron 2x/día
```

---

## GitHub Actions workflow

```yaml
name: Stock Recommendations

on:
  schedule:
    - cron: '0 13 * * 1-5'   # 13:00 UTC lun-vie
    - cron: '0 21 * * 1-5'   # 21:00 UTC lun-vie
  workflow_dispatch:          # permite ejecución manual

jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'
      - run: pip install -r requirements.txt
      - run: python -m src.main
        env:
          DB_HOST: ${{ secrets.DB_HOST }}
          DB_USER: ${{ secrets.DB_USER }}
          DB_PASS: ${{ secrets.DB_PASS }}
          DB_NAME: ${{ secrets.DB_NAME }}
          DB_PORT: ${{ secrets.DB_PORT }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          REDDIT_CLIENT_ID: ${{ secrets.REDDIT_CLIENT_ID }}
          REDDIT_CLIENT_SECRET: ${{ secrets.REDDIT_CLIENT_SECRET }}
          REDDIT_USER_AGENT: ${{ secrets.REDDIT_USER_AGENT }}
```

---

## Credenciales/Secrets necesarios

A configurar como **GitHub Secrets** en el repo (`Settings → Secrets and variables → Actions`):

| Secret | Origen |
|---|---|
| `DB_HOST`, `DB_USER`, `DB_PASS`, `DB_NAME`, `DB_PORT` | Mismas que usa `stock-snapshots` |
| `ANTHROPIC_API_KEY` | https://console.anthropic.com/ |
| `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` | Reddit app tipo "script" |
| `REDDIT_USER_AGENT` | String descriptivo, ej. `"stock-recs by /u/{user}"` |

---

## Orden de construcción (build plan)

1. **Migración SQL** — crear las 4 tablas en la DB.
2. **Estructura del proyecto** + `requirements.txt` + `.env.example`.
3. **Módulo `db.py`** — conexión MySQL, helper para leer tickers activos.
4. **Módulo `collectors/prices.py`** — yfinance + cálculo de indicadores técnicos.
5. **Módulo `collectors/reddit.py`** — scraping /r/stocks + detección de tickers.
6. **Módulo `collectors/news.py`** — RSS feeds + yfinance news.
7. **Módulo `analysis/claude_client.py`** — wrapper Anthropic SDK con prompt caching.
8. **Módulo `analysis/macro.py`** — análisis macro de noticias.
9. **Módulo `analysis/recommendation.py`** — recomendación por ticker.
10. **Módulo `analysis/summary.py`** — resumen diario.
11. **Detección de tickers trending** — lógica para sugerencias nuevas.
12. **Módulo `persistence/writers.py`** — INSERTs a las 4 tablas.
13. **`main.py`** — orquestador.
14. **GitHub Actions workflow** + configuración de secrets.
15. **Pruebas locales** — `python -m src.main` con DB de prueba o flag `--dry-run`.
16. **Paneles de Grafana** (opcional, después de la primera ejecución exitosa).

---

## Notas importantes

- **No modificar** tablas/SPs del proyecto `stock-snapshots`. Solo lectura.
- **No introducir abstracciones prematuras**. Código directo, pocas capas.
- **Manejar errores en bordes externos** (APIs de yfinance, Reddit, RSS) pero no envolver código interno en try/except defensivos.
- **Idempotencia**: si una ejecución falla a mitad, una re-ejecución no debería duplicar datos. Las UNIQUE keys de las tablas ayudan.
- **Modo dry-run** desde el inicio (`--dry-run` no escribe en DB, solo loggea).
- **Logs claros** — esta cosa corre desatendida; los logs son tu única ventana.
- **Rate limits**: yfinance puede tirar 429; PRAW respeta automáticamente el rate limit de Reddit.
