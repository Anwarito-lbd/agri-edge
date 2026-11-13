"use client";

import Link from "next/link";

import { useI18n } from "@/components/I18nProvider";
import { CONTACT_EMAIL, contactHref } from "@/lib/contact";

export function AboutContent() {
  const { t } = useI18n();
  const mailto = contactHref("agri-edge — contact");
  return (
    <div className="v2">
      <section className="page-hero">
        <div className="wrap">
          <div className="eyebrow">{t("d.k5f39f8e2")}</div>
          <h1>{t("d.k5f44bb06")}</h1>
          <p className="lede">{t("d.k5adb1a64")}</p>
        </div>
      </section>
      <section className="section" aria-labelledby="pr-h">
        <div className="wrap">
          <div className="section-head">
            <h2 id="pr-h" className="bar">{t("d.k52e22052")}</h2>
          </div>
          <div className="grid-3">
            <div className="card">
              <svg className="ico" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                <path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" />
                <path d="M9 12l2 2 4-4" />
              </svg>
              <h3>{t("d.k7e23a268")}</h3>
              <p>{t("d.ke0a56e4e")}</p>
            </div>
            <div className="card">
              <svg className="ico" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                <path d="M5 12.5l4.5 4.5L19 7.5" />
              </svg>
              <h3>{t("d.kde0a68b6")}</h3>
              <p>{t("d.kb2268d69")}</p>
            </div>
            <div className="card">
              <svg className="ico" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                <circle cx="12" cy="8" r="4" />
                <path d="M4 21c0-4 4-6 8-6s8 2 8 6" />
              </svg>
              <h3>{t("d.k6b809046")}</h3>
              <p>{t("d.k58bf76ac")}</p>
            </div>
          </div>
        </div>
      </section>
      <section className="section alt" aria-labelledby="ms-h">
        <div className="wrap">
          <div className="section-head">
            <h2 id="ms-h" className="bar">{t("d.kc3a896dd")}</h2>
            <p>{t("d.k42d6fdfe")}</p>
          </div>
          <div className="timeline">
            <div className="tl done">
              <div className="dot"></div>
              <div className="eyebrow">{t("d.ke31d3728")}</div>
              <h3>{t("d.k21e4180d")}</h3>
              <p>{t("d.k48d8a461")}</p>
            </div>
            <div className="tl done">
              <div className="dot"></div>
              <div className="eyebrow">{t("d.kae282337")}</div>
              <h3>{t("d.k4b79cf33")}</h3>
              <p>{t("d.k8a9496b2")}</p>
            </div>
            <div className="tl plan">
              <div className="dot"></div>
              <div className="eyebrow">{t("d.k8ec8389b")}</div>
              <h3>{t("d.k97e57426")}</h3>
              <p>{t("d.k02d20f09")}</p>
            </div>
          </div>
        </div>
      </section>
      <section className="section" aria-labelledby="tm-h">
        <div className="wrap">
          <div className="section-head">
            <h2 id="tm-h" className="bar">{t("d.kf1476e35")}</h2>
            <p>{t("d.k54eb0478")}</p>
          </div>
          <div className="grid-3">
            <div className="placeholder-card">
              <div className="av">
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <circle cx="12" cy="8" r="4" />
                  <path d="M4 21c0-4 4-6 8-6s8 2 8 6" />
                </svg>
              </div>
              <h3>{t("d.kfa6eae86")}</h3>
              <p className="body-sm muted">{t("d.k9f883966")}</p>
            </div>
            <div className="placeholder-card">
              <div className="av">
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <circle cx="12" cy="8" r="4" />
                  <path d="M4 21c0-4 4-6 8-6s8 2 8 6" />
                </svg>
              </div>
              <h3>{t("d.kfa6eae86")}</h3>
              <p className="body-sm muted">{t("d.k9f883966")}</p>
            </div>
            <div className="placeholder-card">
              <div className="av">
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <circle cx="12" cy="8" r="4" />
                  <path d="M4 21c0-4 4-6 8-6s8 2 8 6" />
                </svg>
              </div>
              <h3>{t("d.kfa6eae86")}</h3>
              <p className="body-sm muted">{t("d.k9f883966")}</p>
            </div>
          </div>
        </div>
      </section>
      <section className="section alt" id="contact" aria-labelledby="ct-h">
        <div className="wrap">
          <div className="cols2">
            <div>
              <h2 className="bar" id="ct-h">{t("d.k10e857a2")}</h2>
            </div>
            <div className="card">
              <svg className="ico" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                <rect x="3" y="5" width="18" height="14" rx="2" />
                <path d="M3 7l9 6 9-6" />
              </svg>
              <h3>{t("d.kd0aefa4a")}</h3>
              {mailto ? (
                <>
                  <p style={{ marginTop: "8px", fontSize: "18px", fontWeight: 500 }}>
                    <a href={mailto}>{CONTACT_EMAIL}</a>
                  </p>
                </>
              ) : (
                <>
                  {/* Placeholder until NEXT_PUBLIC_CONTACT_EMAIL is set (see src/lib/contact.ts). */}
                  <p
                    data-todo="contact-email"
                    style={{ marginTop: "8px", fontSize: "18px", color: "#173D68", fontWeight: 500 }}
                  >
                    hello@[domain to be set]
                  </p>
                  <p style={{ marginTop: "8px" }}>{t("d.k9005c836")}</p>
                </>
              )}
            </div>
          </div>
        </div>
      </section>
      <section className="section navy band" id="pilot">
        <div className="wrap">
          <div className="inner">
            <div>
              <h2>{t("d.k346e6246")}</h2>
              <p>
                <span>{t("d.k8c894771")}</span>
              </p>
            </div>
            <div className="btn-row">
              <Link href="/about#contact" className="btn btn-light">
                <span>{t("d.k346e6246")}</span>
              </Link>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
