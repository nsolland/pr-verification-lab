"""Fail-closed synthetic source-patch lab with actual before/after HTTP verification.

Original repo files are never edited. A deliberately vulnerable fixture module is
created in a temporary directory, tested, patched in that directory and retested.
No subprocess, no model calls and no external network connections.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import pathlib
import tempfile
import threading
from http.server import ThreadingHTTPServer
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "test_functional_e2e.py"
# Match exact source with explicit count; fail closed on upstream drift.
SAFE_GUARD = 'if authorized or fault == "auth_bypass" else 403,'
VULNERABLE_GUARD = 'if authorized or True else 403,'
SAFE_PAYLOAD = '{"admin": True} if authorized or fault == "auth_bypass" else {"error": "forbidden"}'
VULNERABLE_PAYLOAD = '{"admin": True} if authorized or True else {"error": "forbidden"}'


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def guarded_substitution(source: str, old: str, new: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"expected one source anchor, found {count}: {old!r}")
    return source.replace(old, new, 1)


def inject_vulnerability(original: str) -> str:
    vulnerable = guarded_substitution(original, SAFE_GUARD, VULNERABLE_GUARD)
    return guarded_substitution(vulnerable, SAFE_PAYLOAD, VULNERABLE_PAYLOAD)


def propose_patch(vulnerable: str) -> dict[str, Any]:
    # This is a fixed narrowly scoped repair recipe, not generative code repair.
    patched = guarded_substitution(vulnerable, VULNERABLE_GUARD,
                                   'if authorized else 403,')
    patched = guarded_substitution(patched, VULNERABLE_PAYLOAD,
                                   '{"admin": True} if authorized else {"error": "forbidden"}')
    return {"source": patched, "rule": "enforce_explicit_authz", "before_sha256": digest(vulnerable),
            "after_sha256": digest(patched), "modified_source": digest(vulnerable) != digest(patched)}


def load_fixture(path: pathlib.Path):
    # Unique module for each before/after snapshot. Does not modify live import.
    name = "qa_" + path.stem + "_" + digest(path.read_text(encoding="utf-8"))[:12]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def run_oracles(module) -> dict[str, bool]:
    outcomes: dict[str, bool] = {}
    # Fresh server and in-memory datastore for every oracle. Otherwise checkout
    # pollutes the subsequent persistence check and produces a false regression.
    for name in module.FAULTS:
        server = ThreadingHTTPServer(("127.0.0.1", 0), module.app(""))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}"
            outcomes[name] = bool(module.check(url, name))
        finally:
            server.shutdown()
            worker.join(timeout=5)
            server.server_close()
    return outcomes


def repair_lab(source_path: pathlib.Path = FIXTURE) -> dict[str, Any]:
    source_path = source_path.resolve(strict=True)
    if source_path != FIXTURE.resolve(strict=True):
        raise ValueError("only repository's original synthetic fixture permitted")
    original = source_path.read_text(encoding="utf-8")
    vulnerable = inject_vulnerability(original)
    patch = propose_patch(vulnerable)
    if not patch["modified_source"]:
        raise ValueError("patch made no change")
    with tempfile.TemporaryDirectory(prefix="qa-source-repair-") as d:
        root = pathlib.Path(d)
        before_path = root / "before.py"
        after_path = root / "after.py"
        before_path.write_text(vulnerable, encoding="utf-8")
        after_path.write_text(patch["source"], encoding="utf-8")
        before = run_oracles(load_fixture(before_path))
        after = run_oracles(load_fixture(after_path))

    # Require before failure of target, after success of *all* contracts.
    # Also require no other contract regresses relative to vulnerable source.
    approved = (before["auth_bypass"] is False
                and all(after.values())
                and all(after[key] or not val for key, val in before.items()))
    return {
        "schema": "synthetic_source_repair_v1",
        "source": str(source_path.relative_to(ROOT)),
        "original_sha256": digest(original),
        "vulnerable_sha256": digest(vulnerable),
        "patched_sha256": patch["after_sha256"],
        "patch_rule": patch["rule"],
        "before_contracts": before,
        "after_contracts": after,
        "verified": approved,
        "patch_applied_to": "temporary isolated source copy",
        "production_modified": False,
        "requires_independent_sha_attestation": True,
        "network_scope": "localhost HTTP only",
        "limit": "One known auth bypass repair recipe on a synthetic fixture; not generalized or LLM patch synthesis",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    result = repair_lab()
    data = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        pathlib.Path(args.output).write_text(data, encoding="utf-8")
    else:
        print(data)
    return 0 if result["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
