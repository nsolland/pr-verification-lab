"""Local-only functional benchmark with six seeded user-facing faults.

Uses Python standard library, localhost only, no cloud services or telemetry.
Run: python3 -m unittest discover -s tests -p 'test_functional_e2e.py' -v
"""
from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

FAULTS = ("checkout", "api_500", "auth_bypass", "ui_regression", "validation", "persistence")


def app(fault: str):
    """Construct fresh mutable state so tests cannot bleed into each other."""
    state = {"orders": [], "tokens": {"test-admin-token"}}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            return

        def reply(self, status, payload, content_type="application/json"):
            data = payload.encode() if isinstance(payload, str) else json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/health":
                self.reply(500 if fault == "api_500" else 200, {"ok": fault != "api_500"})
            elif self.path == "/":
                title = "BROKEN" if fault == "ui_regression" else "Checkout"
                self.reply(200, f"<html><title>{title}</title><form id='checkout'></form></html>", "text/html")
            elif self.path == "/admin":
                authorized = self.headers.get("Authorization") == "Bearer test-admin-token"
                self.reply(200 if authorized or fault == "auth_bypass" else 403,
                           {"admin": True} if authorized or fault == "auth_bypass" else {"error": "forbidden"})
            elif self.path == "/orders":
                self.reply(200, {"orders": state["orders"]})
            else:
                self.reply(404, {"error": "not_found"})

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            if length > 4096:
                self.reply(413, {"error": "too_large"})
                return
            try:
                body = json.loads(self.rfile.read(length))
            except (ValueError, UnicodeError):
                self.reply(400, {"error": "invalid_json"})
                return
            if self.path != "/checkout":
                self.reply(404, {"error": "not_found"})
                return
            if not isinstance(body, dict):
                self.reply(400, {"error": "invalid_body"})
                return
            email = body.get("email")
            if not isinstance(email, str) or "@" not in email:
                if fault != "validation":
                    self.reply(422, {"error": "invalid_email"})
                    return
            order = {"id": len(state["orders"]) + 1, "email": email}
            if fault != "persistence":
                state["orders"].append(order)
            if fault == "checkout":
                self.reply(200, {"status": "payment_failed"})
            else:
                self.reply(201, {"status": "confirmed", "order": order})

    return Handler


def request(base, path, method="GET", payload=None, token=None):
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = Request(base + path, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=3) as response:
            return response.status, response.read().decode()
    except HTTPError as exc:
        return exc.code, exc.read().decode()


def check(base, fault):
    """Independent oracle: returns True if behavior is correct (fault absent)."""
    if fault == "checkout":
        status, data = request(base, "/checkout", "POST", {"email": "valid@example.test"})
        return status == 201 and json.loads(data).get("status") == "confirmed"
    if fault == "api_500":
        status, data = request(base, "/health")
        return status == 200 and json.loads(data).get("ok") is True
    if fault == "auth_bypass":
        unauthorized, _ = request(base, "/admin")
        authorized, _ = request(base, "/admin", token="test-admin-token")
        return unauthorized == 403 and authorized == 200
    if fault == "ui_regression":
        status, html = request(base, "/")
        return status == 200 and "<title>Checkout</title>" in html and "id='checkout'" in html
    if fault == "validation":
        status, _ = request(base, "/checkout", "POST", {"email": "invalid"})
        return status == 422
    if fault == "persistence":
        status, _ = request(base, "/checkout", "POST", {"email": "valid@example.test"})
        code, data = request(base, "/orders")
        return status == 201 and code == 200 and len(json.loads(data)["orders"]) == 1
    raise ValueError(fault)


def run_case(fault, injected):
    if fault not in FAULTS:
        raise ValueError(f"unknown fault: {fault}")
    server = ThreadingHTTPServer(("127.0.0.1", 0), app(fault if injected else ""))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        return {"case": fault, "injected": injected, "detected": not check(f"http://127.0.0.1:{server.server_port}", fault)}
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def benchmark():
    rows = [run_case(fault, injected) for fault in FAULTS for injected in (False, True)]
    true_positive = sum(row["detected"] for row in rows if row["injected"])
    false_positive = sum(row["detected"] for row in rows if not row["injected"])
    return {"runner": "local_python_stdlib", "cases": rows, "true_positive": true_positive,
            "false_positive": false_positive, "total_injected": len(FAULTS),
            "external_model_calls": 0, "network": "127.0.0.1 only"}


class BenchmarkTests(unittest.TestCase):
    def test_all_six_injected_faults_detected_and_controls_clean(self):
        report = benchmark()
        self.assertEqual(report["true_positive"], 6, report)
        self.assertEqual(report["false_positive"], 0, report)


if __name__ == "__main__":
    print(json.dumps(benchmark(), indent=2))
