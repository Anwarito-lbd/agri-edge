"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { useI18n } from "@/components/I18nProvider";

export function HomeContent() {
  const { t } = useI18n();
  const [aud, setAud] = useState<"grower" | "investor">("investor");

  // Deep link: /?aud=grower. The choice lives in the URL only (no storage, no analytics).
  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("aud");
    // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time sync with the URL after hydration
    if (q === "grower" || q === "investor") setAud(q);
  }, []);

  const chooseAud = (a: "grower" | "investor", scroll = false) => {
    setAud(a);
    if (scroll) {
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      document.getElementById("path")?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
      document.getElementById("path")?.focus({ preventScroll: true });
    }
    const url = new URL(window.location.href);
    url.searchParams.set("aud", a);
    window.history.replaceState(null, "", url.toString());
  };
  return (
    <div className="v2">
      <section className="hero" aria-labelledby="h1">
        <div className="wrap grid">
          <div>
            <div className="eyebrow">{t("d.k0365c256")}</div>
            <h1 className="display" id="h1">{t("d.k88f07009")}</h1>
            <p className="lede">{t("d.k0e37f54c")}</p>
            <div className="btn-row">
              <Link href="/ops" className="btn btn-primary">
                <span>{t("d.k1abad565")}</span>
              </Link>
              <Link href="/about#contact" className="btn btn-secondary">
                <span>{t("d.k346e6246")}</span>
              </Link>
            </div>
            <p className="body-sm muted" style={{ marginTop: "24px" }}>
              <span>{t("d.k9e0abd0e")}</span>
              {" "}
              <button type="button" className="link-cta" style={{ padding: "0" }} onClick={() => chooseAud("grower", true)}>
                <span>{t("d.k659e764a")}</span>
              </button>
            </p>
          </div>
          <figure className="fig">
            <svg viewBox="0 0 640 520" role="img" aria-label={t("d.k789fcaf4")}>
              <rect width="640" height="520" fill="#EEF2F6" />
              <g stroke="#DFE6EC" strokeWidth="1" fill="none">
                <path d="M40 0V520" />
                <path d="M80 0V520" />
                <path d="M120 0V520" />
                <path d="M160 0V520" />
                <path d="M240 0V520" />
                <path d="M280 0V520" />
                <path d="M320 0V520" />
                <path d="M360 0V520" />
                <path d="M440 0V520" />
                <path d="M480 0V520" />
                <path d="M520 0V520" />
                <path d="M560 0V520" />
                <path d="M0 40 H640" />
                <path d="M0 80 H640" />
                <path d="M0 120 H640" />
                <path d="M0 160 H640" />
                <path d="M0 240 H640" />
                <path d="M0 280 H640" />
                <path d="M0 320 H640" />
                <path d="M0 360 H640" />
                <path d="M0 440 H640" />
                <path d="M0 480 H640" />
              </g>
              <g stroke="#C3CED9" strokeWidth="1" fill="none">
                <path d="M200 0V520" />
                <path d="M400 0V520" />
                <path d="M600 0V520" />
                <path d="M0 200 H640" />
                <path d="M0 400 H640" />
              </g>
              <g stroke="#173D68" strokeWidth="1">
                <path d="M40 0v5 M40 520v-5" />
                <path d="M80 0v5 M80 520v-5" />
                <path d="M120 0v5 M120 520v-5" />
                <path d="M160 0v5 M160 520v-5" />
                <path d="M200 0v10 M200 520v-10" />
                <path d="M240 0v5 M240 520v-5" />
                <path d="M280 0v5 M280 520v-5" />
                <path d="M320 0v5 M320 520v-5" />
                <path d="M360 0v5 M360 520v-5" />
                <path d="M400 0v10 M400 520v-10" />
                <path d="M440 0v5 M440 520v-5" />
                <path d="M480 0v5 M480 520v-5" />
                <path d="M520 0v5 M520 520v-5" />
                <path d="M560 0v5 M560 520v-5" />
                <path d="M600 0v10 M600 520v-10" />
                <path d="M0 40h5 M640 40h-5" />
                <path d="M0 80h5 M640 80h-5" />
                <path d="M0 120h5 M640 120h-5" />
                <path d="M0 160h5 M640 160h-5" />
                <path d="M0 200h10 M640 200h-10" />
                <path d="M0 240h5 M640 240h-5" />
                <path d="M0 280h5 M640 280h-5" />
                <path d="M0 320h5 M640 320h-5" />
                <path d="M0 360h5 M640 360h-5" />
                <path d="M0 400h10 M640 400h-10" />
                <path d="M0 440h5 M640 440h-5" />
                <path d="M0 480h5 M640 480h-5" />
              </g>
              <text x="100.0" y="22" fontSize="11" fontWeight="600" fill="#5B6B7A" textAnchor="middle" className="minor" letterSpacing="1">
                A
              </text>
              <text x="300.0" y="22" fontSize="11" fontWeight="600" fill="#5B6B7A" textAnchor="middle" className="minor" letterSpacing="1">
                B
              </text>
              <text x="500.0" y="22" fontSize="11" fontWeight="600" fill="#5B6B7A" textAnchor="middle" className="minor" letterSpacing="1">
                C
              </text>
              <text x="16" y="104.0" fontSize="11" fontWeight="600" fill="#5B6B7A" textAnchor="middle" className="minor">
                1
              </text>
              <text x="16" y="304.0" fontSize="11" fontWeight="600" fill="#5B6B7A" textAnchor="middle" className="minor">
                2
              </text>
              <polygon points="120,130 500,96 556,318 462,424 138,402 76,266" fill="#3879C1" fillOpacity=".10" stroke="#173D68" strokeWidth="2" strokeDasharray="8 5" />
              <path className="draw" pathLength="1" d="M127.4 138.0 L500.6 138.0 L507.2 164.0 L119.0 164.0 L110.6 190.0 L513.7 190.0 L520.3 216.0 L102.2 216.0 L93.8 242.0 L526.8 242.0 L533.4 268.0 L86.9 268.0 L98.8 294.0 L539.9 294.0 L544.2 320.0 L110.6 320.0 L122.5 346.0 L521.2 346.0 L498.1 372.0 L134.3 372.0" fill="none" stroke="#225FA3" strokeWidth="1.5" />
              <circle cx="127" cy="138" r="6" fill="#006EB0" />
              <rect x="129" y="366" width="11" height="11" fill="#173D68" />
              <g className="pop" style={{ animationDelay: "1.20s" }}>
                <rect x="213" y="159" width="14" height="14" rx="2" fill="#fff" stroke="#173D68" strokeWidth="1.5" />
                <text x="231" y="157" fontSize="10" fontWeight="600" fill="#173D68" textAnchor="start" className="minor">
                  D01
                </text>
              </g>
              <g className="pop" style={{ animationDelay: "1.32s" }}>
                <rect x="323" y="185" width="14" height="14" rx="2" fill="#fff" stroke="#173D68" strokeWidth="1.5" />
                <text x="341" y="183" fontSize="10" fontWeight="600" fill="#173D68" textAnchor="start" className="minor">
                  D02
                </text>
              </g>
              <g className="pop" style={{ animationDelay: "1.44s" }}>
                <rect x="395" y="213" width="14" height="14" rx="2" fill="#fff" stroke="#173D68" strokeWidth="1.5" />
                <text x="413" y="211" fontSize="10" fontWeight="600" fill="#173D68" textAnchor="start" className="minor">
                  D03
                </text>
              </g>
              <g className="pop" style={{ animationDelay: "1.56s" }}>
                <rect x="273" y="239" width="14" height="14" rx="2" fill="#fff" stroke="#173D68" strokeWidth="1.5" />
                <text x="291" y="237" fontSize="10" fontWeight="600" fill="#173D68" textAnchor="start" className="minor">
                  D04
                </text>
              </g>
              <g className="pop" style={{ animationDelay: "1.68s" }}>
                <rect x="443" y="265" width="14" height="14" rx="2" fill="#fff" stroke="#173D68" strokeWidth="1.5" />
                <text x="461" y="263" fontSize="10" fontWeight="600" fill="#173D68" textAnchor="start" className="minor">
                  D05
                </text>
              </g>
              <g className="pop" style={{ animationDelay: "1.80s" }}>
                <rect x="203" y="291" width="14" height="14" rx="2" fill="#fff" stroke="#173D68" strokeWidth="1.5" />
                <text x="221" y="289" fontSize="10" fontWeight="600" fill="#173D68" textAnchor="start" className="minor">
                  D06
                </text>
              </g>
              <g className="pop" style={{ animationDelay: "1.92s" }}>
                <rect x="353" y="317" width="14" height="14" rx="2" fill="#fff" stroke="#173D68" strokeWidth="1.5" />
                <text x="371" y="315" fontSize="10" fontWeight="600" fill="#173D68" textAnchor="start" className="minor">
                  D07
                </text>
              </g>
              <g className="pop" style={{ animationDelay: "2.04s" }}>
                <rect x="283" y="343" width="14" height="14" rx="2" fill="#fff" stroke="#173D68" strokeWidth="1.5" />
                <text x="301" y="341" fontSize="10" fontWeight="600" fill="#173D68" textAnchor="start" className="minor">
                  D08
                </text>
              </g>
              <g stroke="#173D68" strokeWidth="1.2" fill="none">
                <circle cx="76" cy="266" r="6" />
                <path d="M82 266h16M70 266h-16M76 272v16M76 260v-16" />
              </g>
              <g stroke="#173D68" strokeWidth="1.2" fill="none">
                <circle cx="556" cy="318" r="6" />
                <path d="M562 318h16M550 318h-16M556 324v16M556 312v-16" />
              </g>
              <text x="84" y="112" fontSize="11" fontWeight="500" fill="#5B6B7A" textAnchor="start" className="minor">
                00°00′00″N
              </text>
              <text x="84" y="124" fontSize="11" fontWeight="500" fill="#5B6B7A" textAnchor="start" className="minor">
                000°00′00″W
              </text>
              <text x="300" y="90" fontSize="13" fontWeight="600" fill="#173D68" textAnchor="middle">{t("d.kc8261493")}</text>
              <g>
                <rect x="20" y="430" width="196" height="72" rx="4" fill="#fff" stroke="#D5DDE5" />
                <line x1="34" y1="450" x2="62" y2="450" stroke="#173D68" strokeWidth="2" strokeDasharray="6 4" />
                <text x="72" y="454" fontSize="12" fontWeight="500" fill="#173D68" textAnchor="start">{t("d.kc8261493")}</text>
                <line x1="34" y1="468" x2="62" y2="468" stroke="#225FA3" strokeWidth="1.5" />
                <text x="72" y="472" fontSize="12" fontWeight="500" fill="#173D68" textAnchor="start">{t("d.k7aab6b68")}</text>
                <rect x="41" y="478" width="10" height="10" rx="2" fill="#fff" stroke="#173D68" strokeWidth="1.5" />
                <text x="72" y="487" fontSize="12" fontWeight="500" fill="#173D68" textAnchor="start">{t("d.k9532ca80")}</text>
              </g>
              <g>
                <rect x="380" y="448" width="240" height="56" rx="4" fill="#fff" stroke="#173D68" />
                <path d="M380 470H620" stroke="#D5DDE5" />
                <text x="390" y="464" fontSize="11" fontWeight="700" fill="#173D68" textAnchor="start" letterSpacing="1">{t("d.kd60fbd14")}</text>
                <text x="390" y="489" fontSize="12" fontWeight="500" fill="#5B6B7A" textAnchor="start">{t("d.k0cf006f8")}</text>
              </g>
              <g transform="translate(596,44)" stroke="#173D68" strokeWidth="1.5" fill="none">
                <path d="M0 36V0M0 0l-6 11M0 0l6 11" />
              </g>
              <text x="596" y="98" fontSize="13" fontWeight="600" fill="#173D68" textAnchor="middle">
                N
              </text>
            </svg>
            <figcaption>
              <span>{t("d.k03571d50")}</span>
              <span>{t("d.k4e74aa62")}</span>
            </figcaption>
          </figure>
        </div>
      </section>
      <div className="aud" role="region" aria-label={t("d.ke2688c71")}>
        <div className="wrap">
          <span className="q">
            <span>{t("d.k3139b453")}</span>
          </span>
          <div className="seg" role="group" aria-label={t("d.k75ae7a53")}>
            <button type="button" onClick={() => chooseAud("grower")} aria-pressed={aud === "grower"}>
              <span>{t("d.kc534a398")}</span>
            </button>
            <button type="button" onClick={() => chooseAud("investor")} aria-pressed={aud === "investor"}>
              <span>{t("d.kba55615a")}</span>
            </button>
          </div>
        </div>
      </div>
      <section className="strip" aria-labelledby="stand-h">
        <div className="wrap">
          <div className="strip-head">
            <h2 className="eyebrow" id="stand-h">{t("d.kbf32588e")}</h2>
            <Link href="/vision" className="link-cta">
              <span>{t("d.kf2ffd65e")}</span>
            </Link>
          </div>
          <div className="strip-cells">
            <div className="strip-cell">
              <div className="eyebrow">
                <i className="pip" aria-hidden="true"></i>
                <span>{t("d.ke4d85eec")}</span>
              </div>
              <h3>{t("d.k6cd9877e")}</h3>
              <p>{t("d.kbb6982fd")}</p>
            </div>
            <div className="strip-cell">
              <div className="eyebrow">
                <i className="pip" aria-hidden="true"></i>
                <span>{t("d.kc833ff5f")}</span>
              </div>
              <h3>{t("d.k6c1bfbe7")}</h3>
              <p>{t("d.kb4bfc9f1")}</p>
            </div>
            <div className="strip-cell">
              <div className="eyebrow">
                <i className="pip hollow" aria-hidden="true"></i>
                <span>{t("d.k8cdd8702")}</span>
              </div>
              <h3>{t("d.k3ddac32a")}</h3>
              <p>{t("d.k46e6c995")}</p>
            </div>
            <div className="strip-cell">
              <div className="eyebrow">
                <i className="pip" aria-hidden="true"></i>
                <span>{t("d.kfde2f260")}</span>
              </div>
              <h3>{t("d.kbfd4d7b7")}</h3>
              <p>{t("d.k9c909f5a")}</p>
            </div>
          </div>
        </div>
      </section>
      <div id="path" tabIndex={-1}>
        <div hidden={aud !== "investor"} id="investor">
          <section className="section" aria-labelledby="prob-h">
            <div className="wrap">
              <div className="section-head">
                <h2 className="bar" id="prob-h">{t("d.k4e9fe7a4")}</h2>
                <p>{t("d.kb8332052")}</p>
              </div>
              <div className="problem">
                <div>
                  <div className="n">
                    01
                  </div>
                  <h3>{t("d.kc558a092")}</h3>
                  <p>{t("d.k75a4d9e3")}</p>
                </div>
                <div>
                  <div className="n">
                    02
                  </div>
                  <h3>{t("d.ka7c421d1")}</h3>
                  <p>{t("d.kbd4db0fc")}</p>
                </div>
                <div>
                  <div className="n">
                    03
                  </div>
                  <h3>{t("d.ke5500c17")}</h3>
                  <p>{t("d.k18b319f9")}</p>
                </div>
              </div>
            </div>
          </section>
          <section className="tiles" aria-label="Scout, plan, review">
            <div className="tile">
              <svg className="" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                <circle cx="12" cy="12" r="3" />
                <circle cx="12" cy="12" r="8" />
                <path d="M12 2v3M12 19v3M2 12h3M19 12h3" />
              </svg>
              <h3>{t("d.keac59431")}</h3>
              <p>{t("d.kc39ade99")}</p>
            </div>
            <div className="tile">
              <svg className="" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                <circle cx="5" cy="19" r="2" />
                <circle cx="19" cy="5" r="2" />
                <path d="M7 19h6a3 3 0 0 0 0-6h-2a3 3 0 0 1 0-6h6" />
              </svg>
              <h3>{t("d.kad029b61")}</h3>
              <p>{t("d.k768a43a8")}</p>
            </div>
            <div className="tile">
              <svg className="" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                <rect x="4" y="3" width="16" height="18" rx="2" />
                <path d="M8 8h8M8 12h8M8 16h4" />
                <path d="M14.5 17l1.5 1.5 3-3.5" />
              </svg>
              <h3>{t("d.k6f3f2994")}</h3>
              <p>{t("d.k2fc30460")}</p>
            </div>
          </section>
          <section className="section" aria-labelledby="ev-h">
            <div className="wrap">
              <div className="section-head">
                <h2 className="bar" id="ev-h">{t("d.kff3efdd7")}</h2>
                <p>{t("d.kce491bef")}</p>
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
              <p className="note">
                <span>{t("d.k74cf3bde")}</span>
              </p>
            </div>
          </section>
          <section className="section alt" aria-labelledby="saf-h">
            <div className="wrap">
              <div className="section-head">
                <h2 className="bar" id="saf-h">{t("d.k46db32a6")}</h2>
                <p>{t("d.kd5fba04a")}</p>
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
          <section className="section" aria-labelledby="stg-h">
            <div className="wrap">
              <div className="cols2" style={{ gap: "64px", alignItems: "start" }}>
                <div className="section-head" style={{ margin: "0" }}>
                  <h2 className="bar" id="stg-h">{t("d.kf60145ae")}</h2>
                  <p>{t("d.kcfe3e8dc")}</p>
                  <div style={{ marginTop: "24px" }}>
                    <Link href="/vision" className="link-cta">
                      <span>{t("d.k67326411")}</span>
                    </Link>
                  </div>
                </div>
                <div>
                  <div className="card">
                    <h3>
                      <span>{t("d.k17120444")}</span>
                    </h3>
                    <ul className="check-list no">
                      <li>
                        <svg className="" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                          <path d="M6 6l12 12M18 6L6 18" />
                        </svg>
                        <span>{t("d.k12ef97d1")}</span>
                      </li>
                      <li>
                        <svg className="" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                          <path d="M6 6l12 12M18 6L6 18" />
                        </svg>
                        <span>{t("d.k17259f5e")}</span>
                      </li>
                      <li>
                        <svg className="" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                          <path d="M6 6l12 12M18 6L6 18" />
                        </svg>
                        <span>{t("d.k7c0b8ea5")}</span>
                      </li>
                      <li>
                        <svg className="" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                          <path d="M6 6l12 12M18 6L6 18" />
                        </svg>
                        <span>{t("d.k6041f068")}</span>
                      </li>
                    </ul>
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
                    <span>{t("d.kdbbb55a2")}</span>
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
        <div hidden={aud !== "grower"} id="grower">
          <section className="section paper" aria-labelledby="gl-h">
            <div className="wrap">
              <div className="section-head">
                <h2 className="bar" id="gl-h">{t("d.k193c027a")}</h2>
                <p>{t("d.kf07b57c1")}</p>
              </div>
              <div className="look">
                <div className="item">
                  <svg className="" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                    <rect x="4" y="4" width="6" height="6" rx="1" />
                    <rect x="14" y="9" width="6" height="6" rx="1" />
                    <rect x="6" y="15" width="6" height="6" rx="1" />
                  </svg>
                  <h3>{t("d.k62497cc0")}</h3>
                  <p>{t("d.kad44e8cb")}</p>
                </div>
                <div className="item">
                  <svg className="" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                    <path d="M4 8l4-4M4 14l10-10M4 20L20 4M10 20l10-10M16 20l4-4" />
                    <path d="M3 3h18v18H3z" />
                  </svg>
                  <h3>{t("d.kda2aefc4")}</h3>
                  <p>{t("d.kf6aa3f21")}</p>
                </div>
                <div className="item">
                  <svg className="" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                    <circle cx="6" cy="6" r="1.6" />
                    <circle cx="12" cy="6" r="1.6" />
                    <circle cx="18" cy="6" r="1.6" />
                    <circle cx="6" cy="12" r="1.6" />
                    <circle cx="12" cy="12" r="1.6" />
                    <circle cx="18" cy="12" r="1.6" />
                    <circle cx="9" cy="18" r="1.6" />
                    <circle cx="15" cy="18" r="1.6" />
                  </svg>
                  <h3>{t("d.kd10b5481")}</h3>
                  <p>{t("d.k2e4b346d")}</p>
                </div>
              </div>
              <p className="note">
                <span>{t("d.ka93fa509")}</span>
              </p>
            </div>
          </section>
          <section className="section paper" style={{ paddingTop: "0" }} aria-labelledby="gs-h">
            <div className="wrap">
              <div className="you">
                <div>
                  <h3 id="gs-h">{t("d.k823a558d")}</h3>
                  <ul className="check-list">
                    <li>
                      <svg className="" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                        <path d="M5 12.5l4.5 4.5L19 7.5" />
                      </svg>
                      <span>{t("d.k37a9d77d")}</span>
                    </li>
                    <li>
                      <svg className="" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                        <path d="M5 12.5l4.5 4.5L19 7.5" />
                      </svg>
                      <span>{t("d.kd8c4e790")}</span>
                    </li>
                    <li>
                      <svg className="" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                        <path d="M5 12.5l4.5 4.5L19 7.5" />
                      </svg>
                      <span>{t("d.k87deef93")}</span>
                    </li>
                  </ul>
                </div>
                <div>
                  <h3>{t("d.k42254f4b")}</h3>
                  <ul className="check-list">
                    <li>
                      <svg className="" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                        <path d="M7 11V6a1.5 1.5 0 0 1 3 0v4M10 10V4.5a1.5 1.5 0 0 1 3 0V10M13 10V5.5a1.5 1.5 0 0 1 3 0V12M16 11a1.5 1.5 0 0 1 3 0v4a6 6 0 0 1-6 6h-1a6 6 0 0 1-5-3l-3-4a1.5 1.5 0 0 1 2.3-1.9L7 14" />
                      </svg>
                      <span>{t("d.k151eaa96")}</span>
                    </li>
                    <li>
                      <svg className="" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                        <path d="M7 11V6a1.5 1.5 0 0 1 3 0v4M10 10V4.5a1.5 1.5 0 0 1 3 0V10M13 10V5.5a1.5 1.5 0 0 1 3 0V12M16 11a1.5 1.5 0 0 1 3 0v4a6 6 0 0 1-6 6h-1a6 6 0 0 1-5-3l-3-4a1.5 1.5 0 0 1 2.3-1.9L7 14" />
                      </svg>
                      <span>{t("d.k9822dca3")}</span>
                    </li>
                    <li>
                      <svg className="" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                        <path d="M7 11V6a1.5 1.5 0 0 1 3 0v4M10 10V4.5a1.5 1.5 0 0 1 3 0V10M13 10V5.5a1.5 1.5 0 0 1 3 0V12M16 11a1.5 1.5 0 0 1 3 0v4a6 6 0 0 1-6 6h-1a6 6 0 0 1-5-3l-3-4a1.5 1.5 0 0 1 2.3-1.9L7 14" />
                      </svg>
                      <span>{t("d.k8029805f")}</span>
                    </li>
                  </ul>
                </div>
              </div>
            </div>
          </section>
          <section className="section paper" style={{ paddingTop: "0" }} aria-labelledby="ctl-h">
            <div className="wrap">
              <div className="section-head" style={{ marginBottom: "32px" }}>
                <h2 className="bar" id="ctl-h">{t("d.kb8862490")}</h2>
              </div>
              <div className="principles">
                <div className="principle">
                  <svg className="" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                    <rect x="5" y="11" width="14" height="10" rx="2" />
                    <path d="M8 11V8a4 4 0 0 1 8 0v3" />
                  </svg>
                  <div>
                    <h3>{t("d.k4004473a")}</h3>
                    <p>{t("d.k462302f7")}</p>
                  </div>
                </div>
                <div className="principle">
                  <svg className="" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                    <path d="M4 7l8-4 8 4v10l-8 4-8-4z" strokeDasharray="3 3" />
                    <circle cx="12" cy="12" r="2" />
                  </svg>
                  <div>
                    <h3>{t("d.k785cf522")}</h3>
                    <p>{t("d.k64fab25a")}</p>
                  </div>
                </div>
                <div className="principle">
                  <svg className="" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                    <rect x="7" y="2" width="10" height="20" rx="2" />
                    <path d="M11 18h2" />
                  </svg>
                  <div>
                    <h3>{t("d.k71a62c10")}</h3>
                    <p>{t("d.kb441476c")}</p>
                  </div>
                </div>
                <div className="principle">
                  <svg className="" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                    <circle cx="12" cy="8" r="4" />
                    <path d="M4 21c0-4 4-6 8-6s8 2 8 6" />
                  </svg>
                  <div>
                    <h3>{t("d.kdfafce46")}</h3>
                    <p>{t("d.k42981fb5")}</p>
                  </div>
                </div>
              </div>
            </div>
          </section>
          <section className="section paper" style={{ paddingTop: "0" }}>
            <div className="wrap">
              <div className="jump paper">
                <p>{t("d.kb45fa15d")}</p>
                <div className="btn-row">
                  <Link href="/ops" className="btn btn-secondary">
                    <span>{t("d.k1abad565")}</span>
                  </Link>
                  <Link href="/about#contact" className="btn btn-primary">
                    <span>{t("d.k346e6246")}</span>
                  </Link>
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
                    <span>{t("d.kb7bcf612")}</span>
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
      </div>
    </div>
  );
}
