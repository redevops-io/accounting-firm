"""The console HTTP surface — stdlib only (no web framework dependency).

Two things: `GET /api/deliverable` serialises the governed §41 study, and `GET /` serves the single-page
review UI. Deliberately zero-dependency and read-only for P0–P2 (the sign gate, EXPLAIN and LEDGER
interactions arrive in P3). A production console would put FastAPI + auth in front of the same serializer.
"""
from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .serialize import ReviewSession

HERE = os.path.dirname(os.path.abspath(__file__))
_INDEX = os.path.join(HERE, "static", "index.html")

# One live review session (single-tenant demo surface). Lazily created, guarded for the threading server.
# Reentrant: the POST handlers hold the lock while calling _get_session(), which locks again.
_session: ReviewSession | None = None
_lock = threading.RLock()


def _get_session() -> ReviewSession:
    global _session
    with _lock:
        if _session is None:
            _session = ReviewSession()
        return _session


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
                self._send(200, json.dumps(_get_session().json()).encode(), "application/json")
            except Exception as exc:                             # surface the error to the browser, don't hang
                self._send(500, json.dumps({"error": str(exc)}).encode(), "application/json")
        elif path == "/healthz":
            self._send(200, b'{"ok":true}', "application/json")
        else:
            self._send(404, b'{"error":"not found"}', "application/json")

    def do_POST(self) -> None:                                   # noqa: N802
        path = self.path.split("?", 1)[0]
        try:
            n = int(self.headers.get("Content-Length", 0) or 0)
            body = json.loads(self.rfile.read(n) or b"{}") if n else {}
        except Exception:
            return self._send(400, b'{"error":"bad json"}', "application/json")
        if path == "/api/sign":
            with _lock:
                out = _get_session().sign(body.get("decision", ""), body.get("amendments"),
                                          body.get("cpa", "A. Mats, CPA"))
            self._send(200 if "error" not in out else 409, json.dumps(out).encode(), "application/json")
        elif path == "/api/reset":
            with _lock:
                _get_session().reset()
                out = _get_session().json()
            self._send(200, json.dumps(out).encode(), "application/json")
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
