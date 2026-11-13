import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Pricing",
  description:
    "Early access and pilot structure for agri-edge. No published prices; pricing is not final and the product is a software prototype, simulated and bench-tested.",
};

export default function PricingLayout({ children }: { children: React.ReactNode }) {
  return children;
}
