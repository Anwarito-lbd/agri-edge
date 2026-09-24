"""The ground IoT broker fails closed.

Finding F5 of docs/audit-2026-09-24.md: mosquitto.conf set
`allow_anonymous true` on both listeners and docker-compose published them on
every interface, so anything on the farm network could publish
`.../irrigation/set`. The file also began with a UTF-8 BOM, which
test_source_encoding did not scan `.conf` files for.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "ground_iot"
CONF = (ROOT / "mosquitto" / "mosquitto.conf").read_text(encoding="utf-8")
ACL = (ROOT / "mosquitto" / "acl").read_text(encoding="utf-8")
COMPOSE = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")


def _directives(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]


def test_no_anonymous_clients():
    d = _directives(CONF)
    assert "allow_anonymous false" in d
    assert not any(ln.startswith("allow_anonymous true") for ln in d)


def test_password_and_acl_are_required():
    d = _directives(CONF)
    assert any(ln.startswith("password_file ") for ln in d)
    assert any(ln.startswith("acl_file ") for ln in d)
    assert "./mosquitto/passwd:/mosquitto/config/passwd" in COMPOSE
    assert "./mosquitto/acl:/mosquitto/config/acl" in COMPOSE


def test_published_ports_are_loopback_only():
    ports = re.findall(r'^\s*-\s*"([^"]+)"\s*$', COMPOSE, flags=re.M)
    mapped = [p for p in ports if p.count(":") >= 1 and p.split(":")[-1].isdigit()]
    assert mapped, "no port mappings found"
    for p in mapped:
        assert p.startswith("127.0.0.1:"), p


def test_only_nodered_may_command_irrigation():
    """Whoever can publish irrigation/set can open a valve."""
    user = None
    writers = set()
    for ln in _directives(ACL):
        if ln.startswith("user "):
            user = ln.split()[1]
        elif ln.startswith("topic ") and user:
            parts = ln.split()
            access, topic = (parts[1], parts[2]) if len(parts) == 3 else ("readwrite", parts[1])
            if access in ("write", "readwrite") and (
                topic.endswith("irrigation/set") or topic.endswith("#")
            ):
                writers.add(user)
    assert writers == {"nodered"}, writers


def test_credentials_are_not_committable():
    ignore = (ROOT.parent / ".gitignore").read_text(encoding="utf-8")
    assert "ground_iot/mosquitto/passwd" in ignore


def test_images_are_pinned():
    for image in re.findall(r"image:\s*(\S+)", COMPOSE):
        assert not image.endswith(":latest") and ":" in image, image
