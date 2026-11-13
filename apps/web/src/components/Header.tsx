"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { LangSwitch } from "@/components/LangSwitch";
import { useI18n } from "@/components/I18nProvider";
import type { Key } from "@/lib/i18n";

/** Design v2 primary nav. Proof, Hardware, Companion and Dashboard live in the footer. */
const NAV: { href: string; label: Key; match: (p: string) => boolean }[] = [
  { href: "/product", label: "d.k616d2d03", match: (p) => p.startsWith("/product") },
  { href: "/vision", label: "d.kc464de0c", match: (p) => p.startsWith("/vision") },
  { href: "/pricing", label: "d.k3a7e0c0f", match: (p) => p.startsWith("/pricing") },
  { href: "/about", label: "d.k5f39f8e2", match: (p) => p.startsWith("/about") },
  { href: "/ops", label: "d.k97217927", match: (p) => p.startsWith("/ops") },
];

/**
 * Utility bar + sticky nav from the design. Not shown on /ops/*: the ops screens
 * have their own top bar and the persistent SIMULATION banner (OpsShell).
 */
export function Header() {
  const pathname = usePathname();
  const { t } = useI18n();
  const [open, setOpen] = useState(false);

  if (pathname.startsWith("/ops")) return null;

  return (
    <div className="v2 contents">
      <a className="skip" href="#main">
        {t("d.k9a0a553d")}
      </a>
      <div className="util" role="complementary" aria-label={t("d.kb5c65ce5")}>
        <div className="wrap">
          <span className="tag">{t("d.kcc13bfa8")}</span>
          <LangSwitch />
        </div>
      </div>
      <header className={`nav${open ? " open" : ""}`}>
        <div className="wrap">
          <Link className="logo" href="/" aria-label={t("d.kba5fd0cd")} onClick={() => setOpen(false)}>
            <Image src="/brand/logo-horizontal.svg" alt="agri-edge" width={166} height={40} priority unoptimized />
          </Link>
          <button
            className="burger"
            type="button"
            aria-expanded={open}
            aria-controls="primary-nav"
            aria-label={t("d.k2f0587e7")}
            onClick={() => setOpen((o) => !o)}
            onKeyDown={(e) => {
              if (e.key === "Escape") setOpen(false);
            }}
          >
            <svg className="i-open" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
              <path d="M4 7h16M4 12h16M4 17h16" />
            </svg>
            <svg className="i-close" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
          <nav
            id="primary-nav"
            aria-label={t("d.ka9b86a28")}
            onKeyDown={(e) => {
              if (e.key === "Escape") setOpen(false);
            }}
          >
            <ul>
              {NAV.map((item) => {
                const on = item.match(pathname);
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      className={on ? "on" : undefined}
                      aria-current={on ? "page" : undefined}
                      onClick={() => setOpen(false)}
                    >
                      {t(item.label)}
                    </Link>
                  </li>
                );
              })}
              <li className="nav-cta">
                <Link className="login" href="/about#contact" onClick={() => setOpen(false)}>
                  {t("d.k6dbdb8ea")}
                </Link>
              </li>
            </ul>
          </nav>
        </div>
      </header>
    </div>
  );
}
