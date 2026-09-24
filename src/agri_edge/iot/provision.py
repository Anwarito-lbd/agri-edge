"""Per-device MQTT credentials: one identity per sensor, scoped to its own topics.

WHY
---
A shared `sensor` login means one extracted ESP32 can speak for every probe
on the farm -- and read every zone's valve commands. Here each device gets:

* its own username and a random password (never reused, never committed);
* an ACL block granting exactly its farm/zone topics for its kind -- a soil
  probe may write that zone's `soil` and `status`, a valve node may *read*
  that zone's `irrigation/set` and write `irrigation/status`, and nothing may
  publish a command;
* a registry entry (`devices.json`) the ops station uses to notice a device
  that has gone quiet.

The password hash is written in Mosquitto 2's own format (PBKDF2-SHA512,
"$7$<iterations>$<salt b64>$<hash b64>", as `mosquitto_passwd` produces), so
provisioning needs neither Docker nor the Mosquitto tools on this machine.
Mosquitto re-reads the password and ACL files on SIGHUP.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

KINDS = {
    "soil": (["soil", "status"], []),
    "weather": (["weather", "status"], []),
    "valve": (["irrigation/status", "status"], ["irrigation/set"]),
}
_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{1,31}$")
BEGIN, END = "# >>> device {} (managed by agri_edge.iot.provision)", "# <<< device {}"


@dataclass
class Device:
    device_id: str
    farm: str
    zone: str
    kind: str
    transport: str = "wifi"          # wifi | lorawan
    dev_eui: str | None = None       # LoRaWAN only
    interval_s: int = 900
    created: str = ""


def mosquitto_hash(password: str, *, iterations: int = 101, salt: bytes | None = None) -> str:
    salt = salt if salt is not None else secrets.token_bytes(12)
    dk = hashlib.pbkdf2_hmac("sha512", password.encode("utf-8"), salt, iterations, 64)
    return f"$7${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_mosquitto_hash(password: str, stored: str) -> bool:
    try:
        _, tag, it, salt_b64, hash_b64 = stored.split("$")
    except ValueError:
        return False
    if tag != "7":
        return False
    dk = hashlib.pbkdf2_hmac("sha512", password.encode("utf-8"), base64.b64decode(salt_b64),
                             int(it), 64)
    return secrets.compare_digest(base64.b64encode(dk).decode(), hash_b64)


def acl_block(d: Device) -> str:
    writes, reads = KINDS[d.kind]
    base = f"agriedge/farm/{d.farm}/zone/{d.zone}"
    lines = [BEGIN.format(d.device_id), f"user {d.device_id}"]
    lines += [f"topic write {base}/{k}" for k in writes]
    lines += [f"topic read {base}/{k}" for k in reads]
    lines.append(END.format(d.device_id))
    return "\n".join(lines) + "\n"


def _without_block(text: str, device_id: str) -> str:
    pat = re.compile(re.escape(BEGIN.format(device_id)) + r".*?" + re.escape(END.format(device_id)) + r"\n?",
                     re.S)
    return pat.sub("", text)


def _check(d: Device) -> None:
    for name, v in (("device_id", d.device_id), ("farm", d.farm), ("zone", d.zone)):
        if not _ID.match(v):
            raise ValueError(f"{name} must be 2-32 of a-z 0-9 _ -, starting alphanumeric: {v!r}")
    if d.device_id in ("sensor", "agriedge", "nodered", "drone"):
        raise ValueError(f"{d.device_id!r} is a reserved role name")
    if d.kind not in KINDS:
        raise ValueError(f"kind must be one of {sorted(KINDS)}")
    if d.transport == "lorawan" and not (d.dev_eui and re.fullmatch(r"[0-9a-fA-F]{16}", d.dev_eui)):
        raise ValueError("LoRaWAN devices need a 16-hex-digit dev_eui")


def provision(d: Device, *, passwd: Path, acl: Path, registry: Path) -> str:
    """Create or rotate a device. Returns the new plaintext password (shown
    once, for flashing into the device; only the hash is stored)."""
    _check(d)
    d.created = d.created or datetime.now(timezone.utc).isoformat()
    password = secrets.token_urlsafe(24)
    lines = passwd.read_text(encoding="utf-8").splitlines() if passwd.exists() else []
    lines = [ln for ln in lines if not ln.startswith(f"{d.device_id}:")]
    if d.transport == "wifi":
        lines.append(f"{d.device_id}:{mosquitto_hash(password)}")
    passwd.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    try:
        passwd.chmod(0o600)
    except OSError:
        pass
    text = acl.read_text(encoding="utf-8") if acl.exists() else ""
    if d.transport == "wifi":
        text = _without_block(text, d.device_id).rstrip("\n") + "\n\n" + acl_block(d)
    acl.write_text(text, encoding="utf-8")
    reg = load_registry(registry)
    reg[d.device_id] = asdict(d)
    registry.write_text(json.dumps(reg, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return password


def revoke(device_id: str, *, passwd: Path, acl: Path, registry: Path) -> bool:
    found = False
    if passwd.exists():
        lines = passwd.read_text(encoding="utf-8").splitlines()
        kept = [ln for ln in lines if not ln.startswith(f"{device_id}:")]
        found |= len(kept) != len(lines)
        passwd.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    if acl.exists():
        before = acl.read_text(encoding="utf-8")
        after = _without_block(before, device_id)
        found |= after != before
        acl.write_text(after, encoding="utf-8")
    reg = load_registry(registry)
    found |= reg.pop(device_id, None) is not None
    registry.write_text(json.dumps(reg, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return found


def load_registry(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def esphome_secrets(d: Device, password: str, broker: str, wifi_ssid: str = "CHANGEME",
                    wifi_password: str = "CHANGEME") -> str:
    """secrets.yaml for flashing this device (never commit the output)."""
    return (f"wifi_ssid: \"{wifi_ssid}\"\nwifi_password: \"{wifi_password}\"\n"
            f"mqtt_broker: \"{broker}\"\nmqtt_username: \"{d.device_id}\"\n"
            f"mqtt_password: \"{password}\"\n")


def main(argv: list[str] | None = None) -> int:
    import argparse

    here = Path(__file__).resolve().parents[3] / "ground_iot" / "mosquitto"
    ap = argparse.ArgumentParser(prog="python -m agri_edge.iot.provision",
                                 description="Add, rotate or revoke a field device's MQTT identity.")
    ap.add_argument("action", choices=["add", "revoke", "list"])
    ap.add_argument("device_id", nargs="?")
    ap.add_argument("--farm")
    ap.add_argument("--zone")
    ap.add_argument("--kind", choices=sorted(KINDS))
    ap.add_argument("--transport", default="wifi", choices=["wifi", "lorawan"])
    ap.add_argument("--dev-eui")
    ap.add_argument("--broker", default="192.168.1.10")
    ap.add_argument("--dir", default=str(here), help="where passwd, acl and devices.json live")
    args = ap.parse_args(argv)
    base = Path(args.dir)
    paths = {"passwd": base / "passwd", "acl": base / "acl", "registry": base / "devices.json"}
    if args.action == "list":
        for k, v in sorted(load_registry(paths["registry"]).items()):
            print(f"{k:24} {v['kind']:8} {v['farm']}/{v['zone']:12} {v['transport']}")
        return 0
    if not args.device_id:
        ap.error("device_id is required")
    if args.action == "revoke":
        ok = revoke(args.device_id, **paths)
        print("revoked" if ok else "not found", "- send SIGHUP to mosquitto to apply")
        return 0 if ok else 1
    d = Device(args.device_id, args.farm or "", args.zone or "", args.kind or "",
               args.transport, args.dev_eui)
    pw = provision(d, **paths)
    if d.transport == "wifi":
        print("# secrets.yaml for this device -- flash it, then delete this output:")
        print(esphome_secrets(d, pw, args.broker))
    print("Send SIGHUP to mosquitto (docker kill -s HUP agriedge-mosquitto) to apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
