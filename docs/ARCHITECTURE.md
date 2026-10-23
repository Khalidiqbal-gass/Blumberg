# Architecture — initial increment

```text
Licensed/permitted source adapters (future; not yet implemented)
                   |
                   v
       Canonical OHLCV schema -> validation and quality checks
                   |                      |
                   v                      v
       Versioned historical store   rejected-row diagnostics
                   |
                   v
       Lag-safe technical features -> baseline scanner/signal ledger
                   |                      |
                   v                      v
       Walk-forward evaluation       dashboard (later)

Official announcements/licensed news feeds (future)
                   |
                   v
       Provenance + event extraction + order/LOI/cancellation classification
                   |
                   v
       Event features -> separately evaluated combined model
```

## Design principles

- Isolate provider adapters behind interfaces and select them only after permissions, coverage, cost and retention checks.
- Store event time, source-publication time, collection time and effective time separately.
- Keep raw-source pointers and checksums where retention rights permit; do not silently rewrite old announcements.
- Distinguish adjusted from unadjusted prices and test corporate-action handling before production backtests.
- Feature generation must be deterministic and must not use future rows.
- The current backtest helper is a smoke-test utility, not a production portfolio simulator.
