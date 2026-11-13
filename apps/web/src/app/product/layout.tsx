import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Product",
  description:
    "agri-edge: detection pipeline, Ops Station and a read-only phone companion. A software prototype, simulated and bench-tested; nothing here is a field result.",
};

export default function ProductLayout({ children }: { children: React.ReactNode }) {
  return children;
}
