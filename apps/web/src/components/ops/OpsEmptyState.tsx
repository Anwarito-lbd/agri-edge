"use client";

import { useI18n } from "@/components/I18nProvider";

export function OpsEmptyState({
  title,
  detail,
}: {
  title: string;
  detail?: string;
}) {
  const { t } = useI18n();
  return (
    <div className="card border border-border bg-white p-6 text-center">
      <p className="text-sm font-semibold text-ink">{title}</p>
      <p className="mt-2 text-sm text-muted">{detail ?? t("ops.empty.default")}</p>
    </div>
  );
}
