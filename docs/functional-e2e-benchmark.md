# Isolated functional E2E benchmark

Issue: https://github.com/nsolland/pr-verification-lab/issues/4

## Purpose
Prove functional detection beyond static Code QC, and compare another runner (including TestSprite) with **identical oracles**, rather than vendor-marketing claims.

## Local-only baseline
```sh
python3 -m unittest discover -s tests -p 'test_*functional_e2e.py' -v
python3 -m unittest discover -s tests -p 'test_compare_functional_e2e.py' -v
python3 tests/test_functional_e2e.py > baseline.json
```

Six faults, each paired with a clean control: failed checkout, API 500, authorization bypass, HTML/checkout UI regression, invalid form acceptance, non-persisted order. The server listens **only on 127.0.0.1**, uses the Python standard library and closes after every case. A clean result should yield 6/6 seeded faults detected and 0/6 false positives.

These are deterministic HTTP-based functional flows, **not actual browser/Playwright journeys**. Do not claim browser parity from this suite. Browser/video/DOM evidence requires a separate runner with an audited sandbox.

## Candidate evaluation
Have the independent runner report actual observed results as a JSON document with `runner` and 12 `cases` (`case`, `injected` boolean, `detected` boolean) using exactly the same six faults and clean controls. Add observed `duration_seconds`, `cost_eur`, `external_bytes`, `commit_sha` and `cli_version` where available. **Never generate fake candidate results.**

```sh
python3 tools/compare_functional_e2e.py baseline.json candidate.json --output comparison.json
```

The comparison validates completeness and calculates true positives, false positives, misses, incremental catches and regressions. It deliberately never marks cloud E2E as verified.

## Security gate
Never give TestSprite private repositories or credentials. A real TestSprite run requires an explicitly approved synthetic public target, API key, sandbox and No It Phone Home egress controls. Setting `TESTSPRITE_NO_TELEMETRY=1`, `DO_NOT_TRACK=1` and `TESTSPRITE_NO_UPDATE_NOTIFIER=1` is defense in depth, **not** network isolation. Block all traffic unless explicitly approved through the gateway; inspect vendor data retention and subcontractors before use. Do **not** use GitHub Actions.

The TestSprite `--dry-run` path returns canned results, which must never count toward a benchmark.

## Evidence
Record canonical source SHA, fixture SHA, test logs, candidate vendor run IDs, egress logs, timings, credits/cost, oracle adjudication, and REHT receipt. Until verified with an external executor, status is `IMPLEMENTED_UNEXECUTED`.

## Chromium sandbox compatibility (2026-11-21)

Managed Chromium can return `net::ERR_BLOCKED_BY_ADMINISTRATOR` even for `127.0.0.1` navigation. The browser suite now uses `page.set_content` for the synthetic app and a Playwright request route that forwards only the synthetic-origin API requests to a Python `ThreadingHTTPServer` bound on `127.0.0.1`. This retains actual Chromium clicks, DOM checks, JavaScript `fetch`, and real HTTP responses without any Chromium direct outbound connections. Requests outside the synthetic origin are aborted. It is NOT a substitute for process-level egress policy enforcement.

A separately reconstructed minimal six-case smoke test for the new bridge ran in a restricted Chromium sandbox: **6/6 injected defects found and 0/6 clean controls flagged**, including blocked direct navigation. The exact PR-head browser test file still needs an independent runner attestation. Do not equate route-level network protection with the No It Phone Home OS/container gateway.

Run where Playwright and a compatible local Chromium are already installed:

```sh
PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/bin/chromium python3 -m unittest discover -s tests -p 'test_browser_e2e.py' -v
```

Do not install browsers or dependencies through uncontrolled egress.

## Offline autonomous QA loop

`tools/autonomous_qa.py` implements a first, constrained **discover → plan → execute → diagnose → propose → replay** loop. It discovers actual HTML controls, selects executable tests from *curated contracts*, executes seeded fault scenarios against a fresh local HTTP fixture, assigns deterministic failure classifications and proposed remedies, and replays each test against a separate clean fixture to measure false positives. JSON output includes a SHA-256 fixture fingerprint, observations, limitations and a mandatory `repair_verified=false` flag.

```sh
python3 -m unittest discover -s tests -p 'test_autonomous_qa.py' -v
python3 tools/autonomous_qa.py --output qa-loop.json
```

This is **not** an LLM-discovered specification, not an automatic source repair, and not a verified post-patch rerun. Self-modifying source changes and external credentials are deliberately excluded. For genuine self-repair, a separately approved code agent must propose a narrow patch, independent Code QC must validate the exact modified SHA, and the same failing scenario must pass on the patched artifact (with the unpatched fault still detected). Do not call clean baseline replay a fix.

Tests in this PR are committed but require an external runner to validate the exact GitHub SHA. No GitHub Actions.
