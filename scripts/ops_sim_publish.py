#!/usr/bin/env python3
"""Publish synthetic ops demo into the in-memory store (and print summary)."""
from agri_edge.ops.store import reset_store
from agri_edge.ops.simulate import seed_demo
import json

if __name__ == "__main__":
    store = reset_store()
    print(json.dumps(seed_demo(store), indent=2, default=str))
