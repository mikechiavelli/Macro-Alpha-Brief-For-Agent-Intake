# PFT Macro Alpha Brief — Stablecoin Liquidity × Major-Asset Rotation

A single canonical, machine-readable macro alpha brief for the **Post Fiat (PFT) Alpha Registry**.
It turns an analyst read of the current market window into auditable, structured buy-side input
that Post Fiat agent intelligence surfaces (Hive Mind routing, Task Node allocation) can ingest
without re-auditing the underlying sources.

- **Artifact:** [`pft_macro_alpha_brief_v1.json`](./pft_macro_alpha_brief_v1.json)
- **Validator:** [`macro_brief_guard.py`](./macro_brief_guard.py)
- **`brief_id`:** `pft-mab-20260530-0ae6bc15cf`
- **`report_type`:** `macro_alpha_brief` (schema_version `1.1.0`)
- **`data_as_of`:** `2026-05-30T15:57:58Z`
- **Status:** `ACCEPT` — passes `macro_brief_guard.py` with zero rejection codes.

## Thesis

Aggregate stablecoin supply is flat-to-contracting while capital concentrates into BTC at the
expense of ETH and alts. The current window is a **defensive rotation regime**: overweight BTC,
underweight ETH and alt beta, until either stablecoin supply re-expands (fresh liquidity) or
ETH/BTC bases and turns up (rotation back out the risk curve).

- **Direction:** `risk_off_btc_overweight`
- **Horizon:** 30 days
- **Conviction:** `0.62` (overall confidence tier `MEDIUM`)

## Evidence readings (as of `2026-05-30T15:57:58Z`)

| Metric | Reading | Window | Confidence |
|---|---|---|---|
| Stablecoin aggregate market cap | $315.46B | spot | HIGH |
| USDT+USDC supply change | −0.96% (−$2.57B) | 30d | MEDIUM (supply proxy) |
| BTC dominance | 57.45% | spot | HIGH |
| ETH/BTC ratio | 0.027408 | spot | HIGH |
| ETH/BTC change (ETH −10.54% vs BTC −3.18%) | −7.30% | 30d | HIGH |
| TOTAL3 (ex-BTC, ex-ETH market cap) | $850.93B | spot | HIGH |

## Scoring readiness

Normalized to `[-1, 1]` against bull/bear thresholds; consumed directly by the routing layer.

| Signal | Reading | Bear → Bull | Normalized | Weight |
|---|---|---|---|---|
| `SIG_LIQ` (stablecoin supply 30d %) | −0.96 | 0.0 → 2.0 | −0.481 | 0.40 |
| `SIG_DOM` (BTC dominance %) | 57.45 | 60.0 → 55.0 | −0.021 | 0.25 |
| `SIG_ROT` (ETH/BTC 30d %) | −7.30 | −5.0 → 5.0 | −1.000 | 0.35 |

`routing_hint`: favor `BTC`; reduce `ETH`, `alts`; posture `defensive`.

## Invalidation (logic: `ANY`)

The thesis is falsified if any condition is met:

1. `INV1` — `usdt_usdc_supply_change_30d_pct >= 2.0%` (fresh liquidity entering; no-fuel premise breaks)
2. `INV2` — `eth_btc_ratio >= 0.0300` (ETH/BTC reclaims the window-open level; rotation reverses)
3. `INV3` — `btc_dominance_pct <= 55.0%` (capital rotating out to alts; defensive thesis weakens)

Each condition is `{metric, comparator, value, unit}`, so a consumer can evaluate it programmatically
against live data with no parsing of prose.

## Data sources & provenance

All market reads are live aggregated data from the CoinGecko API:

- `S1` — `GET /api/v3/global` (total cap, BTC dominance, derived TOTAL2/TOTAL3)
- `S2` — `GET /api/v3/coins/categories` (Stablecoins aggregate)
- `S3` — `GET /api/v3/coins/{id}/market_chart` for USDT + USDC, 30d daily (supply-delta proxy)
- `S4` — `GET /api/v3/simple/price` + `/coins/ethereum/market_chart?vs_currency=btc` (ETH/BTC level and trend)

`provenance.completeness_score = 0.92`, `live_fetched_ratio = 1.0`. One disclosed proxy substitution:
`net_stablecoin_flow` is approximated by the USDT+USDC aggregate supply delta because on-chain mint/burn
and exchange-netflow feeds are not reachable in the build environment. Declared `data_gaps`:
`exchange_stablecoin_netflows`, `stablecoin_mint_burn_events`, `spot_etf_net_flows`,
`perp_funding_open_interest`. These gaps are why the composite confidence is held at `MEDIUM` rather
than `HIGH`.

## Validate before ingesting

The brief ships with a self-contained, stdlib-only guard (no pip installs). It checks structure,
controlled vocabularies, the `report_type` ⇄ `report_type_guard` discriminator, referential integrity
of `source_ref` → `sources[]`, machine-checkability of invalidation conditions, signal threshold/normalization
sanity, timestamp format, and freshness — emitting composite rejection codes.

```bash
# Validate the artifact (exit 0 = ACCEPT, 1 = REJECT)
python3 macro_brief_guard.py pft_macro_alpha_brief_v1.json

# Run the guard's own fixtures (proves it catches each failure mode)
python3 macro_brief_guard.py --test
```

Load and validate straight from the raw URL:

```bash
curl -sL <RAW_URL>/pft_macro_alpha_brief_v1.json -o brief.json \
  && python3 macro_brief_guard.py brief.json
```

## Consuming the artifact

The JSON is the canonical interface — load it directly, no login or paywall. Suggested consumer flow:

1. Fetch the raw JSON.
2. Run `macro_brief_guard.py` (or your own Draft-07 validator) and reject on any ERROR-level code.
3. Read `scoring_readiness.signals[].normalized` and `conviction_weight` into the routing score.
4. Register `invalidation.conditions[]` as live monitors; flag the brief stale if any fire or if
   `data_as_of` ages past your freshness tolerance.

## Regenerating

The brief is a point-in-time snapshot of a rolling-30d window. To refresh, re-run the builder against
new CoinGecko reads; `brief_id` is a deterministic hash of `{report_type, theme, window_end, direction}`,
so a new window or a changed thesis direction yields a new id while identical inputs reproduce the same one.

## Disclaimer

This artifact is research and routing infrastructure output, not investment or financial advice. It
encodes one analyst thesis with explicit confidence, provenance, and invalidation so downstream
consumers can weight it accordingly. Verify against current data before acting.
