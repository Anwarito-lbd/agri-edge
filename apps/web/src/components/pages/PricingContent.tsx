"use client";

import Link from "next/link";

import { useI18n } from "@/components/I18nProvider";

export function PricingContent() {
  const { t } = useI18n();
  return (
    <div className="v2">
      <section className="page-hero">
        <div className="wrap">
          <div className="eyebrow">{t("d.k3a7e0c0f")}</div>
          <h1>{t("d.k8d9b383d")}</h1>
          <p className="lede">{t("d.k44cf8f13")}</p>
        </div>
      </section>
      <section className="section" aria-labelledby="eo-h">
        <div className="wrap">
          <div className="section-head">
            <h2 id="eo-h" className="bar">{t("d.k03abe7b6")}</h2>
          </div>
          <div className="grid-3">
            <div className="card hov">
              <div className="eyebrow">{t("d.k7d897f32")}</div>
              <h3 style={{ marginTop: "8px" }}>{t("d.kc2ff3ab4")}</h3>
              <p>{t("d.k0ace232f")}</p>
              <ul>
                <li>
                  <span>{t("d.k4d5f06fc")}</span>
                </li>
                <li>
                  <span>{t("d.k7c8f214d")}</span>
                </li>
                <li>
                  <span>{t("d.k7f1048cc")}</span>
                </li>
              </ul>
              <div className="foot">
                <Link href="/about#contact" className="link-cta">
                  <span>{t("d.k538d3669")}</span>
                </Link>
              </div>
            </div>
            <div className="card hov">
              <div className="eyebrow">{t("d.k7d897f32")}</div>
              <h3 style={{ marginTop: "8px" }}>{t("d.k2d39acc7")}</h3>
              <p>{t("d.ka9a0ed50")}</p>
              <ul>
                <li>
                  <span>{t("d.k2f802e91")}</span>
                </li>
                <li>
                  <span>{t("d.kbf4cd9b0")}</span>
                </li>
                <li>
                  <span>{t("d.ka26bc268")}</span>
                </li>
              </ul>
              <div className="foot">
                <Link href="/about#contact" className="link-cta">
                  <span>{t("d.k538d3669")}</span>
                </Link>
              </div>
            </div>
            <div className="card hov">
              <div className="eyebrow">{t("d.k7d897f32")}</div>
              <h3 style={{ marginTop: "8px" }}>{t("d.k1aff3076")}</h3>
              <p>{t("d.kbb53c35b")}</p>
              <ul>
                <li>
                  <span>{t("d.k52330daf")}</span>
                </li>
                <li>
                  <span>{t("d.k90bf8592")}</span>
                </li>
                <li>
                  <span>{t("d.k43cfb132")}</span>
                </li>
              </ul>
              <div className="foot">
                <Link href="/about#contact" className="link-cta">
                  <span>{t("d.k538d3669")}</span>
                </Link>
              </div>
            </div>
          </div>
        </div>
      </section>
      <section className="section alt" aria-labelledby="inc-h">
        <div className="wrap">
          <div className="cols2">
            <div className="card">
              <h3 id="inc-h">{t("d.kac3b8505")}</h3>
              <ul className="check-list">
                <li>
                  <svg className="" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                    <path d="M5 12.5l4.5 4.5L19 7.5" />
                  </svg>
                  <span>{t("d.k8ce93cd6")}</span>
                </li>
                <li>
                  <svg className="" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                    <path d="M5 12.5l4.5 4.5L19 7.5" />
                  </svg>
                  <span>{t("d.k8d2aab65")}</span>
                </li>
                <li>
                  <svg className="" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                    <path d="M5 12.5l4.5 4.5L19 7.5" />
                  </svg>
                  <span>{t("d.k84ad9cd6")}</span>
                </li>
                <li>
                  <svg className="" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                    <path d="M5 12.5l4.5 4.5L19 7.5" />
                  </svg>
                  <span>{t("d.k288231e4")}</span>
                </li>
                <li>
                  <svg className="" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                    <path d="M5 12.5l4.5 4.5L19 7.5" />
                  </svg>
                  <span>{t("d.kb9407701")}</span>
                </li>
              </ul>
            </div>
            <div className="card">
              <h3>{t("d.kdc3e807a")}</h3>
              <ul className="check-list no">
                <li>
                  <svg className="" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                    <path d="M6 6l12 12M18 6L6 18" />
                  </svg>
                  <span>{t("d.k6b1c6cd5")}</span>
                </li>
                <li>
                  <svg className="" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                    <path d="M6 6l12 12M18 6L6 18" />
                  </svg>
                  <span>{t("d.k6facd76a")}</span>
                </li>
                <li>
                  <svg className="" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                    <path d="M6 6l12 12M18 6L6 18" />
                  </svg>
                  <span>{t("d.ka9d5812c")}</span>
                </li>
                <li>
                  <svg className="" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                    <path d="M6 6l12 12M18 6L6 18" />
                  </svg>
                  <span>{t("d.k9419e41b")}</span>
                </li>
                <li>
                  <svg className="" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                    <path d="M6 6l12 12M18 6L6 18" />
                  </svg>
                  <span>{t("d.k71bcf596")}</span>
                </li>
              </ul>
            </div>
          </div>
        </div>
      </section>
      <section className="section" aria-labelledby="q-h">
        <div className="wrap">
          <div className="section-head">
            <h2 id="q-h" className="bar">{t("d.k9781b374")}</h2>
          </div>
          <div className="faq">
            <details open>
              <summary>
                <span>{t("d.kfa458655")}</span>
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M5 12h14" />
                  <path className="v" d="M12 5v14" />
                </svg>
              </summary>
              <p className="faq-a">{t("d.kf6094e91")}</p>
            </details>
            <details>
              <summary>
                <span>{t("d.k7b7b2d99")}</span>
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M5 12h14" />
                  <path className="v" d="M12 5v14" />
                </svg>
              </summary>
              <p className="faq-a">{t("d.kae5ffbda")}</p>
            </details>
            <details>
              <summary>
                <span>{t("d.k7503e0d2")}</span>
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M5 12h14" />
                  <path className="v" d="M12 5v14" />
                </svg>
              </summary>
              <p className="faq-a">{t("d.kcac24fcd")}</p>
            </details>
            <details>
              <summary>
                <span>{t("d.k1f46e88e")}</span>
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M5 12h14" />
                  <path className="v" d="M12 5v14" />
                </svg>
              </summary>
              <p className="faq-a">{t("d.k55b15b83")}</p>
            </details>
          </div>
        </div>
      </section>
      <section className="section navy band" id="pilot">
        <div className="wrap">
          <div className="inner">
            <div>
              <h2>{t("d.k346e6246")}</h2>
              <p>
                <span>{t("d.k25f299f2")}</span>
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
