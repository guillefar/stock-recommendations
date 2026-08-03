"""Asset-class resolution for instruments the source `tickers` table leaves untyped.

Session 28. `tickers.quote_type` comes from the read-only stock-snapshots
database, and it is NULL for two of the 63 active tickers — **VHYL.AS**
(Vanguard FTSE All-World High Dividend Yield UCITS ETF, Amsterdam) and
**SPY5.PA** (State Street SPDR S&P 500 UCITS ETF, Paris). Both are genuine
ETFs: yfinance reports `quoteType='ETF'` for each, and their own names say so.

That NULL was not cosmetic. Session 26 scaled the grading bands by asset class
(`ASSET_CLASS_BAND_SCALE`) precisely because ETFs move ~0.30× as far as stocks,
but it keyed the scale on `quote_type` and treated NULL as "unknown → use the
unscaled single-stock bands", so these two ETFs kept being graded as if they
were stocks. Measured 30d mean absolute move:

    EQUITY    15.87%      ETF     4.32%
    VHYL.AS    2.05%      SPY5.PA 1.28%

They are not merely ETF-like, they are calmer than the average ETF — 0.13× and
0.08× a stock. Grading them on stock bands reproduced exactly the artifact
session 26 fixed everywhere else: HOLD is CORRECT when flat and these are
always flat, so 70 of their HOLD rows scored a free CORRECT.

Session 27's market-relative cohort inherited the same NULL. `_cohort_key`
splits on ETF-vs-not, so both landed in the equity cohort (mean −8.57%) while
returning like ETFs (−1.17%), manufacturing a **+10pp excess** out of nothing.
The miner found it immediately and called `WATCH × (otro)` a "colapso
catastrófico" — a bucket whose headline number was pure mis-cohorting.

The fix is a lookup applied at the three points where the column is read
(`get_active_tickers`, `get_outcome_features`, `_fetch_matured`), so every
consumer downstream — grading bands, mining cohort, the ETF prompt block, the
sector bucket — sees the corrected class without knowing this file exists.

**^STOXX50E is deliberately not here.** It is an INDEX, not an instrument
anyone can hold, so its verdicts are a different question from an asset-class
scale (see PLAN.md's decisions log and HANDOFF_28).

Add an entry only for an instrument whose class is genuinely known and wrong at
the source — verify against `yfinance` `Ticker.info['quoteType']` first, and
remember that changing a mapping changes stored verdicts and needs a
`--regrade` with the user's sign-off.
"""

# symbol -> the asset class the source table should have carried.
QUOTE_TYPE_OVERRIDES = {
    "VHYL.AS": "ETF",
    "SPY5.PA": "ETF",
}


def resolve_quote_type(symbol: str | None, quote_type: str | None) -> str | None:
    """The instrument's true asset class, correcting known-bad source values.

    Only fills gaps: a symbol with a real `quote_type` is returned untouched, so
    an override can never silently contradict the source table once it starts
    populating the column.
    """
    if quote_type:
        return quote_type
    return QUOTE_TYPE_OVERRIDES.get(symbol)


def apply_quote_type_overrides(rows: list[dict]) -> list[dict]:
    """Corrects `quote_type` in place across DB rows carrying `symbol`.

    Rows without a `symbol` key are left alone rather than raising — a query
    that forgets to select it should lose the correction, not the run.
    """
    for row in rows:
        if "symbol" in row:
            row["quote_type"] = resolve_quote_type(row.get("symbol"), row.get("quote_type"))
    return rows
