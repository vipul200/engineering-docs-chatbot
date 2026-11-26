"""Contract test: the committed API spec must match the running code.

If this fails, you changed the API. Regenerate with
`PYTHONPATH=src python scripts/export_openapi.py` and review the diff.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from export_openapi import OUT, render  # noqa: E402


def test_openapi_spec_is_up_to_date():
    assert OUT.exists(), "docs/openapi.json missing; run scripts/export_openapi.py"
    assert json.loads(OUT.read_text()) == json.loads(render())
