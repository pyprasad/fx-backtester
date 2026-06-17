# USDJPY News Guard Research, 2022-2025

This note records the broad NASDAQ macro-calendar news guard experiment for the selected
USDJPY swing trend reclaim strategy.

## Setup

- Strategy variant: `min_risk_3pips_spread_ratio_20pct_lifecycle_throttled`
- Sessions: London morning, London-New York overlap, Tokyo
- Calendar: `data/macro_calendar/usd_jpy_events_2022_2025_nasdaq.csv`
- Calendar source: NASDAQ economic calendar cache
- Calendar size: 4,591 events
- Block window: 60 minutes before and 60 minutes after event time
- Affected currencies: USD, JPY
- Impact level: HIGH

The NASDAQ feed is useful for research, but it is not treated as production-grade without spot
checking event timestamps against official release schedules.

## Result

| Metric | Baseline | Broad news guard |
| --- | ---: | ---: |
| Trades | 644 | 575 |
| Net profit | 9,492.97 | 8,240.17 |
| Return | 94.93% | 82.40% |
| Profit factor | 2.066 | 2.089 |
| Max drawdown | 2.4864% | 2.1518% |
| Average R | 0.4175 | 0.4210 |
| Worst trade R | -2.0171 | -1.3206 |
| News-skipped signals | 0 | 152 |

Yearly PnL delta versus baseline:

| Year | Baseline PnL | News guard PnL | Delta |
| --- | ---: | ---: | ---: |
| 2022 | 1,562.12 | 1,477.42 | -84.70 |
| 2023 | 1,957.22 | 1,665.38 | -291.84 |
| 2024 | 1,593.64 | 1,316.11 | -277.53 |
| 2025 | 4,379.99 | 3,781.25 | -598.74 |

## Interpretation

The broad news guard improved risk quality slightly:

- Lower max drawdown.
- Better worst trade.
- Slightly better profit factor and average R.

It removed too much opportunity:

- Net profit dropped by about 1,252.80.
- Every year lost PnL versus the baseline.
- Many skipped signals were caused by lower-confidence event classes such as Fed member speeches,
  ADP, Nonfarm Productivity, Cleveland CPI, and ISM subcomponents.

## Decision

Do not enable the broad NASDAQ news guard as the selected strategy default.

Keep the feature available as an opt-in risk-control/research switch. A better future test is a
narrow major-events-only calendar:

- US CPI / Core CPI
- US Nonfarm Payrolls, Unemployment Rate, Average Hourly Earnings
- FOMC statement, rate decision, projections
- BoJ policy statement / rate decision
- Japan CPI / Tokyo CPI
- Optional: PCE and GDP

Exclude routine Fed speaker events, ADP, Cleveland CPI, Nonfarm Productivity, and ISM subcomponents
unless separate analysis proves they remove poor trades without materially reducing expectancy.

## Runtime Configuration

The selected strategy keeps `news_guard.enabled: false` in YAML. To opt in without editing the
strategy file:

```bash
export NEWS_GUARD_ENABLED=true
export NEWS_GUARD_CALENDAR_FILE=data/macro_calendar/usd_jpy_events_2022_2025_nasdaq.csv
export NEWS_GUARD_BEFORE_MINUTES=60
export NEWS_GUARD_AFTER_MINUTES=60
```

CLI flags such as `--news-guard-enabled false` still override the environment for one command.
