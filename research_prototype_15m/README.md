# Research Prototype – Kalshi 15-Minute Up/Down Dashboard

**THIS IS A READ-ONLY RESEARCH PROTOTYPE.**

It does not trade, size tickets, place orders, run background collectors, or use authenticated Kalshi endpoints.
It is **not** the GrokBot paper watcher. Paper stays with GrokBot.

Brain on screen: **B1** (Kalshi midpoint + jumpy/quiet, trend/sideways, distance-to-strike).
Phase 2R overlays (CVD, funding Z-score) exist as hidden stubs only.

## Universe

Book A (CALL allowed): BTC, ETH, SOL, ZEC, XRP, NEAR, HYPE, DOGE, BNB, GOLD, SILVER, WTI
Book B (quotes only): ADA, BCH, TON
Skipped: Crypto Leader / coin-race products

## How to run (on your machine)

```powershell
cd research_prototype_15m
$env:PYTHONPATH = "../src"
python -m streamlit run app.py
```

## Notes

- Settlement for coins is CF Benchmarks (60-second average). The dashboard uses a public spot proxy and labels it as such.
- Gold / silver / WTI settle on named Pyth feeds. If no public spot is available, the panel says so.
- Historical volatility uses `data/market.db` when coverage exists and degrades cleanly otherwise.
- Polls only while the browser tab is open. Backs off on HTTP 429.
