import type { Key } from "@/lib/i18n";

export type SeverityClass = "critical" | "warn" | "ok" | "neutral";

/** Badge class for an alert severity word as the Ops API sends it (EMERGENCY/CRITICAL/WARNING/INFO). */
export function severityClass(severity: string | undefined | null): SeverityClass {
  switch ((severity ?? "").toUpperCase()) {
    case "EMERGENCY":
    case "CRITICAL":
      return "critical";
    case "WARNING":
      return "warn";
    case "INFO":
      return "ok";
    default:
      return "neutral";
  }
}

/** Design label key for a severity class (Critical / Warning / Info). */
export const SEVERITY_LABEL: Record<Exclude<SeverityClass, "neutral">, Key> = {
  critical: "d.k3f478af8",
  warn: "d.k320c6102",
  ok: "d.k6d9dc464",
};
