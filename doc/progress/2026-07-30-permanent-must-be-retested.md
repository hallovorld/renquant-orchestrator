# A claim about the future cannot be derived entirely from the past

**Date:** 2026-07-30 · GOAL-5 · orchestrator

**Bottom line:** `undelivered_alert_scan.py` labelled a failure **`PERMANENT`** —
*"this call site can never deliver until the code changes"* — by regexing the error
text out of a log line. That is a claim about the **future** decided entirely from
the **past**, and it had no way to notice its own expiry.

## 1. It had already expired

Measured 2026-07-30, the scan reported:

```
[PERMANENT] 'rq104 blend 假想前10 — 2026-07-28'
            ('latin-1' codec can't encode characters in position 12-14)
```

That defect was **fixed on 2026-07-29** by `renquant_common.notify.encode_header`
(RFC 2047 base64). Handing the real title to the real encoder today, it encodes
`[VERIFIED — this session]`. The same is true of the rq105 sentinel's 🚨 title.

**Two false PERMANENT claims, and the scan would have repeated them every run
forever.** orch#650 had just placed this scan into a *scheduled* audit, where a
permanently-false alarm poisons every other member.

## 2. Re-test, do not recall

`status` is now measured at report time, not read off the log:

| status | meaning |
|---|---|
| `PERMANENT` | re-tested against today's encoder — **still** undeliverable |
| `RESOLVED` | re-tested — **now encodes**; the historical failure is closed |
| `UNTESTABLE` | the encoder could not be imported — the claim is **unverified**, not true |
| `TRANSIENT` | never an encoding defect (SSL timeouts and the like) |

**`RESOLVED` is reported, not dropped.** A closed historical gap is information — it
says the fix landed. Hiding it would make the fix invisible; calling it `PERMANENT`
would make the fix a lie.

**`UNTESTABLE` fails towards unverified.** Reporting `RESOLVED` because the test
could not run would silently close a gap that may still be open — the same shape as
a guard passing because its input was absent.

## 3. Live output after the change

`[VERIFIED — this session]` — three genuine `TRANSIENT` SSL timeouts, two
`RESOLVED`, and **zero `PERMANENT`**, because there genuinely are none any more.

## 4. Suite — 7 tests

Both real titles are `RESOLVED`; a network error stays `TRANSIENT`; **`PERMANENT`
survives only when the re-test still fails** (anti-vacuity — a category that can
never fire is dead, and a genuine encoding defect would ship as `RESOLVED`); an
unimportable encoder is `UNTESTABLE`; the re-test strips the quotes the regex
captured (or it tests a different string than the one that failed); `RESOLVED` is
reported; `PERMANENT` sorts above `RESOLVED`.

## 5. A harness error of mine, recorded

The test module first died at import with
`'NoneType' object has no attribute '__dict__'`. Loading a module via
`spec_from_file_location` **without registering it in `sys.modules`** breaks
`@dataclass`, which resolves type hints through `sys.modules[cls.__module__]`. **A
harness failure that looks exactly like a code failure** — worth the comment it now
carries, since three other test files in this repo load ops modules the same way and
only this one has a dataclass.
