"""Configuration for the edge pipeline.

Every threshold that decides whether an image is kept, flagged or discarded lives
here rather than being buried in the check that applies it. Field crews change
these; they should not have to read Python to do it.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import yaml


@dataclass
class CameraGeometry:
    """The lens, so a detection's pixels can become a place on the ground.

    Defaults are the Pi Camera Module 3 (IMX708). Change them for a different
    camera -- these come off a datasheet, and a wrong focal length scales every
    ground position by a constant factor, which looks like a GNSS offset.

    `yaw_offset_deg` is the camera's rotation on the airframe, clockwise from
    "top of image points at the nose". A camera bolted on sideways needs 90 here,
    and getting it wrong rotates an entire flight.

    `terrain_uncertainty_m` feeds the reported per-detection error budget: how
    far the real ground may sit from the flat plane the projection assumes.
    """

    sensor_width_mm: float = 7.4
    focal_length_mm: float = 4.74
    yaw_offset_deg: float = 0.0
    terrain_uncertainty_m: float = 2.0
    # Off. Georeferencing needs a real AGL altitude and a real heading; on a
    # bench with neither, every position would be fiction. Turn it on when the
    # aircraft supplies both.
    enabled: bool = False


@dataclass
class QAConfig:
    """Thresholds for edge image quality assessment.

    Defaults are deliberately conservative. An image that fails QA is not deleted
    -- it is flagged and spooled at low priority, because a blurry frame over an
    anomaly is still evidence that something is there.
    """

    # Variance of the Laplacian. Below this, the frame is considered blurred.
    # Scale is sensor- and scene-dependent: calibrate on a known-sharp flight
    # before trusting the default.
    blur_threshold: float = 100.0

    # Fraction of pixels at the extremes before the frame is called clipped.
    overexposed_fraction: float = 0.05
    underexposed_fraction: float = 0.05
    saturation_high: int = 250
    saturation_low: int = 5

    # GNSS quality gate. RTK fixed = 6 in the MAVLink GPS_FIX_TYPE enum.
    min_fix_type: int = 3          # 3D fix minimum
    require_rtk_fixed: bool = False
    max_hdop: float = 2.0
    min_satellites: int = 8

    # Multispectral completeness: every declared band must be present.
    required_bands: list[str] = field(default_factory=list)


@dataclass
class CaptureConfig:
    resolution: tuple[int, int] = (4056, 3040)
    interval_s: float = 2.0
    output_dir: Path = Path("./data/raw")
    # Refuse to capture if the autopilot has not reported a position this recently.
    max_telemetry_age_s: float = 2.0

    # Picamera2's "RGB888" actually delivers B, G, R in numpy order. We swap so
    # the model receives real RGB. Verify once on hardware with
    # Picamera2Camera.verify_channel_order(); flip this only if that says to.
    swap_red_blue: bool = True

    # Video configuration streams at a steady rate; still configuration
    # reconfigures the sensor per shot and costs hundreds of ms per frame.
    video_mode: bool = True

    # Ambient temperature/humidity/pressure: none | simulated | bme280.
    # Not optional for spray work -- docs/briefs/04-compliance-checklist.md
    # requires temperature and humidity on every application record.
    # Measures AIR, not soil moisture.
    environment_sensor: str = "none"
    environment_i2c_address: int = 0x76


@dataclass
class InferenceConfig:
    enabled: bool = False
    model_path: Path | None = None
    backend: str = "simulated"      # simulated | onnx | hailo
    confidence_threshold: float = 0.5
    input_size: tuple[int, int] = (640, 640)
    class_names: list[str] = field(default_factory=list)

    # Report every detection under this single label, keeping the predicted class
    # in the sidecar as `source_label`. Leave null to report the model's own
    # classes.
    #
    # This exists because a detector can localise well while classifying badly.
    # `imageweeds_yolox_s` puts 76% of its predictions in one of five species
    # classes, but its boxes are right: collapsing to `weed` takes measured
    # AP@.50 from 0.246 to 0.520. Reporting a species we cannot support is worse
    # than reporting "a weed", because the species is what picks the chemical.
    collapse_labels_to: str | None = None

    # --- green-on-brown backend (backend: greenonbrown) -------------------
    # Classical vegetation-index thresholding, ported from OpenWeedLocator (MIT).
    # No model, no training set, no accelerator -- and no ability to tell a weed
    # from a crop plant. Only meaningful where green implies weed: fallow ground,
    # stubble, pre-emergence. See inference/greenonbrown.py.
    #
    # `class_names` supplies the label; keep it [vegetation] unless you are
    # deliberately asserting that green means weed on this ground.
    # `confidence_threshold` applies -- and MIND THE SCALE. For a YOLOX model it
    # is a probability, where 0.30 is a permissive scouting threshold. Here it is
    # index strength, (mean_index - green_index_min) / (green_index_max -
    # green_index_min), and typical field vegetation lands around 0.10-0.20. So
    # the 0.30 that is permissive for a model silently discards EVERYTHING here.
    # Set it explicitly when switching backends; the two numbers are not
    # comparable and sharing one field is the trap.
    green_index: str = "exg"              # exg | exgr | nexg | maxg
    green_threshold_mode: str = "absolute"  # absolute (explainable) | adaptive (OWL's)
    green_index_min: float = 30.0
    # 255, not OpenWeedLocator's 250: the indices saturate at 255, so pure
    # sunlit vegetation lands exactly there and a 250 ceiling silently discards
    # the greenest pixels in the frame.
    green_index_max: float = 255.0
    green_min_area_px: int = 100
    green_max_detections: int = 50

    # Tiled inference: slice the frame into native-resolution tiles instead of
    # letterboxing the whole thing down to 640x640.
    #
    # Not an optimisation -- for small targets it is the difference between
    # detectable and invisible. Downscaling a 4056-wide frame to 640 discards
    # 6.3x of linear resolution, which puts a 3 cm weed seedling below one pixel
    # at any useful altitude. Run training/gsd_calculator.py for your camera and
    # target size before deciding.
    #
    # Costs one inference per tile. Measure with training/benchmark.py.
    tiled: bool = False
    tile_size: int = 640
    tile_overlap: float = 0.2       # must exceed the largest target's share of a tile
    max_tiles: int = 64             # guard against silently running 400 inferences/frame


@dataclass
class SpoolConfig:
    """Store-and-forward. Rural Canadian connectivity cannot be assumed."""

    spool_dir: Path = Path("./data/spool")
    max_bytes: int = 64 * 1024 * 1024 * 1024   # 64 GB

    # Leave null to run fully offline -- the normal case. When set, `agri-edge
    # spool --upload` POSTs to <endpoint>/frames.
    upload_endpoint: str | None = None
    upload_timeout_s: float = 20.0
    upload_api_key: str | None = None

    # "metadata" sends only the JSON sidecar (telemetry, QA, indices, detections)
    # -- kilobytes, and the part that carries the decision. "full" also sends the
    # image, which is megabytes. On a rural link, metadata-first is what makes
    # the uplink usable at all.
    upload_mode: str = "metadata"


@dataclass
class FarmOSSettings:
    """Where the farm record system lives. Credentials are NOT here.

    farmOS uses OAuth2, and this file is committed to git. The username,
    password and client secret are read from the environment at run time by
    `FarmOSConfig.from_env` -- a leaked client secret is not fixed by rotating
    one key, so it must never enter the repository in the first place.
    """

    url: str | None = None
    # farmOS land asset this site maps to. Optional: without it the observation
    # logs are still created, just not attached to a field.
    land_asset_id: str = ""
    timeout_s: float = 20.0


@dataclass
class MavlinkConfig:
    # Read-only by design. See telemetry/mavlink_link.py.
    connection: str = "udpin:0.0.0.0:14550"
    source_system: int = 200         # Distinct from the autopilot and the GCS.
    heartbeat_timeout_s: float = 5.0


@dataclass
class Config:
    site: str = "unnamed-site"
    field_id: str = "unnamed-field"
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    camera_geometry: CameraGeometry = field(default_factory=CameraGeometry)
    qa: QAConfig = field(default_factory=QAConfig)
    inference: InferenceConfig = field(default_factory=InferenceConfig)
    spool: SpoolConfig = field(default_factory=SpoolConfig)
    farmos: FarmOSSettings = field(default_factory=FarmOSSettings)
    mavlink: MavlinkConfig = field(default_factory=MavlinkConfig)

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Config":
        def sub(kls, key):
            data = dict(raw.get(key, {}) or {})
            unknown = set(data) - set(kls.__dataclass_fields__)
            if unknown:
                raise ValueError(
                    f"Unknown key(s) under '{key}': {', '.join(sorted(unknown))}. "
                    "A typo in a threshold silently disables the check it belongs to, "
                    "so unrecognised keys are rejected rather than ignored."
                )
            for f in kls.__dataclass_fields__.values():
                if f.name not in data:
                    continue
                value = data[f.name]
                # `null` in YAML stays None -- an optional path is legitimately unset.
                if value is None:
                    continue
                type_str = str(f.type)
                if "Path" in type_str:
                    data[f.name] = Path(value)
                elif "tuple" in type_str and isinstance(value, list):
                    data[f.name] = tuple(value)
            return kls(**data)

        return cls(
            site=raw.get("site", "unnamed-site"),
            field_id=raw.get("field_id", "unnamed-field"),
            capture=sub(CaptureConfig, "capture"),
            camera_geometry=sub(CameraGeometry, "camera_geometry"),
            qa=sub(QAConfig, "qa"),
            inference=sub(InferenceConfig, "inference"),
            spool=sub(SpoolConfig, "spool"),
            farmos=sub(FarmOSSettings, "farmos"),
            mavlink=sub(MavlinkConfig, "mavlink"),
        )

    def to_dict(self) -> dict[str, Any]:
        def convert(o):
            if isinstance(o, Path):
                return str(o)
            if isinstance(o, dict):
                return {k: convert(v) for k, v in o.items()}
            if isinstance(o, (list, tuple)):
                return [convert(v) for v in o]
            return o

        return convert(asdict(self))
