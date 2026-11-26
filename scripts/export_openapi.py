"""Regenerate docs/openapi.json from the FastAPI app (the API contract).

    PYTHONPATH=src python scripts/export_openapi.py
"""

import json
from pathlib import Path

from docs_chatbot.api import app

OUT = Path(__file__).resolve().parents[1] / "docs" / "openapi.json"


def render() -> str:
    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":
    OUT.write_text(render())
    print(f"wrote {OUT}")
