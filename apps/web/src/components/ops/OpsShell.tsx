"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { useI18n } from "@/components/I18nProvider";
import { LangSwitch } from "@/components/LangSwitch";
import { clearOfflineData } from "@/components/ServiceWorkerRegistration";
import type { Key } from "@/lib/i18n";
import { OPS_BANNER_DETAIL, OPS_BANNER_HEADLINE, opsBannerMode } from "@/lib/ops-banner";
import { isDemo, isSimulation, opsGet, type OpsBannerFields } from "@/lib/ops-api";

/** 24px stroke icons from the design (no icon font, no emoji). */
const ICONS = {
  overview:
    '<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
  map: '<path d="M9 4L3 6v14l6-2 6 2 6-2V4l-6 2z"/><path d="M9 4v14M15 6v14"/>',
  live: '<path d="M3 12h4l2-6 4 12 2-6h6"/>',
  weather: '<path d="M7 18a4 4 0 0 1-.5-8A6 6 0 0 1 18 11a3.5 3.5 0 0 1-.5 7z"/>',
  sensors: '<circle cx="12" cy="14" r="2"/><path d="M8 10a5.7 5.7 0 0 1 8 0M5 7a10 10 0 0 1 14 0"/><path d="M12 16v5"/>',
  alerts: '<path d="M6 17V11a6 6 0 0 1 12 0v6l2 2H4z"/><path d="M10 21h4"/>',
  review: '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h4"/><path d="M14.5 17l1.5 1.5 3-3.5"/>',
  target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4"/>',
  doc: '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M9 12h6M9 16h6"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/>',
} as const;

function Icon({ name }: { name: keyof typeof ICONS }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" dangerouslySetInnerHTML={{ __html: ICONS[name] }} />
  );
}

// The six design screens first, then the farmer screens this app already had.
const OPS_NAV: { href: string; key: Key; icon: keyof typeof ICONS; exact?: boolean }[] = [
  { href: "/ops", key: "nav.overview", icon: "overview", exact: true },
  { href: "/ops/map", key: "nav.map", icon: "map" },
  { href: "/ops/live", key: "nav.live", icon: "live" },
  { href: "/ops/weather", key: "nav.weather", icon: "weather" },
  { href: "/ops/sensors", key: "nav.sensors", icon: "sensors" },
  { href: "/ops/alerts", key: "nav.alerts", icon: "alerts" },
  { href: "/ops/recommendations", key: "nav.recommendations", icon: "review" },
  { href: "/ops/fields", key: "nav.fields", icon: "target" },
  { href: "/ops/prescriptions", key: "nav.prescriptions", icon: "doc" },
];

type Me = { name: string; role: string; kind: string; auth_enabled?: boolean };

type OpsStatus = {
  /** Answers come from the built-in synthetic sample data (no live farm connected). */
  demo: boolean;
  simulation: boolean;
  offline: boolean;
  cachedAt: string | null;
  me: Me | null;
  message: string | null;
  refreshStatus: () => void;
};

const OpsStatusContext = createContext<OpsStatus>({
  demo: false,
  simulation: false,
  offline: false,
  cachedAt: null,
  me: null,
  message: null,
  refreshStatus: () => {},
});

export function useOpsStatus() {
  return useContext(OpsStatusContext);
}

export function OpsShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { t } = useI18n();
  const [demo, setDemo] = useState(false);
  const [simulation, setSimulation] = useState(false);
  const [known, setKnown] = useState(false);
  const [offline, setOffline] = useState(false);
  const [cachedAt, setCachedAt] = useState<string | null>(null);
  const [me, setMe] = useState<Me | null>(null);

  const refreshStatus = useCallback(() => {
    void (async () => {
      const result = await opsGet<OpsBannerFields>("overview");
      if (!result.ok) {
        if (result.authRequired) {
          // The station has users and nobody is logged in here.
          router.push(`/login?next=${encodeURIComponent(pathname)}`);
          return;
        }
        setKnown(true);
        setOffline(true);
        setDemo(false);
        setSimulation(false);
        setCachedAt(null);
        return;
      }
      setKnown(true);
      setOffline(false);
      setCachedAt(result.cachedAt && !navigator.onLine ? result.cachedAt : null);
      setDemo(isDemo(result.data));
      setSimulation(isSimulation(result.data));
    })();
  }, [pathname, router]);

  useEffect(() => {
    refreshStatus();
  }, [refreshStatus]);

  useEffect(() => {
    void fetch("/api/auth/me", { cache: "no-store" })
      .then(async (r) => (r.ok ? ((await r.json()) as Me) : null))
      .then((m) => setMe(m && m.kind === "user" ? m : null))
      .catch(() => setMe(null));
  }, [pathname]);

  const logout = useCallback(async () => {
    await fetch("/api/auth/logout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    }).catch(() => undefined);
    clearOfflineData();
    setMe(null);
    router.push("/login");
  }, [router]);

  // ONE banner, always on, always amber: this prototype's ops screens are simulated. The left text is the
  // design's SIMULATION statement; the right text says which mode is answering. (PR #4's DEMO banner is
  // merged in here, so there are never two competing banners.)
  const mode = opsBannerMode({ cachedAt, offline, demo, simulation, known });
  const detail = t(
    OPS_BANNER_DETAIL[mode],
    mode === "cached" ? { time: new Date(cachedAt as string).toLocaleTimeString() } : undefined,
  );
  const message = `${t(OPS_BANNER_HEADLINE)} ${detail}`;

  const value = useMemo(
    () => ({ demo, simulation, offline, cachedAt, me, message, refreshStatus }),
    [demo, simulation, offline, cachedAt, me, message, refreshStatus],
  );

  return (
    <OpsStatusContext.Provider value={value}>
      <div className="opsx">
        <div className="v2 contents">
          <a className="skip" href="#ops-main">
            {t("d.k9a0a553d")}
          </a>
          <header>
            <div className="sim" role="status" data-ops-mode={mode}>
              <div className="in">
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M12 3l10 18H2z" />
                  <path d="M12 10v5M12 18v.01" />
                </svg>
                <span>{t(OPS_BANNER_HEADLINE)}</span>
                <span className="r">{detail}</span>
              </div>
            </div>
            <div className="opsbar">
              <div className="in">
                <Link href="/" aria-label={t("d.kba5fd0cd")}>
                  <Image src="/brand/logo-horizontal.svg" alt="agri-edge" width={130} height={32} unoptimized />
                </Link>
                <div className="site">
                  <b>{t("shell.title")}</b> · <span>{t("d.k52ff664a")}</span>
                </div>
                <div className="sp">
                  <LangSwitch />
                  <Link className="exit" href="/">
                    {t("d.k0fd9ded2")}
                  </Link>
                  {me ? (
                    <>
                      <span className="hidden sm:inline">{t("shell.loggedInAs", { name: me.name, role: me.role })}</span>
                      <button type="button" className="btn-sm" onClick={() => void logout()}>
                        {t("shell.logout")}
                      </button>
                    </>
                  ) : (
                    <Link className="exit" href={`/login?next=${encodeURIComponent(pathname)}`}>
                      {t("shell.login")}
                    </Link>
                  )}
                  <span className="av" aria-hidden="true">
                    <Icon name="user" />
                  </span>
                </div>
              </div>
            </div>
          </header>
        </div>

        <div className="shell">
          <nav className="side" aria-label={t("ops.nav.aria")}>
            {OPS_NAV.map((item) => {
              const active = item.exact
                ? pathname === item.href
                : pathname === item.href || pathname.startsWith(`${item.href}/`);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={active ? "on" : undefined}
                  aria-current={active ? "page" : undefined}
                >
                  <Icon name={item.icon} />
                  <span>{t(item.key)}</span>
                </Link>
              );
            })}
            <div className="sf">{t("d.k2f5a4228")}</div>
          </nav>
          <div className="main" id="ops-main" tabIndex={-1}>
            <div className="mb-4 flex flex-wrap items-center gap-3">
              <span className="chip">{t("d.k43834928")}</span>
            </div>
            {children}
          </div>
        </div>
      </div>
    </OpsStatusContext.Provider>
  );
}
