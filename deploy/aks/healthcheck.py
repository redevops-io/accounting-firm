"""Container health probe (HEALTHCHECK CMD). Stdlib only; exits 0 when the console answers /healthz with 200."""
import os
import sys
import urllib.request

port = os.environ.get("FIRM_CONSOLE_PORT", "8108")
base = os.environ.get("FIRM_CONSOLE_BASE", "").rstrip("/")
try:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{base}/healthz", timeout=4) as resp:
        sys.exit(0 if resp.status == 200 else 1)
except Exception:
    sys.exit(1)
