export type ProofItem = {
  src: string;
  title: string;
  caption: string;
  category: "airframe" | "detection" | "livestock" | "weeds" | "physics";
};

export const PROOF_ITEMS: ProofItem[] = [
  {
    src: "/proof/airframe_iso.png",
    title: "Airframe — isometric",
    caption:
      "CAD isometric of the planned under-25 kg RPAS airframe. Companion computer (Pi 5 + Hailo AI HAT) rides alongside a Pixhawk/Cube autopilot; the Pi never commands the aircraft.",
    category: "airframe",
  },
  {
    src: "/proof/airframe_top.png",
    title: "Airframe — top view",
    caption:
      "Top orthographic view of the same airframe layout. Payload bay sized for downward camera, reflectance panel workflow, and store-and-forward spool storage.",
    category: "airframe",
  },
  {
    src: "/proof/airframe_side.png",
    title: "Airframe — side view",
    caption:
      "Side orthographic view showing landing gear clearance and belly camera mounting. A belly camera follows the belly, not the wing — roll/pitch handedness matters for georeferencing.",
    category: "airframe",
  },
  {
    src: "/proof/gob_vs_yolox.jpg",
    title: "Green-on-brown vs YOLOX",
    caption:
      "Side-by-side comparison: classical ExG green-on-brown (OpenWeedLocator, MIT) versus YOLOX-s inference on the same frame. Green-on-brown runs ~62 ms with no NPU; YOLOX ~270 ms on CPU. Different confidence semantics — set thresholds explicitly when switching.",
    category: "detection",
  },
  {
    src: "/proof/sheep_gt.jpg",
    title: "Sheep — ground truth",
    caption:
      "Ground-truth annotation from the aerial sheep evaluation set. Model aerial_sheep_yolox_s scored AP@.50 0.905 on 5,603 boxes. Livestock targets are large enough that this model runs usefully on a bare Pi with no accelerator.",
    category: "livestock",
  },
  {
    src: "/proof/pred_sheep_1.jpg",
    title: "Sheep — model prediction",
    caption:
      "Example detection output from aerial_sheep_yolox_s through the deployed ONNX engine (letterbox + host-side decode). Same path the Pi runs — not a training-only torch path.",
    category: "livestock",
  },
  {
    src: "/proof/pred_weed_1.jpg",
    title: "Weed binary — prediction",
    caption:
      "Example weed detection output. imageweeds_yolox_s: species AP@.50 ~0.457; collapsed binary weed AP@.50 0.673. Species ID still needs locally annotated field imagery before validated_locally can become true.",
    category: "weeds",
  },
  {
    src: "/proof/pred_weeds_species_1.jpg",
    title: "Weed species — prediction",
    caption:
      "Five prairie species head (horseweed, ragweed, kochia usable; redrootpigweed and waterhemp weak — treat those labels as “a weed,” not an ID). weed_crop_yolox_s is pipeline proof only (seedling/tray imagery — not field aerial).",
    category: "weeds",
  },
  {
    src: "/proof/airframe_endurance_physics.png",
    title: "650 mm Airframe Endurance & Vibration Isolation (Simulated)",
    caption:
      "Computed directly from mechanical/airframe_spec.py: 3.43 kg baseline AUW, 2.56:1 thrust-to-weight, 23.6 min hover endurance (6S 10 Ah), 35 Hz isolator separation vs 153 Hz blade-pass (4.4x), and 135 mm IMX708 view-pyramid gear clearance.",
    category: "physics",
  },
  {
    src: "/proof/georef_3d_trajectory.png",
    title: "3D Boustrophedon Survey & Ray-Plane Projection (Simulated)",
    caption:
      "7-pass coverage plan (9.12 ha, 0.00% gap) over a notched field with an exclusion hole + 10 m buffer, plus ZYX body-to-NED frustum projection showing 5.29 m ground shift at 10 deg roll (30 m AGL).",
    category: "physics",
  },
  {
    src: "/proof/spray_drift_envelope.png",
    title: "Spray-Window Weather Gates & Nozzle Flow Envelope (Simulated)",
    caption:
      "EnvironmentReading.spray_advisory wind/VPD gates (ground mast required, airframe downwash rejected, inversion calm <0.83 m/s flagged POOR) paired with Q = R * v * W * 0.006 (7.68 L/min at 20 L/ha, 8 m/s, 8 m swath; bench hardware blocked).",
    category: "physics",
  },
  {
    src: "/proof/ml_models_optics_envelope.png",
    title: "YOLOX-s Model Card APs & IMX708 Optical Budget",
    caption:
      "Verified ONNX test AP@.50 / AP@.50:.95 from models/*_CARD.md alongside pinhole detectability ceilings (7.2x whole-frame downscale loss vs native 4608 px tiling) and 1-px motion-blur shutter limits.",
    category: "physics",
  },
  {
    src: "/proof/agri-edge-fleet-hero.png",
    title: "Fleet Architecture & Ops Station (Concept / Illustrative Art)",
    caption:
      "Illustrative concept rendering (not a photograph or live deployment) depicting the 3 platform tiers: 650 mm X-quad scouting platform, broad-acre VTOL survey class, and spot-spray class with field-edge anemometer mast and Ops Station.",
    category: "physics",
  },
];
