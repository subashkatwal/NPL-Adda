import { useEffect, useState } from "react";

import { PrefsContext, readPref, writePref } from "./prefs.js";

const LANG_KEY = "npl-adda.lang";
const THEME_KEY = "npl-adda.theme";

function systemTheme() {
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

/** Language (en/ne) and theme (light/dark), persisted per browser and reflected on <html>. */
export function PrefsProvider({ children }) {
  const [lang, setLang] = useState(() => readPref(LANG_KEY, "en"));
  const [theme, setTheme] = useState(() => readPref(THEME_KEY, null) ?? systemTheme());

  useEffect(() => {
    document.documentElement.lang = lang === "ne" ? "ne" : "en";
    writePref(LANG_KEY, lang);
  }, [lang]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    writePref(THEME_KEY, theme);
  }, [theme]);

  return <PrefsContext.Provider value={{ lang, setLang, theme, setTheme }}>{children}</PrefsContext.Provider>;
}
