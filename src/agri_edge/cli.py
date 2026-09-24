"""Command-line interface.

    agri-edge fly      --simulate           run the capture pipeline
    agri-edge spool    --status | --export  inspect or offload the spool
    agri-edge indices  <bands>              which indices a payload supports
    agri-edge preflight                     check the edge system before a flight
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

from .capture.camera import build_camera
from .config import Config
from .inference.engine import build_engine
from .pipeline.runner import Pipeline
from .sensors.environment import build_environment_sensor
from .store.spool import Spool
from .telemetry.mavlink_link import build_telemetry_source


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    )


def _load_config(path: str | None) -> Config:
    if path is None:
        return Config()
    return Config.load(path)


def cmd_fly(args) -> int:
    cfg = _load_config(args.config)
    bands = args.bands.split(",") if args.bands else ["red", "green", "blue", "nir", "red-edge"]

    # --bench: real camera, synthetic telemetry. For testing a camera and model on
    # the bench with no autopilot attached.
    #
    # The alternative -- a flag that disables the stale-telemetry check -- was
    # rejected deliberately. That gate exists because an image with no trustworthy
    # position cannot support the cross-date comparison repeated monitoring is
    # for, and a flag to switch it off would eventually be left on in flight.
    # Supplying synthetic telemetry keeps the gate intact and makes the fake
    # position obvious in every sidecar it touches.
    #
    # --sitl is the mirror of --bench: SYNTHETIC camera, REAL telemetry. It is the
    # combination needed to test against ArduPilot SITL or workstation/
    # fake_autopilot.py, where there is a genuine MAVLink stream but no camera.
    #
    # Note which half is fake in each mode. --bench fabricates POSITION, so its
    # data must never be mapped. --sitl fabricates IMAGERY, so its detections mean
    # nothing -- but the telemetry, and therefore every QA gate that reads it, is
    # real. That is precisely what makes it useful for fault injection.
    simulate_telemetry = args.simulate or args.bench
    simulate_camera = args.simulate or args.sitl

    telemetry = build_telemetry_source(cfg.mavlink, simulated=simulate_telemetry)
    camera = build_camera(cfg.capture, simulated=simulate_camera, bands=bands)
    spool = Spool(cfg.spool.spool_dir, cfg.spool.max_bytes)
    engine = build_engine(cfg.inference)
    environment = build_environment_sensor(cfg.capture, simulated=simulate_camera)
    from .iot.edge_publisher import build_publisher

    publisher = build_publisher(cfg.publish)

    if args.simulate:
        mode = "SIMULATED"
    elif args.bench:
        mode = "BENCH"
    elif args.sitl:
        mode = "SITL"
    else:
        mode = "LIVE"
    print(f"Site: {cfg.site} | Field: {cfg.field_id} | Bands: {', '.join(bands)}")
    print(f"Mode: {mode} | Spool: {cfg.spool.spool_dir}")
    if args.bench:
        print(
            "\n  BENCH MODE: real camera, SYNTHETIC telemetry. Every position recorded\n"
            "  in this run is fabricated. Do not use this data for mapping, and do not\n"
            "  use this flag in flight.\n"
        )
    if args.sitl:
        print(
            "\n  SITL MODE: REAL telemetry, SYNTHETIC imagery. The positions and QA\n"
            "  gates are genuine; the pictures are not, so any detection in this run\n"
            "  is an artefact of the synthetic scene. Use it to test the pipeline,\n"
            "  never to judge a model.\n"
        )
    if engine is not None and not engine.metadata.validated_locally:
        print(
            "\n  NOTE: the loaded model is not marked as locally validated.\n"
            "  Detections are decision support only and must not drive treatment.\n"
        )

    with Pipeline(cfg, camera, telemetry, spool, engine, environment,
                  publisher=publisher) as pipeline:
        stats = pipeline.run(duration_s=args.duration, max_frames=args.frames)

    print("\n--- run summary ---")
    print(json.dumps(stats.as_dict(), indent=2))
    print("\n--- spool ---")
    print(json.dumps(spool.stats(), indent=2))
    return 0


def cmd_spool(args) -> int:
    cfg = _load_config(args.config)
    spool = Spool(cfg.spool.spool_dir, cfg.spool.max_bytes)

    if args.export:
        n = spool.export(Path(args.export))
        print(f"Exported {n} files to {args.export}")
        return 0

    if args.upload and args.upload_to == "farmos":
        from .store.farmos import FarmOSConfig, push_spool

        if not cfg.farmos.url:
            print(
                "No farmos.url configured. Set it in the config file; the\n"
                "credentials come from FARMOS_USERNAME / FARMOS_PASSWORD /\n"
                "FARMOS_CLIENT_SECRET in the environment, never from the file.",
                file=sys.stderr,
            )
            return 1

        fcfg = FarmOSConfig.from_env(
            cfg.farmos.url,
            land_asset_id=cfg.farmos.land_asset_id,
            timeout_s=cfg.farmos.timeout_s,
        )
        missing = fcfg.missing_credentials()
        if missing:
            print(
                "farmOS credentials missing from the environment: "
                + ", ".join(missing)
                + "\nExport them and retry; they are deliberately not read from config.",
                file=sys.stderr,
            )
            return 1

        pending = len(spool.pending())
        print(f"Pushing {pending} pending sidecars to farmOS at {cfg.farmos.url}")
        print("  sidecars only -- images stay spooled for the workstation.")
        farm_result = push_spool(spool, fcfg, limit=args.limit_uploads)
        print(json.dumps(farm_result.as_dict(), indent=2))
        return 0 if farm_result.ok else 1

    if args.upload:
        from .store.uploader import build_uploader

        mode = args.upload_mode or cfg.spool.upload_mode
        uploader = build_uploader(spool, cfg.spool, mode=mode)
        if uploader is None:
            print(
                "No spool.upload_endpoint configured -- nothing to upload to.\n"
                "Running offline is the normal case; use --export to copy the\n"
                "spool to removable media instead.",
                file=sys.stderr,
            )
            return 1

        pending = len(spool.pending())
        print(f"Uploading to {uploader.endpoint}  (mode: {mode}, {pending} pending)")
        if mode == "metadata":
            print("  metadata only -- sidecars, not images. Use --upload-mode full for images.")

        result = uploader.upload_pending(limit=args.limit_uploads)
        print(json.dumps(result.as_dict(), indent=2))
        if result.failed:
            print(
                f"\n  {result.failed} failed and remain spooled. Nothing is lost --"
                f"\n  they will be retried on the next pass.",
                file=sys.stderr,
            )
        return 0 if result.all_ok else 1

    stats = spool.stats()
    print(json.dumps(stats, indent=2))
    if args.list:
        for e in spool.pending()[: args.list]:
            print(f"  [{e.priority}] {e.entry_id}  seq={e.sequence}  {e.size_bytes:,} B")
    return 0


def cmd_indices(args) -> int:
    """Report which indices a given band set supports, and why not the others."""
    import numpy as np

    from .geo.indices import INDEX_REQUIREMENTS, BandStack, available_indices

    bands = [b.strip() for b in args.bands.split(",") if b.strip()]
    dummy = np.zeros((4, 4, len(bands)), dtype=np.uint8)
    stack = BandStack(dummy, bands)

    ok = set(available_indices(stack))
    print(f"Bands recognised: {', '.join(stack.available) or '(none)'}\n")
    for name, req in sorted(INDEX_REQUIREMENTS.items()):
        if name in ok:
            print(f"  [available] {name:<13} needs {', '.join(req)}")
        else:
            missing = [r for r in req if not stack.has(r)]
            print(f"  [  missing] {name:<13} needs {', '.join(req)}  -- lacking {', '.join(missing)}")
    return 0


def cmd_preflight(args) -> int:
    """Edge-system preflight.

    Checks only what this software can check: configuration, storage, telemetry
    and model provenance. It is NOT an aviation preflight and does not substitute
    for the regulatory checklist in docs/briefs/04-compliance-checklist.md --
    airspace, NOTAMs, certification, weather and label conditions are all outside
    what a Python process can verify.
    """
    cfg = _load_config(args.config)
    failures: list[str] = []
    warnings: list[str] = []

    spool_dir = Path(cfg.spool.spool_dir)
    try:
        spool_dir.mkdir(parents=True, exist_ok=True)
        probe = spool_dir / ".preflight"
        probe.write_bytes(b"ok")
        probe.unlink()
        print(f"  [ok]   spool writable: {spool_dir}")
    except OSError as exc:
        failures.append(f"spool directory not writable: {exc}")

    try:
        import shutil

        free = shutil.disk_usage(spool_dir).free
        gb = free / 1e9
        if gb < 8:
            warnings.append(f"only {gb:.1f} GB free on the spool volume")
        print(f"  [ok]   free space: {gb:.1f} GB")
    except OSError as exc:
        warnings.append(f"could not determine free space: {exc}")

    if cfg.qa.require_rtk_fixed:
        print("  [ok]   QA requires RTK fixed -- confirm base station and correction link are up")

    if cfg.inference.enabled:
        engine = build_engine(cfg.inference)
        if engine is None:
            failures.append("inference enabled but no engine could be built")
        else:
            print(f"  [ok]   model: {engine.metadata.name} v{engine.metadata.version}")
            if not engine.metadata.validated_locally:
                warnings.append(
                    "model is NOT locally validated -- output is decision support only "
                    "and must not drive treatment"
                )
    else:
        print("  [ok]   inference disabled")

    if not args.simulate:
        try:
            telemetry = build_telemetry_source(cfg.mavlink, simulated=False)
            telemetry.start()
            # start() returns on the first heartbeat; position arrives on its
            # own stream afterwards. Reading once, immediately, nearly always
            # warned "no 3D position" on a perfectly healthy link.
            deadline = time.monotonic() + 5.0
            snap = telemetry.snapshot()
            while not snap.has_position and time.monotonic() < deadline:
                time.sleep(0.2)
                snap = telemetry.snapshot()
            telemetry.stop()
            if not snap.has_position:
                warnings.append(f"no 3D position yet (fix: {snap.fix_name})")
            else:
                print(f"  [ok]   telemetry: {snap.fix_name}, {snap.satellites} sats, HDOP {snap.hdop:.2f}")
        except Exception as exc:
            failures.append(f"telemetry link failed: {exc}")

    print()
    for w in warnings:
        print(f"  WARN   {w}")
    for f in failures:
        print(f"  FAIL   {f}")

    if failures:
        print("\nPreflight FAILED.")
        return 1
    print("\nEdge preflight passed." + (" Review warnings." if warnings else ""))
    print("This is not an aviation preflight. See docs/briefs/04-compliance-checklist.md.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agri-edge",
        description="Companion-computer edge pipeline for agricultural RPAS.",
    )
    parser.add_argument("-c", "--config", help="Path to a YAML config file.")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p_fly = sub.add_parser("fly", help="Run the capture pipeline.")
    p_fly.add_argument("--simulate", action="store_true", help="Use simulated camera and telemetry.")
    p_fly.add_argument(
        "--sitl", action="store_true",
        help="Simulated camera, REAL telemetry. For ArduPilot SITL or "
             "workstation/fake_autopilot.py -- see config/sitl.yaml.",
    )
    p_fly.add_argument(
        "--bench", action="store_true",
        help="Real camera, synthetic telemetry. Bench testing with no autopilot attached.",
    )
    p_fly.add_argument("--duration", type=float, help="Run for this many seconds.")
    p_fly.add_argument("--frames", type=int, help="Stop after this many frames.")
    p_fly.add_argument("--bands", help="Comma-separated band names.")
    p_fly.set_defaults(func=cmd_fly)

    p_spool = sub.add_parser("spool", help="Inspect, export or upload the spool.")
    p_spool.add_argument("--list", type=int, metavar="N", help="List the first N pending entries.")
    p_spool.add_argument("--export", metavar="DIR", help="Copy pending entries to DIR.")
    p_spool.add_argument("--upload", action="store_true",
                         help="Upload pending entries to spool.upload_endpoint.")
    p_spool.add_argument(
        "--upload-to", choices=["endpoint", "farmos"], default="endpoint",
        help="Where --upload sends. 'farmos' creates observation logs in farmOS "
             "(URL from config, credentials from the environment).",
    )
    p_spool.add_argument("--upload-mode", choices=["metadata", "full"], default=None,
                         help="metadata = sidecars only (kB); full = also images (MB).")
    p_spool.add_argument("--limit-uploads", type=int, default=None, metavar="N",
                         help="Upload at most N entries this pass.")
    p_spool.set_defaults(func=cmd_spool)

    p_idx = sub.add_parser("indices", help="Show which indices a band set supports.")
    p_idx.add_argument("bands", help="Comma-separated band names, e.g. red,green,blue,nir")
    p_idx.set_defaults(func=cmd_indices)

    p_pre = sub.add_parser("preflight", help="Check the edge system before a flight.")
    p_pre.add_argument("--simulate", action="store_true", help="Skip the live telemetry check.")
    p_pre.set_defaults(func=cmd_preflight)

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    if args.command == "fly" and args.duration is None and args.frames is None:
        args.duration = 30.0

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
