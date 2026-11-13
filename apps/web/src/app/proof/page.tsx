import type { Metadata } from "next";
import { ProofCard } from "@/components/ProofCard";
import { PROOF_ITEMS } from "@/lib/proof";

export const metadata: Metadata = {
  title: "Pipeline proof",
  description:
    "Real pipeline and CAD imagery from agri-edge: airframe views, green-on-brown vs YOLOX, sheep ground truth and predictions, weed detections.",
};

const ORDER: Array<{
  key: (typeof PROOF_ITEMS)[number]["category"];
  label: string;
  blurb: string;
}> = [
  {
    key: "airframe",
    label: "Airframe",
    blurb: "CAD renders of the planned under-25 kg RPAS layout.",
  },
  {
    key: "detection",
    label: "Detection comparison",
    blurb: "Classical ExG green-on-brown versus YOLOX on the same frame.",
  },
  {
    key: "livestock",
    label: "Livestock",
    blurb:
      "Ground truth and ONNX predictions from aerial_sheep_yolox_s (AP@.50 0.905).",
  },
  {
    key: "weeds",
    label: "Weeds",
    blurb:
      "ImageWeeds species ~0.457 / binary weed 0.673; weed_crop is pipeline proof only.",
  },
  {
    key: "physics",
    label: "Physics, ML Optics & Fleet Architecture",
    blurb:
      "Simulated propulsion, 3D ray-plane georeferencing, meteorological spray gates, and verified model-card evaluation curves.",
  },
];

export default function ProofPage() {
  return (
    <div className="bg-surface min-h-full">
      <div className="container-page py-12 sm:py-14">
        <header className="max-w-3xl">
          <p className="eyebrow">Ops evidence</p>
          <h1 className="page-title mt-3">Proof from the pipeline</h1>
          <p className="lede mt-4">
            These are real assets copied from the agri-edge engineering tree —
            CAD airframe renders and evaluation imagery. Captions state what each
            file is. Metrics match HANDOFF: sheep AP@.50 0.905; imageweeds species
            ~0.457 / binary weed 0.673; weed_crop is pipeline proof only.
          </p>
        </header>

        {ORDER.map((section, idx) => {
          const items = PROOF_ITEMS.filter((p) => p.category === section.key);
          if (!items.length) return null;
          const denseGrid =
            items.length >= 2
              ? "grid gap-3 sm:grid-cols-2 lg:grid-cols-3"
              : "grid gap-3 max-w-3xl";
          return (
            <section key={section.key} className={idx === 0 ? "mt-10" : "mt-12"}>
              <div className="mb-4 flex flex-wrap items-end justify-between gap-3 border-b border-border pb-3">
                <div>
                  <h2 className="section-title section-title-accent text-[1.35rem]">
                    {section.label}
                  </h2>
                  <p className="mt-4 text-sm text-muted">{section.blurb}</p>
                </div>
                <span className="text-[11px] font-semibold uppercase tracking-wide text-muted">
                  {items.length} asset{items.length === 1 ? "" : "s"}
                </span>
              </div>
              <div className={denseGrid}>
                {items.map((item) => (
                  <ProofCard key={item.src} item={item} dense />
                ))}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
