import { createContext, useContext } from "react";

import { STRINGS } from "../i18n/strings.js";

export const PrefsContext = createContext({ lang: "en", theme: "dark", setLang: () => {}, setTheme: () => {} });

export const usePrefs = () => useContext(PrefsContext);

/** Translate a key with {placeholders}; Nepali falls back to English for missing keys. */
export function translate(lang, key, vars = {}) {
  const template = STRINGS[lang]?.[key] ?? STRINGS.en[key] ?? key;
  return template.replace(/\{(\w+)\}/g, (_, name) => (vars[name] ?? `{${name}}`));
}

export function useT() {
  const { lang } = usePrefs();
  return (key, vars) => translate(lang, key, vars);
}

export function readPref(key, fallback) {
  try {
    return localStorage.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
}

export function writePref(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* storage unavailable; the preference lasts for this page only */
  }
}
