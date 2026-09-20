"""No byte-order mark in a source file.

WHY THIS TEST EXISTS
--------------------
Twenty-four files in this repository picked up a UTF-8 BOM, and it turned the
whole test suite red in a way that pointed at the wrong thing. `ast.parse` on a
string that starts with U+FEFF raises a SyntaxError, so
`tests/test_runtime_deps.py` -- the guard that keeps heavy imports off the Pi --
failed with a parse error on sixteen modules at once. The modules themselves
were fine. The first byte was not.

It comes from PowerShell: `Set-Content`, `Out-File` and `>` write UTF-8 *with*
a BOM by default on Windows, so any file written from a shell one-liner instead
of an editor acquires one. It is invisible in every editor and in `git diff`.

A BOM in a `.py` file is legal to *import* -- CPython's tokenizer strips it --
which is why this survived long enough to reach a commit. It is anything that
reads the file as text and parses it itself that breaks: `ast`, some linters,
JSON and YAML loaders, and `#!/usr/bin/env` on the first line of a shell script,
which stops working entirely because the kernel sees three bytes before the `#!`.

So the rule is simply: no BOM, anywhere, and fail with the fix in the message.
"""

from pathlib import Path

import pytest

BOM = b"\xef\xbb\xbf"
ROOT = Path(__file__).resolve().parents[1]

# Third-party trees are not ours to reformat, and generated output is not
# committed. Everything else is in scope.
SKIP_PARTS = {".git", "vendor", "__pycache__", "node_modules", "runs",
              "weights", "data", "YOLOX_outputs", "YOLOX_outputs_crashed",
              ".venv", "venv", ".mypy_cache", ".pytest_cache", ".ruff_cache"}
TEXT_SUFFIXES = {".py", ".yaml", ".yml", ".json", ".md", ".sh", ".toml",
                 ".cfg", ".ini", ".txt"}


def _in_scope(path: Path) -> bool:
    return not (SKIP_PARTS & set(path.relative_to(ROOT).parts))


def text_files() -> list[Path]:
    return sorted(
        p for p in ROOT.rglob("*")
        if p.is_file() and p.suffix in TEXT_SUFFIXES and _in_scope(p)
    )


FILES = text_files()


def test_the_scan_actually_found_files():
    """A glob that matches nothing passes every test below it. This is the
    same trap as a CI job whose test step silently skips."""
    assert len(FILES) > 50, f"only {len(FILES)} files in scope -- the filter is wrong"


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_no_byte_order_mark(path):
    head = path.open("rb").read(3)
    assert head != BOM, (
        f"{path.relative_to(ROOT).as_posix()} starts with a UTF-8 BOM.\n"
        "This breaks ast.parse (and therefore tests/test_runtime_deps.py), "
        "JSON/YAML loaders, and the shebang line of a shell script.\n"
        "It comes from PowerShell's Set-Content / Out-File / '>' , which write "
        "UTF-8 with a BOM by default. Pass -Encoding utf8NoBOM, or write the "
        "file from an editor.\n"
        "To strip them all: python -c \"import pathlib;"
        "[p.write_bytes(p.read_bytes()[3:]) for p in pathlib.Path('.').rglob('*.py') "
        "if p.read_bytes()[:3]==b'\\xef\\xbb\\xbf']\""
    )


@pytest.mark.parametrize(
    "path",
    [p for p in FILES if p.suffix == ".sh"],
    ids=lambda p: p.relative_to(ROOT).as_posix(),
)
def test_shell_scripts_start_with_a_shebang(path):
    """The failure a BOM causes here is the least obvious of the lot: the
    script is executable, looks correct, and runs under the wrong interpreter
    or not at all, because three bytes sit in front of `#!`."""
    first = path.open("rb").readline()
    assert first.startswith(b"#!"), (
        f"{path.relative_to(ROOT).as_posix()} does not begin with a shebang; "
        f"its first bytes are {first[:8]!r}"
    )


@pytest.mark.parametrize(
    "path",
    [p for p in FILES if p.suffix == ".py"],
    ids=lambda p: p.relative_to(ROOT).as_posix(),
)
def test_every_python_file_parses(path):
    """Cheap, and it catches a half-written file before a hundred collection
    errors bury the real message. `test_runtime_deps.py` parses the runtime
    package for a different reason; this covers training, workstation,
    mechanical and the scripts as well."""
    import ast

    source = path.read_text(encoding="utf-8")
    try:
        ast.parse(source)
    except SyntaxError as exc:
        pytest.fail(f"{path.relative_to(ROOT).as_posix()}:{exc.lineno}: {exc.msg}")
