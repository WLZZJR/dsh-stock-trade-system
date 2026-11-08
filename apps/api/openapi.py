"""OpenAPI export and the committed contract snapshot (P1-26).

``python -m api.openapi`` (``make openapi``) rewrites the snapshot. A test compares it with the
schema generated from the code, so an API change cannot pass CI without the snapshot changing in
the same commit, which makes every contract change visible in review.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from api.main import create_app

SNAPSHOT_PATH = Path(__file__).resolve().parents[2] / "tests" / "contract" / "openapi_snapshot.json"


def generated_document() -> dict[str, Any]:
    document: dict[str, Any] = create_app().openapi()
    return document


def render(document: dict[str, Any]) -> str:
    """Canonical text: sorted keys, two-space indent, trailing newline."""
    return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    SNAPSHOT_PATH.write_text(render(generated_document()), encoding="utf-8")
    print(f"wrote {SNAPSHOT_PATH.relative_to(SNAPSHOT_PATH.parents[2])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
