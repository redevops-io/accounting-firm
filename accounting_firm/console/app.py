"""The console HTTP surface — stdlib only (no web framework dependency).

Two things: `GET /api/deliverable` serialises the governed §41 study, and `GET /` serves the single-page
review UI. Deliberately zero-dependency and read-only for P0–P2 (the sign gate, EXPLAIN and LEDGER
interactions arrive in P3). A production console would put FastAPI + auth in front of the same serializer.
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .serialize import build_deliverable

HERE = os.path.dirname(os.path.abspath(__file__))
_INDEX = os.path.join(HERE, "static", "index.html")


class _Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:                                    # noqa: N802 (stdlib signature)
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            with open(_INDEX, "rb") as fh:
                self._send(200, fh.read(), "text/html; charset=utf-8")
        elif path == "/api/deliverable":
            try:
                data = build_deliverable()
                self._send(200, json.dumps(data).encode(), "application/json")
            except Exception as exc:                             # surface the error to the browser, don't hang
                self._send(500, json.dumps({"error": str(exc)}).encode(), "application/json")
        elif path == "/healthz":
            self._send(200, b'{"ok":true}', "application/json")
        else:
            self._send(404, b'{"error":"not found"}', "application/json")

    def log_message(self, *args) -> None:                        # keep the demo console quiet
        pass


def serve(host: str = "127.0.0.1", port: int = 8088) -> None:
    httpd = ThreadingHTTPServer((host, port), _Handler)
    print(f"CPA review console → http://{host}:{port}  (runtime: {os.environ.get('FIRM_LLM_BASE_URL') and 'live' or 'deterministic'})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()


if __name__ == "__main__":
    serve(os.environ.get("FIRM_CONSOLE_HOST", "127.0.0.1"),
          int(os.environ.get("FIRM_CONSOLE_PORT", "8088")))
