import { ArrowRight } from "lucide-react";
import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";

import { useT } from "../lib/prefs.js";

const prefersReducedMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/**
 * Landing hero: the photo drifts slowly, shifts with the pointer or finger (parallax)
 * and a soft floodlight glow follows it. Motion is skipped for reduced-motion users.
 */
export default function Hero({ to, label }) {
  const t = useT();
  const ref = useRef(null);
  const frame = useRef(0);

  useEffect(() => () => cancelAnimationFrame(frame.current), []);

  function track(event) {
    const el = ref.current;
    if (!el || prefersReducedMotion()) return;
    const rect = el.getBoundingClientRect();
    const x = (event.clientX - rect.left) / rect.width;
    const y = (event.clientY - rect.top) / rect.height;
    cancelAnimationFrame(frame.current);
    frame.current = requestAnimationFrame(() => {
      el.style.setProperty("--px", (x * 2 - 1).toFixed(3));
      el.style.setProperty("--py", (y * 2 - 1).toFixed(3));
      el.style.setProperty("--mx", `${(x * 100).toFixed(1)}%`);
      el.style.setProperty("--my", `${(y * 100).toFixed(1)}%`);
      el.classList.add("is-tracking");
    });
  }

  function reset() {
    const el = ref.current;
    if (!el) return;
    cancelAnimationFrame(frame.current);
    el.style.setProperty("--px", "0");
    el.style.setProperty("--py", "0");
    el.classList.remove("is-tracking");
  }

  return (
    <section ref={ref} className="hero" onPointerMove={track} onPointerDown={track} onPointerLeave={reset}
      onPointerCancel={reset}>
      <div className="hero-bg" aria-hidden />
      <div className="hero-light" aria-hidden />
      <div className="hero-shade" aria-hidden />
      <div className="hero-copy">
        <p className="eyebrow">{t("hero.eyebrow")}</p>
        <h1>
          <span className="line">{t("hero.line1")}</span>
          <span className="line accent">{t("hero.line2")}</span>
        </h1>
        <p className="lede">{t("hero.lede")}</p>
        <Link className="btn btn-primary btn-hero" to={to}>
          {label} <ArrowRight size={20} aria-hidden />
        </Link>
      </div>
      <a className="scroll-cue" href="#teams" aria-label={t("hero.scroll")}>
        <svg viewBox="0 0 32 32" width="28" height="28" aria-hidden>
          <circle cx="16" cy="16" r="13" fill="#C8102E" />
          <path d="M8 6.5c4 5 4 14 0 19M24 6.5c-4 5-4 14 0 19" stroke="#F5F7FA" strokeWidth="1.4" fill="none"
            strokeDasharray="2 2" />
        </svg>
      </a>
    </section>
  );
}
