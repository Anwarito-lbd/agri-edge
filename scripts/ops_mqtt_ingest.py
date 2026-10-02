#!/usr/bin/env python3
"""Run the Ops Station MQTT ingest (and optionally the Ops HTTP API) -- SIMULATED.

    # against the ground_iot Mosquitto (docker compose -f ground_iot/docker-compose.yml up -d)
    python scripts/ops_mqtt_ingest.py --host 127.0.0.1 --port 1883 --serve

    # self-contained, no broker: in-memory transport + a synthetic publisher
    python scripts/ops_mqtt_ingest.py --loopback --serve

The ingest is SUBSCRIBE-ONLY. paho-mqtt is imported lazily (pip install paho-mqtt),
only when a real broker is used. MQTT_USERNAME / MQTT_PASSWORD come from the
environment. DATABASE_URL (sqlite:/// or postgresql://) selects persistence.
"""
from __future__ import annotations

import argparse
import json
import signal
import sys
import threading
import time
from http.server import ThreadingHTTPServer

from agri_edge.iot.transport import InMemoryTransport, PahoTransport
from agri_edge.ops.api import HOST, PORT, OpsHandler
from agri_edge.ops.live_ingest import IngestConfig, OpsIngestor
from agri_edge.ops.mqtt_sim import publish_demo
from agri_edge.ops.store import reset_store


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--farm", action="append", help="only ingest this farm id (repeatable)")
    ap.add_argument("--loopback", action="store_true", help="in-memory transport + synthetic publisher")
    ap.add_argument("--serve", action="store_true", help="also serve the Ops API/UI")
    ap.add_argument("--api-host", default=HOST)
    ap.add_argument("--api-port", type=int, default=PORT)
    ap.add_argument("--duration", type=float, default=0.0, help="stop after N seconds (0 = run until Ctrl-C)")
    args = ap.parse_args(argv)

    store = reset_store()
    cfg = IngestConfig(farm_ids=frozenset(args.farm) if args.farm else None)
    transport = InMemoryTransport() if args.loopback else PahoTransport(args.host, args.port, client_id="agriedge-ops-ingest")
    ing = OpsIngestor(store, transport, cfg)
    ing.start()
    if args.loopback:
        n = publish_demo(transport, farm=(args.farm or ["demo_farm"])[0])
        print(f"loopback: published {n} synthetic messages")
    print("ingest started (SIMULATED, subscribe-only):", json.dumps(ing.stats, default=str))

    httpd = None
    if args.serve:
        httpd = ThreadingHTTPServer((args.api_host, args.api_port), OpsHandler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        print(f"Ops API (SIMULATION banner on): http://{args.api_host}:{args.api_port}/ops/")

    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    t0 = time.time()
    while not stop.is_set():
        if args.duration and time.time() - t0 >= args.duration:
            break
        time.sleep(0.2)
    if httpd:
        httpd.shutdown()
    ing.stop()
    print("final stats:", json.dumps(ing.stats, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
