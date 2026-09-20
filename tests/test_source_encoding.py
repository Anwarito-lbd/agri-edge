"""Bytes that make a file unusable on the machine it is meant to run on.

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

CRLF, THE SAME STORY A WEEK LATER
---------------------------------
`core.autocrlf=true` is the Windows default, so every checkout rewrote LF to
CRLF in the working tree. Harmless for Python. Fatal for a shell script the
moment it runs on Linux, because bash takes the carriage return as part of the
last token on the line:

    scripts/hailo_compile.sh: line 17: $'\\r': command not found
    scripts/hailo_compile.sh: line 18: set: pipefail\\r: invalid option name

Found when the Hailo preflight was finally run inside WSL2 -- the only place
the Dataflow Compiler can run. Those scripts had never been executed on Linux,
so nothing surfaced it. `.gitattributes` now pins LF and the tests below assert
both the file and the rule.
"""

from pathlib import Path

import pytest

BOM = b"\xef\xbb\xbf"
CRLF = b"\x0d\x0a"
ROOT = Path(__file__).resolve().parents[1]

# Third-party trees are not ours to reformat, and generated output is not
# committed. Everything else is in scope.
SKIP_PARTS = {".git", "vendor", "__pycache__", "node_modules", "runs",
              "weights", "data", "YOLOX_outputs", "YOLOX_outputs_crashed",
              ".venv", "venv", ".mypy_cache", ".pytest_cache", ".ruff_cache"}
TEXT_SUFFIXES = {".py", ".yaml", ".yml", ".json", ".md", ".sh", ".toml",
                 ".cfg", ".ini", ".txt"}


def _in_scope(path: Path) -> bool:
    parts = path.relative_to(ROOT).parts
    if SKIP_PARTS & set(parts):
        return False
    # Any virtualenv, whatever it is called. A list of known names missed a
    # throwaway `.lean-venv` and this suite silently grew from 1128 tests to
    # 3665 by linting site-packages -- which is a scope bug, not more coverage.
    for i in range(1, len(parts)):
        if (ROOT.joinpath(*parts[:i]) / "pyvenv.cfg").exists():
            return False
    return True


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


@pytest.mark.parametrize(
    "path",
    [p for p in FILES if p.suffix in {".sh", ".bash"}],
    ids=lambda p: p.relative_to(ROOT).as_posix(),
)
def test_shell_scripts_use_lf(path):
    """A CRLF shell script is a Linux script that cannot run on Linux.

    bash reads the carriage return as part of the last token on every line, so
    `set -euo pipefail` becomes `pipefail<CR>`, a path argument gains an
    invisible trailing character, and `$'\\r': command not found` is the only
    clue. Nothing in the error names line endings.
    """
    raw = path.read_bytes()
    assert CRLF not in raw, (
        f"{path.relative_to(ROOT).as_posix()} has CRLF line endings and will "
        "fail on Linux.\n"
        ".gitattributes pins *.sh to LF; if this fires, the working tree "
        "predates it. Fix with:  git add --renormalize ."
    )


def test_gitattributes_pins_line_endings():
    """The test above catches one bad file. This catches the missing rule that
    would let every future file be bad -- on a Windows clone, silently."""
    attrs = ROOT / ".gitattributes"
    assert attrs.exists(), (
        ".gitattributes is missing, so line endings are decided by whatever "
        "core.autocrlf each contributor happens to have."
    )
    text = attrs.read_text(encoding="utf-8")
    assert "*.sh" in text and "eol=lf" in text, (
        ".gitattributes does not pin *.sh to LF"
    )
