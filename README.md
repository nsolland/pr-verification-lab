# PR Verification Lab

Public, isolated verification fixtures for Quality Factory.

## Purpose

Run review tools and reproducible checks on **original, synthetic or explicitly approved public code**. This repository is not a mirror of private repositories and must not be used to evade third-party licensing or usage terms.

## Process

1. Confirm provenance and permission to publish each file and dependency.
2. Reproduce a minimal, sanitized behavior in a branch; keep original private code in its source repository.
3. Open a PR against `main`. Automated unit tests and scope heuristics run, and installed review apps may review it.
4. Resolve actual findings and rerun checks. Record exact source/head SHA and observed test results.
5. Independently implement or cherry-pick only authorized code in the target repository.
6. Run local target-repository tests; only then merge using the target repository's ordinary rules.

A green lab PR is **not** approval to merge a target PR. Manual review for confidentiality, licenses and data provenance is required. The scope script catches obvious files/secrets but is not a DLP guarantee.

## Baseline

`python -m unittest discover -s tests -v`
`python scripts/check_public_scope.py`

Do not copy proprietary source, customer data, credentials, internal URLs, production dumps or confidential issue descriptions here. Do not upload a private patch merely to get a free review.
