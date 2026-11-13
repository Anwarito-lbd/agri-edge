"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { LANG_COOKIE, parseLang, translate, type Key, type Lang } from "@/lib/i18n";

type I18n = {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: Key, vars?: Record<string, string | number>) => string;
};

const Ctx = createContext<I18n>({
  lang: "en",
  setLang: () => {},
  t: (key, vars) => translate("en", key, vars),
});

function readCookie(): Lang | undefined {
  if (typeof document === "undefined") return undefined;
  const m = document.cookie.match(new RegExp(`(?:^|; )${LANG_COOKIE}=([^;]*)`));
  return parseLang(m?.[1]);
}

export function I18nProvider({ children }: { children: ReactNode }) {
  // Server render and first client render agree on English; the saved or
  // browser language is applied after hydration.
  const [lang, setLangState] = useState<Lang>("en");

  useEffect(() => {
    const saved = readCookie();
    const browser = navigator.language?.toLowerCase().startsWith("fr") ? "fr" : undefined;
    const next = saved ?? browser;
    if (next && next !== "en") {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time sync with the browser
      setLangState(next);
    }
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const setLang = useCallback((l: Lang) => {
    document.cookie = `${LANG_COOKIE}=${l}; path=/; max-age=31536000; samesite=lax`;
    setLangState(l);
  }, []);

  const value = useMemo<I18n>(
    () => ({ lang, setLang, t: (key, vars) => translate(lang, key, vars) }),
    [lang, setLang],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useI18n(): I18n {
  return useContext(Ctx);
}

export function LanguageToggle({ className }: { className?: string }) {
  const { lang, setLang, t } = useI18n();
  return (
    <button
      type="button"
      className={className}
      onClick={() => setLang(lang === "en" ? "fr" : "en")}
      lang={lang === "en" ? "fr" : "en"}
      aria-label={lang === "en" ? "Afficher en français" : "Show in English"}
    >
      {t("lang.toggle")}
    </button>
  );
}
