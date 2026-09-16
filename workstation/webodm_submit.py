"""Turn a flight's spool into an orthomosaic, DSM and 3D model via WebODM.

Runs on the workstation, never on the aircraft. Photogrammetry wants tens of
gigabytes of RAM and a real GPU; a Pi at 100 m AGL is the wrong machine and the
wrong moment.

THE TRAP THIS EXISTS TO AVOID
-----------------------------
Spooled frames are `.npy` plus a JSON sidecar. **They carry no EXIF at all.**
WebODM reads position from EXIF, so handing it raw exports produces a confident,
completely wrong reconstruction — or none. Every frame here is converted to JPEG
with GPS EXIF written from its own sidecar telemetry before anything is
submitted. That conversion is the whole point of this script; the HTTP part is
incidental.

A second guard: frames whose GNSS QA check failed are **refused by default**.
Feeding known-bad positions into a bundle adjustment does not average out, it
drags the whole model. `--include-failed-gnss` overrides it, loudly.

LICENCE
-------
WebODM is **AGPL-3.0** and is run unmodified as a separate Docker service,
reached over HTTP. None of its code is here. Section 13 obliges you to offer
*modified* source to users who interact with it over a network: running it
internally triggers nothing, and if you ever expose its interface to customers,
the obligation is satisfied by pointing at upstream — because it is unmodified.
Patch it and that stops being true. See NOTICE.md.

SETUP
-----
    git clone https://github.com/OpenDroneMap/WebODM vendor/WebODM
    cd vendor/WebODM && ./webodm.sh start        # needs Docker

Then:
    python workstation/webodm_submit.py --spool data/spool --out runs/ortho
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

# Deliberately module-level: this is a workstation tool, not Pi runtime, so the
# heavy imports are fine here and `tests/test_runtime_deps.py` never sees them.
import numpy as np
from PIL import Image
from PIL.TiffImagePlugin import IFDRational


# ---------------------------------------------------------------------------
# EXIF
# ---------------------------------------------------------------------------

GPS_IFD = 0x8825


def _to_dms(degrees: float) -> tuple:
    """Decimal degrees -> EXIF (deg, min, sec) rationals, sign handled by the ref."""
    d_abs = abs(degrees)
    d = int(d_abs)
    m = int((d_abs - d) * 60)
    s = (d_abs - d - m / 60) * 3600
    return (
        IFDRational(d, 1),
        IFDRational(m, 1),
        # 1e-4 arcsec is about 3 mm -- far finer than any GNSS this will see, so
        # the quantisation here is never the limiting error.
        IFDRational(int(round(s * 10000)), 10000),
    )


def write_geotagged_jpeg(
    image: np.ndarray, lat: float, lon: float, alt_m: float, dest: Path, quality: int = 92
) -> Path:
    """Write an RGB array to JPEG carrying GPS EXIF. This is the load-bearing bit.

    Altitude is stored as metres above sea level with `GPSAltitudeRef = 0`, so
    pass MSL altitude, not height above the launch point. Handing WebODM relative
    altitude makes every reconstruction sit at the wrong elevation, which looks
    plausible until it is compared against anything else.
    """
    arr = np.asarray(image)
    if arr.ndim == 3 and arr.shape[2] > 3:
        arr = arr[..., :3]          # drop NIR/red-edge; photogrammetry wants RGB
    if arr.dtype != np.uint8:
        # Multispectral frames are often 16-bit. Scale by the actual range rather
        # than assuming 0-65535, or a dim frame becomes black.
        a = arr.astype(np.float64)
        lo, hi = float(a.min()), float(a.max())
        arr = np.zeros(a.shape, np.uint8) if hi <= lo else \
            ((a - lo) / (hi - lo) * 255.0).astype(np.uint8)

    img = Image.fromarray(arr, mode="RGB" if arr.ndim == 3 else "L").convert("RGB")
    exif = img.getexif()
    gps = exif.get_ifd(GPS_IFD)
    gps.update({
        1: "N" if lat >= 0 else "S",
        2: _to_dms(lat),
        3: "E" if lon >= 0 else "W",
        4: _to_dms(lon),
        5: 0,                                    # 0 = above sea level
        6: IFDRational(int(round(abs(alt_m) * 100)), 100),
    })
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, format="JPEG", quality=quality, exif=exif)
    return dest


def read_gps_exif(path: Path) -> tuple[float, float, float] | None:
    """Read back (lat, lon, alt). Used to verify what was written, not guessed."""
    gps = Image.open(path).getexif().get_ifd(GPS_IFD)
    if not gps or 2 not in gps or 4 not in gps:
        return None

    def deg(v, ref):
        out = float(v[0]) + float(v[1]) / 60.0 + float(v[2]) / 3600.0
        return -out if ref in ("S", "W") else out

    return deg(gps[2], gps.get(1, "N")), deg(gps[4], gps.get(3, "E")), float(gps.get(6, 0))


# ---------------------------------------------------------------------------
# Spool -> images
# ---------------------------------------------------------------------------


@dataclass
class PrepResult:
    written: list[Path] = field(default_factory=list)
    skipped_no_position: int = 0
    skipped_failed_gnss: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "written": len(self.written),
            "skipped_no_position": self.skipped_no_position,
            "skipped_failed_gnss": self.skipped_failed_gnss,
            "errors": self.errors[:5],
        }


def _gnss_failed(meta: dict) -> bool:
    for check in (meta.get("qa", {}) or {}).get("checks", []) or []:
        if check.get("name") == "gnss" and check.get("severity") == "fail":
            return True
    return False


def prepare_images(
    spool_dir: Path, out_dir: Path, include_failed_gnss: bool = False
) -> PrepResult:
    """Convert every spooled frame into a geotagged JPEG ready for WebODM."""
    result = PrepResult()
    out_dir.mkdir(parents=True, exist_ok=True)

    for meta_path in sorted(spool_dir.glob("*.json")):
        if meta_path.stem == "index":
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            telem = meta.get("telemetry", {}) or {}
            lat, lon = telem.get("lat"), telem.get("lon")
            if lat is None or lon is None:
                result.skipped_no_position += 1
                continue
            if _gnss_failed(meta) and not include_failed_gnss:
                # Bad positions do not average out in a bundle adjustment; they
                # drag the whole reconstruction.
                result.skipped_failed_gnss += 1
                continue

            npy = meta_path.with_suffix(".npy")
            if not npy.exists():
                result.errors.append(f"{meta_path.name}: image payload missing")
                continue

            alt = telem.get("alt_msl_m")
            if alt is None:
                alt = telem.get("alt_rel_m") or 0.0
            result.written.append(
                write_geotagged_jpeg(np.load(npy), float(lat), float(lon), float(alt),
                                     out_dir / f"{meta_path.stem}.jpg")
            )
        except Exception as exc:
            result.errors.append(f"{meta_path.name}: {exc}")
    return result


# ---------------------------------------------------------------------------
# WebODM
# ---------------------------------------------------------------------------


class WebODMClient:
    """Just enough of WebODM's REST API to submit a task and collect the results."""

    def __init__(self, url: str, username: str, password: str, timeout_s: float = 60.0):
        self.base = url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout_s = timeout_s
        self._token: str | None = None

    def authenticate(self) -> None:
        data = urllib.parse.urlencode(
            {"username": self.username, "password": self.password}
        ).encode()
        req = urllib.request.Request(
            f"{self.base}/api/token-auth/", data=data, method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            self._token = json.loads(resp.read().decode()).get("token")
        if not self._token:
            raise RuntimeError("WebODM returned no token.")

    def _auth_header(self) -> dict:
        if not self._token:
            raise RuntimeError("Call authenticate() first.")
        return {"Authorization": f"JWT {self._token}"}

    def create_project(self, name: str) -> int:
        req = urllib.request.Request(
            f"{self.base}/api/projects/",
            data=json.dumps({"name": name}).encode(),
            method="POST",
            headers={**self._auth_header(), "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            return int(json.loads(resp.read().decode())["id"])

    def create_task(self, project_id: int, images: list[Path], name: str) -> int:
        """Upload the images as one task. Multipart, hand-rolled as in uploader.py."""
        boundary = "----agriedge-webodm-boundary"
        parts: list[bytes] = []

        def field_part(key: str, value: str) -> None:
            parts.append(
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n"
                f"{value}\r\n".encode()
            )

        field_part("name", name)
        # Defaults are reasonable; this only pins what matters for agriculture.
        field_part("options", json.dumps([
            {"name": "dsm", "value": True},
            {"name": "orthophoto-resolution", "value": 2.0},
            {"name": "auto-boundary", "value": True},
        ]))
        for p in images:
            parts.append(
                f"--{boundary}\r\nContent-Disposition: form-data; "
                f"name=\"images\"; filename=\"{p.name}\"\r\n"
                f"Content-Type: image/jpeg\r\n\r\n".encode()
            )
            parts.append(p.read_bytes())
            parts.append(b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        body = b"".join(parts)

        req = urllib.request.Request(
            f"{self.base}/api/projects/{project_id}/tasks/",
            data=body, method="POST",
            headers={
                **self._auth_header(),
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )
        with urllib.request.urlopen(req, timeout=self.timeout_s * 10) as resp:
            return int(json.loads(resp.read().decode())["id"])

    def task_status(self, project_id: int, task_id: int) -> dict:
        req = urllib.request.Request(
            f"{self.base}/api/projects/{project_id}/tasks/{task_id}/",
            headers=self._auth_header(),
        )
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            return json.loads(resp.read().decode())

    def download(self, project_id: int, task_id: int, asset: str, dest: Path) -> Path:
        req = urllib.request.Request(
            f"{self.base}/api/projects/{project_id}/tasks/{task_id}/download/{asset}",
            headers=self._auth_header(),
        )
        dest.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(req, timeout=self.timeout_s * 10) as resp:
            dest.write_bytes(resp.read())
        return dest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spool", type=Path, default=Path("data/spool"))
    ap.add_argument("--out", type=Path, default=Path("runs/ortho"))
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--username", default="admin")
    ap.add_argument("--password", default="admin")
    ap.add_argument("--project", default=None, help="Project name (default: from the spool).")
    ap.add_argument("--include-failed-gnss", action="store_true",
                    help="Submit frames whose GNSS check FAILED. Bad positions drag "
                         "the whole bundle adjustment -- only do this knowingly.")
    ap.add_argument("--prepare-only", action="store_true",
                    help="Write geotagged JPEGs and stop. Useful without Docker.")
    ap.add_argument("--poll-s", type=float, default=15.0)
    args = ap.parse_args()

    if not args.spool.exists():
        print(f"No spool at {args.spool}", file=sys.stderr)
        return 1

    images_dir = args.out / "images"
    print(f"Converting {args.spool} -> geotagged JPEG in {images_dir}")
    prep = prepare_images(args.spool, images_dir, args.include_failed_gnss)
    print(json.dumps(prep.as_dict(), indent=2))

    if prep.skipped_failed_gnss:
        print(f"\n  {prep.skipped_failed_gnss} frames skipped: their GNSS check FAILED.")
        print("  Their positions are untrustworthy and would drag the reconstruction.")
        print("  Use --include-failed-gnss to submit them anyway.")
    if not prep.written:
        print("\nNothing to submit.", file=sys.stderr)
        return 1

    # Verify what was written rather than trusting the write. A silently
    # ungeotagged set is the single most expensive failure in this pipeline.
    sample = read_gps_exif(prep.written[0])
    if sample is None:
        print("\nERROR: the first output JPEG has no GPS EXIF. Refusing to submit.",
              file=sys.stderr)
        return 1
    print(f"\nEXIF verified on {prep.written[0].name}: "
          f"lat {sample[0]:.6f}, lon {sample[1]:.6f}, alt {sample[2]:.1f} m")

    if args.prepare_only:
        print("\n--prepare-only: stopping before submission.")
        return 0

    name = args.project or f"agri-edge {args.spool.name}"
    client = WebODMClient(args.url, args.username, args.password)
    try:
        client.authenticate()
        project_id = client.create_project(name)
        task_id = client.create_task(project_id, prep.written, name)
    except (urllib.error.URLError, OSError) as exc:
        print(f"\nCould not reach WebODM at {args.url}: {exc}", file=sys.stderr)
        print("Start it with: cd vendor/WebODM && ./webodm.sh start   (needs Docker)",
              file=sys.stderr)
        print(f"The geotagged images are ready in {images_dir} regardless.", file=sys.stderr)
        return 1

    print(f"\nSubmitted project {project_id}, task {task_id}. Polling...")
    while True:
        status = client.task_status(project_id, task_id)
        code = status.get("status")
        print(f"  status={code} progress={status.get('running_progress', 0):.0%}")
        if code == 40:      # COMPLETED
            break
        if code in (30, 50):  # FAILED, CANCELED
            print(f"\nTask ended: {status.get('last_error', code)}", file=sys.stderr)
            return 1
        time.sleep(args.poll_s)

    for asset, fname in (("orthophoto.tif", "orthophoto.tif"), ("dsm.tif", "dsm.tif")):
        try:
            out = client.download(project_id, task_id, asset, args.out / fname)
            print(f"  downloaded {out}")
        except urllib.error.HTTPError as exc:
            print(f"  {asset} unavailable ({exc.code})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
