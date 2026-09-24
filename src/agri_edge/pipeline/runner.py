"""The capture -> QA -> inference -> spool loop.

This is the whole edge pipeline in one place. What belongs here is what the report
calls edge work: image quality checking, data-integrity checks, telemetry fusion,
simple detection, and selective spooling. What does not belong here is
photogrammetry -- orthomosaics, dense point clouds and DSMs go on a workstation
with 32-64 GB of RAM and a real GPU, not on an airborne Pi.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from ..capture.camera import Camera, Frame
from ..config import Config
from ..geo.indices import BandStack, available_indices, compute
from ..inference.engine import InferenceEngine
from ..qa.checks import QAReport, Severity, run_qa
from ..store.spool import Priority, Spool
from ..telemetry.mavlink_link import TelemetrySource

log = logging.getLogger("agri_edge.pipeline")


@dataclass
class RunStats:
    captured: int = 0
    passed_qa: int = 0
    failed_qa: int = 0
    skipped_no_telemetry: int = 0
    detections: int = 0
    spooled: int = 0
    inference_errors: int = 0
    qa_failure_counts: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "captured": self.captured,
            "passed_qa": self.passed_qa,
            "failed_qa": self.failed_qa,
            "skipped_no_telemetry": self.skipped_no_telemetry,
            "detections": self.detections,
            "spooled": self.spooled,
            "inference_errors": self.inference_errors,
            "qa_failure_counts": dict(self.qa_failure_counts),
        }


class Pipeline:
    def __init__(
        self,
        cfg: Config,
        camera: Camera,
        telemetry: TelemetrySource,
        spool: Spool,
        engine: InferenceEngine | None = None,
        environment=None,
    ):
        self.cfg = cfg
        self.camera = camera
        self.telemetry = telemetry
        self.spool = spool
        self.engine = engine
        # Optional. Environmental data is valuable -- and required on spray
        # records -- but never flight-critical, so its absence must not stop a run.
        self.environment = environment
        self.stats = RunStats()

    def __enter__(self) -> "Pipeline":
        self.telemetry.start()
        self.camera.start()
        return self

    def __exit__(self, *exc) -> None:
        try:
            self.camera.stop()
            self.telemetry.stop()
        finally:
            # Release the accelerator too. The Hailo VDevice is exclusive: a
            # process that never releases it blocks the next run from opening it.
            if self.engine is not None:
                self.engine.close()

    # -- one frame -------------------------------------------------------------

    def process_once(self) -> dict | None:
        """Capture and process a single frame.

        Returns the frame's metadata record, or None if capture was skipped.
        """
        telem = self.telemetry.snapshot()

        # Refuse to capture without fresh telemetry. An image with no trustworthy
        # position cannot support the temporal comparison that repeated monitoring
        # exists for, and an unlocatable frame costs storage for nothing.
        #
        # Position and attitude are checked separately: the georeference needs
        # both, and one stream can stall while the other keeps arriving.
        max_age = self.cfg.capture.max_telemetry_age_s
        age = telem.age_s()
        if telem.timestamp == 0.0 or age > max_age:
            self.stats.skipped_no_telemetry += 1
            log.warning("Skipping capture: position stale (%.1f s old).", age)
            return None
        att_age = telem.attitude_age_s()
        if att_age is not None and att_age > max_age:
            self.stats.skipped_no_telemetry += 1
            log.warning("Skipping capture: attitude stale (%.1f s old).", att_age)
            return None

        frame = self.camera.capture(telem)
        self.stats.captured += 1

        qa = run_qa(frame.image, telem, self.cfg.qa, bands_present=frame.bands)
        if qa.passed:
            self.stats.passed_qa += 1
        else:
            self.stats.failed_qa += 1
            for f in qa.failures:
                self.stats.qa_failure_counts[f.name] = self.stats.qa_failure_counts.get(f.name, 0) + 1

        # The frame is spooled whatever the detector does. Inference used to run
        # before spool.add with nothing around it, so one exception from the
        # engine -- a driver hiccup, a bad tensor shape -- lost the imagery too,
        # and imagery is the one thing that can be re-processed later.
        inference_error = None
        try:
            detections = self._infer(frame, qa)
        except Exception as exc:  # noqa: BLE001 - recorded, and the frame is kept
            self.stats.inference_errors += 1
            inference_error = f"{type(exc).__name__}: {exc}"
            log.exception("Inference failed on frame %s; spooling it without detections.",
                          frame.sequence)
            detections = []
        indices = self._index_summaries(frame)
        priority = self._priority(qa, detections)

        metadata = self._metadata(frame, qa, detections, indices, priority)
        metadata["inference_error"] = inference_error
        self.spool.add(
            image=frame.image,
            metadata=metadata,
            priority=priority,
            site=self.cfg.site,
            field_id=self.cfg.field_id,
            sequence=frame.sequence,
        )
        self.stats.spooled += 1
        return metadata

    def _infer(self, frame: Frame, qa: QAReport) -> list:
        """Run detection, but not on frames that failed QA.

        Inference on a blurred or clipped frame produces confident nonsense, and
        confident nonsense is worse than no output: it gets believed.
        """
        if self.engine is None or qa.severity is Severity.FAIL:
            return []
        dets = self.engine.infer(frame.image)
        keep = [d for d in dets if d.confidence >= self.cfg.inference.confidence_threshold]
        self.stats.detections += len(keep)
        self._georeference(keep, frame)
        return keep

    def _georeference(self, detections: list, frame: Frame) -> None:
        """Give each detection a place on the ground, when we honestly can.

        Off by default and skipped without telemetry: a position derived from a
        missing altitude or an unknown heading is fiction, and fiction with seven
        decimal places is worse than an empty field.
        """
        geom = self.cfg.camera_geometry
        if not geom.enabled or not detections:
            return
        from ..geo.georeference import CameraIntrinsics, CameraMount, georeference_detections

        h, w = frame.image.shape[:2]
        intrinsics = CameraIntrinsics(
            sensor_width_mm=geom.sensor_width_mm,
            focal_length_mm=geom.focal_length_mm,
            # The ACTUAL frame size, not the configured one. Binning or a cropped
            # sensor mode changes the pixel count, and a stale value would scale
            # every position.
            image_width_px=w,
            image_height_px=h,
        )
        georeference_detections(
            detections,
            intrinsics,
            frame.telemetry,
            mount=CameraMount(yaw_offset_deg=geom.yaw_offset_deg),
            terrain_uncertainty_m=geom.terrain_uncertainty_m,
        )
        self._check_treatment_zone(detections)

    def _check_treatment_zone(self, detections: list) -> None:
        """Mark which detections sit inside the treatment boundary.

        Only detections with a position can be judged. One without stays None --
        an unasked question, which `may_drive_treatment` treats as "no".
        """
        fence = self._treatment_fence()
        if fence is None:
            return
        poly, holes, origin = fence
        from ..geo.geofence import TreatmentGeofence, project_to_local

        gf = TreatmentGeofence(poly, self.cfg.treatment_zone.buffer_m, holes_m=holes)
        for d in detections:
            if not d.has_position:
                continue
            east, north = project_to_local([d.lat], [d.lon], origin)[0]
            # The georeference's own uncertainty comes out of the buffer.
            d.in_treatment_zone = gf.may_treat(
                (east, north), position_error_m=float(d.position_error_m or 0.0)
            )

    def _treatment_fence(self):
        """Load the boundary once and cache it. None when none is configured.

        A boundary that fails to load is logged and treated as absent, which
        means nothing becomes treatable -- the safe direction. Refusing to fly
        over a malformed GeoJSON would be worse: the imagery is still worth
        having, and only the treatment authorisation depends on this.
        """
        if hasattr(self, "_fence_cache"):
            return self._fence_cache
        self._fence_cache = None
        path = self.cfg.treatment_zone.boundary_geojson
        if path is not None:
            from ..geo.geofence import load_treatment_boundary

            try:
                self._fence_cache = load_treatment_boundary(path)
            except Exception as exc:
                log.error(
                    "Treatment boundary %s could not be loaded (%s). No detection "
                    "will be marked treatable this flight.", path, exc,
                )
        return self._fence_cache

    def _index_summaries(self, frame: Frame) -> dict:
        """Compute whichever vegetation indices this payload supports.

        Only summary statistics are spooled, not the full index rasters -- the
        rasters are cheap to recompute on the ground from the preserved bands, and
        the summary is what a store-and-forward link should be spending bytes on.
        """
        try:
            stack = BandStack(frame.image, frame.bands)
        except ValueError as exc:
            log.debug("Skipping indices: %s", exc)
            return {}

        out = {}
        for name in available_indices(stack):
            try:
                # calibrated=False: these are digital numbers, not reflectance.
                # Nothing downstream may compare them across dates.
                out[name] = compute(stack, name, calibrated=False).summary()
            except KeyError:
                continue
        return out

    def _environment(self) -> dict | None:
        """Sample ambient conditions, if a sensor is fitted.

        Never raises: a failed I2C read must not cost the flight its imagery.
        """
        if self.environment is None:
            return None
        try:
            return self.environment.read().to_dict()
        except Exception:
            log.warning("Environmental sensor read failed; frame recorded without it.")
            return None

    def _priority(self, qa: QAReport, detections: list) -> Priority:
        if qa.severity is Severity.FAIL:
            return Priority.DEGRADED
        if detections:
            return Priority.ANOMALY
        return Priority.NORMAL

    def _metadata(self, frame: Frame, qa: QAReport, detections, indices, priority) -> dict:
        """Build the provenance sidecar.

        Every derived product must be able to point back to its raw imagery,
        flight, calibration state, software version and CRS. Without that, nobody
        can explain why an NDVI anomaly moved between two flights.
        """
        t = frame.telemetry
        return {
            "schema": "agri-edge/frame/1",
            "site": self.cfg.site,
            "field_id": self.cfg.field_id,
            "sequence": frame.sequence,
            "captured_at": frame.captured_at,
            "bands": frame.bands,
            "image_shape": list(frame.image.shape),
            "image_dtype": str(frame.image.dtype),
            "crs": "EPSG:4326",
            "telemetry": {
                "lat": t.lat,
                "lon": t.lon,
                "alt_msl_m": t.alt_msl_m,
                "alt_rel_m": t.alt_rel_m,
                "roll_deg": t.roll_deg,
                "pitch_deg": t.pitch_deg,
                "yaw_deg": t.yaw_deg,
                "groundspeed_ms": t.groundspeed_ms,
                "fix_type": t.fix_type,
                "fix_name": t.fix_name,
                "satellites": t.satellites,
                "hdop": t.hdop,
                "battery_pct": t.battery_pct,
            },
            "qa": qa.to_dict(),
            "indices": indices,
            # Ambient conditions at capture. Required on spray application
            # records (temperature and humidity), and what makes cross-date
            # thermal and multispectral comparison checkable rather than
            # guessed. Measures air, never soil moisture.
            "environment": self._environment(),
            "detections": [d.to_dict() for d in detections],
            "model": (
                {
                    "name": self.engine.metadata.name,
                    "version": self.engine.metadata.version,
                    "validated_locally": self.engine.metadata.validated_locally,
                    "trained_on": self.engine.metadata.trained_on,
                }
                if self.engine is not None
                else None
            ),
            "priority": int(priority),
            # Explicit, because the whole safety argument rests on it.
            "decision_support_only": not any(d.may_drive_treatment for d in detections),
        }

    # -- loop ------------------------------------------------------------------

    def run(self, duration_s: float | None = None, max_frames: int | None = None) -> RunStats:
        start = time.time()
        while True:
            if max_frames is not None and self.stats.captured >= max_frames:
                break
            if duration_s is not None and (time.time() - start) >= duration_s:
                break

            loop_start = time.time()
            try:
                self.process_once()
            except Exception:
                # A single bad frame must never end the flight's data collection.
                # Log it and carry on; the autopilot is flying the aircraft
                # regardless of what happens in this process.
                log.exception("Frame processing failed; continuing.")

            elapsed = time.time() - loop_start
            sleep_for = self.cfg.capture.interval_s - elapsed
            if sleep_for > 0:
                time.sleep(sleep_for)
            elif self.stats.captured % 10 == 0:
                log.warning(
                    "Processing (%.2f s) is slower than the %.2f s capture interval.",
                    elapsed,
                    self.cfg.capture.interval_s,
                )
        return self.stats
