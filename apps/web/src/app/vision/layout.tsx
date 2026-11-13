import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Vision",
  description:
    "A staged roadmap for agri-edge, with no dates: detection benchmarked, Ops Station simulation-complete, then planned bench, field-pilot and wider-use stages. A software prototype, simulated and bench-tested.",
};

export default function VisionLayout({ children }: { children: React.ReactNode }) {
  return children;
}
