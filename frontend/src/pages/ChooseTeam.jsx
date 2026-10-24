import { Check, CreditCard, Home, Loader2 } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { BackLink, ErrorState, Loading, Select, TeamCrest } from "../components/ui.jsx";
import { PERSONALITY_LABELS } from "../i18n/strings.js";
import { api, results } from "../lib/api.js";
import { useAuth } from "../lib/authContext.js";
import { useFan } from "../lib/fanContext.js";
import { usePrefs, useT } from "../lib/prefs.js";
import { useApi } from "../lib/useApi.js";

export default function ChooseTeam() {
  const t = useT();
  const { lang } = usePrefs();
  const [params] = useSearchParams();
  const { profile, refresh } = useFan();
  const { user, openAuth } = useAuth();
  const teams = useApi("/teams");
  const [selected, setSelected] = useState(params.get("team"));
  const [nickname, setNickname] = useState("");
  const [personality, setPersonality] = useState("casual");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [joined, setJoined] = useState(null);

  const teamList = results(teams.data);
  const chosen = teamList.find((x) => x.id === selected);
  const needsProfile = !profile;

  async function join(event) {
    event.preventDefault();
    if (!chosen) return;
    if (!user) {
      // Browsing teams is open; joining needs an account. The selection is kept for after login.
      openAuth({ reason: t("auth.joinReason", { team: chosen.name }) });
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      if (needsProfile) {
        await api("/fanpage", {
          method: "POST",
          body: { nickname: (nickname.trim() || user.display_name || "").trim(), fan_personality: personality, team: chosen.id },
        });
      } else {
        await api("/fanpage/me/membership", { method: "POST", body: { team: chosen.id } });
      }
      const me = await refresh();
      if (me?.current_team?.id !== chosen.id) throw new Error(t("choose.unconfirmed"));
      setJoined(me.current_team);
    } catch (err) {
      setError(err);
    } finally {
      setSubmitting(false);
    }
  }

  if (joined) {
    return (
      <section className="page confirm" aria-live="polite" style={{ "--team": joined.primary_color }}>
        <TeamCrest team={joined} size={112} />
        <p className="eyebrow">{t("choose.confirmed")}</p>
        <h1>{t("choose.welcome", { team: joined.name })}</h1>
        <p className="lede">{t("choose.saved")}</p>
        <div className="actions">
          <Link className="btn btn-primary" to="/card"><CreditCard size={18} aria-hidden /> {t("choose.seeCard")}</Link>
          <Link className="btn" to="/home"><Home size={18} aria-hidden /> {t("choose.goHome")}</Link>
        </div>
      </section>
    );
  }

  return (
    <section className="page">
      <BackLink fallback={profile?.current_team ? "/home" : "/"} />
      <p className="eyebrow">{profile?.current_team ? t("choose.switch") : t("choose.step1")}</p>
      <h1>{t("choose.title")}</h1>
      {profile?.current_team && <p className="lede">{t("choose.current", { team: profile.current_team.name })}</p>}

      {teams.loading && <Loading />}
      {teams.error && <ErrorState>{t("state.unavailable")}</ErrorState>}

      <form onSubmit={join}>
        <fieldset className="team-grid">
          <legend className="sr-only">Teams</legend>
          {teamList.map((team, i) => (
            <label key={team.id} className={`team-option ${selected === team.id ? "is-selected" : ""}`}
              style={{ "--team": team.primary_color, "--team-2": team.secondary_color }}>
              <input type="radio" name="team" value={team.id} checked={selected === team.id}
                onChange={() => setSelected(team.id)} />
              <span className="team-index">{String(i + 1).padStart(2, "0")}</span>
              <TeamCrest team={team} size={64} />
              <span className="team-name">{team.name}</span>
              <span className="team-city">{team.city}</span>
              {selected === team.id && <Check className="tick" size={18} aria-hidden />}
            </label>
          ))}
        </fieldset>

        {chosen && user && needsProfile && (
          <div className="profile-fields">
            <p className="eyebrow">{t("choose.step2")}</p>
            <label>
              {t("choose.nickname")}
              <input value={nickname} onChange={(e) => setNickname(e.target.value)} required minLength={2}
                maxLength={40} placeholder="Rhino Roar" />
            </label>
            <label>
              {t("choose.personality")}
              <Select value={personality} onChange={(e) => setPersonality(e.target.value)}>
                {Object.entries(PERSONALITY_LABELS[lang]).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </Select>
            </label>
          </div>
        )}

        {error && <ErrorState error={error} />}

        <div className="choose-submit">
          <button className="btn btn-primary btn-lg" type="submit"
            disabled={!chosen || submitting || (user && needsProfile && nickname.trim().length < 2) ||
              chosen?.id === profile?.current_team?.id}>
            {submitting ? <Loader2 className="spin" size={18} aria-hidden /> : <Check size={18} aria-hidden />}
            {!chosen ? t("choose.pick") : user ? t("choose.join", { team: chosen.short_name })
              : t("auth.loginToJoin", { team: chosen.short_name })}
          </button>
        </div>
      </form>
    </section>
  );
}
