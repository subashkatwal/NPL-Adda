import { Download, ImagePlus, Loader2, RefreshCw, Send, Share2, Sparkles, Wand2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { ErrorState, Loading, LoginPrompt, Select } from "../../components/ui.jsx";
import { results } from "../../lib/api.js";
import { useAuth } from "../../lib/authContext.js";
import { useFan } from "../../lib/fanContext.js";
import { useFeedback } from "../../lib/feedbackContext.js";
import { timeAgo } from "../../lib/format.js";
import { usePrefs } from "../../lib/prefs.js";
import { downloadBlob, shareCard } from "../../lib/share.js";
import { useApi } from "../../lib/useApi.js";
import { memeService } from "../../services/memelab.js";

const STYLES = { funny: "Funny", roast: "Roast", rivalry: "Rivalry", reaction: "Reaction", fan_pain: "Fan pain" };
const LANGS = { en: "English", ne: "नेपाली", ne_rom: "Romanized Nepali", mixed: "Mix" };
const COLORS = ["#F5F7FA", "#C8FF4D", "#FF7043", "#FFD54F", "#0B1020"];
const DEFAULT_STYLE = {
  top_y: 0.04, bottom_y: 0.78, size: 1, top_size: 1, bottom_size: 1, color: "#F5F7FA", align: "center",
  font: "bold", caps: true, outline: true, band: false, collage: "single",
};
const FONTS = { bold: "Bold", display: "Display", italic: "Italic punch", serif: "Serif", mono: "Typewriter", clean: "Clean" };
const COLLAGES = { single: ["One photo", 1], side: ["Side by side", 2], stack: ["Top & bottom", 2], grid: ["2 × 2 grid", 4] };
const STATUS_LABEL = { draft: "Draft", pending_review: "In review", approved: "Approved", published: "Live", rejected: "Not approved" };
const MAX_UPLOAD = 5 * 1024 * 1024;

function useDebounced(value, ms) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export default function Create() {
  const { user } = useAuth();
  const { profile } = useFan();
  if (!user) return <LoginPrompt message="Log in to make memes. Browsing is open to everyone." />;
  if (!profile) {
    return <p className="state">Pick your team first so your memes count for it. <Link className="text-link" to="/choose-team">Choose a team →</Link></p>;
  }
  return <Editor profile={profile} />;
}

function Editor({ profile }) {
  const { lang } = usePrefs();
  const { notify, confirm } = useFeedback();
  const templates = results(useApi("/memelab/templates").data);
  const teams = results(useApi("/teams").data);
  const captionStatus = useApi("/memelab/caption-status").data;
  const [teamId, setTeamId] = useState(profile.current_team?.id ?? "");
  const matches = results(useApi(teamId ? `/matches?team=${teamId}&ordering=-starts_at` : null).data);
  const [matchId, setMatchId] = useState("");
  const [templateId, setTemplateId] = useState(null);
  const [upload, setUpload] = useState(null);
  const [extras, setExtras] = useState([]);  // more photos for a collage (up to 3)
  const [top, setTop] = useState("");
  const [bottom, setBottom] = useState("");
  const [style, setStyle] = useState(DEFAULT_STYLE);
  const [language, setLanguage] = useState(lang === "ne" ? "ne" : "en");
  const [preview, setPreview] = useState({ url: null, blob: null, loading: false, error: null });
  const [busy, setBusy] = useState(null);
  const [mine, setMine] = useState({ items: null, version: 0 });
  const fileRef = useRef(null);

  const template = templates.find((t) => t.id === templateId) ?? templates[0];
  const renderBody = useMemo(() => ({
    template: upload ? null : template?.id ?? null, upload: upload?.id ?? null, team: teamId || null,
    top_text: top, bottom_text: bottom, text_style: style,
    extra_uploads: style.collage === "single" ? [] : extras.map((x) => x.id),
  }), [upload, template, teamId, top, bottom, style, extras]);
  const debounced = useDebounced(renderBody, 450);

  useEffect(() => {
    if (!debounced.template && !debounced.upload && !debounced.extra_uploads.length) return undefined;
    const controller = new AbortController();
    setPreview((p) => ({ ...p, loading: true, error: null }));
    memeService.render(debounced, controller.signal)
      .then((blob) => setPreview((p) => {
        if (p.url) URL.revokeObjectURL(p.url);
        return { url: URL.createObjectURL(blob), blob, loading: false, error: null };
      }))
      .catch((error) => {
        if (error.name !== "AbortError") setPreview((p) => ({ ...p, loading: false, error }));
      });
    return () => controller.abort();
  }, [debounced]);

  useEffect(() => {
    memeService.drafts().then((d) => setMine({ items: results(d), version: 0 })).catch(() => setMine({ items: [], version: 0 }));
  }, [mine.version]);

  async function uploadFile(file) {
    if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) throw new Error("Use a JPEG, PNG or WebP image.");
    if (file.size > MAX_UPLOAD) throw new Error("Images must be 5 MB or smaller.");
    return memeService.upload(file);
  }

  /** Main photo, or (for collages) more photos; several files can be picked at once. */
  async function onFile(e) {
    const files = [...(e.target.files ?? [])];
    e.target.value = "";
    if (!files.length) return;
    const slots = COLLAGES[style.collage][1];
    setBusy("upload");
    try {
      const done = [];
      for (const file of files.slice(0, Math.max(1, slots))) done.push(await uploadFile(file));
      const [first, ...rest] = upload ? [upload, ...done] : done;
      setUpload(first);
      if (rest.length) setExtras((x) => [...x, ...rest].slice(0, 3));
      notify({ text: `${done.length === 1 ? "Photo" : `${done.length} photos`} ready. Checked and cleaned on our server.` });
    } catch (err) {
      notify({ type: "error", text: err.data?.image?.[0] ?? err.data?.image ?? err.message });
    } finally {
      setBusy(null);
    }
  }

  function removePhoto(index) {
    if (index === 0) {
      const [next, ...rest] = extras;
      setUpload(next ?? null);
      setExtras(rest);
    } else {
      setExtras((x) => x.filter((_, i) => i !== index - 1));
    }
  }

  const draftBody = () => ({
    template: template?.id ?? null, upload: upload?.id ?? null, team: teamId || null, match: matchId || null,
    top_text: top.trim(), bottom_text: bottom.trim(), text_style: style, language,
    extra_uploads: style.collage === "single" ? [] : extras.map((x) => x.id),
  });

  async function saveDraft() {
    return memeService.createDraft(draftBody());
  }

  function textError() {
    if (!top.trim() && !bottom.trim()) return "Add a top or bottom caption first.";
    return null;
  }

  async function publish() {
    if (textError()) return notify({ type: "error", text: textError() });
    const ok = await confirm({
      title: "Publish this meme?",
      message: "It goes live in Meme Zone right away. You can't edit it afterwards, but you can delete it.",
      confirmLabel: "Publish",
    });
    if (!ok) return;
    setBusy("publish");
    try {
      const draft = await saveDraft();
      const post = await memeService.submitDraft(draft.id);
      notify({ text: post.status === "published" ? "Your meme is live!" : "Sent for review. You'll see it in the feed once approved." });
      setTop("");
      setBottom("");
      setMine((m) => ({ ...m, version: m.version + 1 }));
    } catch (err) {
      const fields = err.data && typeof err.data === "object" ? Object.values(err.data).flat().join(" ") : "";
      notify({ type: "error", text: err.data?.code === "duplicate_content" ? "A very similar meme already exists - make it yours!" : fields || err.message });
    } finally {
      setBusy(null);
    }
  }

  async function download() {
    if (textError()) return notify({ type: "error", text: textError() });
    setBusy("download");
    try {
      const draft = await saveDraft();
      downloadBlob(await memeService.draftImage(draft.id), "npl-adda-meme.jpg");
      setMine((m) => ({ ...m, version: m.version + 1 }));
    } catch (err) {
      notify({ type: "error", text: err.message });
    } finally {
      setBusy(null);
    }
  }

  async function share() {
    if (!preview.blob) return;
    const outcome = await shareCard({ blob: preview.blob, fileName: "npl-adda-meme.jpg", title: "NPL Adda meme",
      text: [top, bottom].filter(Boolean).join(" / "), url: `${window.location.origin}/meme-zone` });
    if (outcome !== "cancelled") notify({ text: outcome.startsWith("shared") ? "Shared." : "Downloaded - share it anywhere." });
  }

  const setS = (k, v) => setStyle((s) => ({ ...s, [k]: v }));

  return (
    <div className="mz-lab">
      <div className="mz-lab-controls">
        <section className="mz-panel">
          <h2>1 · Background</h2>
          <div className="mz-templates" role="radiogroup" aria-label="Templates">
            {templates.map((t) => (
              <button key={t.id} type="button" role="radio" aria-checked={!upload && template?.id === t.id}
                className={!upload && template?.id === t.id ? "is-on" : ""} onClick={() => { setUpload(null); setTemplateId(t.id); }}>
                <span className={`mz-tpl mz-tpl-${t.layout_config?.background ?? "scoreboard"}`} aria-hidden />
                {t.name}
              </button>
            ))}
            <button type="button" className={`mz-upload ${upload ? "is-on" : ""}`} onClick={() => fileRef.current?.click()} disabled={busy === "upload"}>
              {busy === "upload" ? <Loader2 className="spin" size={18} aria-hidden /> : upload
                ? <img src={upload.image_url} alt="" /> : <ImagePlus size={20} aria-hidden />}
              {upload ? "Your photo" : "Upload photo"}
            </button>
            <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" multiple hidden onChange={onFile} />
          </div>
          <div className="mz-collage" role="radiogroup" aria-label="Photo layout">
            {Object.entries(COLLAGES).map(([value, [label, n]]) => (
              <button key={value} type="button" role="radio" aria-checked={style.collage === value}
                className={style.collage === value ? "is-on" : ""} onClick={() => setS("collage", value)}>
                <span className={`mz-collage-icon mz-collage-${value}`} aria-hidden>{Array.from({ length: n }, (_, i) => <i key={i} />)}</span>
                {label}
              </button>
            ))}
          </div>
          {style.collage !== "single" && (
            <ul className="mz-photo-slots" aria-label="Collage photos">
              {Array.from({ length: COLLAGES[style.collage][1] }, (_, i) => {
                const photo = i === 0 ? upload : extras[i - 1];
                return (
                  <li key={i}>
                    {photo ? (
                      <>
                        <img src={photo.image_url} alt={`Photo ${i + 1}`} />
                        <button type="button" className="mz-slot-remove" aria-label={`Remove photo ${i + 1}`} onClick={() => removePhoto(i)}>×</button>
                      </>
                    ) : (
                      <button type="button" className="mz-slot-add" onClick={() => fileRef.current?.click()} disabled={busy === "upload"}>
                        <ImagePlus size={18} aria-hidden /> Add photo {i + 1}
                      </button>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
          <p className="meta">Only upload images you own or have permission to use. JPEG/PNG/WebP, max 5 MB each. You can pick several at once.</p>
        </section>

        <section className="mz-panel">
          <h2>2 · Captions</h2>
          <div className="mz-langs" role="radiogroup" aria-label="Language">
            {Object.entries(LANGS).map(([v, l]) => (
              <button key={v} type="button" role="radio" aria-checked={language === v} className={language === v ? "is-on" : ""}
                onClick={() => setLanguage(v)}>{l}</button>
            ))}
          </div>
          <label>Top text
            <input value={top} maxLength={140} onChange={(e) => setTop(e.target.value)} placeholder="When the toss is delayed…" />
          </label>
          <label>Bottom text
            <input value={bottom} maxLength={140} onChange={(e) => setBottom(e.target.value)} placeholder="…and the chai is finished" />
          </label>
          <div className="mz-fonts" role="radiogroup" aria-label="Font">
            {Object.entries(FONTS).map(([value, label]) => (
              <button key={value} type="button" role="radio" aria-checked={style.font === value}
                className={`mz-font-${value} ${style.font === value ? "is-on" : ""}`} onClick={() => setS("font", value)}>
                {label}
              </button>
            ))}
          </div>
          <div className="mz-sliders">
            <label>Top size <output>{Math.round(style.top_size * 100)}%</output>
              <input type="range" min="0.5" max="2" step="0.05" value={style.top_size} onChange={(e) => setS("top_size", Number(e.target.value))} /></label>
            <label>Bottom size <output>{Math.round(style.bottom_size * 100)}%</output>
              <input type="range" min="0.5" max="2" step="0.05" value={style.bottom_size} onChange={(e) => setS("bottom_size", Number(e.target.value))} /></label>
            <label>Top position<input type="range" min="0" max="0.5" step="0.01" value={style.top_y} onChange={(e) => setS("top_y", Number(e.target.value))} /></label>
            <label>Bottom position<input type="range" min="0.5" max="0.95" step="0.01" value={style.bottom_y} onChange={(e) => setS("bottom_y", Number(e.target.value))} /></label>
          </div>
          <div className="mz-toggles">
            {[["caps", "ALL CAPS"], ["outline", "Black outline"], ["band", "Dark band behind text"]].map(([key, label]) => (
              <label key={key} className="mz-toggle">
                <input type="checkbox" checked={style[key]} onChange={(e) => setS(key, e.target.checked)} /> {label}
              </label>
            ))}
          </div>
          <div className="mz-colors" role="radiogroup" aria-label="Text colour">
            {COLORS.map((c) => (
              <button key={c} type="button" role="radio" aria-checked={style.color === c} aria-label={c}
                className={style.color === c ? "is-on" : ""} style={{ background: c }} onClick={() => setS("color", c)} />
            ))}
            <Select value={style.align} onChange={(e) => setS("align", e.target.value)} aria-label="Alignment">
              <option value="center">Centre</option><option value="left">Left</option><option value="right">Right</option>
            </Select>
          </div>
        </section>

        <AiPanel status={captionStatus} teams={teams} teamId={teamId} setTeamId={setTeamId} matches={matches}
          matchId={matchId} setMatchId={setMatchId} language={language}
          onPick={(o) => { setTop(o.top); setBottom(o.bottom); }} />
      </div>

      <aside className="mz-lab-preview">
        {/* On phones this dock pins to the top so every edit is visible without scrolling back up. */}
        <div className="mz-preview-dock">
          <div className="mz-preview-frame" aria-live="polite">
            {preview.url ? <img src={preview.url} alt="Meme preview" /> : <Loading label="Drawing preview" />}
            {preview.loading && preview.url && <span className="mz-preview-busy"><Loader2 className="spin" size={16} aria-hidden /></span>}
          </div>
          <div className="actions">
            <button type="button" className="btn btn-primary" onClick={publish} disabled={busy === "publish"}>
              {busy === "publish" ? <Loader2 className="spin" size={16} aria-hidden /> : <Send size={16} aria-hidden />} Publish
            </button>
            <button type="button" className="btn" onClick={download} disabled={busy === "download"}><Download size={16} aria-hidden /> Download</button>
            <button type="button" className="btn" onClick={share} disabled={!preview.blob}><Share2 size={16} aria-hidden /> Share</button>
          </div>
          {preview.error && <ErrorState>{preview.error.status === 429 ? "Slow down a little - preview will catch up." : "Preview unavailable."}</ErrorState>}
        </div>
        <div className="mz-mine-wrap"><MyMemes items={mine.items} /></div>
      </aside>
    </div>
  );
}

function AiPanel({ status, teams, teamId, setTeamId, matches, matchId, setMatchId, language, onPick }) {
  const { notify } = useFeedback();
  const [topic, setTopic] = useState("");
  const [style, setStyle] = useState("funny");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);

  async function suggest() {
    if (topic.trim().length < 3) return notify({ type: "error", text: "Describe the moment in at least 3 characters." });
    setBusy(true);
    try {
      const res = await memeService.generate({ topic: topic.trim(), language, style, team: teamId || null, match: matchId || null });
      setResult(res);
      if (res.options[0]) onPick(res.options[0]);
    } catch (err) {
      notify({ type: "error", text: err.status === 429 ? "You've hit the suggestion limit for now. Try later." : err.data?.detail ?? err.data?.topic?.[0] ?? err.message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="mz-panel mz-ai">
      <h2><Sparkles size={18} aria-hidden /> 3 · Need ideas? <small>optional</small></h2>
      <p className="meta">
        {status?.ai ? `AI suggestions by ${status.model || status.provider}. They're only ideas: edit them before publishing.`
          : "AI isn't configured, so suggestions come from our offline caption templates."}
      </p>
      <div className="field-row">
        <label>Team
          <Select value={teamId} onChange={(e) => { setTeamId(e.target.value); setMatchId(""); }}>
            <option value="">Any team</option>
            {teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </Select>
        </label>
        <label>Match (optional)
          <Select value={matchId} onChange={(e) => setMatchId(e.target.value)} disabled={!teamId}>
            <option value="">No specific match</option>
            {matches.map((m) => <option key={m.id} value={m.id}>{m.home_team_detail.short_name} vs {m.away_team_detail.short_name} · {m.starts_at.slice(0, 10)}</option>)}
          </Select>
        </label>
      </div>
      <label>What's the moment?
        <input value={topic} maxLength={200} onChange={(e) => setTopic(e.target.value)} placeholder="e.g. rain before the final over" />
      </label>
      <div className="mz-langs" role="radiogroup" aria-label="Humour style">
        {Object.entries(STYLES).map(([v, l]) => (
          <button key={v} type="button" role="radio" aria-checked={style === v} className={style === v ? "is-on" : ""} onClick={() => setStyle(v)}>{l}</button>
        ))}
      </div>
      <button type="button" className="btn" onClick={suggest} disabled={busy}>
        {busy ? <Loader2 className="spin" size={16} aria-hidden /> : result ? <RefreshCw size={16} aria-hidden /> : <Wand2 size={16} aria-hidden />}
        {result ? "New ideas" : "Suggest 3 captions"}
      </button>
      {result && (
        <>
          {result.notice && <p className="mock-note">{result.notice}</p>}
          {!result.verified_facts && <p className="meta">No verified match data used, so these stay generic: no scores or results.</p>}
          <ul className="mz-options">
            {result.options.map((o, i) => (
              <li key={i}><button type="button" onClick={() => onPick(o)}>
                {o.top && <span>{o.top}</span>}<strong>{o.bottom}</strong>
              </button></li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

function MyMemes({ items }) {
  if (!items) return null;
  const shown = items.filter((d) => d.status !== "draft").slice(0, 8); // working drafts stay out of the way
  if (!shown.length) return null;
  return (
    <section className="mz-mine" aria-label="My memes">
      <h3>My memes</h3>
      <ul>
        {shown.map((d) => (
          <li key={d.id}>
            <span className={`chip status-chip s-${d.status}`}>{STATUS_LABEL[d.status] ?? d.status}</span>
            <span className="clip">{d.caption}</span>
            <time dateTime={d.created_at}>{timeAgo(d.created_at)}</time>
            {d.status === "published" && d.published_post && <Link to={`/meme-zone/m/${d.published_post}`} className="text-link">View</Link>}
          </li>
        ))}
      </ul>
    </section>
  );
}
