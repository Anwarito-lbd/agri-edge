import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Companion app",
  description:
    "DEMO mock-Pi companion shell for agri-edge. Does not arm, disarm, or fly the aircraft.",
};

export default function CompanionLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
