"""RTK corrections from an NTRIP caster, so `require_rtk_fixed` can pass.

THE GATE THAT COULD NEVER OPEN
------------------------------
`qa.require_rtk_fixed` exists and is tested, and until now there was no way to
achieve an RTK fix at all: nothing in this project delivered correction data.
Turn the gate on and every frame fails. A gate that cannot pass is not a safety
feature, it is a bug with good intentions.

Centimetre positioning is what makes a June map and a July map of the same field
comparable. Without it, a metre of drift between flights looks exactly like a
change in the crop.

WHERE THE CORRECTIONS GO -- AND WHY NOT OVER MAVLINK
-----------------------------------------------------
ArduPilot accepts RTCM injected as MAVLink `GPS_RTCM_DATA`, and a ground station
usually does exactly that. **This deliberately does not.**

`telemetry/mavlink_link.py` is read-only *by construction*, and a test asserts no
method exists on it that could write to the vehicle. That property is worth more
than the convenience. Adding a write path "just for corrections" means the class
can now transmit, and the next thing that wants to transmit has a precedent to
point at. The contract is valuable precisely because it has no exceptions.

So corrections go **straight to the GNSS receiver** over its own serial port,
which is also the normal hardware topology: the receiver has a correction input,
and the flight controller never sees the bytes. The aircraft cannot be commanded
by this code because this code is not connected to anything that takes commands.

    NTRIP caster --HTTP--> this client --serial--> GNSS receiver --> flight controller

WHAT THIS IS NOT
----------------
It does not parse RTCM. It is a pipe: authenticate, stream bytes, forward them,
reconnect when the link drops. Interpreting RTCM is the receiver's job and doing
it here would add a second implementation to disagree with.

CREDENTIALS
-----------
From the environment (`NTRIP_USERNAME`, `NTRIP_PASSWORD`), never from config, for
the same reason as farmOS: config files are committed.
"""

from __future__ import annotations

import base64
import logging
import os
import socket
import threading
import time
from dataclasses import dataclass, field

log = logging.getLogger("agri_edge.telemetry.ntrip")


@dataclass
class NtripConfig:
    """Caster connection details. Secrets come from the environment."""

    host: str = ""
    port: int = 2101
    mountpoint: str = ""
    username: str = ""
    password: str = ""
    # Where the bytes go: a serial device wired to the GNSS receiver's correction
    # input. NOT the flight controller -- see the module docstring.
    sink: str = ""
    sink_baud: int = 115200
    timeout_s: float = 10.0
    # A caster that goes quiet has failed even though the socket is open, which
    # is the same trap as stale MAVLink.
    stale_after_s: float = 30.0

    @classmethod
    def from_env(cls, host: str, mountpoint: str, sink: str, **kw) -> "NtripConfig":
        return cls(
            host=host,
            mountpoint=mountpoint,
            sink=sink,
            username=os.environ.get("NTRIP_USERNAME", ""),
            password=os.environ.get("NTRIP_PASSWORD", ""),
            **kw,
        )

    def missing(self) -> list[str]:
        out = []
        if not self.host:
            out.append("host")
        if not self.mountpoint:
            out.append("mountpoint")
        if not self.sink:
            out.append("sink")
        if not self.username:
            out.append("NTRIP_USERNAME")
        if not self.password:
            out.append("NTRIP_PASSWORD")
        return out


@dataclass
class NtripStats:
    connected: bool = False
    bytes_forwarded: int = 0
    last_data_at: float = 0.0
    reconnects: int = 0
    errors: list[str] = field(default_factory=list)

    def is_stale(self, stale_after_s: float, now: float | None = None) -> bool:
        """Open socket, no bytes. The failure that looks like success."""
        if not self.last_data_at:
            return True
        return (now if now is not None else time.time()) - self.last_data_at > stale_after_s

    def as_dict(self) -> dict:
        return {
            "connected": self.connected,
            "bytes_forwarded": self.bytes_forwarded,
            "last_data_at": self.last_data_at,
            "reconnects": self.reconnects,
            "errors": self.errors[-3:],
        }


def build_request(cfg: NtripConfig) -> bytes:
    """The NTRIP v1 request line. Plain HTTP with a Basic auth header.

    `Ntrip-Version` is sent because some casters serve a v1 source table instead
    of the stream without it, which surfaces as a confusing blob of text where
    RTCM was expected.
    """
    token = base64.b64encode(
        f"{cfg.username}:{cfg.password}".encode("utf-8")
    ).decode("ascii")
    return (
        f"GET /{cfg.mountpoint} HTTP/1.0\r\n"
        f"Host: {cfg.host}:{cfg.port}\r\n"
        "Ntrip-Version: Ntrip/1.0\r\n"
        "User-Agent: NTRIP agri-edge/0.1\r\n"
        f"Authorization: Basic {token}\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode("ascii")


def check_response(header: bytes) -> None:
    """Raise with something actionable if the caster refused us."""
    text = header.decode("ascii", errors="replace")
    first = text.split("\r\n", 1)[0]
    # SOURCETABLE FIRST, because a caster announces it as "SOURCETABLE 200 OK".
    # Checking for "200" before this accepts a source table as a stream, and the
    # receiver then gets a wall of ASCII where RTCM should be -- which is exactly
    # the confusing failure this function exists to prevent. An earlier version
    # of this check had the order the wrong way round and the test caught it.
    if "SOURCETABLE" in text:
        raise RuntimeError(
            "The caster returned its SOURCE TABLE instead of a stream, which "
            "means the mountpoint was not recognised. That table lists the "
            "mountpoints the caster does serve."
        )
    if "200" in first or first.startswith("ICY 200"):
        return
    if "401" in first:
        raise RuntimeError(
            f"NTRIP caster rejected the credentials ({first.strip()}). Check "
            "NTRIP_USERNAME and NTRIP_PASSWORD."
        )
    if "404" in first:
        raise RuntimeError(
            f"NTRIP mountpoint not found ({first.strip()}). The caster's source "
            "table lists valid mountpoints."
        )
    raise RuntimeError(f"Unexpected NTRIP response: {first.strip()!r}")


class NtripClient:
    """Streams RTCM from a caster to the GNSS receiver. Never to the autopilot.

    Runs a background thread and reconnects on failure. Correction loss is a
    *degradation*, not an emergency: the receiver falls back to a standard fix,
    `check_gnss` notices, and frames spool as DEGRADED. Nothing here should ever
    stop a flight.
    """

    def __init__(self, cfg: NtripConfig, sink_factory=None):
        missing = cfg.missing()
        if missing:
            raise ValueError(
                "NTRIP is not configured: missing " + ", ".join(missing) + ". "
                "Credentials come from the environment (NTRIP_USERNAME, "
                "NTRIP_PASSWORD), never from a config file."
            )
        self.cfg = cfg
        self.stats = NtripStats()
        # Injectable so the whole path is testable without a serial port.
        self._sink_factory = sink_factory or self._open_serial
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _open_serial(self):
        try:
            import serial
        except ImportError as exc:  # pragma: no cover - optional extra
            raise RuntimeError(
                "pyserial is required to forward RTCM to the receiver. "
                "Install with: pip install 'agri-edge[mavlink]'"
            ) from exc
        return serial.Serial(self.cfg.sink, self.cfg.sink_baud, timeout=1.0)

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="ntrip", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)

    def __enter__(self) -> "NtripClient":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    # -- the pipe ----------------------------------------------------------

    def _run(self) -> None:  # pragma: no cover - exercised via stream_once
        backoff = 1.0
        while not self._stop.is_set():
            try:
                self.stream_once()
                backoff = 1.0
            except Exception as exc:
                self.stats.connected = False
                self.stats.errors.append(str(exc))
                self.stats.reconnects += 1
                log.warning(
                    "NTRIP stream ended (%s). Reconnecting in %.0fs. The receiver "
                    "falls back to a standard fix; frames will spool DEGRADED.",
                    exc, backoff,
                )
                # Capped exponential backoff: a caster that is down stays down for
                # minutes, and hammering it helps nobody.
                self._stop.wait(backoff)
                backoff = min(backoff * 2.0, 60.0)

    def stream_once(self, max_bytes: int | None = None) -> int:
        """Connect, authenticate and forward until the stream ends.

        Returns bytes forwarded. Separated from the retry loop so the protocol
        can be tested against a stub caster without threads or sleeps.
        """
        sink = self._sink_factory()
        try:
            with socket.create_connection(
                (self.cfg.host, self.cfg.port), timeout=self.cfg.timeout_s
            ) as sock:
                sock.sendall(build_request(self.cfg))

                # Read only as far as the end of the header, so the first RTCM
                # bytes that follow it in the same packet are not discarded.
                buf = b""
                while b"\r\n\r\n" not in buf:
                    chunk = sock.recv(1024)
                    if not chunk:
                        raise RuntimeError("Caster closed the connection during the handshake.")
                    buf += chunk
                    if len(buf) > 8192:
                        raise RuntimeError("NTRIP header too large; this is not a caster.")

                header, _, leftover = buf.partition(b"\r\n\r\n")
                check_response(header)
                self.stats.connected = True

                total = 0
                if leftover:
                    sink.write(leftover)
                    total += len(leftover)
                    self.stats.last_data_at = time.time()

                while not self._stop.is_set():
                    data = sock.recv(4096)
                    if not data:
                        break
                    sink.write(data)
                    total += len(data)
                    self.stats.bytes_forwarded += len(data)
                    self.stats.last_data_at = time.time()
                    if max_bytes is not None and total >= max_bytes:
                        break
                return total
        finally:
            self.stats.connected = False
            close = getattr(sink, "close", None)
            if close is not None:
                close()
