"""Compare independent runner outputs without inventing TestSprite outcomes.

Input JSON:
{"runner":"testsprite","cases":[{"case":"checkout","injected":true,"detected":true}, ...],
 "duration_seconds":42.0,"cost_eur":0.4,"external_bytes":1234}
Each of the six cases MUST occur for both injected=true and false.
"""
import argparse
import json
import sys

FAULTS = {"checkout", "api_500", "auth_bypass", "ui_regression", "validation", "persistence"}


def validate(report):
    if not isinstance(report, dict) or not isinstance(report.get("runner"), str) or not report["runner"]:
        raise ValueError("report requires nonempty runner")
    cases = report.get("cases")
    if not isinstance(cases, list) or len(cases) != 12:
        raise ValueError("exactly 12 cases required (6 injected + 6 controls)")
    seen = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("case must be object")
        fault = case.get("case")
        injected = case.get("injected")
        detected = case.get("detected")
        if fault not in FAULTS or type(injected) is not bool or type(detected) is not bool:
            raise ValueError(f"invalid case: {case}")
        key = (fault, injected)
        if key in seen:
            raise ValueError(f"duplicate case {key}")
        seen.add(key)
    if seen != {(fault, injected) for fault in FAULTS for injected in (True, False)}:
        raise ValueError("missing required cases")
    return report


def metrics(report):
    validate(report)
    cases = report["cases"]
    tp = sum(c["detected"] for c in cases if c["injected"])
    fp = sum(c["detected"] for c in cases if not c["injected"])
    out = {"runner": report["runner"], "true_positives": tp, "false_positives": fp,
           "missed_faults": 6 - tp, "precision": tp / (tp + fp) if tp + fp else None,
           "recall": tp / 6}
    for field in ("duration_seconds", "cost_eur", "external_bytes", "commit_sha", "cli_version"):
        if field in report:
            out[field] = report[field]
    return out


def compare(left, right):
    a, b = metrics(left), metrics(right)
    by_key_left = {(c["case"], c["injected"]): c["detected"] for c in left["cases"]}
    by_key_right = {(c["case"], c["injected"]): c["detected"] for c in right["cases"]}
    return {"baseline": a, "candidate": b,
            "additional_true_positives": [
                fault for fault in sorted(FAULTS)
                if by_key_right[(fault, True)] and not by_key_left[(fault, True)]],
            "regressions": [
                fault for fault in sorted(FAULTS)
                if by_key_left[(fault, True)] and not by_key_right[(fault, True)]],
            "candidate_false_positives": [
                fault for fault in sorted(FAULTS) if by_key_right[(fault, False)]],
            "verified_e2e": False,
            "reason": "Comparison only; vendor cloud execution and egress must be independently attested."}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline", help="JSON report from independent baseline runner")
    parser.add_argument("candidate", help="JSON report from TestSprite or other candidate")
    parser.add_argument("--output", help="Write JSON comparison to this file")
    args = parser.parse_args(argv)
    with open(args.baseline, encoding="utf-8") as f:
        baseline = json.load(f)
    with open(args.candidate, encoding="utf-8") as f:
        candidate = json.load(f)
    result = compare(baseline, candidate)
    encoded = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(encoded + "\n")
    else:
        print(encoded)
    return 0


if __name__ == "__main__":
    sys.exit(main())
