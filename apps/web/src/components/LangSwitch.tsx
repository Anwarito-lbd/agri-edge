"use client";

import { useI18n } from "@/components/I18nProvider";
import type { Key } from "@/lib/i18n";

/** The design's EN | FR pair (aria-pressed buttons). Uses the same cookie as LanguageToggle. */
export function LangSwitch({ label = "d.ke14b7c7e" }: { label?: Key }) {
  const { lang, setLang, t } = useI18n();
  return (
    <div className="lang" role="group" aria-label={t(label)}>
      <button type="button" lang="en" aria-pressed={lang === "en"} onClick={() => setLang("en")}>
        EN
      </button>
      <i aria-hidden="true">|</i>
      <button type="button" lang="fr" aria-pressed={lang === "fr"} onClick={() => setLang("fr")}>
        FR
      </button>
    </div>
  );
}
