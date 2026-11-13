"use client";

import dynamic from "next/dynamic";

import { useI18n } from "@/components/I18nProvider";

function MapLoading() {
  const { t } = useI18n();
  return (
    <div className="flex h-full min-h-[22rem] w-full items-center justify-center bg-ops-slate text-sm text-white/50">
      {t("map.loadingDemo")}
    </div>
  );
}

const DemoMapInner = dynamic(
  () => import("./DemoMap").then((m) => m.DemoMap),
  {
    ssr: false,
    loading: () => <MapLoading />,
  },
);

export function DemoMapLazy({ className = "" }: { className?: string }) {
  return <DemoMapInner className={className} />;
}
