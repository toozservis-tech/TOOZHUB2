#!/usr/bin/env python3
"""
CLI: uvolnění konkrétních e-mailů v customers před integračním / E2E register (viz release_customer_emails_for_re_register).

  cd .../app && ../.venv/bin/python scripts/recycle_integration_emails.py a@example.com b@example.com
"""
from __future__ import annotations

import sys
from pathlib import Path

_APP = Path(__file__).resolve().parent.parent
if str(_APP) not in sys.path:
    sys.path.insert(0, str(_APP))

from tests.api.integration_accounts import release_customer_emails_for_re_register


def main() -> int:
    release_customer_emails_for_re_register(list(sys.argv[1:]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
