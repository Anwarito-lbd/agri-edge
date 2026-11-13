"use client";

import Link from "next/link";

import { useI18n } from "@/components/I18nProvider";

export function ProductContent() {
  const { t } = useI18n();
  return (
    <div className="v2">
      <section className="page-hero">
        <div className="wrap">
          <div className="eyebrow">{t("d.k616d2d03")}</div>
          <h1>{t("d.k6f8dca44")}</h1>
          <p className="lede">{t("d.k2f69edd7")}</p>
        </div>
      </section>
      <section className="section" aria-labelledby="mod-h">
        <div className="wrap">
          <div className="section-head">
            <h2 className="bar" id="mod-h">{t("d.kcab89f53")}</h2>
          </div>
          <div className="grid-3">
            <div className="card">
              <svg className="ico" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                <rect x="3" y="4" width="6" height="6" rx="1" />
                <rect x="15" y="14" width="6" height="6" rx="1" />
                <path d="M9 7h4a2 2 0 0 1 2 2v5" />
              </svg>
              <h3>{t("d.k82a1a6a6")}</h3>
              <p>{t("d.k87f97f62")}</p>
              <div className="foot">
                <span className="badge neutral">
                  <span>{t("d.k5aba147f")}</span>
                </span>
              </div>
            </div>
            <div className="card">
              <svg className="ico" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                <rect x="3" y="4" width="18" height="12" rx="2" />
                <path d="M8 20h8M12 16v4" />
              </svg>
              <h3>{t("d.kc833ff5f")}</h3>
              <p>{t("d.kc502f53d")}</p>
              <div className="foot">
                <span className="badge neutral">
                  <span>{t("d.k6c1bfbe7")}</span>
                </span>
              </div>
            </div>
            <div className="card">
              <svg className="ico" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                <rect x="7" y="2" width="10" height="20" rx="2" />
                <path d="M11 18h2" />
              </svg>
              <h3>{t("d.k618a0185")}</h3>
              <p>{t("d.k802e7dde")}</p>
              <div className="foot">
                <span className="badge neutral">
                  <span>{t("d.k39ef0bc6")}</span>
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>
      <section className="section alt" aria-labelledby="arch-h">
        <div className="wrap">
          <div className="section-head">
            <h2 id="arch-h" className="bar">{t("d.ke3e46d2d")}</h2>
            <p>{t("d.k001960de")}</p>
          </div>
          <figure className="fig" style={{ background: "#fff" }}>
            <svg viewBox="0 0 1200 320" role="img" style={{ fontFamily: "Inter,sans-serif" }} aria-label={t("d.kcf8d0f6d")}>
              <rect width="1200" height="320" fill="#fff" />
              <rect x="20" y="100" width="190" height="104" rx="8" fill="#EEF2F6" stroke="#173D68" strokeWidth="1.5" />
              <text x="40" y="142" fontSize="18" fontWeight="600" fill="#173D68" textAnchor="start">{t("d.k2578b0c4")}</text>
              <text x="40" y="166" fontSize="14" fontWeight="400" fill="#5B6B7A" textAnchor="start">{t("d.kc62c17e3")}</text>
              <text x="40" y="190" fontSize="12" fontWeight="600" fill="#173D68" textAnchor="start" letterSpacing="0.5">{t("d.kc369a009")}</text>
              <rect x="300" y="100" width="260" height="104" rx="8" fill="#173D68" stroke="#173D68" strokeWidth="1.5" />
              <text x="320" y="142" fontSize="18" fontWeight="600" fill="#fff" textAnchor="start">{t("d.k7e705b06")}</text>
              <text x="320" y="166" fontSize="14" fontWeight="400" fill="#D6E4F2" textAnchor="start">{t("d.k5b003794")}</text>
              <text x="320" y="190" fontSize="12" fontWeight="600" fill="#D6E4F2" textAnchor="start" letterSpacing="0.5">{t("d.kdc3e807a")}</text>
              <rect x="640" y="100" width="230" height="104" rx="8" fill="#EEF2F6" stroke="#173D68" strokeWidth="1.5" />
              <text x="660" y="142" fontSize="18" fontWeight="600" fill="#173D68" textAnchor="start">{t("d.kbb0ec953")}</text>
              <text x="660" y="166" fontSize="14" fontWeight="400" fill="#5B6B7A" textAnchor="start">{t("d.k6436dc27")}</text>
              <text x="660" y="190" fontSize="12" fontWeight="600" fill="#173D68" textAnchor="start" letterSpacing="0.5">{t("d.kdc3e807a")}</text>
              <rect x="930" y="100" width="240" height="104" rx="8" fill="#EEF2F6" stroke="#173D68" strokeWidth="1.5" />
              <text x="950" y="142" fontSize="18" fontWeight="600" fill="#173D68" textAnchor="start">{t("d.kc833ff5f")}</text>
              <text x="950" y="166" fontSize="14" fontWeight="400" fill="#5B6B7A" textAnchor="start">{t("d.kc0da37cc")}</text>
              <text x="950" y="190" fontSize="12" fontWeight="600" fill="#173D68" textAnchor="start" letterSpacing="0.5">{t("d.k972b87ec")}</text>
              <path d="M210 152H292" stroke="#173D68" strokeWidth="2" />
              <path d="M300 152l-9 -6v12z" fill="#173D68" />
              <path d="M560 152H632" stroke="#173D68" strokeWidth="2" />
              <path d="M640 152l-9 -6v12z" fill="#173D68" />
              <path d="M870 152H922" stroke="#173D68" strokeWidth="2" />
              <path d="M930 152l-9 -6v12z" fill="#173D68" />
              <rect x="214" y="48" width="196" height="30" rx="15" fill="#fff" stroke="#173D68" />
              <text x="312" y="68" fontSize="12" fontWeight="700" fill="#173D68" textAnchor="middle" letterSpacing="0.6">{t("d.k0656ecbd")}</text>
              <path d="M312 78V148" stroke="#173D68" strokeDasharray="3 3" />
              <text x="250" y="236" fontSize="13" fontWeight="500" fill="#5B6B7A" textAnchor="middle">{t("d.k67d70a5e")}</text>
              <text x="770" y="236" fontSize="13" fontWeight="500" fill="#5B6B7A" textAnchor="middle">{t("d.kb083aa7e")}</text>
              <g transform="translate(20,252)">
                <rect width="280" height="40" rx="4" fill="#fff" stroke="#D5DDE5" />
                <path d="M12 20h30M34 13l8 7-8 7" stroke="#173D68" strokeWidth="2" fill="none" />
                <text x="54" y="25" fontSize="13" fontWeight="600" fill="#173D68" textAnchor="start">{t("d.k825b3025")}</text>
              </g>
            </svg>
            <figcaption>
              <span>{t("d.k3e21ef8d")}</span>
              <span>{t("d.k6a247391")}</span>
            </figcaption>
          </figure>
        </div>
      </section>
      <section className="section" aria-labelledby="evi-h">
        <div className="wrap">
          <div className="section-head">
            <h2 id="evi-h" className="bar">{t("d.k67702740")}</h2>
            <p>{t("d.k5ba0a6af")}</p>
          </div>
          <div className="ev" role="group" aria-label={t("d.k25bf7c13")}>
            <div className="ev-c">
              <div className="k">{t("d.ka1111486")}</div>
              <div className="v">
                0.905
              </div>
              <div className="d">{t("d.k1aefcca7")}</div>
              <div className="scope">
                <span className="badge neutral">
                  <span>{t("d.k2c4c4d36")}</span>
                </span>
              </div>
            </div>
            <div className="ev-c">
              <div className="k">{t("d.kfe485c70")}</div>
              <div className="v">
                ~0.457
              </div>
              <div className="d">{t("d.k1aefcca7")}</div>
              <div className="scope">
                <span className="badge neutral">
                  <span>{t("d.k2c4c4d36")}</span>
                </span>
              </div>
            </div>
            <div className="ev-c">
              <div className="k">{t("d.k3ee7b8b0")}</div>
              <div className="v">
                0.673
              </div>
              <div className="d">{t("d.k1aefcca7")}</div>
              <div className="scope">
                <span className="badge neutral">
                  <span>{t("d.k2c4c4d36")}</span>
                </span>
              </div>
            </div>
            <div className="ev-c">
              <div className="k">{t("d.kc32a770e")}</div>
              <div className="v">
                0.749
              </div>
              <div className="d">{t("d.ke77e98dd")}</div>
              <div className="scope">
                <span className="badge warn">
                  <span>{t("d.kce1384b1")}</span>
                </span>
              </div>
            </div>
            <div className="ev-c">
              <div className="k">{t("d.k9313060a")}</div>
              <div className="v">
                88/88
              </div>
              <div className="d">{t("d.k81ce2f97")}</div>
              <div className="scope">
                <span className="badge neutral">
                  <span>{t("d.kabed0e2a")}</span>
                </span>
              </div>
            </div>
          </div>
          <div className="tablewrap" style={{ marginTop: "32px" }} tabIndex={0} role="region" aria-label={t("d.k6106e419")}>
            <table className="t">
              <thead>
                <tr>
                  <th scope="col">
                    <span>{t("d.k6ba0f11d")}</span>
                  </th>
                  <th scope="col">
                    <span>{t("d.k787143da")}</span>
                  </th>
                  <th scope="col">
                    <span>{t("d.kb8c27cbd")}</span>
                  </th>
                  <th scope="col">
                    <span>{t("d.ke4d85eec")}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td className="item">
                    <span>{t("d.ka1111486")}</span>
                  </td>
                  <td>
                    <span>{t("d.ke32db82d")}</span>
                  </td>
                  <td className="num">
                    <span>{t("d.ke97bd0f6")}</span>
                  </td>
                  <td>
                    <span>{t("d.k1aefcca7")}</span>
                  </td>
                </tr>
                <tr>
                  <td className="item">
                    <span>{t("d.k3db620ff")}</span>
                  </td>
                  <td>
                    <span>{t("d.k9382db30")}</span>
                  </td>
                  <td className="num">
                    <span>{t("d.k4a9a0b4c")}</span>
                  </td>
                  <td>
                    <span>{t("d.k1aefcca7")}</span>
                  </td>
                </tr>
                <tr>
                  <td className="item">
                    <span>{t("d.k9915bcbc")}</span>
                  </td>
                  <td>
                    <span>{t("d.k9382db30")}</span>
                  </td>
                  <td className="num">
                    <span>{t("d.kadb781c1")}</span>
                  </td>
                  <td>
                    <span>{t("d.k1aefcca7")}</span>
                  </td>
                </tr>
                <tr>
                  <td className="item">
                    <span>{t("d.kc32a770e")}</span>
                  </td>
                  <td>
                    <span>{t("d.k4d93439d")}</span>
                  </td>
                  <td className="num">
                    <span>{t("d.k26a14a42")}</span>
                  </td>
                  <td>
                    <span>{t("d.ke77e98dd")}</span>
                  </td>
                </tr>
                <tr>
                  <td className="item">
                    <span>{t("d.kb1486d05")}</span>
                  </td>
                  <td>
                    <span>{t("d.k54191341")}</span>
                  </td>
                  <td className="num">
                    <span>{t("d.k4bc7db30")}</span>
                  </td>
                  <td>
                    <span>{t("d.kf03502fd")}</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p className="note">
            <span>{t("d.k9e4e2e42")}</span>
          </p>
        </div>
      </section>
      <section className="section alt" aria-labelledby="sp-h">
        <div className="wrap">
          <div className="section-head">
            <h2 id="sp-h" className="bar">{t("d.k5f422a29")}</h2>
          </div>
          <div className="principles">
            <div className="principle">
              <svg className="" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                <rect x="5" y="11" width="14" height="10" rx="2" />
                <path d="M8 11V8a4 4 0 0 1 8 0v3" />
              </svg>
              <div>
                <h3>{t("d.k498e9062")}</h3>
                <p>{t("d.k9af5e2a7")}</p>
              </div>
            </div>
            <div className="principle">
              <svg className="" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                <path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z" />
                <circle cx="12" cy="12" r="3" />
              </svg>
              <div>
                <h3>{t("d.kfa41a3ff")}</h3>
                <p>{t("d.k9fe5b31e")}</p>
              </div>
            </div>
            <div className="principle">
              <svg className="" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                <path d="M4 7l8-4 8 4v10l-8 4-8-4z" strokeDasharray="3 3" />
                <circle cx="12" cy="12" r="2" />
              </svg>
              <div>
                <h3>{t("d.k33eb3a38")}</h3>
                <p dangerouslySetInnerHTML={{ __html: t("d.kea937318") }} />
              </div>
            </div>
            <div className="principle">
              <svg className="" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                <rect x="7" y="2" width="10" height="20" rx="2" />
                <path d="M11 18h2" />
              </svg>
              <div>
                <h3>{t("d.k3e9f21e4")}</h3>
                <p dangerouslySetInnerHTML={{ __html: t("d.kcc42128d") }} />
              </div>
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
              <Link href="/ops" className="btn btn-outline-light">
                <span>{t("d.k1abad565")}</span>
              </Link>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
