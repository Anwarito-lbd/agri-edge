import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Hardware",
  description:
    "Under-25 kg RPAS airframe with Raspberry Pi 5 companion, Hailo AI HAT, and Pixhawk/Cube — staged hardware plan.",
};

export default function HardwarePage() {
  return (
    <div>
      <section className="border-b border-border">
        <div className="container-page grid gap-12 py-14 sm:py-16 lg:grid-cols-2 lg:items-center lg:gap-16">
          <div>
            <p className="eyebrow">Platform</p>
            <h1 className="page-title mt-3">Airframe & companion computer</h1>
            <p className="lede mt-4">
              Keep the aircraft under 25&nbsp;kg — above that is Transport Canada’s
              medium-drone class and a different regulatory project. Software gaps
              are closed; remaining work is blocked on hardware that does not exist
              yet.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-3">
              <Link href="/proof" className="btn-primary">
                See CAD & detections
              </Link>
              <Link href="/vision" className="link-arrow">
                Roadmap →
              </Link>
            </div>
          </div>
          <div className="relative aspect-square border border-border bg-surface">
            <Image
              src="/proof/airframe_iso.png"
              alt="Airframe isometric"
              fill
              className="object-contain p-6"
              priority
              sizes="(max-width: 1024px) 100vw, 50vw"
            />
          </div>
        </div>
      </section>

      <section className="container-page section">
        <h2 className="section-title section-title-accent">
          Three views of the airframe
        </h2>
        <p className="mt-6 max-w-xl text-sm text-muted">
          Product-page angles for layout review — payload bay, clearances, and
          gear height.
        </p>
        <div className="mt-10 grid gap-6 lg:grid-cols-3">
          {[
            {
              src: "/proof/airframe_iso.png",
              title: "Isometric",
              caption:
                "Overall layout: payload bay, landing gear, companion mount.",
            },
            {
              src: "/proof/airframe_top.png",
              title: "Top",
              caption: "Plan view for bay and antenna / radio clearances.",
            },
            {
              src: "/proof/airframe_side.png",
              title: "Side",
              caption: "Belly camera height and gear clearance for rough fields.",
            },
          ].map((img) => (
            <figure key={img.src} className="card overflow-hidden">
              <div className="relative aspect-square bg-surface">
                <Image
                  src={img.src}
                  alt={img.title}
                  fill
                  className="object-contain p-4"
                  sizes="(max-width: 1024px) 100vw, 33vw"
                />
              </div>
              <figcaption className="border-t border-border px-4 py-4">
                <p className="text-sm font-semibold text-ink">{img.title}</p>
                <p className="mt-1 text-sm text-muted leading-relaxed">
                  {img.caption}
                </p>
              </figcaption>
            </figure>
          ))}
        </div>
      </section>

      <section className="bg-surface">
        <div className="container-page section">
          <h2 className="section-title section-title-accent">Stack</h2>
          <div className="mt-10 overflow-x-auto border border-border bg-white">
            <table className="table-inst w-full min-w-[28rem]">
              <thead>
                <tr>
                  <th>Role</th>
                  <th>Hardware</th>
                  <th>Owns</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td className="emph">Flight</td>
                  <td>Pixhawk / Cube</td>
                  <td>Attitude, nav, failsafes — survives Pi death</td>
                </tr>
                <tr>
                  <td className="emph">Companion</td>
                  <td>Pi 5 8&nbsp;GB + AI HAT+ 26&nbsp;TOPS</td>
                  <td>
                    Capture, QA, inference, indices, spool (read-only MAVLink)
                  </td>
                </tr>
                <tr>
                  <td className="emph">Camera</td>
                  <td>Camera Module 3 (IMX708)</td>
                  <td>
                    Default sensor for georeference model; verify channel order
                  </td>
                </tr>
                <tr>
                  <td className="emph">Positioning</td>
                  <td>RTK GNSS (+ NTRIP)</td>
                  <td>Corrections → receiver serial, not FC MAVLink</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section className="container-page section">
        <h2 className="section-title section-title-accent">
          Staged spend (approx. CAD)
        </h2>
        <ol className="mt-10 space-y-0 border border-border divide-y divide-border">
          {[
            {
              stage: "0",
              cost: "Free",
              what: "WSL2, Docker, GPU power mode — unblocks SITL, Hailo compile, WebODM, farmOS",
            },
            {
              stage: "1",
              cost: "~C$400",
              what: "Pi 5, cooler, PSU, SD, Camera Module 3, reflectance panel — local imagery without an aircraft",
            },
            {
              stage: "2",
              cost: "~C$150",
              what: "AI HAT+ 26 TOPS — tiled weed survey becomes flyable (~288 ms vs seconds on CPU)",
            },
            {
              stage: "3",
              cost: "C$1,200–2,500",
              what: "Airframe, FC, batteries, RC, telemetry, rangefinder for AGL",
            },
            {
              stage: "4–5",
              cost: "C$750–1,950",
              what: "RTK / NTRIP, anemometer on a field-edge mast (not airframe downwash)",
            },
          ].map((row) => (
            <li
              key={row.stage}
              className="flex flex-col gap-1 bg-white px-4 py-4 sm:flex-row sm:items-baseline sm:gap-8"
            >
              <span className="shrink-0 font-mono text-xs font-semibold text-primary sm:w-24">
                Stage {row.stage}
              </span>
              <span className="shrink-0 text-sm font-semibold text-foreground sm:w-32">
                {row.cost}
              </span>
              <span className="text-sm text-muted leading-relaxed">{row.what}</span>
            </li>
          ))}
        </ol>
        <p className="mt-6 text-sm text-muted leading-relaxed">
          Livestock demo first if budget is tight:{" "}
          <code className="rounded bg-surface px-1 text-xs font-mono">
            aerial_sheep_yolox_s
          </code>{" "}
          (AP@.50 0.905) runs on a bare Pi. See{" "}
          <Link href="/proof" className="link-arrow">
            pipeline proof
          </Link>
          .
        </p>
      </section>

      <section className="border-t border-border bg-surface">
        <div className="container-page section space-y-10">
          <div>
            <p className="eyebrow">Fleet, ML & Physics</p>
            <h2 className="section-title section-title-accent mt-2">
              Drone platforms, YOLOX-s training & flight physics
            </h2>
            <p className="mt-4 max-w-3xl text-sm text-muted leading-relaxed">
              The Python runtime separates three operational drone classes from three
              custom YOLOX-s Apache-2.0 perception models. All endurance, spray-flow,
              and ray-plane projections below are computed from repository physics
              modules (<code className="font-mono text-xs">mechanical/airframe_spec.py</code>,{" "}
              <code className="font-mono text-xs">src/agri_edge/geo/</code>, and{" "}
              <code className="font-mono text-xs">src/agri_edge/sensors/environment.py</code>);
              no physical aircraft has flown yet.
            </p>
          </div>

          <figure className="card overflow-hidden bg-white">
            <div className="relative aspect-[16/9] bg-surface">
              <Image
                src="/proof/agri-edge-fleet-hero.png"
                alt="Concept illustration of the 3 Agri-Edge agricultural drone tiers, weather mast, and Ops Station"
                fill
                priority
                className="object-cover"
                sizes="(max-width: 1024px) 100vw, 1100px"
              />
            </div>
            <figcaption className="border-t border-border px-4 py-3 text-xs text-muted">
              <strong className="text-ink">Concept / Illustrative Art (not field telemetry):</strong>{" "}
              Three platform classes coordinated around one fail-closed ground station —
              650 mm X-quad scouting CAD (`mechanical/`), broad-acre survey VTOL tier (`docs/source/research-report.md`),
              and bench-gated spot-spray tier (`WATER_ONLY_BENCH_TEST_PLAN.md`), anchored by a ground-mast anemometer.
            </figcaption>
          </figure>

          <div className="grid gap-6 lg:grid-cols-3">
            {[
              {
                tier: "Tier 1 · Scouting X-Quad (CAD Spec)",
                specs: "650 mm wheelbase · 3.43 kg AUW · 15\" props · 2.56:1 TWR",
                detail:
                  "IMX708 + Pi 5 + AI HAT+ (26 TOPS). 23.6 min hover (6S 10 Ah), 67.4 ha/h raw coverage @ 30 m AGL, 35 Hz isolator vs 153 Hz blade-pass (4.4x).",
              },
              {
                tier: "Tier 2 · Broad-Acre Survey / VTOL",
                specs: "Fixed-wing / QuadPlane · 5 m/s–15 m/s survey envelope",
                detail:
                  "Whole-frame vs 640-px native tiling trades 7.2x resolution loss against shutter/rolling skew (33 ms IMX708 vs 0 ms global shutter IMX296).",
              },
              {
                tier: "Tier 3 · Precision Treatment Class",
                specs: "Q = R · v · W · 0.006 (7.68 L/min @ 20 L/ha, 8 m/s, 8 m)",
                detail:
                  "10-gate TreatmentDecisionEngine (SIMULATION_ONLY=True), dual flight/treatment geofences + holes, and wind-first EnvironmentReading spray advisory.",
              },
            ].map((card) => (
              <div key={card.tier} className="card bg-white p-5">
                <p className="eyebrow">{card.tier}</p>
                <p className="mt-2 font-mono text-xs font-semibold text-primary">
                  {card.specs}
                </p>
                <p className="mt-3 text-sm text-muted leading-relaxed">{card.detail}</p>
              </div>
            ))}
          </div>

          <div className="overflow-x-auto border border-border bg-white">
            <table className="table-inst w-full min-w-[36rem]">
              <thead>
                <tr>
                  <th>Model (Apache-2.0 YOLOX-s)</th>
                  <th>Dataset & Licence</th>
                  <th>Test AP@.50</th>
                  <th>Test AP@.50:.95</th>
                  <th>Operational Envelope & Caveat</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td className="emph font-mono text-xs">aerial_sheep_yolox_s</td>
                  <td>Aerial Sheep (Public Domain, 5,603 test GT boxes)</td>
                  <td>0.9049</td>
                  <td>0.4664</td>
                  <td>Whole-frame viable up to 24.6 m (sheep) / 41.0 m (cattle) on bare Pi CPU.</td>
                </tr>
                <tr>
                  <td className="emph font-mono text-xs">imageweeds_yolox_s</td>
                  <td>ImageWeeds nadir aerial (CC BY 4.0, 306 test GT boxes)</td>
                  <td>0.4570 (5-cls) / 0.673 (binary)</td>
                  <td>0.2590 / 0.375</td>
                  <td>Needs Hailo NPU (~288 ms tiled) for survey flight; run with label collapse to weed.</td>
                </tr>
                <tr>
                  <td className="emph font-mono text-xs">weed_crop_yolox_s</td>
                  <td>LibreYOLO/weed-crop-aerial (CC BY 4.0, 781 test GT boxes)</td>
                  <td>0.6893</td>
                  <td>0.3924</td>
                  <td>Pipeline proof only: 98.3% of crop boxes come from indoor propagation trays.</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>
  );
}
