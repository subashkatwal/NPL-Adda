import { useEffect, useRef } from "react";

import { usePrefs, useT } from "../lib/prefs.js";

const CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;
let gisPromise = null;

/** Load Google Identity Services once. */
function loadGis() {
  gisPromise ??= new Promise((resolve, reject) => {
    if (window.google?.accounts?.id) return resolve(window.google);
    const script = Object.assign(document.createElement("script"), {
      src: "https://accounts.google.com/gsi/client", async: true, defer: true,
    });
    script.onload = () => resolve(window.google);
    script.onerror = () => {
      gisPromise = null;
      reject(new Error("Google sign-in could not load."));
    };
    document.head.appendChild(script);
  });
  return gisPromise;
}

/**
 * Google's official button. It returns a signed ID token ("credential") which the backend
 * verifies; the browser never sees a client secret or access token.
 */
export default function GoogleButton({ onCredential, onError, text = "continue_with" }) {
  const t = useT();
  const { theme } = usePrefs();
  const ref = useRef(null);
  const handler = useRef(onCredential);
  handler.current = onCredential;

  useEffect(() => {
    if (!CLIENT_ID) return undefined;
    let cancelled = false;
    loadGis()
      .then((google) => {
        if (cancelled || !ref.current) return;
        google.accounts.id.initialize({
          client_id: CLIENT_ID,
          callback: (response) => handler.current(response.credential),
          ux_mode: "popup",
          auto_select: false,
        });
        ref.current.innerHTML = "";
        google.accounts.id.renderButton(ref.current, {
          theme: theme === "dark" ? "filled_black" : "outline", size: "large", text, shape: "rectangular",
          width: Math.min(360, ref.current.offsetWidth || 320),
        });
      })
      .catch((err) => onError?.(err));
    return () => {
      cancelled = true;
    };
  }, [theme, text, onError]);

  if (!CLIENT_ID) {
    return (
      <div className="google-off">
        <button type="button" className="btn google-btn" disabled>
          <GoogleMark /> {t("auth.google")}
        </button>
        <p className="meta">{t("auth.googleOff")}</p>
      </div>
    );
  }
  return <div ref={ref} className="google-slot" />;
}

function GoogleMark() {
  return (
    <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden>
      <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.3 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3 0 5.8 1.1 7.9 3l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z" />
      <path fill="#FF3D00" d="m6.3 14.7 6.6 4.8C14.7 15.1 19 12 24 12c3 0 5.8 1.1 7.9 3l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
      <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z" />
      <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z" />
    </svg>
  );
}
