"""Print the content map of a Figma file.

    python -m wp_brief_agent.figma https://www.figma.com/design/<KEY>/<name>

Needs FIGMA_TOKEN (a Figma personal access token with read access to file content).
"""

from __future__ import annotations

import json
import os
import sys

from .__main__ import _load_dotenv
from .figma_client import FigmaError, load_design


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print(__doc__)
        return 1
    try:
        design = load_design(args[0], os.getenv("FIGMA_TOKEN", ""))
    except FigmaError as exc:
        print(f"Error: {exc}")
        return 2
    print(json.dumps(design, indent=2, ensure_ascii=False))
    count = len(design["sections"])
    print(f"\n{count} section(s) with text in '{design['name']}'.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
