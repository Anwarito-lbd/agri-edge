"use client";

import Link from "next/link";

import { useI18n } from "@/components/I18nProvider";

export function VisionContent() {
  const { t } = useI18n();
  return (
    <div className="v2">
      <section className="page-hero">
        <div className="wrap">
          <div className="eyebrow">{t("d.kc464de0c")}</div>
          <h1>{t("d.kbb9cea18")}</h1>
          <p className="lede">{t("d.k1964c443")}</p>
        </div>
      </section>
      <section className="section" aria-labelledby="rd-h">
        <div className="wrap">
          <div className="section-head">
            <h2 id="rd-h" className="bar">{t("d.kb1e0f525")}</h2>
            <p>{t("d.ka044d9c8")}</p>
          </div>
          <div className="road" role="list">
            <div className="stage" role="listitem">
              <div className="lab">
                <span>{t("d.k172349ec")}</span>
                <b>
                  1
                </b>
                <span className="badge navy plain">
                  <span>{t("d.kd4389850")}</span>
                </span>
              </div>
              <div>
                <h3>{t("d.k21e4180d")}</h3>
                <p>{t("d.k6d7afea6")}</p>
              </div>
              <div>
                <ul>
                  <li>
                    <span>{t("d.k3ce475ee")}</span>
                  </li>
                  <li>
                    <span>{t("d.kd29d50de")}</span>
                  </li>
                  <li>
                    <span>{t("d.k43b487e5")}</span>
                  </li>
                </ul>
              </div>
            </div>
            <div className="stage" role="listitem">
              <div className="lab">
                <span>{t("d.k172349ec")}</span>
                <b>
                  2
                </b>
                <span className="badge navy plain">
                  <span>{t("d.k333f2f20")}</span>
                </span>
              </div>
              <div>
                <h3>{t("d.k44a611b6")}</h3>
                <p>{t("d.k453327eb")}</p>
              </div>
              <div>
                <ul>
                  <li>
                    <span>{t("d.ka09edb1b")}</span>
                  </li>
                  <li>
                    <span>{t("d.k5a2400ac")}</span>
                  </li>
                  <li>
                    <span>{t("d.ka36e8e81")}</span>
                  </li>
                </ul>
              </div>
            </div>
            <div className="stage planned" role="listitem">
              <div className="lab">
                <span>{t("d.k172349ec")}</span>
                <b>
                  3
                </b>
                <span className="badge neutral plain">
                  <span>{t("d.k5944e9f1")}</span>
                </span>
              </div>
              <div>
                <h3>{t("d.k3b69d011")}</h3>
                <p>{t("d.k46a99996")}</p>
              </div>
              <div>
                <ul>
                  <li>
                    <span>{t("d.k3bead28d")}</span>
                  </li>
                  <li>
                    <span>{t("d.k8fd4e6b3")}</span>
                  </li>
                </ul>
              </div>
            </div>
            <div className="stage planned" role="listitem">
              <div className="lab">
                <span>{t("d.k172349ec")}</span>
                <b>
                  4
                </b>
                <span className="badge neutral plain">
                  <span>{t("d.k5944e9f1")}</span>
                </span>
              </div>
              <div>
                <h3>{t("d.k707d5efa")}</h3>
                <p>{t("d.k4e1b4d08")}</p>
              </div>
              <div>
                <ul>
                  <li>
                    <span>{t("d.k06b4ed11")}</span>
                  </li>
                  <li>
                    <span>{t("d.k47d390e7")}</span>
                  </li>
                  <li>
                    <span>{t("d.k8f00fa65")}</span>
                  </li>
                </ul>
              </div>
            </div>
            <div className="stage planned" role="listitem">
              <div className="lab">
                <span>{t("d.k172349ec")}</span>
                <b>
                  5
                </b>
                <span className="badge neutral plain">
                  <span>{t("d.kf64ef887")}</span>
                </span>
              </div>
              <div>
                <h3>{t("d.kbebe5a08")}</h3>
                <p>{t("d.kfdf054d3")}</p>
              </div>
              <div>
                <ul>
                  <li>
                    <span>{t("d.k7d7dd4cc")}</span>
                  </li>
                  <li>
                    <span>{t("d.k31f699a3")}</span>
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </section>
      <section className="section alt" aria-labelledby="gd-h">
        <div className="wrap">
          <div className="cols2" style={{ gap: "64px", alignItems: "start" }}>
            <div>
              <h2 className="bar" id="gd-h">{t("d.k51d67e88")}</h2>
              <p style={{ marginTop: "24px", color: "#44525F" }}>{t("d.kf6fc9242")}</p>
            </div>
            <div className="card">
              <h3>
                <span>{t("d.k5ade8375")}</span>
              </h3>
              <ul className="check-list">
                <li>
                  <svg className="" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                    <path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" />
                    <path d="M9 12l2 2 4-4" />
                  </svg>
                  <span>{t("d.k9c909f5a")}</span>
                </li>
                <li>
                  <svg className="" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                    <path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" />
                    <path d="M9 12l2 2 4-4" />
                  </svg>
                  <span>{t("d.k01935f6d")}</span>
                </li>
                <li>
                  <svg className="" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                    <path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" />
                    <path d="M9 12l2 2 4-4" />
                  </svg>
                  <span>{t("d.k1e82ce83")}</span>
                </li>
                <li>
                  <svg className="" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                    <path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" />
                    <path d="M9 12l2 2 4-4" />
                  </svg>
                  <span>{t("d.k55f5e3d2")}</span>
                </li>
              </ul>
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
                <span>{t("d.k61cde7f2")}</span>
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
