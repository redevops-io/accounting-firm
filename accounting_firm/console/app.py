"""The console HTTP surface — stdlib only (no web framework dependency).

Serves the single-page review UI at the base path and the JSON API beneath it: GET `<base>/api/engagements`,
GET `<base>/api/deliverable?id=<id>`, POST `<base>/api/sign?id=<id>`, POST `<base>/api/reset?id=<id>`.
`FIRM_CONSOLE_BASE` sets the prefix (e.g. `/accounting`) so the same app hosts behind a path-routed tunnel
(demo.redevops.io/accounting) with no path rewriting; empty by default, so local dev and tests use `/` and
`/api/*`. One session per deliverable is held (the engagement has several); a production console would put
FastAPI + auth in front of the same serializer.
"""
from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from .serialize import DEFAULT_ID, SPECS, ReviewSession

HERE = os.path.dirname(os.path.abspath(__file__))
_INDEX = os.path.join(HERE, "static", "index.html")
BASE = os.environ.get("FIRM_CONSOLE_BASE", "").rstrip("/")     # e.g. "/accounting" when path-routed

# One live review session per deliverable (single-tenant demo surface). Reentrant lock: POST handlers hold
# the lock while calling _get_session(), which locks again.
_sessions: dict[str, ReviewSession] = {}
_lock = threading.RLock()


def _get_session(deliverable_id: str) -> ReviewSession:
    did = deliverable_id if deliverable_id in SPECS and SPECS[deliverable_id].available else DEFAULT_ID
    with _lock:
        if did not in _sessions:
            _sessions[did] = ReviewSession(did)
        return _sessions[did]


def _statuses() -> dict[str, str]:
    """Live status of each available deliverable (creating its session on first ask) for the zoom-out."""
    with _lock:
        for did, spec in SPECS.items():
            if spec.available and did not in _sessions:
                _sessions[did] = ReviewSession(did)
        return {did: s.deliverable.status for did, s in _sessions.items()}


def _subpath(path: str) -> str:
    if BASE and (path == BASE or path.startswith(BASE + "/")):
        return path[len(BASE):] or "/"
    return path


def _index_html() -> bytes:
    with open(_INDEX, encoding="utf-8") as fh:
        return fh.read().replace("__BASE__", BASE).encode()


class _Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _did(self) -> str:
        q = parse_qs(urlsplit(self.path).query)
        return (q.get("id", [DEFAULT_ID])[0])

    def do_GET(self) -> None:                                    # noqa: N802 (stdlib signature)
        path = _subpath(urlsplit(self.path).path)
        if path in ("/", "/index.html"):
            # A fresh page load restarts any *completed* review so each visitor to the shared demo opens on
            # "ready for your review" — but never disturbs a review already in progress.
            with _lock:
                for s in _sessions.values():
                    if s.deliverable.status in ("signed", "rejected"):
                        s.reset()
            self._send(200, _index_html(), "text/html; charset=utf-8")
        elif path == "/api/engagements":
            self._send(200, json.dumps({"engagements": _get_session(DEFAULT_ID).json(_statuses())["engagements"]}).encode(),
                       "application/json")
        elif path == "/api/deliverable":
            try:
                self._send(200, json.dumps(_get_session(self._did()).json(_statuses())).encode(),
                           "application/json")
            except Exception as exc:                             # surface the error to the browser, don't hang
                self._send(500, json.dumps({"error": str(exc)}).encode(), "application/json")
        elif path == "/healthz":
            self._send(200, b'{"ok":true}', "application/json")
        else:
            self._send(404, b'{"error":"not found"}', "application/json")

    def do_POST(self) -> None:                                   # noqa: N802
        path = _subpath(urlsplit(self.path).path)
        did = self._did()
        try:
            n = int(self.headers.get("Content-Length", 0) or 0)
            body = json.loads(self.rfile.read(n) or b"{}") if n else {}
        except Exception:
            return self._send(400, b'{"error":"bad json"}', "application/json")
        if path == "/api/sign":
            with _lock:
                out = _get_session(did).sign(body.get("decision", ""), body.get("amendments"),
                                             body.get("cpa", "A. Mats, CPA"))
                if "error" not in out:
                    out = _get_session(did).json(_statuses())          # refresh cross-deliverable statuses
            self._send(200 if "error" not in out else 409, json.dumps(out).encode(), "application/json")
        elif path == "/api/reset":
            with _lock:
                _get_session(did).reset()
                out = _get_session(did).json(_statuses())
            self._send(200, json.dumps(out).encode(), "application/json")
        else:
            self._send(404, b'{"error":"not found"}', "application/json")

    def log_message(self, *args) -> None:                        # keep the demo console quiet
        pass


def serve(host: str = "127.0.0.1", port: int = 8088) -> None:
    httpd = ThreadingHTTPServer((host, port), _Handler)
    print(f"CPA review console → http://{host}:{port}{BASE or '/'}  "
          f"(runtime: {os.environ.get('FIRM_LLM_BASE_URL') and 'live' or 'deterministic'})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()


if __name__ == "__main__":
    serve(os.environ.get("FIRM_CONSOLE_HOST", "127.0.0.1"),
          int(os.environ.get("FIRM_CONSOLE_PORT", "8088")))
