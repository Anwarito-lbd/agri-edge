#!/usr/bin/env python3
"""Laptop entrypoint for RelateAnything offline pass.

Never run on the Pi. Example:
  python scripts/laptop_relate_anything.py --spool runs/spool --repo-root .
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running without install
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agri_edge.relations.laptop_relate import (  # noqa: E402
    NotConfiguredError,
    assert_laptop_only,
    relation_feature,
    relations_to_geojson,
    run_offline,
)


def main() -> int:
    p = argparse.ArgumentParser(description="RelateAnything laptop offline hook")
    p.add_argument("--spool", type=Path, required=True)
    p.add_argument("--repo-root", type=Path, default=ROOT)
    p.add_argument("--demo-schema", action="store_true", help="Print example GeoJSON schema and exit")
    args = p.parse_args()

    try:
        assert_laptop_only()
    except NotConfiguredError as e:
        print(e, file=sys.stderr)
        return 2

    if args.demo_schema:
        feat = relation_feature("weed", "in", "crop_row", confidence=0.8, frame_id="demo")
        print(json.dumps(relations_to_geojson([feat]), indent=2))
        return 0

    try:
        run_offline(args.spool, repo_root=args.repo_root)
    except NotConfiguredError as e:
        print(e, file=sys.stderr)
        return 3
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
