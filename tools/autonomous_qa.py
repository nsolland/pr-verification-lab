"""Offline autonomous QA loop for synthetic fixtures (no model or cloud calls).

Discover -> formulate checks -> execute -> diagnose -> propose repair -> replay
on an independently clean fixture. Replay is NOT validation of a code fix.

Run from repo root: python3 -m unittest discover -s tests -p 'test_autonomous_qa.py' -v
                  python3 tools/autonomous_qa.py --output report.json
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import pathlib
from html.parser import HTMLParser
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE = ROOT / "tests" / "test_functional_e2e.py"
SPEC = importlib.util.spec_from_file_location("functional_fixture", MODULE)
fixture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixture)

# Curated contracts, not inferred truth. Only original synthetic fixture allowed.
CONTRACTS = {
    "checkout": {"action": "buy", "description": "Checkout confirms payment",
                 "hypothesis": "Successful checkout must return 201 and confirmed"},
    "api_500": {"action": "health", "description": "Health endpoint returns healthy",
                "hypothesis": "GET /health returns 200 and ok=true"},
    "auth_bypass": {"action": "admin", "description": "Admin denies anonymous access",
                    "hypothesis": "GET /admin returns 403 without token and 200 with token"},
    "ui_regression": {"action": "heading", "description": "Checkout heading is present",
                      "hypothesis": "Rendered document has Checkout title"},
    "validation": {"action": "buy", "description": "Reject invalid email",
                   "hypothesis": "Malformed email must return 422"},
    "persistence": {"action": "orders", "description": "Order persists after checkout",
                    "hypothesis": "Created order appears in subsequent GET /orders"},
}
DIAGNOSES = {
    "checkout": ("CHECKOUT_NOT_CONFIRMED", "Checkout response does not satisfy success contract",
                 "Inspect checkout payment-result and status mapping"),
    "api_500": ("HEALTH_FAILURE", "Health check returned unexpected status/body",
                "Inspect health handler exception path and service dependencies"),
    "auth_bypass": ("UNAUTHORIZED_ACCESS", "Anonymous request can reach protected content",
                    "Restore authorization gate; add negative access test"),
    "ui_regression": ("UI_CONTRACT_MISMATCH", "Expected Checkout heading/title changed",
                      "Compare rendered DOM with approved UI contract"),
    "validation": ("INPUT_ACCEPTED", "Invalid user input accepted",
                   "Validate email before order creation"),
    "persistence": ("ORDER_NOT_DURABLE", "Successful checkout not reflected in order list",
                    "Verify transaction commit and subsequent read"),
}


class Discover(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.buttons = set()
        self.inputs = set()

    def handle_starttag(self, tag, attrs):
        properties = dict(attrs)
        identifier = properties.get("id")
        if identifier:
            self.ids.add(identifier)
            if tag == "button":
                self.buttons.add(identifier)
            if tag == "input":
                self.inputs.add(identifier)


def discover(html: str) -> dict[str, Any]:
    parser = Discover()
    parser.feed(html)
    # Actual discovered UI affordances determine which known contracts are runnable.
    capabilities = {
        "buy": "buy" in parser.buttons and "email" in parser.inputs,
        "health": "health" in parser.buttons,
        "admin": "admin" in parser.buttons,
        "heading": "heading" in parser.ids,
        "orders": "orders" in parser.buttons and "buy" in parser.buttons,
    }
    plans = [
        {"case": case, "action": c["action"], "expected": c["hypothesis"]}
        for case, c in sorted(CONTRACTS.items())
        if capabilities[c["action"]]
    ]
    return {"identified_controls": sorted(parser.ids), "capabilities": capabilities, "plans": plans}


def evaluate_case(case: str, injected: bool) -> dict[str, Any]:
    # Real HTTP observations from ephemeral local server; no direct outbound.
    outcome = fixture.run_case(case, injected)
    code, analysis, proposal = DIAGNOSES[case]
    details = None
    if outcome["detected"]:
        details = {"code": code, "finding": analysis,
                   "suggested_repair": proposal,
                   "requires_human_or_independent_agent": True,
                   "patch_applied": False}
    return {**outcome, "diagnosis": details}


def execute(html: str, cases: tuple[str, ...] | None = None) -> dict[str, Any]:
    found = discover(html)
    planned = {p["case"] for p in found["plans"]}
    requested = tuple(cases) if cases is not None else tuple(sorted(CONTRACTS))
    if not requested:
        raise ValueError("no cases selected")
    unknown = set(requested) - set(CONTRACTS)
    if unknown:
        raise ValueError(f"unknown contract: {sorted(unknown)}")
    missing = set(requested) - planned
    if missing:
        raise ValueError(f"UI controls missing for: {sorted(missing)}")
    results = []
    for case in requested:
        before = evaluate_case(case, injected=True)
        # Demonstrate the check is not an unconditional failure by re-running
        # against the independent unmodified baseline. Not a code repair.
        control = evaluate_case(case, injected=False)
        results.append({"case": case, "before": before,
                        "control_replay": control,
                        "repair_verified": False})
    return {
        "schema": "qa_loop_v1",
        "runner": "offline_autonomous_contract_discovery",
        "fixture_sha256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
        "discovery": found,
        "results": results,
        "detected": sum(x["before"]["detected"] for x in results),
        "false_positive_controls": sum(x["control_replay"]["detected"] for x in results),
        "patches_applied": 0,
        "repair_verified": False,
        "network_scope": "127.0.0.1 local HTTP server only",
        "model_calls": 0,
        "vendor_calls": 0,
        "limitations": [
            "Contract hypotheses are curated, not independently invented by an LLM",
            "This runner uses HTTP and HTML discovery, not browser automation",
            "Clean control replay does not prove that a proposed repair works",
            "No PR, code patch or production change is performed",
        ],
    }


# Source HTML is an explicitly allowed, original synthetic fixture.
SYNTHETIC_HTML = """<html><title>Checkout</title><h1 id="heading">Checkout</h1>
<input id="email"><button id="buy">Buy</button>
<button id="health">Health</button><button id="admin">Admin</button>
<button id="orders">Orders</button></html>"""


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--output", help="Write machine-readable report to file")
    args = p.parse_args(argv)
    result = execute(SYNTHETIC_HTML)
    output = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        pathlib.Path(args.output).write_text(output, encoding="utf-8")
    else:
        print(output)
    return 0 if result["detected"] == len(CONTRACTS) and result["false_positive_controls"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
