#!/usr/bin/env python3
"""Publish synthetic ops demo data (SIMULATED; everything is synthetic=true).

    python scripts/ops_sim_publish.py                 # seed the in-memory store, print summary
    python scripts/ops_sim_publish.py --mqtt          # publish to a real broker (127.0.0.1:1883)
    python scripts/ops_sim_publish.py --mqtt --loopback
                                                      # no broker: publish -> in-memory broker ->
                                                      # OpsIngestor -> store, then print what arrived

`--mqtt` publishes DATA topics only (never irrigation/set, arm, mission...). paho-mqtt is
imported lazily and only for a real broker.
"""
import argparse
import json
import sys

from agri_edge.ops.simulate import seed_demo
from agri_edge.ops.store import reset_store


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mqtt", action="store_true", help="publish over MQTT instead of seeding directly")
    ap.add_argument("--loopback", action="store_true", help="with --mqtt: in-memory broker + ingestor round trip")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--farm", default="demo_farm")
    ap.add_argument("--frost", action="store_true", help="publish a sub-zero air temperature")
    ap.add_argument("--replay", action="store_true", help="send every message twice (dedupe demo)")
    args = ap.parse_args(argv)

    if not args.mqtt:
        store = reset_store()
        print(json.dumps(seed_demo(store), indent=2, default=str))
        return 0

    from agri_edge.iot.transport import InMemoryTransport, PahoTransport
    from agri_edge.ops.mqtt_sim import publish_demo

    if args.loopback:
        from agri_edge.ops.live_ingest import OpsIngestor

        store = reset_store()
        t = InMemoryTransport()
        ing = OpsIngestor(store, t)
        ing.start()
        n = publish_demo(t, farm=args.farm, frost=args.frost, replay=args.replay)
        print(json.dumps({"published": n, "ingest": ing.stats,
                          "devices": sorted(store.devices),
                          "alerts": [a.title for a in store.alerts.list_alerts()],
                          "detections": len(store.detections)}, indent=2, default=str))
        return 0

    t = PahoTransport(args.host, args.port, client_id="agriedge-sim-publisher")
    t.connect()
    t.wait_connected(5.0)
    n = publish_demo(t, farm=args.farm, frost=args.frost, replay=args.replay)
    t.disconnect()
    print(f"published {n} synthetic messages to {args.host}:{args.port}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
