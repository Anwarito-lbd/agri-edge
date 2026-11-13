"use client";

import Image from "next/image";
import Link from "next/link";

import { useI18n } from "@/components/I18nProvider";
import type { Key } from "@/lib/i18n";
import { usePathname } from "next/navigation";

const PRODUCT: { href: string; label: Key }[] = [
  { href: "/product", label: "d.k61c05b6c" },
  { href: "/vision", label: "d.kc464de0c" },
  { href: "/pricing", label: "d.k3a7e0c0f" },
  { href: "/ops", label: "d.k97217927" },
  { href: "/proof", label: "nav.site.proof" },
  { href: "/hardware", label: "nav.site.hardware" },
  { href: "/app", label: "nav.site.companion" },
  { href: "/dashboard", label: "nav.site.dashboard" },
];

const COMPANY: { href: string; label: Key }[] = [
  { href: "/about", label: "d.k5f39f8e2" },
  { href: "/about#contact", label: "d.k10e857a2" },
];

/** Design v2 footer (dark). Hidden on /ops/*, which has its own shell. */
export function Footer() {
  const { t, lang, setLang } = useI18n();
  const pathname = usePathname();
  if (pathname.startsWith("/ops")) return null;
  return (
    <div className="v2">
      <footer className="footer">
        <div className="wrap">
          <div className="cols">
            <div>
              <Image src="/brand/logo-horizontal-dark.svg" alt="agri-edge" width={166} height={40} unoptimized />
              <p className="fnote">{t("d.k54d1eb25")}</p>
            </div>
            <div>
              <p className="fh">{t("d.k616d2d03")}</p>
              <ul>
                {PRODUCT.map((l) => (
                  <li key={l.href}>
                    <Link href={l.href}>{t(l.label)}</Link>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <p className="fh">{t("d.kb36e470e")}</p>
              <ul>
                {COMPANY.map((l) => (
                  <li key={l.href}>
                    <Link href={l.href}>{t(l.label)}</Link>
                  </li>
                ))}
                <li>
                  <a href="https://github.com/Anwarito-lbd/agri-edge" rel="noopener noreferrer">
                    {t("footer.github")}
                  </a>
                </li>
              </ul>
            </div>
            <div>
              <p className="fh">{t("d.ke14b7c7e")}</p>
              <ul>
                <li>
                  <button type="button" lang="en" aria-pressed={lang === "en"} onClick={() => setLang("en")}>
                    English
                  </button>
                </li>
                <li>
                  <button type="button" lang="fr" aria-pressed={lang === "fr"} onClick={() => setLang("fr")}>
                    Français
                  </button>
                </li>
              </ul>
            </div>
          </div>
          <div className="legal">
            <span>{t("d.k6a14b6be")}</span>
            <span>{t("d.kf863020a")}</span>
          </div>
          <p className="frnote">{t("footer.legal")}</p>
          <p className="frnote">{t("d.k4f36afc7")}</p>
        </div>
      </footer>
    </div>
  );
}
