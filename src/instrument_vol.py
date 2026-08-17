"""Per-instrument grading-band scales, measured from pre-corpus price history.

Session 30. Session 26 established that a verdict must measure the *call*, not
the instrument, and scaled the grading bands by asset class to get there
(`ASSET_CLASS_BAND_SCALE = {"ETF": 0.30}`). Session 28 found the class *field*
had gaps. This file is the next term in that series: the class **itself** is too
coarse a unit, and the artifact it was meant to remove survives inside it.

Measured on the live 30d corpus, the implied scale (each ticker's mean absolute
30d move over the median equity's) spans:

    ETFs       0.087 (VUSA.AS)  ->  0.766 (SEME.PA)     8.8x, against a flat 0.30
    equities   0.286 (1GOOGL.MI) -> 2.688 (TOYO)        9.4x, against a flat 1.00

and the two classes overlap heavily — SEME.PA, ISUN.L, CNRG and INRG.SW are all
ETFs that move further than AAPL or MDT. So "ETF" predicted volatility only in
the average, and the instruments at the edges were graded on bands that decided
their verdict before the call was read:

    ^STOXX50E   moves 1.56% in a month, needs 10% for a CORRECT WATCH
                -> 22 WATCH INCORRECT, 0 CORRECT, ever. A 0.0% hit rate that
                   measured nothing but the index's beta.
    SPY5.PA     moves 0.57%, and HOLD is CORRECT when flat within 1.2%
                -> 17 free CORRECTs, a 92% hit rate. The session-26 artifact
                   surviving *inside* the corrected class.

One auto-fails, the other auto-passes; both are the same bug.

**The estimation window ends before the corpus it grades** (12 months to
2026-05-16, the day before the earliest recommendation). This is the property
that makes the scale honest rather than circular: bands fitted to the same
returns they score would flatten every hit rate by construction and peek at the
future. Validated at that window against what the corpus actually did —
Spearman 0.90, Pearson 0.84, 84% of tickers inside 2x — so history ranks the
instruments well, and its worst individual error (~3x, TOYO and PYPL) is far
smaller than the ~9x spread the class constant imposes on everyone.

A scale of 1.00 is the median equity, so `HORIZON_BANDS` keep meaning exactly
what they meant: they were calibrated on a typical stock.

Re-derive with `scripts/derive_instrument_scales.py`, quarterly, alongside
`scripts/check_bands.py`. Changing a scale changes stored verdicts and needs a
`--regrade` with the user's sign-off — the same rule as the class constant and
`src/quote_types.py`, and for the same reason: mixed semantics in one corpus is
the bug session 26 spent a session undoing.
"""

# symbol -> mean absolute 30d move over the median equity's, measured
# 2025-05-16 -> 2026-05-16 (see the module docstring and the derivation script).
# Ordered by scale so the volatility spread is legible at a glance.
INSTRUMENT_BAND_SCALE = {
    "GERD.SW": 0.12,
    "VHYL.AS": 0.13,
    "VWRL.AS": 0.13,
    "SPY5.PA": 0.13,
    "VUSA.AS": 0.13,
    "IQSA.DE": 0.14,
    "EXSA.DE": 0.14,
    "EXUS.DE": 0.15,
    "^STOXX50E": 0.15,
    "BBVAE.MC": 0.15,
    "XESC.DE": 0.15,
    "HEDJ.MI": 0.15,
    "VUAA.L": 0.16,
    "SPY": 0.16,
    "LDEU.L": 0.16,
    "CHGX": 0.17,
    "NANC": 0.17,
    "GOP": 0.18,
    "EQQQ.DE": 0.18,
    "VXUS": 0.19,
    "LYXIB.MC": 0.20,
    "VUG": 0.21,
    "MDT": 0.27,
    "IQQH.DE": 0.29,
    "Q8Y0.DE": 0.29,
    "LYM9.F": 0.30,
    "AAPL": 0.32,
    "INRG.SW": 0.34,
    "AIR.PA": 0.34,
    "GCLE.MI": 0.34,
    "HWM": 0.37,
    "RR.L": 0.37,
    "ISUN.L": 0.42,
    "PYPL": 0.42,
    "AVGO": 0.49,
    "CNRG": 0.49,
    "SEME.PA": 0.50,
    "FSLR": 0.51,
    "1GOOGL.MI": 0.52,
    "GEV": 0.60,
    "NXT": 0.67,
    "AUR": 0.71,
    "FIX": 0.76,
    "SMCI": 0.89,
    "CLS": 0.92,
    "RDDT": 1.00,
    "KRKNF": 1.00,
    "TOYO": 1.01,
    "AMD": 1.11,
    "AVAV": 1.15,
    "MU": 1.19,
    "CSIQ": 1.21,
    "NBIS": 1.24,
    "RKLB": 1.43,
    "LITE": 1.52,
    "POET": 1.52,
    "ASTS": 1.59,
    "APLD": 1.61,
    "RGTI": 1.62,
    "AMPX": 1.78,
    "TE": 1.83,
    "IREN": 1.91,
}


def instrument_scale(symbol: str | None) -> float | None:
    """This instrument's band scale, or None if it has no measured history.

    None means "fall back to the asset-class scale" — it is not 1.0. A ticker
    added after the last derivation (or one too newly listed to estimate, like
    SOLS at 144 closes) must keep the coarser class behaviour rather than
    silently be declared as volatile as a typical stock.
    """
    if not symbol:
        return None
    return INSTRUMENT_BAND_SCALE.get(symbol)
