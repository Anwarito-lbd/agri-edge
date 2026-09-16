"""Emit real MAVLink over UDP, with scriptable faults. No aircraft required.

WHY THIS EXISTS
---------------
`telemetry/mavlink_link.py` has never parsed a real MAVLink packet. Its tests
call `_ingest()` with hand-built dicts, which verifies the folding logic and
nothing about the wire format, the UDP socket, the heartbeat handshake or the
field scaling. Those are exactly where a telemetry bug hides: lat/lon are int32
degrees x 1e7, altitude is millimetres, HDOP is centimetres, and getting any of
them wrong produces plausible-looking numbers in the wrong place.

The honest thing would be ArduPilot SITL, and `scripts/sitl.sh` runs it when the
machine can. This machine has no compiler, no WSL and no Docker, so SITL cannot
be built or run here at all. This emitter is the fallback: it speaks genuine
MAVLink through pymavlink, so it tests **our** decoder against the real protocol.

What it does NOT test, and SITL would: flight dynamics, EKF behaviour, mode
changes, failsafes, and whether a real autopilot sends what we expect it to. It
proves our side of the link, not theirs. Do not mistake a green run here for
having tested against an autopilot.

FAULTS
------
Each fault maps onto a row of the fault-injection matrix in
`docs/source/research-report.md` and onto a gate that already exists in
`qa/checks.py`:

    gnss-loss    fix_type -> 0          check_gnss FAIL   -> spooled DEGRADED
    rtk-float    fix_type -> 5          check_gnss FAIL   (when require_rtk_fixed)
    low-sats     satellites -> 3        check_gnss WARN
    high-hdop    eph -> 500 (5.0)       check_gnss WARN
    tilt         roll/pitch -> 25 deg   check_attitude FAIL
    silence      stops transmitting     max_telemetry_age_s -> no blind capture

Run:
    python workstation/fake_autopilot.py --duration 30
    python workstation/fake_autopilot.py --fault gnss-loss --fault-after 5
"""

from __future__ import annotations

import argparse
import math
import sys
import threading
import time

FAULTS = ("none", "gnss-loss", "rtk-float", "low-sats", "high-hdop", "tilt", "silence")


class FakeAutopilot:
    """Sends MAVLink as if it were a Pixhawk. Start it, point agri-edge at it.

    Deliberately a *sender* only. It never listens for commands, because
    `MavlinkTelemetry` is read-only by construction and there is nothing for a
    test autopilot to receive. If this class ever grows a command handler, that
    is a sign the safety contract has been broken somewhere upstream.
    """

    def __init__(
        self,
        connection: str = "udpout:127.0.0.1:14550",
        rate_hz: float = 10.0,
        lat: float = 49.8951,      # Winnipeg-ish; anywhere on the Prairies
        lon: float = -97.1384,
        alt_m: float = 30.0,
        fault: str = "none",
        fault_after_s: float = 0.0,
    ):
        if fault not in FAULTS:
            raise ValueError(f"Unknown fault '{fault}'. Choose from: {', '.join(FAULTS)}")
        self.connection = connection
        self.rate_hz = rate_hz
        self.lat = lat
        self.lon = lon
        self.alt_m = alt_m
        self.fault = fault
        self.fault_after_s = fault_after_s

        self._conn = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._started = 0.0

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        from pymavlink import mavutil

        # source_system 1 = a vehicle. agri-edge uses 200 so the two never collide.
        self._conn = mavutil.mavlink_connection(
            self.connection, source_system=1, source_component=1
        )
        self._started = time.time()
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="fake-autopilot", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        if self._conn is not None:
            self._conn.close()

    def __enter__(self) -> "FakeAutopilot":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    # -- the wire ----------------------------------------------------------

    @property
    def _fault_active(self) -> bool:
        return self.fault != "none" and (time.time() - self._started) >= self.fault_after_s

    def _loop(self) -> None:
        period = 1.0 / self.rate_hz
        boot = time.time()
        while not self._stop.is_set():
            if self._fault_active and self.fault == "silence":
                # The point of this one: the link goes quiet without closing, so
                # the reader blocks rather than erroring. Staleness is the only
                # thing that catches it.
                time.sleep(period)
                continue
            try:
                self._send(int((time.time() - boot) * 1000))
            except Exception as exc:  # pragma: no cover - socket teardown races
                if not self._stop.is_set():
                    print(f"fake-autopilot send failed: {exc}", file=sys.stderr)
                return
            time.sleep(period)

    def _send(self, boot_ms: int) -> None:
        m = self._conn.mav
        fault = self.fault if self._fault_active else "none"

        # --- GPS quality -------------------------------------------------
        fix_type, sats, eph = 6, 18, 80          # RTK fixed, 18 sats, HDOP 0.80
        if fault == "gnss-loss":
            fix_type, sats, eph = 0, 0, 9999
        elif fault == "rtk-float":
            fix_type = 5
        elif fault == "low-sats":
            sats = 3
        elif fault == "high-hdop":
            eph = 500                             # HDOP 5.00

        # --- attitude ----------------------------------------------------
        roll = pitch = 0.0
        if fault == "tilt":
            roll, pitch = math.radians(25.0), math.radians(10.0)

        m.heartbeat_send(
            type=2,          # MAV_TYPE_QUADROTOR
            autopilot=3,     # MAV_AUTOPILOT_ARDUPILOTMEGA
            base_mode=81,
            custom_mode=0,
            system_status=4,  # MAV_STATE_ACTIVE
        )
        # lat/lon are degrees x 1e7 and altitudes are MILLIMETRES. Every one of
        # these scalings is a place a telemetry bug looks like a plausible number.
        m.global_position_int_send(
            boot_ms,
            int(self.lat * 1e7),
            int(self.lon * 1e7),
            int((self.alt_m + 230.0) * 1000),    # MSL, Prairie ground ~230 m
            int(self.alt_m * 1000),              # relative to home
            0, 0, 0,                             # vx, vy, vz cm/s
            9000,                                # heading centi-degrees = 90.00
        )
        m.gps_raw_int_send(
            boot_ms * 1000,
            fix_type,
            int(self.lat * 1e7),
            int(self.lon * 1e7),
            int((self.alt_m + 230.0) * 1000),
            eph, 65535,                          # eph (HDOP x100), epv unknown
            0, 0,                                # vel, cog
            sats,
        )
        m.attitude_send(boot_ms, roll, pitch, math.radians(90.0), 0.0, 0.0, 0.0)
        m.vfr_hud_send(5.0, 5.0, 90, 0, self.alt_m, 0.0)
        m.sys_status_send(
            0, 0, 0, 500,
            14800, -1, 72,                       # voltage mV, current, battery %
            0, 0, 0, 0, 0, 0,
        )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--connection", default="udpout:127.0.0.1:14550",
                    help="Where to send. agri-edge listens on udpin:0.0.0.0:14550.")
    ap.add_argument("--rate", type=float, default=10.0, help="Hz")
    ap.add_argument("--duration", type=float, default=30.0, help="Seconds, 0 = forever")
    ap.add_argument("--fault", default="none", choices=FAULTS)
    ap.add_argument("--fault-after", type=float, default=0.0,
                    help="Seconds of healthy telemetry before the fault begins.")
    args = ap.parse_args()

    ap_sim = FakeAutopilot(
        connection=args.connection, rate_hz=args.rate,
        fault=args.fault, fault_after_s=args.fault_after,
    )
    print(f"fake autopilot -> {args.connection} at {args.rate:g} Hz")
    if args.fault != "none":
        print(f"  fault '{args.fault}' begins after {args.fault_after:g}s")
    print("  NOT a flight stack: this tests our MAVLink decoding, not an autopilot's behaviour.")

    ap_sim.start()
    try:
        if args.duration > 0:
            time.sleep(args.duration)
        else:
            while True:
                time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        ap_sim.stop()
    print("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
