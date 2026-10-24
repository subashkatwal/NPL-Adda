import { toBlob } from "html-to-image";
import {
  Camera, Check, Copy, Download, ImagePlus, Link2, Loader2, MessageCircle, Save, Share2, Trash2, Trophy,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Navigate } from "react-router-dom";

import FanCardFace from "../components/FanCardFace.jsx";
import { BADGE_ICONS } from "../lib/badgeIcons.js";
import { BackLink, ErrorState, Loading, Select, TeamCrest } from "../components/ui.jsx";
import { PERSONALITY_LABELS } from "../i18n/strings.js";
import { results } from "../lib/api.js";
import { CARD_THEMES, useFan } from "../lib/fanContext.js";
import { useFeedback } from "../lib/feedbackContext.js";
import { usePrefs } from "../lib/prefs.js";
import { downloadBlob, shareCard } from "../lib/share.js";
import { useApi } from "../lib/useApi.js";
import { fanService } from "../services/fan.js";

const PRIVACY = [
  ["avatar", "Show my photo"],
  ["stats", "Show my stats"],
  ["badges", "Show my badges"],
  ["since", "Show 'fan since' year"],
];
const SHARE_MESSAGES = {
  "shared-file": "Card shared.",
  "shared-link": "Link shared.",
  cancelled: "Sharing cancelled.",
  "copied-and-downloaded": "Copied your card link and downloaded the image.",
  downloaded: "Downloaded your card image.",
};

function draftFrom(card, profile) {
  return {
    nickname: card.nickname, tagline: card.tagline ?? "", personality: profile.fan_personality, theme: card.theme,
    teamId: card.team?.id ?? "", privacy: { ...card.privacy }, isPublic: card.is_public,
  };
}

/** Render a DOM node to PNG. pixelRatio 3 turns the 360px story stage into a 1080x1920 image. */
const renderPng = (node, pixelRatio = 3) => toBlob(node, { pixelRatio, cacheBust: true, backgroundColor: "#0b1020" });

export default function FanCard() {
  const { lang } = usePrefs();
  const { profile, status, setProfile } = useFan();
  const { notify } = useFeedback();
  const [card, setCard] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [draft, setDraft] = useState(null);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [exporting, setExporting] = useState(null);
  const teams = useApi(profile ? "/teams" : null);
  const allBadges = useApi(profile ? "/fanpage/badges" : null);
  const fileRef = useRef(null);
  const cardRef = useRef(null);
  const storyRef = useRef(null);
  const photoStep = useRef(null);

  useEffect(() => {
    if (!profile) return;
    fanService.myCard().then((c) => {
      setCard(c);
      setDraft((d) => d ?? draftFrom(c, profile));
    }).catch(setLoadError);
  }, [profile]);

  const teamList = results(teams.data);
  const draftTeam = useMemo(() => teamList.find((t) => t.id === draft?.teamId) ?? card?.team ?? null,
    [teamList, draft?.teamId, card?.team]);

  if (status === "loading") return <section className="page"><Loading /></section>;
  if (!profile) return <Navigate to="/choose-team" replace />;
  if (loadError) return <section className="page"><ErrorState error={loadError} /></section>;
  if (!card || !draft) return <section className="page"><Loading label="Loading your fan card" /></section>;

  const saved = draftFrom(card, profile);
  const dirty = JSON.stringify(saved) !== JSON.stringify(draft);
  const hasPhoto = Boolean(card.avatar_url);
  const set = (patch) => setDraft((d) => ({ ...d, ...patch }));
  const preview = {
    theme: draft.theme, nickname: draft.nickname, tagline: draft.tagline, team: draftTeam, privacy: draft.privacy,
    personality: draft.personality,
  };
  const publicUrl = `${window.location.origin}/fans/${card.profile_id}`;
  const fileName = `npl-adda-${(card.nickname || "fan").replace(/\W+/g, "-").toLowerCase()}`;
  const steps = [
    ["Team", Boolean(draftTeam)],
    ["Your details", draft.nickname.trim().length >= 2],
    ["Photo", hasPhoto],
    ["Theme", true],
    ["Preview & save", !dirty],
  ];

  async function onPhoto(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (!/^image\/(jpeg|png|webp)$/.test(file.type)) return notify({ type: "error", text: "Use a JPEG, PNG or WebP photo." });
    if (file.size > 5 * 1024 * 1024) return notify({ type: "error", text: "Photos must be 5 MB or smaller." });
    setUploading(true);
    try {
      const updated = await fanService.uploadAvatar(file);
      setProfile(updated);
      setCard((c) => ({ ...c, avatar_url: updated.avatar_url }));
      notify({ text: "Photo added to your card." });
    } catch (err) {
      notify({ type: "error", text: err.data?.image ?? err.message });
    } finally {
      setUploading(false);
    }
  }

  async function removePhoto() {
    setUploading(true);
    try {
      const updated = await fanService.removeAvatar();
      setProfile(updated);
      setCard((c) => ({ ...c, avatar_url: "" }));
    } catch (err) {
      notify({ type: "error", text: err.message });
    } finally {
      setUploading(false);
    }
  }

  async function save(event) {
    event?.preventDefault();
    setSaving(true);
    try {
      const updated = await fanService.updateProfile(card.profile_id, {
        nickname: draft.nickname.trim(), tagline: draft.tagline.trim(), fan_personality: draft.personality,
        card_theme: draft.theme, is_public: draft.isPublic,
        card_show_avatar: draft.privacy.avatar, card_show_stats: draft.privacy.stats,
        card_show_badges: draft.privacy.badges, card_show_since: draft.privacy.since,
      });
      if (draft.teamId && draft.teamId !== card.team?.id) await fanService.switchTeam(draft.teamId);
      const fresh = await fanService.myCard();
      setProfile({ ...updated, current_team: fresh.team });
      setCard(fresh);
      setDraft(draftFrom(fresh, { ...profile, fan_personality: updated.fan_personality }));
      notify({ text: "Fan card saved." });
    } catch (err) {
      const fields = err.data && typeof err.data === "object" ? Object.values(err.data).flat().join(" ") : "";
      notify({ type: "error", text: fields || err.message });
    } finally {
      setSaving(false);
    }
  }

  async function exportImage(kind) {
    setExporting(kind);
    try {
      const blob = kind === "card" ? await renderPng(cardRef.current, 3) : await renderPng(storyRef.current, 3);
      if (kind === "share") {
        const outcome = await shareCard({
          blob, fileName: `${fileName}-story.png`, title: "My NPL Adda fan card",
          text: `Backing ${card.team?.name ?? "Nepali cricket"} on NPL Adda.`, url: publicUrl,
        });
        notify({ text: SHARE_MESSAGES[outcome] });
      } else {
        downloadBlob(blob, `${fileName}-${kind}.png`);
      }
    } catch {
      notify({ type: "error", text: "Couldn't create the image. Try again." });
    } finally {
      setExporting(null);
    }
  }

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(publicUrl);
      notify({ text: "Card link copied." });
    } catch {
      notify({ type: "error", text: publicUrl });
    }
  }

  const earnedCodes = new Set((card.badges ?? []).map((b) => b.code));

  return (
    <section className="page fc-page">
      <BackLink fallback="/profile" />
      <header className="fc-hero">
        <div>
          <p className="eyebrow">Your fan identity</p>
          <h1>Fan <span>card</span></h1>
          <p className="lede">Not just a fan. A part of the journey.</p>
        </div>
        <ul className="fc-perks">
          <li><b>Personalize</b> your identity</li>
          <li><b>Earn badges</b> &amp; level up</li>
          <li><b>Share</b> your card</li>
          <li><b>Represent</b> your team</li>
        </ul>
      </header>

      {!hasPhoto && (
        <div className="fc-ask" role="note">
          <Camera size={22} aria-hidden />
          <div>
            <strong>Add your photo to finish your card</strong>
            <span>Fan cards look best with your face in the ring. Only you choose what's shown.</span>
          </div>
          <button type="button" className="btn btn-primary btn-sm" onClick={() => fileRef.current?.click()} disabled={uploading}>
            {uploading ? <Loader2 className="spin" size={16} aria-hidden /> : <ImagePlus size={16} aria-hidden />} Upload photo
          </button>
        </div>
      )}

      <div className="fc-studio">
        <form className="fc-form" onSubmit={save}>
          <h2>Create your fan card</h2>
          <ol className="fc-steps" aria-label="Progress">
            {steps.map(([label, done], i) => (
              <li key={label} className={done ? "is-done" : ""}><span>{done ? <Check size={13} aria-hidden /> : i + 1}</span>{label}</li>
            ))}
          </ol>

          <fieldset className="fc-step">
            <legend><span>1</span> Select your team</legend>
            <div className="fc-team-grid" role="radiogroup" aria-label="Team">
              {teamList.map((t) => (
                <button key={t.id} type="button" role="radio" aria-checked={draft.teamId === t.id}
                  className={draft.teamId === t.id ? "is-on" : ""} style={{ "--team": t.primary_color }}
                  onClick={() => set({ teamId: t.id })}>
                  <TeamCrest team={t} size={34} /><span>{t.name}</span>
                </button>
              ))}
            </div>
            {draft.teamId && card.team && draft.teamId !== card.team.id && (
              <p className="meta">Switching team is saved to your fan history. Your points stay with you.</p>
            )}
          </fieldset>

          <fieldset className="fc-step">
            <legend><span>2</span> Your details</legend>
            <div className="field-row">
              <label>Name / nickname
                <input value={draft.nickname} minLength={2} maxLength={40} required onChange={(e) => set({ nickname: e.target.value })} />
              </label>
              <label>Tagline <small className="muted">optional</small>
                <input value={draft.tagline} maxLength={80} placeholder="Cricket is life" onChange={(e) => set({ tagline: e.target.value })} />
              </label>
            </div>
            <label>Fan personality
              <Select value={draft.personality} onChange={(e) => set({ personality: e.target.value })}>
                {Object.entries(PERSONALITY_LABELS[lang]).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </Select>
            </label>
          </fieldset>

          <fieldset className="fc-step" ref={photoStep}>
            <legend><span>3</span> Your photo</legend>
            <div className="fc-photo">
              <span className="fc-photo-ring">
                {hasPhoto ? <img src={card.avatar_url} alt="Your fan card photo" /> : <Camera size={26} aria-hidden />}
              </span>
              <div className="fc-photo-actions">
                <button type="button" className="btn btn-sm" onClick={() => fileRef.current?.click()} disabled={uploading}>
                  {uploading ? <Loader2 className="spin" size={16} aria-hidden /> : <ImagePlus size={16} aria-hidden />}
                  {hasPhoto ? "Change photo" : "Upload photo"}
                </button>
                {hasPhoto && (
                  <button type="button" className="btn btn-sm btn-ghost" onClick={removePhoto} disabled={uploading}>
                    <Trash2 size={16} aria-hidden /> Remove
                  </button>
                )}
                <small className="muted">JPEG, PNG or WebP up to 5 MB. We crop it square and remove location and camera data.</small>
              </div>
              <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={onPhoto} />
            </div>
          </fieldset>

          <fieldset className="fc-step">
            <legend><span>4</span> Card theme</legend>
            <div className="fc-themes" role="radiogroup" aria-label="Card theme">
              {Object.entries(CARD_THEMES).map(([value, label]) => (
                <button key={value} type="button" role="radio" aria-checked={draft.theme === value}
                  className={`fc-theme-swatch fc-swatch-${value} ${draft.theme === value ? "is-on" : ""}`}
                  onClick={() => set({ theme: value })}>
                  <i aria-hidden />{label}{draft.theme === value && <Check className="fc-swatch-tick" size={14} aria-hidden />}
                </button>
              ))}
            </div>
          </fieldset>

          <fieldset className="fc-step">
            <legend><span>5</span> Privacy</legend>
            <p className="meta">Your name, team and level always show. Email and account details never appear on a card.</p>
            <div className="fc-switches">
              {PRIVACY.map(([key, label]) => (
                <label key={key} className="fc-switch">
                  <span>{label}</span>
                  <input type="checkbox" role="switch" checked={draft.privacy[key]}
                    onChange={(e) => set({ privacy: { ...draft.privacy, [key]: e.target.checked } })} />
                </label>
              ))}
              <label className="fc-switch">
                <span>Public card link <small className="muted">others can open your card</small></span>
                <input type="checkbox" role="switch" checked={draft.isPublic} onChange={(e) => set({ isPublic: e.target.checked })} />
              </label>
            </div>
          </fieldset>

          <div className={`fc-savebar ${dirty ? "is-dirty" : ""}`}>
            <button type="submit" className="btn btn-primary" disabled={saving || !dirty || draft.nickname.trim().length < 2}>
              {saving ? <Loader2 className="spin" size={16} aria-hidden /> : <Save size={16} aria-hidden />} {dirty ? "Save my card" : "Saved"}
            </button>
            {dirty && <button type="button" className="btn btn-ghost" onClick={() => setDraft(saved)}>Discard</button>}
          </div>
        </form>

        <aside className="fc-preview" aria-label="Live preview">
          <p className="eyebrow">Live preview {dirty && <span className="fc-unsaved">· unsaved</span>}</p>
          <div className="fc-stage">
            <FanCardFace ref={cardRef} card={card} draft={preview} interactive />
          </div>
          <div className="fc-share">
            <button type="button" className="btn btn-primary" onClick={() => exportImage("share")} disabled={Boolean(exporting) || dirty}>
              {exporting === "share" ? <Loader2 className="spin" size={16} aria-hidden /> : <Share2 size={16} aria-hidden />} Share
            </button>
            <button type="button" className="btn" onClick={() => exportImage("story")} disabled={Boolean(exporting) || dirty}>
              <Download size={16} aria-hidden /> Story 9:16
            </button>
            <button type="button" className="btn" onClick={() => exportImage("card")} disabled={Boolean(exporting) || dirty}>
              <Download size={16} aria-hidden /> Card
            </button>
            <a className="btn" href={`https://wa.me/?text=${encodeURIComponent(`My NPL Adda fan card: ${publicUrl}`)}`}
              target="_blank" rel="noreferrer"><MessageCircle size={16} aria-hidden /> WhatsApp</a>
            <button type="button" className="btn" onClick={copyLink} disabled={!card.is_public}>
              <Copy size={16} aria-hidden /> Copy link
            </button>
          </div>
          {dirty && <p className="meta">Save first, so the image you share matches your card.</p>}
          {!card.is_public && <p className="meta"><Link2 size={14} aria-hidden /> Your card link is private. Turn on “Public card link” to share it.</p>}
        </aside>
      </div>

      <div className="fc-panels">
        <section className="fc-panel">
          <h2>Badges</h2>
          <p className="meta">Awarded automatically by the server when you do these.</p>
          <ul className="fc-badge-list">
            {results(allBadges.data).map((b) => {
              const Icon = BADGE_ICONS[b.icon_name] ?? Trophy;
              const earned = earnedCodes.has(b.code);
              return (
                <li key={b.id} className={earned ? "is-earned" : ""}>
                  <span><Icon size={18} aria-hidden /></span>
                  <strong>{b.name}</strong>
                  <small>{earned ? "Earned" : b.description}</small>
                </li>
              );
            })}
          </ul>
        </section>

        <section className="fc-panel">
          <h2>Your stats</h2>
          <p className="meta">Real activity, counted on the server.</p>
          <dl className="fc-statlist">
            <div className="is-total"><dt>Total points</dt><dd>{card.stats.points}</dd></div>
            <div><dt>Memes published</dt><dd>{card.stats.memes}</dd></div>
            <div><dt>Comments</dt><dd>{card.stats.comments}</dd></div>
            <div><dt>Predictions</dt><dd>{card.stats.predictions} <small>({card.stats.predictions_correct} correct)</small></dd></div>
            <div><dt>Poll votes</dt><dd>{card.stats.votes}</dd></div>
            <div><dt>Badges</dt><dd>{(card.badges ?? []).length}/{card.badges_total}</dd></div>
          </dl>
        </section>
      </div>

      <p className="fc-disclaimer">An independent digital fan identity. Not official team or league membership.</p>

      {/* Off-screen 9:16 stage for Instagram/TikTok/WhatsApp stories (exported at 1080x1920). */}
      <div className="fc-story-host" aria-hidden>
        <div ref={storyRef} className={`fc-story fc-story-${card.theme}`}>
          <p className="fc-story-head">NPL <b>ADDA</b></p>
          <FanCardFace card={card} draft={{ privacy: card.privacy }} />
          <p className="fc-story-foot">Be loud. Be proud. <b>Be NPL Adda.</b></p>
        </div>
      </div>
    </section>
  );
}
