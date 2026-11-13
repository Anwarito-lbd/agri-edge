import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "About",
  description:
    "agri-edge is software for aerial scouting that stays honest about its evidence: a software prototype, simulated and bench-tested. Hardware and field validation are planned, not started.",
};

export default function AboutLayout({ children }: { children: React.ReactNode }) {
  return children;
}
