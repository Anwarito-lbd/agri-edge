"""Every value the ops UI writes into innerHTML goes through esc().

Finding F4 of docs/audit-2026-09-24.md: each page rendered
`JSON.stringify(response)` straight into innerHTML. Strings in those responses
come from clients -- an alert ACK's `by`, a note's `text` -- so POSTing
`{"by": "<img src=x onerror=...>"}` ran script in the next operator's browser.

This is a static check over the page sources: a template interpolation `${...}`
must either be `esc(...)` or `rows`, the one variable that is itself built from
escaped cells. It is deliberately strict; a new page that needs raw markup
should build it from escaped parts and add its variable name here.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

UI_DIR = Path(__file__).resolve().parents[1] / "src" / "agri_edge" / "ops" / "ui"
PAGES = sorted(UI_DIR.glob("*.html"))
# Variables assembled from esc()-ed parts by string concatenation.
PREBUILT_FROM_ESCAPED = {"rows", "items", "extra"}
INTERPOLATION = re.compile(r"\$\{((?:[^{}]|\{[^{}]*\})*)\}")


def test_there_are_pages_to_check():
    assert PAGES, UI_DIR


@pytest.mark.parametrize("page", PAGES, ids=[p.name for p in PAGES])
def test_every_interpolation_is_escaped(page):
    src = page.read_text(encoding="utf-8")
    bad = [m.group(0) for m in INTERPOLATION.finditer(src)
           if not (m.group(1).startswith("esc(") or m.group(1) in PREBUILT_FROM_ESCAPED)]
    assert not bad, f"{page.name}: unescaped {bad}"


@pytest.mark.parametrize("page", PAGES, ids=[p.name for p in PAGES])
def test_page_defines_esc(page):
    if "${" in page.read_text(encoding="utf-8"):
        assert "function esc(" in page.read_text(encoding="utf-8")


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_esc_neutralises_markup():
    line = next(ln for ln in PAGES[0].read_text(encoding="utf-8").splitlines()
                if ln.startswith("function esc("))
    payload = "<img src=x onerror=alert(1)>\"'&"
    out = subprocess.run(
        ["node", "-e", f"{line}; process.stdout.write(esc(process.argv[1]))", payload],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "<" not in out and ">" not in out and '"' not in out and "'" not in out
    assert out.startswith("&lt;img")
