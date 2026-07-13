# 2026-07-13 Rename crypto battery env prefix ALPACA_SHORTS → ALPACA_PAPER

## Summary

Rename the crypto battery environment variable prefix from `ALPACA_SHORTS` to
`ALPACA_PAPER` for consistency with the paper-trading account it references.

## What changed

- `deploy/com.renquant.crypto-session.plist`: env var prefix renamed
- No behavioral change — same account, same credentials, same endpoint
