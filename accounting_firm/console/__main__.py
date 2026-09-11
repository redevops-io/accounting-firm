"""`python -m accounting_firm.console` → the CPA review console."""
import os

from .app import serve

if __name__ == "__main__":
    serve(os.environ.get("FIRM_CONSOLE_HOST", "127.0.0.1"),
          int(os.environ.get("FIRM_CONSOLE_PORT", "8088")))
