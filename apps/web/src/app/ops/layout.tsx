import type { Metadata } from "next";
import { OpsShell } from "@/components/ops/OpsShell";

export const metadata: Metadata = {
  title: "Operations Station",
  description:
    "Farm operations station — weather, soil, sensors, alerts, and map. Simulation banner when synthetic or offline.",
};

export default function OpsLayout({ children }: { children: React.ReactNode }) {
  return <OpsShell>{children}</OpsShell>;
}
